import pytest

from apps.securewise.services.api_pentest import _safe_endpoint_path
from apps.securewise.services.security_planner import _safe_parameter_schema


@pytest.mark.parametrize(
    ("schema", "override", "expected"),
    [
        ({"enum": ["open", "closed"]}, "open", "/items?state=open"),
        ({"enum": ["open", "closed"]}, "unknown", None),
        ({"type": "integer"}, 3, "/items?state=3"),
        ({"type": "integer"}, True, None),
        ({"type": "integer"}, 100001, None),
        ({"type": "boolean"}, True, "/items?state=True"),
        ({"type": "boolean"}, "true", None),
        ({"type": "string"}, "arbitrary", None),
    ],
)
def test_query_overrides_are_bounded_by_approved_schema(schema, override, expected):
    parameters = [{"name": "state", "in": "query", "schema": schema}]
    assert _safe_endpoint_path("/items", parameters, "owner", query_overrides={"state": override}) == expected


@pytest.mark.parametrize(
    ("parameter", "expected"),
    [
        ({"name": "state", "schema": {"enum": ["open", "closed"]}}, "/items?state=open"),
        ({"name": "state", "required": True, "schema": {"type": "integer"}}, "/items?state=1"),
        ({"name": "state", "required": True, "schema": {"type": "object"}}, None),
        ({"name": "state", "example": {"nested": "unsafe"}}, None),
        ({"name": "api_key", "example": "synthetic"}, None),
        ({"name": "bad name"}, None),
    ],
)
def test_query_fixture_values_cannot_smuggle_credentials_or_objects(parameter, expected):
    assert _safe_endpoint_path("/items", [{"in": "query", **parameter}], "owner") == expected


@pytest.mark.parametrize("path", ["relative", "//external.test/", "/bad\\path", "/{unknown}", "/{unclosed"])
def test_unsafe_or_unresolved_endpoint_paths_are_not_executed(path):
    assert _safe_endpoint_path(path, [], "owner") is None


@pytest.mark.parametrize(
    ("name", "schema", "expected"),
    [
        ("userId", {}, "/items/owner-123"),
        ("item", {"enum": ["approved-item"]}, "/items/approved-item"),
        ("item", {"default": "default-item"}, "/items/default-item"),
        ("item", {"default": "../unsafe/path"}, None),
        ("item", {}, None),
    ],
)
def test_path_parameters_require_explicit_safe_values_or_the_authenticated_subject(name, schema, expected):
    parameters = [None, {"name": "ignored", "in": "header"}, {"name": name, "in": "path", "schema": schema}]
    assert _safe_endpoint_path("/items/{" + name + "}", parameters, "owner-123") == expected


def test_only_safe_query_parameters_are_exposed_to_planner():
    schema = _safe_parameter_schema(
        [
            None,
            {"in": "header", "name": "Authorization"},
            {"in": "query", "name": "api_key", "schema": {"type": "integer"}},
            {"in": "query", "name": "mode", "schema": {"enum": ["open", {"unsafe": True}, "x" * 101]}},
            {"in": "query", "name": "limit", "schema": {"type": "integer"}},
            {"in": "query", "name": "enabled", "schema": {"type": "boolean"}},
            {"in": "query", "name": "free_text", "schema": {"type": "string"}},
        ]
    )
    assert schema == {
        "mode": {"type": "enum", "values": ["open"]},
        "limit": {"type": "integer"},
        "enabled": {"type": "boolean"},
    }
