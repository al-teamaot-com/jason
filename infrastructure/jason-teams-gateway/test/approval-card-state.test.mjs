import assert from 'node:assert/strict';
import { mkdtempSync, rmSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { createApprovalDecisionStore } from '../approval-decision-store.mjs';
import { recordIssuedApprovalCard, updateOriginalApprovalCard, terminalCard, canonicalDecision } from '../approval-card-state.mjs';

function fixture(t) {
  const dir=mkdtempSync(join(tmpdir(),'jason-card-state-'));
  t.after(()=>rmSync(dir,{recursive:true,force:true}));
  const path=join(dir,'decisions.json');
  const store=createApprovalDecisionStore({path});
  const scope={tenantId:'tenant-a',aadObjectId:'owner-a',conversationId:'conversation-a',messageId:'real-message-a'};
  const submit={approvalId:'procapproval-test',decision:'approve'};
  const card={type:'AdaptiveCard',version:'1.4',body:[],actions:['approve','deny'].map(decision=>({
    type:'Action.Submit',data:{approval_id:submit.approvalId,decision,card_challenge:'b'.repeat(48)}}))};
  const terminal={type:'AdaptiveCard',version:'1.4',body:[{type:'TextBlock',text:'Purchase approved'}],actions:[]};
  const result={httpStatus:200,payload:{status:'blocked',approval_decision:{approval_id:submit.approvalId,
    decision:'approve',status:'approved',card:terminal}}};
  return {store,path,scope,submit,card,result};
}

test('real issued card survives restart and updates only its authenticated message',async t=>{
  const f=fixture(t);
  assert.equal(recordIssuedApprovalCard({store:f.store,card:f.card,...f.scope}),true);
  const updates=[];
  const changed=await updateOriginalApprovalCard({context:{updateActivity:async activity=>updates.push(activity)},
    store:createApprovalDecisionStore({path:f.path}),...f.scope,replyToId:f.scope.messageId,
    approvalSubmit:f.submit,result:f.result});
  assert.equal(changed,true);
  assert.equal(updates[0].id,f.scope.messageId);
  assert.deepEqual(updates[0].attachments[0].content.actions,[]);
  // An execution blocker does not erase a genuinely recorded approval.
  assert.equal(canonicalDecision(f.result,f.submit).status,'approved');
});

test('untracked synthetic, forwarded, cross-tenant and wrong-actor cards cannot be edited',async t=>{
  const f=fixture(t);
  assert.equal(recordIssuedApprovalCard({store:f.store,card:f.card,...f.scope,messageId:'accepted:unknown'}),false);
  recordIssuedApprovalCard({store:f.store,card:f.card,...f.scope});
  for (const change of [{tenantId:'other'},{aadObjectId:'other'}, {conversationId:'other'}, {replyToId:'other-message'}]) {
    assert.equal(await updateOriginalApprovalCard({context:{updateActivity:async()=>assert.fail('must not edit')},
      store:f.store,...f.scope,replyToId:f.scope.messageId,approvalSubmit:f.submit,result:f.result,...change}),false);
  }
});

test('completed workflow status alone or mismatched vote cannot retire a card',async t=>{
  const f=fixture(t);
  assert.equal(canonicalDecision({httpStatus:200,payload:{status:'completed'}},f.submit),null);
  assert.equal(canonicalDecision(f.result,{...f.submit,decision:'deny'}),null);
  assert.equal(canonicalDecision({...f.result,httpStatus:500},f.submit),null);
});

test('terminal cards reject hidden and nested vote actions',()=>{
  assert.throws(()=>terminalCard({type:'AdaptiveCard',body:[{items:[{type:'Action.Submit'}]}],actions:[]}),/vote/);
  assert.throws(()=>terminalCard({type:'AdaptiveCard',body:[],actions:[{type:'Action.Submit'}]}),/invalid/);
});

test('provider update failure leaves canonical decision and original reference intact',async t=>{
  const f=fixture(t);
  recordIssuedApprovalCard({store:f.store,card:f.card,...f.scope});
  await assert.rejects(updateOriginalApprovalCard({context:{updateActivity:async()=>{throw new Error('provider unavailable');}},
    store:f.store,...f.scope,replyToId:f.scope.messageId,approvalSubmit:f.submit,result:f.result}),/provider unavailable/);
  assert.equal(f.store.issuedCards({tenantId:f.scope.tenantId,aadObjectId:f.scope.aadObjectId,
    approvalId:f.submit.approvalId}).length,1);
  assert.equal(canonicalDecision(f.result,f.submit).status,'approved');
});

test('gateway image includes every local module imported by its entry point',()=>{
  const source=readFileSync(new URL('../index.mjs',import.meta.url),'utf8');
  const docker=readFileSync(new URL('../Dockerfile',import.meta.url),'utf8');
  for (const [,file] of source.matchAll(/from "\.\/([^\"]+)"/g)) {
    assert.ok(docker.includes(`./${file}`),`unpackaged module: ${file}`);
  }
});

test('authenticated fallback updates all stored original cards through the existing bot',async t=>{
  const {updateIssuedApprovalCards}=await import('../approval-card-state.mjs');
  const f=fixture(t);
  recordIssuedApprovalCard({store:f.store,card:f.card,...f.scope});
  const updated=[];
  const adapter={continueConversation:async(identity,reference,fn)=>{
    assert.equal(reference.conversation.id,f.scope.conversationId);
    await fn({updateActivity:async activity=>updated.push(activity)});
  }};
  const result=await updateIssuedApprovalCards({adapter,store:f.store,...f.scope,
    proactiveRecord:{tenantId:f.scope.tenantId,identity:{verified:'fixture'},reference:{conversation:{id:'recent'}}},
    approvalId:f.submit.approvalId,status:'approved',card:f.result.payload.approval_decision.card});
  assert.deepEqual(result,[f.scope.messageId]);
  assert.equal(updated[0].attachments[0].content.actions.length,0);
  await assert.rejects(updateIssuedApprovalCards({adapter,store:f.store,...f.scope,
    proactiveRecord:{tenantId:'wrong'},approvalId:f.submit.approvalId,status:'approved',
    card:f.result.payload.approval_decision.card}),/scope invalid/);
});
