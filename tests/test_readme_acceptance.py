"""README acceptance tests.

These treat the README as the executable contract for WriteSQL. Each test
mirrors a code block from the README and asserts the SQL string a caller would
get back. SQL is compared after whitespace normalization so the README's visual
indentation does not couple the tests to formatting choices.
"""

from __future__ import annotations

from pathlib import Path
import re

import pytest

from writesql import Columns, Table, clause, parameterize, share, statement
from writesql._parameterization import _reset_parameterization

README = Path(__file__).resolve().parents[1] / "README.md"


@pytest.fixture(autouse=True)
def reset_parameterization():
    _reset_parameterization()
    yield
    _reset_parameterization()


def _normalize(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


# --- Basic statement rendering -------------------------------------------------


def test_basic_statement_renders_value_parameters():
    @statement
    def get_orders(start_date: str, end_date: str, regions: list[str]) -> str:
        return f"""
        SELECT id, amount, user_id
        FROM orders
        WHERE status = 'completed'
          AND created_at >= {start_date}
          AND created_at < {end_date}
          AND region IN {regions}
        """

    sql = get_orders(
        start_date="2024-01-01",
        end_date="2024-02-01",
        regions=["EU", "US"],
    )

    expected = """
        SELECT id, amount, user_id
        FROM orders
        WHERE status = 'completed'
          AND created_at >= '2024-01-01'
          AND created_at < '2024-02-01'
          AND region IN ('EU', 'US')
    """
    assert _normalize(str(sql)) == _normalize(expected)


def test_basic_statement_result_is_string_compatible():
    @statement
    def trivial() -> str:
        return "SELECT 1"

    sql = trivial()
    # Callers should be able to treat it as a plain string.
    assert str(sql).strip() == "SELECT 1"


def test_readme_documents_sequence_parameterization_example():
    readme = README.read_text()

    assert 'parameterize("sequence", placeholder=lambda p: "?")' in readme
    assert "cursor.execute(str(sql), sql.params)" in readme
    assert "sql.debug_sql" in readme
    assert "not for execution" in readme


def test_readme_sequence_parameterization_example_is_string_compatible():
    parameterize("sequence", placeholder=lambda p: "?")

    @statement
    def get_orders(start_date: str, end_date: str, regions: list[str]) -> str:
        return f"""
        SELECT id, amount, user_id
        FROM orders
        WHERE status = 'completed'
          AND created_at >= {start_date}
          AND created_at < {end_date}
          AND region IN {regions}
        """

    sql = get_orders(
        start_date="2024-01-01",
        end_date="2024-02-01",
        regions=["EU", "US"],
    )
    expected_driver_sql = """
        SELECT id, amount, user_id
        FROM orders
        WHERE status = 'completed'
          AND created_at >= ?
          AND created_at < ?
          AND region IN (?, ?)
    """
    expected_debug_sql = """
        SELECT id, amount, user_id
        FROM orders
        WHERE status = 'completed'
          AND created_at >= '2024-01-01'
          AND created_at < '2024-02-01'
          AND region IN ('EU', 'US')
    """

    assert isinstance(sql, str)
    assert _normalize(str(sql)) == _normalize(expected_driver_sql)
    assert sql.params == ["2024-01-01", "2024-02-01", "EU", "US"]
    assert _normalize(sql.debug_sql) == _normalize(expected_debug_sql)

    executed: list[tuple[str, list[str]]] = []

    class Cursor:
        def execute(self, statement: str, params: list[str]) -> None:
            executed.append((statement, params))

    cursor = Cursor()
    cursor.execute(str(sql), sql.params)

    assert executed == [(str(sql), sql.params)]


# --- Clause composition --------------------------------------------------------


def test_clause_composition_via_default_parameter():
    @clause
    def dashboard_filters(
        start_date: str, end_date: str, regions: list[str]
    ) -> str:
        return f"""
          AND created_at >= {start_date}
          AND created_at < {end_date}
          AND region IN {regions}
        """

    @statement
    def get_orders(
        start_date: str,
        end_date: str,
        regions: list[str],
        filters=dashboard_filters,
    ) -> str:
        return f"""
        SELECT id, amount, user_id
        FROM orders
        WHERE status = 'completed'
          {filters}
        """

    sql = get_orders(
        start_date="2024-01-01",
        end_date="2024-02-01",
        regions=["EU", "US"],
    )

    expected = """
        SELECT id, amount, user_id
        FROM orders
        WHERE status = 'completed'
          AND created_at >= '2024-01-01'
          AND created_at < '2024-02-01'
          AND region IN ('EU', 'US')
    """
    assert _normalize(str(sql)) == _normalize(expected)


# --- share() runtime context ---------------------------------------------------


def test_share_binds_runtime_context_to_clause():
    @clause
    def tenant_filter(tenant_id: int) -> str:
        return f"AND tenant_id = {tenant_id}"

    @statement
    def get_orders(filters=tenant_filter) -> str:
        return f"""
        SELECT id, amount, user_id
        FROM orders
        WHERE status = 'completed'
          {filters}
        """

    share(tenant_filter, {"tenant_id": 123})

    sql = get_orders()

    expected = """
        SELECT id, amount, user_id
        FROM orders
        WHERE status = 'completed'
          AND tenant_id = 123
    """
    assert _normalize(str(sql)) == _normalize(expected)


def test_column_mapping_for_reusable_dashboard_filters():
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
    def get_orders(filters=dashboard_filters) -> str:
        return f"""
        SELECT id, amount, user_id
        FROM orders o
        WHERE status = 'completed'
          {filters.on(
              date="o.created_at",
              region="o.region",
          )}
        """

    share(
        dashboard_filters,
        {
            "start_date": "2024-01-01",
            "end_date": "2024-02-01",
            "regions": ["EU", "US"],
        },
    )

    expected = """
        SELECT id, amount, user_id
        FROM orders o
        WHERE status = 'completed'
          AND o.created_at >= '2024-01-01'
          AND o.created_at < '2024-02-01'
          AND o.region IN ('EU', 'US')
    """
    assert _normalize(str(get_orders())) == _normalize(expected)


# --- Identifier parameters (Table, Column) ------------------------------------


def test_identifier_parameters_render_verbatim():
    @statement
    def get_orders(
        source: Table,
        start_date: str,
        end_date: str,
        regions: list[str],
    ) -> str:
        return f"""
        SELECT id, amount, user_id
        FROM {source}
        WHERE status = 'completed'
          AND created_at >= {start_date}
          AND created_at < {end_date}
          AND region IN {regions}
        """

    sql = get_orders(
        source="analytics.orders",
        start_date="2024-01-01",
        end_date="2024-02-01",
        regions=["EU", "US"],
    )

    expected = """
        SELECT id, amount, user_id
        FROM analytics.orders
        WHERE status = 'completed'
          AND created_at >= '2024-01-01'
          AND created_at < '2024-02-01'
          AND region IN ('EU', 'US')
    """
    assert _normalize(str(sql)) == _normalize(expected)
