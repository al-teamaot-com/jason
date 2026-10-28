# Native release manager same-profile rollforward

The Release Manager checks the live Autotask profile against the immutable candidate's two source-declared values. A live service already on the intended candidate read profile is a legitimate same-profile rollforward; a live service on the declared last-known-good profile is a legitimate profile migration. An unknown or third live profile remains a hard denial.

This fix changes only the pre-mutation profile consistency predicate, not the owner freeze, exact-SHA approval, protected checks, CCC, rollback, or provider write permissions. See the focused release-manager regression tests for both allowed and denied cases.
