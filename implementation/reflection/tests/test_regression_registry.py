from pathlib import Path

from reflection.regression_registry import load_regression_registry


def test_regression_registry_is_bounded_and_references_real_tests() -> None:
    root = Path(__file__).resolve().parents[3]
    registry = load_regression_registry(root / "implementation/reflection/regression_cases.json")
    assert len(registry) >= 4
    for case in registry:
        rel, test_name = case.test_reference.split("::", 1)
        test_path = root / "implementation" / rel
        assert test_path.exists(), case.test_reference
        text = test_path.read_text(encoding="utf-8")
        assert f"def {test_name}(" in text, case.test_reference
