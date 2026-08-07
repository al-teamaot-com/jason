from __future__ import annotations

import importlib.util
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
COMMAND_PATH = REPOSITORY_ROOT / "tools" / "autotask_business_context.py"


def _load_command_module():
    spec = importlib.util.spec_from_file_location(
        "autotask_business_context_command",
        COMMAND_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_operator_command_requires_company_name_not_provider_id() -> None:
    module = _load_command_module()
    parser = module.build_parser()

    company_action = next(
        action for action in parser._actions if action.dest == "company_name"
    )
    assert company_action.required is True
    assert not any(
        action.dest in {"company_id", "client_id"}
        for action in parser._actions
    )


def test_operator_command_supports_governance_check_only() -> None:
    module = _load_command_module()
    parser = module.build_parser()
    args = parser.parse_args(
        [
            "--company-name",
            "Atlantic Office Technologies",
            "--principal-id",
            "operator-al",
            "--organization-id",
            "aot",
            "--check-only",
        ]
    )
    assert args.check_only is True
    assert args.company_name == "Atlantic Office Technologies"
