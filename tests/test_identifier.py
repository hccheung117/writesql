"""Tests for SQL identifier markers and rendering.

Identifier parameters are annotated with `Table` or `Column` and must render
as bare (unquoted) SQL tokens, unlike value parameters which are quoted as
SQL literals. This module tests `render_identifier` in isolation; end-to-end
tests that exercise the full classifier/render pipeline live alongside the
other integration tests.
"""

from __future__ import annotations

import pytest

from writesql._errors import InvalidIdentifier, UnsupportedValue
from writesql._identifier import render_identifier


@pytest.mark.parametrize(
    "value",
    [
        "orders",
        "_temp",
        "OrdersView",
        "t1",
        "analytics.orders",
        "prod.analytics.orders",
        "schema_1.table_2",
    ],
)
def test_valid_identifiers_render_verbatim(value):
    assert render_identifier(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        "2orders",
        "orders;",
        "orders.",
        ".orders",
        "orders..name",
        "orders name",
        'orders"',
        '"orders"',
        "orders; DROP TABLE users",
        "schema-1.table",
    ],
)
def test_invalid_identifiers_raise(value):
    with pytest.raises(InvalidIdentifier):
        render_identifier(value)


@pytest.mark.parametrize("value", [None, 42, 3.14, ["orders"], ("a",), True])
def test_non_string_values_raise_unsupported_value(value):
    with pytest.raises(UnsupportedValue):
        render_identifier(value)


def test_table_and_column_are_newtypes_over_str():
    from writesql._identifier import Column, Table

    # NewType: calling is identity at runtime, supertype is str.
    assert Table("orders") == "orders"
    assert Column("amount") == "amount"
    assert Table.__supertype__ is str
    assert Column.__supertype__ is str


# --- Integration with share() and caller pool --------------------------------


def test_share_can_supply_an_identifier_parameter():
    from writesql import clause, share, statement
    from writesql._identifier import Table

    @clause
    def from_table(table: Table) -> str:
        return f"FROM {table}"

    @statement
    def q(src=from_table) -> str:
        return f"SELECT * {src}"

    share(from_table, {"table": "orders"})

    assert q() == "SELECT * FROM orders"


def test_share_supplying_invalid_identifier_raises():
    import pytest

    from writesql import clause, share, statement
    from writesql._errors import InvalidIdentifier
    from writesql._identifier import Table

    @clause
    def from_table(table: Table) -> str:
        return f"FROM {table}"

    @statement
    def q(src=from_table) -> str:
        return f"SELECT * {src}"

    share(from_table, {"table": "orders; DROP TABLE users"})

    with pytest.raises(InvalidIdentifier):
        q()


def test_identifier_resolved_from_top_level_caller_pool():
    """A clause's Table-annotated parameter can be satisfied by a matching
    name in the top-level statement's arguments."""
    from writesql import clause, statement
    from writesql._identifier import Table

    @clause
    def from_table(table: Table) -> str:
        return f"FROM {table}"

    @statement
    def q(table: Table, src=from_table) -> str:
        return f"SELECT * {src}"

    assert q(table="orders") == "SELECT * FROM orders"


def test_public_api_exports_table_column_and_invalid_identifier():
    import writesql

    assert writesql.Table is not None
    assert writesql.Column is not None
    assert writesql.InvalidIdentifier is not None

    # Round-trip via public API only
    from writesql import Table, statement

    @statement
    def q(table: Table) -> str:
        return f"SELECT * FROM {table}"

    assert q(table="orders") == "SELECT * FROM orders"
