"""Internal tests for the renderable unit wrapper.

These are white-box tests on the structural metadata that decorated functions
expose. The README acceptance tests cover end-to-end SQL output; these cover
the recordable shape the spec requires of every renderable unit (kind, name,
signature, clause dependencies).
"""

from __future__ import annotations

import inspect

from writesql import clause, statement
from writesql._renderable import Renderable


def test_statement_decorator_returns_renderable_of_statement_kind():
    @statement
    def q() -> str:
        return "SELECT 1"

    assert isinstance(q, Renderable)
    assert q.kind == "statement"


def test_clause_decorator_returns_renderable_of_clause_kind():
    @clause
    def c() -> str:
        return "x = 1"

    assert isinstance(c, Renderable)
    assert c.kind == "clause"


def test_renderable_preserves_name_and_doc():
    @statement
    def get_orders() -> str:
        """fetch orders."""
        return "SELECT 1"

    assert get_orders.__name__ == "get_orders"
    assert get_orders.__doc__ == "fetch orders."


def test_renderable_exposes_original_function():
    def original() -> str:
        return "SELECT 1"

    decorated = statement(original)

    assert decorated.func is original


def test_renderable_exposes_signature_of_original_function():
    @statement
    def q(a: int, b: str = "x") -> str:
        return ""

    assert isinstance(q.signature, inspect.Signature)
    assert list(q.signature.parameters) == ["a", "b"]


def test_renderable_is_callable_and_returns_user_function_output():
    @statement
    def q() -> str:
        return "SELECT 1"

    assert q() == "SELECT 1"


def test_clause_default_parameters_are_recorded_as_clause_dependencies():
    @clause
    def inner() -> str:
        return ""

    @statement
    def outer(filters=inner) -> str:
        return f"{filters}"

    assert outer.clause_dependencies == {"filters": inner}


def test_non_renderable_defaults_are_not_clause_dependencies():
    @statement
    def outer(x: int = 5, name: str = "foo") -> str:
        return ""

    assert outer.clause_dependencies == {}


def test_renderable_caches_identifier_parameter_names():
    from writesql import statement
    from writesql._identifier import Column, Table

    @statement
    def q(table: Table, metric: Column, date: str) -> str:
        return ""

    assert q.identifier_params == frozenset({"table", "metric"})


def test_renderable_identifier_params_empty_when_none_annotated():
    from writesql import statement

    @statement
    def q(a: str, b: int) -> str:
        return ""

    assert q.identifier_params == frozenset()


def test_renderable_identifier_params_ignores_clause_defaults():
    from writesql import clause, statement
    from writesql._identifier import Table

    @clause
    def filt() -> str:
        return ""

    @statement
    def q(table: Table, filters=filt) -> str:
        return ""

    assert q.identifier_params == frozenset({"table"})
