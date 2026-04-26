"""README acceptance tests.

These treat the README as the executable contract for WriteSQL v0.0. Each test
mirrors a code block from the README and asserts the SQL string a caller would
get back. SQL is compared after whitespace normalization so the README's visual
indentation does not couple the tests to formatting choices.
"""

from __future__ import annotations

import re

from writesql import clause, share, statement


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
