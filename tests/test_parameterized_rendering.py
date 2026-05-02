"""Integration tests for parameterized rendering."""

from __future__ import annotations

import pytest

import writesql
from writesql import (
    Column,
    Columns,
    ConfigurationError,
    Table,
    clause,
    parameterize,
    statement,
)
from writesql._errors import InvalidIdentifier, UnsupportedValue
from writesql._parameterization import Param, _reset_parameterization


@pytest.fixture(autouse=True)
def reset_parameterization():
    _reset_parameterization()
    yield
    _reset_parameterization()


def test_unconfigured_statement_returns_compiled_sql_with_literals():
    @statement
    def q(name: str, count: int) -> str:
        return f"SELECT * FROM t WHERE name = {name} AND count = {count}"

    sql = q(name="alice", count=5)

    assert isinstance(sql, str)
    assert str(sql) == "SELECT * FROM t WHERE name = 'alice' AND count = 5"
    assert sql.params == []
    assert sql.debug_sql == str(sql)


def test_sequence_parameterization_collects_scalar_values_and_debug_sql():
    parameterize("sequence", placeholder=lambda p: "?")

    @statement
    def q(name: str, count: int) -> str:
        return f"SELECT * FROM t WHERE name = {name} AND count = {count}"

    sql = q(name="alice", count=5)

    assert str(sql) == "SELECT * FROM t WHERE name = ? AND count = ?"
    assert sql.params == ["alice", 5]
    assert sql.debug_sql == "SELECT * FROM t WHERE name = 'alice' AND count = 5"


def test_reused_rendered_value_fragment_collects_each_placeholder_occurrence():
    parameterize("sequence", placeholder=lambda p: "?")

    @statement
    def q(region: str) -> str:
        condition = f"region = {region}"
        return f"SELECT * FROM t WHERE {condition} OR {condition}"

    sql = q(region="EU")

    assert str(sql) == "SELECT * FROM t WHERE region = ? OR region = ?"
    assert sql.params == ["EU", "EU"]
    assert sql.debug_sql == (
        "SELECT * FROM t WHERE region = 'EU' OR region = 'EU'"
    )


def test_configured_statement_body_executes_once():
    parameterize("sequence", placeholder=lambda p: "?")
    calls = 0

    @statement
    def q(region: str) -> str:
        nonlocal calls
        calls += 1
        return f"SELECT * FROM t WHERE region = {region}"

    sql = q(region="EU")

    assert str(sql) == "SELECT * FROM t WHERE region = ?"
    assert sql.debug_sql == "SELECT * FROM t WHERE region = 'EU'"
    assert calls == 1


def test_mapping_parameterization_collects_scalar_values_by_generated_key():
    parameterize("mapping", placeholder=lambda p: f":{p.key}")

    @statement
    def q(name: str, count: int) -> str:
        return f"SELECT * FROM t WHERE name = {name} AND count = {count}"

    sql = q(name="alice", count=5)

    assert str(sql) == "SELECT * FROM t WHERE name = :name_1 AND count = :count_2"
    assert sql.params == {"name_1": "alice", "count_2": 5}
    assert sql.debug_sql == "SELECT * FROM t WHERE name = 'alice' AND count = 5"


def test_compiled_sql_is_public_and_returned_for_statements_and_direct_clauses():
    assert writesql.CompiledSQL is not None

    @statement
    def q(name: str) -> str:
        return f"SELECT {name}"

    @clause
    def f(region: str) -> str:
        return f"region = {region}"

    assert isinstance(q(name="alice"), writesql.CompiledSQL)
    assert isinstance(f(region="EU"), writesql.CompiledSQL)


def test_placeholder_callback_sees_final_sql_order_param_metadata():
    seen: list[Param] = []

    def placeholder(param: Param) -> str:
        seen.append(param)
        return f"${param.index}"

    parameterize("sequence", placeholder=placeholder)

    @statement
    def q(second: str, first: str) -> str:
        return f"SELECT {first}, {second}, {first}"

    sql = q(first="one", second="two")

    assert str(sql) == "SELECT $1, $2, $3"
    assert sql.params == ["one", "two", "one"]
    assert seen == [
        Param(name="first", index=1, key="first_1", value="one"),
        Param(name="second", index=2, key="second_2", value="two"),
        Param(name="first", index=3, key="first_3", value="one"),
    ]


def test_nested_clauses_share_placeholder_indexes_in_final_sql_order():
    parameterize("sequence", placeholder=lambda p: "?")

    @clause
    def region_filter(region: str) -> str:
        return f"region = {region}"

    @statement
    def q(status: str, region: str, filters=region_filter) -> str:
        return f"SELECT * FROM t WHERE {filters} AND status = {status}"

    sql = q(status="active", region="EU")

    assert str(sql) == "SELECT * FROM t WHERE region = ? AND status = ?"
    assert sql.params == ["EU", "active"]
    assert sql.debug_sql == (
        "SELECT * FROM t WHERE region = 'EU' AND status = 'active'"
    )


def test_direct_fragment_call_inside_statement_uses_outer_render_context():
    parameterize("sequence", placeholder=lambda p: "?")

    @clause
    def date_filter(columns: Columns, start_date: str) -> str:
        return f"AND {columns.date} >= {start_date}"

    @statement
    def q() -> str:
        return (
            "SELECT * FROM orders WHERE 1=1 "
            f"{date_filter.on(date='created_at')(start_date='2024-01-01')}"
        )

    sql = q()

    assert str(sql) == "SELECT * FROM orders WHERE 1=1 AND created_at >= ?"
    assert sql.params == ["2024-01-01"]
    assert sql.debug_sql == (
        "SELECT * FROM orders WHERE 1=1 AND created_at >= '2024-01-01'"
    )


def test_direct_fragment_call_inside_statement_can_forward_outer_value():
    parameterize("sequence", placeholder=lambda p: "?")

    @clause
    def date_filter(columns: Columns, start_date: str) -> str:
        return f"AND {columns.date} >= {start_date}"

    @statement
    def q(start_date: str) -> str:
        return (
            "SELECT * FROM orders WHERE 1=1 "
            f"{date_filter.on(date='created_at')(start_date=start_date)}"
        )

    sql = q(start_date="2024-01-01")

    assert str(sql) == "SELECT * FROM orders WHERE 1=1 AND created_at >= ?"
    assert sql.params == ["2024-01-01"]
    assert sql.debug_sql == (
        "SELECT * FROM orders WHERE 1=1 AND created_at >= '2024-01-01'"
    )


def test_sequence_parameterization_expands_lists_and_tuples_item_by_item():
    parameterize("sequence", placeholder=lambda p: "?")

    @statement
    def q(regions: list[str], codes: tuple[int, int]) -> str:
        return f"SELECT * FROM t WHERE region IN {regions} AND code IN {codes}"

    sql = q(regions=["EU", "US"], codes=(1, 2))

    assert str(sql) == "SELECT * FROM t WHERE region IN (?, ?) AND code IN (?, ?)"
    assert sql.params == ["EU", "US", 1, 2]
    assert sql.debug_sql == (
        "SELECT * FROM t WHERE region IN ('EU', 'US') AND code IN (1, 2)"
    )


def test_mapping_parameterization_expands_lists_and_preserves_empty_lists():
    parameterize("mapping", placeholder=lambda p: f":{p.key}")

    @statement
    def q(regions: list[str], empty: list[str]) -> str:
        return f"SELECT * FROM t WHERE region IN {regions} AND none IN {empty}"

    sql = q(regions=["EU", "US"], empty=[])

    assert str(sql) == (
        "SELECT * FROM t WHERE region IN (:regions_1, :regions_2) AND none IN ()"
    )
    assert sql.params == {"regions_1": "EU", "regions_2": "US"}
    assert sql.debug_sql == (
        "SELECT * FROM t WHERE region IN ('EU', 'US') AND none IN ()"
    )


def test_identifiers_and_columns_render_inline_and_are_not_params():
    parameterize("mapping", placeholder=lambda p: f":{p.key}")

    @clause
    def date_filter(columns: Columns, start_date: str) -> str:
        return f"AND {columns.date} >= {start_date}"

    @statement
    def q(
        table: Table,
        metric: Column,
        start_date: str,
        filters=date_filter,
    ) -> str:
        return f"SELECT {metric} FROM {table} WHERE 1=1 {filters.on(date='created_at')}"

    sql = q(table="orders", metric="revenue", start_date="2024-01-01")

    assert str(sql) == (
        "SELECT revenue FROM orders WHERE 1=1 AND created_at >= :start_date_1"
    )
    assert sql.params == {"start_date_1": "2024-01-01"}
    assert sql.debug_sql == (
        "SELECT revenue FROM orders WHERE 1=1 AND created_at >= '2024-01-01'"
    )


def test_unsupported_value_is_not_collected_into_params():
    seen: list[Param] = []

    def placeholder(param: Param) -> str:
        seen.append(param)
        return "?"

    parameterize("sequence", placeholder=placeholder)

    @statement
    def q(config: dict[str, str]) -> str:
        return f"SELECT {config}"

    with pytest.raises(UnsupportedValue):
        q(config={"region": "EU"})

    assert seen == []


def test_non_string_placeholder_return_raises_configuration_error():
    parameterize("sequence", placeholder=lambda p: 123)

    @statement
    def q(name: str) -> str:
        return f"SELECT {name}"

    with pytest.raises(ConfigurationError, match=r"placeholder.*str.*name"):
        q(name="alice")


def test_direct_clause_returns_compiled_sql_with_params():
    parameterize("sequence", placeholder=lambda p: "?")

    @clause
    def f(region: str) -> str:
        return f"region = {region}"

    sql = f(region="EU")

    assert str(sql) == "region = ?"
    assert sql.params == ["EU"]
    assert sql.debug_sql == "region = 'EU'"


def test_configured_fragment_call_with_columns_returns_compiled_sql_with_params():
    parameterize("sequence", placeholder=lambda p: "?")

    @clause
    def f(columns: Columns, start_date: str) -> str:
        return f"{columns.date} >= {start_date}"

    sql = f.on(date="created_at")(start_date="2024-01-01")

    assert isinstance(sql, writesql.CompiledSQL)
    assert str(sql) == "created_at >= ?"
    assert sql.params == ["2024-01-01"]
    assert sql.debug_sql == "created_at >= '2024-01-01'"


def test_invalid_identifier_still_raises_under_parameterization():
    parameterize("sequence", placeholder=lambda p: "?")

    @statement
    def q(table: Table) -> str:
        return f"SELECT * FROM {table}"

    with pytest.raises(InvalidIdentifier):
        q(table="orders; DROP TABLE users")
