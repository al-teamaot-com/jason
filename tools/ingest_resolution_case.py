#!/usr/bin/env python3
"""Controlled operator ingestion for technician-confirmed Resolution Memory cases.

Consumes a reviewed JSON candidate. It does not infer missing facts from ticket text,
does not call providers, and cannot create execution authority.
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'implementation'))
from decision_memory.resolution_ingestion import ConfirmedResolutionIngestion
from decision_memory.resolution_memory import ResolutionOutcome, ResolutionSignature, ResolutionSourceReference, ResolutionStep, ResolutionStepKind
from decision_memory.resolution_service import ResolutionMemoryService
from decision_memory.resolution_sqlite import SQLiteResolutionMemoryStore

def dt(v): return datetime.fromisoformat(str(v).replace('Z','+00:00'))
def main():
 p=argparse.ArgumentParser(); p.add_argument('--database',required=True); p.add_argument('--input',required=True); a=p.parse_args(); d=json.load(open(a.input))
 refs=tuple(ResolutionSourceReference(**x) for x in d['source_references'])
 steps=tuple(ResolutionStep(step_id=x['step_id'],ordinal=int(x['ordinal']),kind=ResolutionStepKind(x['kind']),action_key=x['action_key'],action_summary=x['action_summary'],outcome=ResolutionOutcome(x['outcome']),evidence_summary=x.get('evidence_summary',''),read_only=bool(x.get('read_only',False)),approval_required=bool(x.get('approval_required',False)),disruptive=bool(x.get('disruptive',False))) for x in d.get('steps',[]))
 sig=ResolutionSignature(**d['signature'])
 c=ConfirmedResolutionIngestion(case_id=d['case_id'],organization_id=d['organization_id'],client_id=d['client_id'],ticket_id=d['ticket_id'],ticket_company_id=str(d['ticket_company_id']),current_company_id=str(d['current_company_id']),signature=sig,source_references=refs,steps=steps,root_cause=d['root_cause'],final_resolution=d['final_resolution'],outcome=ResolutionOutcome(d['outcome']),technician_confirmed=bool(d['technician_confirmed']),terminal_verification_confirmed=bool(d['terminal_verification_confirmed']),recorded_at=dt(d['recorded_at']),resolved_at=dt(d['resolved_at']),owner=d['owner'])
 s=ResolutionMemoryService(store=SQLiteResolutionMemoryStore(a.database)); s.initialize(); case=s.ingest_confirmed_resolution(c); print(json.dumps({'case_id':case.case_id,'status':case.status.value,'client_id':case.client_id,'grants_authority':False},sort_keys=True))
if __name__=='__main__': main()
