"""Tests for clause rendering, raw-fragment embedding, and recursive clause
dependencies.

A clause renders just like a statement when called directly — its value
parameters become SQL literals. When a clause is injected as a default
parameter on another renderable, its rendered output embeds raw (not as a
quoted string) at the substitution site, and its own parameters resolve from
the outer renderable's caller-supplied arguments by name.
"""

from __future__ import annotations

from writesql import clause, statement


def test_clause_called_directly_renders_value_parameters_as_sql_literals():
    @clause
    def f(name: str) -> str:
        return f"name = {name}"

    assert f(name="alice") == "name = 'alice'"


def test_clause_output_embeds_raw_in_the_outer_statement():
    @clause
    def fragment() -> str:
        return "AND active = TRUE"

    @statement
    def q(filt=fragment) -> str:
        return f"SELECT * FROM t WHERE 1=1 {filt}"

    sql = q()
    assert "AND active = TRUE" in sql
    # Raw embedding, not quoted as a SQL string literal.
    assert "'AND active = TRUE'" not in sql


def test_clause_parameters_resolve_from_outer_caller_arguments_by_name():
    @clause
    def filters(region: str) -> str:
        return f"AND region = {region}"

    @statement
    def q(region: str, filt=filters) -> str:
        return f"SELECT * FROM t WHERE 1=1 {filt}"

    assert q(region="EU") == "SELECT * FROM t WHERE 1=1 AND region = 'EU'"


def test_recursive_clause_dependencies_resolve_to_terminal_values():
    @clause
    def innermost(name: str) -> str:
        return f"name = {name}"

    @clause
    def middle(inner=innermost) -> str:
        return f"({inner})"

    @statement
    def outer(name: str, mid=middle) -> str:
        return f"SELECT * FROM t WHERE {mid}"

    assert outer(name="alice") == "SELECT * FROM t WHERE (name = 'alice')"


def test_clause_uses_its_own_python_default_when_outer_does_not_supply():
    @clause
    def f(region: str = "EU") -> str:
        return f"region = {region}"

    @statement
    def q(filt=f) -> str:
        return f"SELECT * FROM t WHERE {filt}"

    assert q() == "SELECT * FROM t WHERE region = 'EU'"


def test_outer_caller_argument_overrides_clause_default():
    @clause
    def f(region: str = "EU") -> str:
        return f"region = {region}"

    @statement
    def q(region: str, filt=f) -> str:
        return f"SELECT * FROM t WHERE {filt}"

    assert q(region="US") == "SELECT * FROM t WHERE region = 'US'"
