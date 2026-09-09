from orchestrator.open_world_schema import (
    flatten_schema_fields,
)


def test_flattens_unknown_nested_structure_without_domain_rules():
    fields = flatten_schema_fields(
        {
            "outer": {
                "alpha": 7,
                "beta": True,
                "nested": {
                    "gamma": "x",
                },
            },
            "items": [
                {
                    "delta": 3.5,
                }
            ],
        }
    )

    paths = {
        field.path
        for field in fields
    }

    assert "outer.alpha" in paths
    assert "outer.beta" in paths
    assert "outer.nested.gamma" in paths
    assert "items" in paths
    assert "items[].delta" in paths


def test_no_predeclared_fact_vocabulary_is_required():
    fields = flatten_schema_fields(
        {
            "totally_unseen_name": 123
        }
    )

    assert fields[0].path == (
        "totally_unseen_name"
    )
