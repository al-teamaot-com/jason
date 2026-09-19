#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,secrets,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools import provider_secret_provision as base
def policy_text():
 lines=[]
 for spec in base.PROVIDERS.values():
  data=str(spec["secret_path"])
  meta=data.replace("/data/","/metadata/",1)
  lines += [f'path "{data}" {{ capabilities=["create","update"] }}',f'path "{meta}" {{ capabilities=["read"] }}']
 lines.append('path "auth/token/revoke-self" { capabilities=["update"] }')
 return "\n".join(lines)+"\n"
def private(path:Path,value:str):
 path.parent.mkdir(parents=True,exist_ok=True,mode=0o700); fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
 with os.fdopen(fd,'w') as f:f.write(value+'\n')
def main():
 p=argparse.ArgumentParser(); p.add_argument('--address',default=base.DEFAULT_ADDRESS); p.add_argument('--admin-username',default=base.DEFAULT_ADMIN_USERNAME); p.add_argument('--output-dir',default='/opt/jason/bootstrap/secrets/openbao/credential-control-approle'); a=p.parse_args()
 import getpass; pw=getpass.getpass(f'OpenBao password for {a.admin_username}: '); token=base.admin_login(a.address,a.admin_username,pw); pw=''
 try:
  base.api_request(a.address,'sys/policies/acl/jason-credential-control',method='POST',token=token,payload={'policy':policy_text()},allow_empty=True)
  base.api_request(a.address,'auth/approle/role/jason-credential-control',method='POST',token=token,payload={'bind_secret_id':True,'secret_id_ttl':'2160h','secret_id_num_uses':0,'token_policies':['jason-credential-control'],'token_no_default_policy':True,'token_ttl':'5m','token_max_ttl':'5m','token_explicit_max_ttl':'5m','token_num_uses':30,'token_type':'service'},allow_empty=True)
  role=base.require_string((base.api_request(a.address,'auth/approle/role/jason-credential-control/role-id',method='GET',token=token).get('data') or {}),'role_id','RoleID'); sec=base.require_string((base.api_request(a.address,'auth/approle/role/jason-credential-control/secret-id',method='POST',token=token,payload={'ttl':'2160h','num_uses':0}).get('data') or {}),'secret_id','SecretID')
  d=Path(a.output_dir); private(d/'role-id',role); private(d/'secret-id',sec); private(d/'http-token',secrets.token_urlsafe(48)); print(json.dumps({'status':'pass','policy':'jason-credential-control','role':'jason-credential-control','credential_dir':str(d),'secret_values_printed':False}))
 finally: base.revoke_admin_token(a.address,token)
if __name__=='__main__':main()
