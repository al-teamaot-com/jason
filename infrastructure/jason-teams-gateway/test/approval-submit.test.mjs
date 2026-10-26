import test from 'node:test';
import assert from 'node:assert/strict';
import { parseApprovalSubmit } from '../approval-submit.mjs';

test('universal decision routes without any caller-asserted authority', () => {
  assert.deepEqual(parseApprovalSubmit({approval_id:'planapproval-reviewed',decision:'approve'}),
    {approvalId:'planapproval-reviewed',decision:'approve',selections:{}});
});

test('old organization-asserting card payload is rejected, not silently trusted', () => {
  assert.equal(parseApprovalSubmit({approval_id:'planapproval-reviewed',decision:'approve',organization_id:'forged'}),null);
});

test('all authority and token-bearing card fields remain forbidden', () => {
  for (const key of ['principal_id','organization_id','client_id','capability','provider','token','access_token','authorization','requested_by']) {
    assert.equal(parseApprovalSubmit({approval_id:'planapproval-reviewed',decision:'approve',[key]:'untrusted'}),null);
  }
});

test('all supported decisions and existing non-authoritative selections remain compatible', () => {
  for (const decision of ['approve','deny','request_changes']) {
    assert.equal(parseApprovalSubmit({approval_id:'procapproval-existing',decision}).decision,decision);
  }
  assert.equal(parseApprovalSubmit({approval_id:'procapproval-existing',decision:'approve',price_choice:'standard'}).selections.price_choice,'standard');
});


test('card data cannot impersonate SDK source activity replyToId', () => {
  assert.equal(parseApprovalSubmit({
    approval_id: 'planapproval-1', decision: 'approve',
    card_challenge: 'a'.repeat(48),
    callback_reply_to_id: 'forged-original-card',
  }), null);
});
