#!/usr/bin/env python3
from __future__ import annotations
import hmac,json,os,secrets,sys,urllib.error,urllib.request
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from typing import Any,Mapping

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from tools import provider_secret_provision as providers
from tools.provider_secret_kv_write import metadata_path

ADDRESS=os.getenv('JASON_OPENBAO_URL','http://127.0.0.1:8200').rstrip('/')
ROLE_FILE=Path(os.getenv('JASON_CREDENTIAL_CONTROL_ROLE_ID_FILE','/run/jason-secrets/credential-control/role-id'))
SECRET_FILE=Path(os.getenv('JASON_CREDENTIAL_CONTROL_SECRET_ID_FILE','/run/jason-secrets/credential-control/secret-id'))
TOKEN_FILE=Path(os.getenv('JASON_CREDENTIAL_CONTROL_HTTP_TOKEN_FILE','/run/jason-secrets/credential-control/http-token'))
AUDIT_FILE=Path(os.getenv('JASON_CREDENTIAL_CONTROL_AUDIT_FILE','/var/lib/jason/credential-control/audit.jsonl'))
PORT=int(os.getenv('JASON_CREDENTIAL_CONTROL_PORT','8788'))
MAX_BODY=65536

class SafeError(RuntimeError): pass

def _read(path:Path,label:str)->str:
    try: v=path.read_text().strip()
    except OSError as e: raise SafeError(f'{label} unavailable') from e
    if not v: raise SafeError(f'{label} unavailable')
    return v

def _request(path:str,method='GET',token:str|None=None,payload:Mapping[str,Any]|None=None)->dict:
    data=None if payload is None else json.dumps(payload).encode(); headers={'Accept':'application/json'}
    if payload is not None: headers['Content-Type']='application/json'
    if token: headers['X-Vault-Token']=token
    req=urllib.request.Request(f'{ADDRESS}/v1/{path.lstrip("/")}',data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=10) as r: raw=r.read().decode()
    except urllib.error.HTTPError as e: raise SafeError(f'OpenBao HTTP {e.code}') from e
    except (urllib.error.URLError,OSError,TimeoutError) as e: raise SafeError('OpenBao unavailable') from e
    if not raw: return {}
    try: out=json.loads(raw)
    except json.JSONDecodeError as e: raise SafeError('OpenBao response invalid') from e
    return out if isinstance(out,dict) else {}

def _login()->str:
    r=_request('auth/approle/login','POST',payload={'role_id':_read(ROLE_FILE,'RoleID'),'secret_id':_read(SECRET_FILE,'SecretID')})
    t=((r.get('auth') or {}).get('client_token') or '')
    if not t: raise SafeError('OpenBao credential-control authentication failed')
    return str(t)

def _revoke(t:str):
    try:_request('auth/token/revoke-self','POST',t,{})
    except SafeError: pass

def _version(token:str,secret_path:str)->int:
    try:r=_request(metadata_path(secret_path),'GET',token)
    except SafeError as e:
        if 'HTTP 404' in str(e): return 0
        raise
    v=((r.get('data') or {}).get('current_version') or 0)
    return v if isinstance(v,int) and v>=0 else 0

def inventory()->list[dict]:
    t=_login(); rows=[]
    try:
      for name,spec in sorted(providers.PROVIDERS.items()):
        v=_version(t,str(spec['secret_path']))
        rows.append({'provider':name,'logical_name':spec['logical_name'],'fields':list(spec['fields']),'required_fields':list(spec.get('required_fields',spec['fields'])),'kv_version':v,'secret_present':v>0})
      return rows
    finally:_revoke(t)

def update(provider:str,values:Mapping[str,Any],actor:str)->dict:
    if provider not in providers.PROVIDERS: raise SafeError('Provider is not approved')
    spec=providers.PROVIDERS[provider]; allowed=tuple(spec['fields']); required=tuple(spec.get('required_fields',allowed))
    if not isinstance(values,Mapping): raise SafeError('Credential fields are invalid')
    unexpected=sorted(set(values)-set(allowed)); missing=[x for x in required if not str(values.get(x) or '').strip()]
    if unexpected: raise SafeError('Unexpected credential fields: '+', '.join(unexpected))
    if missing: raise SafeError('Missing required credential fields: '+', '.join(missing))
    clean={k:str(values[k]) for k in allowed if str(values.get(k) or '').strip()}
    t=_login()
    try:
      old=_version(t,str(spec['secret_path']))
      _request(str(spec['secret_path']),'POST',t,{'options':{'cas':old},'data':clean})
      new=old+1
    finally:
      for k in list(clean): clean[k]=''
      clean.clear(); _revoke(t)
    event={'timestamp':datetime.now(timezone.utc).isoformat(),'actor':actor[:128],'provider':provider,'action':'credential_update','old_version':old,'new_version':new,'status':'succeeded','secret_values_recorded':False,'correlation_id':'cred-'+secrets.token_hex(12)}
    AUDIT_FILE.parent.mkdir(parents=True,exist_ok=True); fd=os.open(AUDIT_FILE,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
    with os.fdopen(fd,'a') as f:f.write(json.dumps(event,sort_keys=True)+'\n')
    return event

class Handler(BaseHTTPRequestHandler):
    server_version='JasonCredentialControl/1'
    def log_message(self,fmt,*args): sys.stderr.write('%s - %s\n'%(self.address_string(),fmt%args))
    def _auth(self)->bool:
      expected=_read(TOKEN_FILE,'HTTP token'); auth=self.headers.get('Authorization','')
      return auth.lower().startswith('bearer ') and hmac.compare_digest(auth.split(' ',1)[1].strip(),expected)
    def _json(self,status:int,body:dict):
      raw=json.dumps(body).encode(); self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
      if not self._auth(): return self._json(403,{'error':'forbidden'})
      try:
       if self.path=='/credential-control/inventory': return self._json(200,{'status':'ok','credentials':inventory(),'secret_values_exposed':False})
       if self.path=='/healthz': return self._json(200,{'status':'ok','service':'jason-credential-control'})
       return self._json(404,{'error':'not_found'})
      except SafeError as e:return self._json(503,{'error':str(e)})
    def do_POST(self):
      if not self._auth(): return self._json(403,{'error':'forbidden'})
      if self.path!='/credential-control/update': return self._json(404,{'error':'not_found'})
      try:
       n=int(self.headers.get('Content-Length','0')); assert 0<n<=MAX_BODY
       body=json.loads(self.rfile.read(n)); provider=str(body.get('provider') or ''); values=body.get('values'); actor=str(self.headers.get('X-Grafana-User') or 'grafana-admin')
       return self._json(200,update(provider,values,actor))
      except (ValueError,AssertionError,json.JSONDecodeError): return self._json(400,{'error':'invalid_request'})
      except SafeError as e:return self._json(400,{'error':str(e)})

def main(): ThreadingHTTPServer(('0.0.0.0',PORT),Handler).serve_forever()
if __name__=='__main__':main()
