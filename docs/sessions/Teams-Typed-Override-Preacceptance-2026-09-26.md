# Teams Typed Override Pre-Acceptance — 2026-09-26

**Status:** Source/runtime pre-acceptance complete; one live authenticated owner reply remains  
**TODO:** TODO-COMM-004

## Purpose

Verify that typed technician text sent while an approval is pending is treated as a new authenticated conversation instruction rather than approval authority for the existing request.

No live provider mutation was performed during this review.

## Contract behavior

The direct Teams/OpenClaw ingress separates two input forms:

1. structured approval interaction:
   - interaction kind must be `approval.submit`;
   - exact `approval_id`, decision, and authenticated Teams response message ID are required;
   - only this structured path invokes the governed approval interaction flow.

2. ordinary typed message:
   - no approval interaction object is present;
   - the text is passed to the normal authenticated conversation flow;
   - the dedicated approval flow is not invoked;
   - text that merely contains words such as “approve” or an approval ID has no approval authority.

Transport attempts to smuggle extra authority fields into the approval interaction fail closed.

## Focused regression proof

Focused tests passed 39/39 on current main revision `74b208e945da7cd380cae50565b4c8508fe648df`.

Covered suites:

- OpenClaw Teams conversation ingress;
- governed Teams approval flow;
- Teams request factory;
- approval continuation guard.

The explicit typed-text regression proves that text resembling an approval response is routed to the normal conversation model/flow and results in zero approval-flow calls.

The structured-card tests separately prove that signed approval interactions route to the dedicated approval flow and require exact authenticated response binding.

## Authority conclusion

Typed text does not inherit, consume, modify, or satisfy the original approval solely because it references the pending approval or uses approval-like language.

Any materially changed instruction must be interpreted/planned through the normal conversation path. If the resulting action requires approval, it must obtain its own current governed approval/execution-plan binding.

## Remaining live acceptance

Use the existing harmless typed-override fixture or a fresh equivalent in the authenticated owner Teams bot conversation.

Acceptance requires:

1. owner sends a modified typed instruction rather than clicking Approve/Deny;
2. the typed message enters as a normal authenticated conversation turn;
3. the original approval ID remains undecided/unconsumed;
4. no provider mutation occurs under the original approval;
5. Jason treats the text as a changed instruction;
6. any resulting approval-governed action requires fresh planning and fresh approval;
7. ordinary Teams messaging remains healthy.

This final acceptance requires the authenticated owner's live reply and is intentionally deferred while the Owner is out of the office.
