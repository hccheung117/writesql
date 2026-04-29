"""Tests for reusable clause column mappings via Columns and .on()."""

from __future__ import annotations

import pytest

import writesql
from writesql import clause, share, statement
from writesql._errors import InvalidIdentifier, MissingParameter


def _squish(sql: str) -> str:
    return " ".join(sql.split())


def test_clause_with_columns_renders_identifiers_supplied_by_on():
    Columns = writesql.Columns

    @clause
    def dashboard_filters(
        columns: Columns,
        start_date: str,
        end_date: str,
        regions: list[str],
    ) -> str:
        return f"""
          AND {columns.date} >= {start_date}
          AND {columns.date} < {end_date}
          AND {columns.region} IN {regions}
        """

    @statement
    def orders_sql(
        start_date: str,
        end_date: str,
        regions: list[str],
        filters=dashboard_filters,
    ) -> str:
        return f"""
        SELECT *
        FROM orders o
        WHERE o.status = 'completed'
          {filters.on(date="o.created_at", region="o.region")}
        """

    sql = orders_sql(
        start_date="2024-01-01",
        end_date="2024-02-01",
        regions=["EU", "US"],
    )

    assert "AND o.created_at >= '2024-01-01'" in sql
    assert "AND o.created_at < '2024-02-01'" in sql
    assert "AND o.region IN ('EU', 'US')" in sql


def test_shared_runtime_values_resolve_with_statement_local_column_mappings():
    Columns = writesql.Columns

    @clause
    def dashboard_filters(
        columns: Columns,
        start_date: str,
        end_date: str,
        regions: list[str],
    ) -> str:
        return f"""
          AND {columns.date} >= {start_date}
          AND {columns.date} < {end_date}
          AND {columns.region} IN {regions}
        """

    @statement
    def orders_sql(filters=dashboard_filters) -> str:
        return f"""
        SELECT *
        FROM orders o
        WHERE 1=1
          {filters.on(date="o.created_at", region="o.region")}
        """

    share(
        dashboard_filters,
        {
            "start_date": "2024-01-01",
            "end_date": "2024-02-01",
            "regions": ["EU", "US"],
        },
    )

    sql = orders_sql()

    assert "AND o.created_at >= '2024-01-01'" in sql
    assert "AND o.created_at < '2024-02-01'" in sql
    assert "AND o.region IN ('EU', 'US')" in sql


def test_same_clause_can_render_different_column_mappings_without_leakage():
    Columns = writesql.Columns

    @clause
    def date_filter(columns: Columns, start_date: str) -> str:
        return f"AND {columns.date} >= {start_date}"

    @statement
    def orders_sql(filters=date_filter) -> str:
        return f"SELECT * FROM orders o WHERE 1=1 {filters.on(date='o.created_at')}"

    @statement
    def users_sql(filters=date_filter) -> str:
        return f"SELECT * FROM users u WHERE 1=1 {filters.on(date='u.signup_at')}"

    share(date_filter, {"start_date": "2024-01-01"})

    assert "o.created_at" in orders_sql()
    assert "u.signup_at" in users_sql()
    assert "u.signup_at" not in orders_sql()


def test_on_does_not_mutate_the_original_clause_renderable():
    Columns = writesql.Columns

    @clause
    def date_filter(columns: Columns, start_date: str) -> str:
        return f"AND {columns.date} >= {start_date}"

    @statement
    def configured(filters=date_filter) -> str:
        return f"SELECT * FROM orders WHERE 1=1 {filters.on(date='created_at')}"

    @statement
    def unconfigured(filters=date_filter) -> str:
        return f"SELECT * FROM orders WHERE 1=1 {filters}"

    share(date_filter, {"start_date": "2024-01-01"})

    assert "created_at" in configured()
    with pytest.raises(MissingParameter, match=r"column mapping.*date_filter"):
        unconfigured()


def test_configured_fragment_passed_as_argument_uses_caller_pool():
    Columns = writesql.Columns

    @clause
    def date_filter(columns: Columns, start_date: str) -> str:
        return f"AND {columns.date} >= {start_date}"

    @statement
    def q(start_date: str, filters=date_filter) -> str:
        return f"SELECT * FROM orders WHERE 1=1 {filters}"

    sql = q(start_date="2024-01-01", filters=date_filter.on(date="created_at"))

    assert sql == "SELECT * FROM orders WHERE 1=1 AND created_at >= '2024-01-01'"


def test_missing_on_for_columns_parameter_raises_clear_error():
    Columns = writesql.Columns

    @clause
    def date_filter(columns: Columns, start_date: str) -> str:
        return f"AND {columns.date} >= {start_date}"

    @statement
    def q(filters=date_filter) -> str:
        return f"SELECT * FROM orders WHERE 1=1 {filters}"

    share(date_filter, {"start_date": "2024-01-01"})

    with pytest.raises(MissingParameter, match=r"column mapping.*date_filter"):
        q()


def test_accessing_unmapped_column_name_raises_clear_error():
    Columns = writesql.Columns

    @clause
    def dashboard_filters(columns: Columns, start_date: str) -> str:
        return f"AND {columns.region} >= {start_date}"

    @statement
    def q(filters=dashboard_filters) -> str:
        return f"SELECT * FROM orders WHERE 1=1 {filters.on(date='created_at')}"

    share(dashboard_filters, {"start_date": "2024-01-01"})

    with pytest.raises(MissingParameter, match=r"region.*dashboard_filters"):
        q()


def test_invalid_identifier_value_in_on_raises_invalid_identifier():
    Columns = writesql.Columns

    @clause
    def date_filter(columns: Columns, start_date: str) -> str:
        return f"AND {columns.date} >= {start_date}"

    @statement
    def q(filters=date_filter) -> str:
        return f"""
        SELECT * FROM orders WHERE 1=1
          {filters.on(date="orders; DROP TABLE users")}
        """

    share(date_filter, {"start_date": "2024-01-01"})

    with pytest.raises(InvalidIdentifier, match=r"date.*date_filter"):
        q()


def test_on_called_on_statement_raises_type_focused_error():
    @statement
    def q() -> str:
        return "SELECT 1"

    with pytest.raises(TypeError, match=r"\.on\(\).*@clause"):
        q.on(date="created_at")


def test_clause_with_more_than_one_columns_parameter_is_rejected():
    Columns = writesql.Columns

    with pytest.raises(TypeError, match=r"one Columns parameter"):

        @clause
        def bad(left: Columns, right: Columns) -> str:
            return f"{left.date} = {right.date}"
