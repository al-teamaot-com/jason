import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PATH = (
    ROOT
    / "tools"
    / "benchmark_openai_semantic_intent.py"
)

spec = importlib.util.spec_from_file_location(
    "benchmark_openai_semantic_intent",
    PATH,
)

module = importlib.util.module_from_spec(
    spec
)

assert spec.loader is not None
spec.loader.exec_module(module)


def test_exact_classification():
    status, missing, extra = module.classify(
        actual_concepts=(
            "last logged in user",
        ),
        acceptable_concept_sets=(
            ("last logged in user",),
        ),
        resolved=True,
    )

    assert status == "exact"
    assert missing == []
    assert extra == []


def test_any_acceptable_semantic_alternative_is_exact():
    status, missing, extra = module.classify(
        actual_concepts=(
            "operating system",
        ),
        acceptable_concept_sets=(
            (
                "operating system",
            ),
            (
                "operating system display version",
            ),
        ),
        resolved=True,
    )

    assert status == "exact"
    assert missing == []
    assert extra == []


def test_over_selection_is_visible():
    status, missing, extra = module.classify(
        actual_concepts=(
            "processor model",
            "logical processor count",
            "total memory",
        ),
        acceptable_concept_sets=(
            (
                "processor model",
                "total memory",
            ),
        ),
        resolved=True,
    )

    assert status == "over_selected"
    assert missing == []
    assert extra == [
        "logical processor count"
    ]


def test_under_selection_is_visible():
    status, missing, extra = module.classify(
        actual_concepts=(
            "LAN IP address",
        ),
        acceptable_concept_sets=(
            (
                "LAN IP address",
                "WAN IP address",
            ),
        ),
        resolved=True,
    )

    assert status == "under_selected"
    assert missing == [
        "WAN IP address"
    ]
    assert extra == []


def test_unresolved_is_visible():
    status, missing, extra = module.classify(
        actual_concepts=(),
        acceptable_concept_sets=(
            ("processor model",),
        ),
        resolved=False,
    )

    assert status == "unresolved"
    assert missing == [
        "processor model"
    ]
    assert extra == []
