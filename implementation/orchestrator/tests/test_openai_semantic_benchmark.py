import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PATH = ROOT / "tools" / "benchmark_openai_semantic_intent.py"

spec = importlib.util.spec_from_file_location(
    "benchmark_openai_semantic_intent",
    PATH,
)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def test_exact_classification():
    status, missing, extra = module.classify(
        actual_resource="endpoint",
        actual_concepts=("last logged in user",),
        expected_resource="endpoint",
        expected_concepts=("last logged in user",),
    )

    assert status == "exact"
    assert missing == []
    assert extra == []


def test_over_selection_is_visible():
    status, missing, extra = module.classify(
        actual_resource="endpoint",
        actual_concepts=(
            "last logged in user",
            "open alerts",
        ),
        expected_resource="endpoint",
        expected_concepts=("last logged in user",),
    )

    assert status == "over_selected"
    assert missing == []
    assert extra == ["open alerts"]


def test_under_selection_is_visible():
    status, missing, extra = module.classify(
        actual_resource="endpoint",
        actual_concepts=("LAN IP address",),
        expected_resource="endpoint",
        expected_concepts=(
            "LAN IP address",
            "WAN IP address",
        ),
    )

    assert status == "under_selected"
    assert missing == ["WAN IP address"]
    assert extra == []


def test_wrong_resource_is_visible():
    status, _, _ = module.classify(
        actual_resource="alert",
        actual_concepts=("alerts",),
        expected_resource="endpoint",
        expected_concepts=("open alerts",),
    )

    assert status == "wrong_resource"


def test_unresolved_is_visible():
    status, missing, extra = module.classify(
        actual_resource=None,
        actual_concepts=(),
        expected_resource="endpoint",
        expected_concepts=("processor model",),
    )

    assert status == "unresolved"
    assert missing == ["processor model"]
    assert extra == []
