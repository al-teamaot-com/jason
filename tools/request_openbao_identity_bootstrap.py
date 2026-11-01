#!/usr/bin/env python3
from __future__ import annotations
import json
from request_openbao_identity_rotation import request_lifecycle_action


def main() -> int:
    result = request_lifecycle_action(
        action='bootstrap_from_init',
        provider='identity_lifecycle',
        reason='one-time protected identity-lifecycle bootstrap and initial administrative token retirement',
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
