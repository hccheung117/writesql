"""Tests for SQL value primitives and statement rendering orchestration."""

from __future__ import annotations

import pytest

from writesql import statement
from writesql._render import render_value


class TestRenderValue:
    def test_string_is_quoted(self):
        assert render_value("hello") == "'hello'"

    def test_apostrophe_is_escaped_by_doubling(self):
        assert render_value("O'Brien") == "'O''Brien'"

    def test_empty_string_renders_as_empty_quotes(self):
        assert render_value("") == "''"

    def test_int_renders_bare(self):
        assert render_value(42) == "42"

    def test_negative_int_renders_with_sign(self):
        assert render_value(-7) == "-7"

    def test_float_renders_bare(self):
        assert render_value(3.14) == "3.14"

    def test_none_renders_as_null(self):
        assert render_value(None) == "NULL"

    def test_list_renders_as_sql_tuple(self):
        assert render_value(["EU", "US"]) == "('EU', 'US')"

    def test_tuple_renders_as_sql_tuple(self):
        assert render_value((1, 2, 3)) == "(1, 2, 3)"

    def test_empty_list_renders_as_empty_tuple(self):
        assert render_value([]) == "()"

    def test_mixed_value_types_inside_a_list(self):
        assert render_value(["a", 1, None]) == "('a', 1, NULL)"

    def test_unsupported_type_raises_type_error(self):
        with pytest.raises(TypeError):
            render_value({"a": 1})

    def test_bool_is_unsupported_in_v0_0(self):
        # bool subclasses int; an explicit check prevents silent 1/0 coercion.
        with pytest.raises(TypeError):
            render_value(True)


class TestStatementRendering:
    def test_value_parameters_are_rendered_as_sql_literals_inside_the_fstring(self):
        @statement
        def q(name: str, count: int) -> str:
            return f"SELECT * FROM t WHERE name = {name} AND count = {count}"

        assert q(name="alice", count=5) == "SELECT * FROM t WHERE name = 'alice' AND count = 5"

    def test_list_value_parameter_renders_as_sql_tuple(self):
        @statement
        def q(regions: list[str]) -> str:
            return f"SELECT * FROM t WHERE region IN {regions}"

        assert q(regions=["EU", "US"]) == "SELECT * FROM t WHERE region IN ('EU', 'US')"

    def test_none_value_parameter_renders_as_null(self):
        @statement
        def q(x) -> str:
            return f"SELECT {x}"

        assert q(x=None) == "SELECT NULL"

    def test_user_function_returning_non_string_raises(self):
        @statement
        def bad() -> str:
            return 42  # type: ignore[return-value]

        with pytest.raises(TypeError):
            bad()


def test_table_annotation_renders_value_verbatim():
    from writesql import statement
    from writesql._identifier import Table

    @statement
    def q(table: Table) -> str:
        return f"SELECT * FROM {table}"

    assert q(table="orders") == "SELECT * FROM orders"


def test_dotted_table_renders_verbatim():
    from writesql import statement
    from writesql._identifier import Table

    @statement
    def q(table: Table) -> str:
        return f"SELECT * FROM {table}"

    assert q(table="analytics.orders") == "SELECT * FROM analytics.orders"


def test_column_and_table_and_value_in_same_statement():
    from writesql import statement
    from writesql._identifier import Column, Table

    @statement
    def kpi(table: Table, metric: Column, date: str) -> str:
        return f"SELECT {metric} FROM {table} WHERE d = {date}"

    assert (
        kpi(table="orders", metric="revenue", date="2026-04-01")
        == "SELECT revenue FROM orders WHERE d = '2026-04-01'"
    )


def test_invalid_identifier_value_raises_invalid_identifier():
    import pytest

    from writesql import statement
    from writesql._errors import InvalidIdentifier
    from writesql._identifier import Table

    @statement
    def q(table: Table) -> str:
        return f"SELECT * FROM {table}"

    with pytest.raises(InvalidIdentifier):
        q(table="orders; DROP TABLE users")


def test_non_string_identifier_value_raises_unsupported_value():
    import pytest

    from writesql import statement
    from writesql._errors import UnsupportedValue
    from writesql._identifier import Table

    @statement
    def q(table: Table) -> str:
        return f"SELECT * FROM {table}"

    with pytest.raises(UnsupportedValue):
        q(table=42)


def test_renderable_value_with_table_annotation_routes_as_clause():
    """Runtime-type wins: a Renderable value is always rendered as a clause,
    even if the parameter is annotated Table."""
    from writesql import clause, statement
    from writesql._identifier import Table

    @clause
    def inner() -> str:
        return "real_table"

    @statement
    def q(table: Table = inner) -> str:
        return f"SELECT * FROM {table}"

    assert q() == "SELECT * FROM real_table"
