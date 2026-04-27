"""Tests for call binding and value-vs-clause parameter classification.

Binding maps caller-supplied positional and keyword arguments to named
parameters using the renderable's signature, applying defaults for omitted
parameters. Each resulting bound parameter is classified as either a value
parameter (raw Python data destined for SQL-literal rendering) or a clause
parameter (a `Renderable` to be rendered recursively).
"""

from __future__ import annotations

import pytest

from writesql import clause, statement
from writesql._binding import BoundParameter, bind_and_classify


# --- Mapping caller args to names --------------------------------------------


def test_positional_args_are_bound_to_parameter_names():
    @statement
    def q(a: str, b: int) -> str:
        return ""

    bound = bind_and_classify(q, "x", 5)

    assert bound["a"].value == "x"
    assert bound["b"].value == 5


def test_keyword_args_are_bound_to_parameter_names():
    @statement
    def q(a: str, b: int) -> str:
        return ""

    bound = bind_and_classify(q, a="x", b=5)

    assert bound["a"].value == "x"
    assert bound["b"].value == 5


def test_defaults_are_applied_when_caller_omits_arguments():
    @statement
    def q(a: str = "default", b: int = 7) -> str:
        return ""

    bound = bind_and_classify(q)

    assert bound["a"].value == "default"
    assert bound["b"].value == 7


def test_missing_required_argument_raises():
    @statement
    def q(a: str) -> str:
        return ""

    with pytest.raises(TypeError):
        bind_and_classify(q)


def test_unknown_keyword_argument_raises():
    @statement
    def q(a: str) -> str:
        return ""

    with pytest.raises(TypeError):
        bind_and_classify(q, a="x", unknown=1)


# --- Classifying value vs clause ---------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["text", 42, 3.14, None, ["a", "b"], ("a", "b")],
)
def test_primitive_arguments_are_classified_as_value_parameters(value):
    @statement
    def q(x) -> str:
        return ""

    bound = bind_and_classify(q, value)

    assert bound["x"].kind == "value"
    assert bound["x"].value == value


def test_renderable_default_is_classified_as_clause_parameter():
    @clause
    def inner() -> str:
        return ""

    @statement
    def outer(filters=inner) -> str:
        return ""

    bound = bind_and_classify(outer)

    assert bound["filters"].kind == "clause"
    assert bound["filters"].value is inner


def test_renderable_passed_explicitly_is_classified_as_clause_parameter():
    @clause
    def inner() -> str:
        return ""

    @clause
    def override() -> str:
        return ""

    @statement
    def outer(filters=inner) -> str:
        return ""

    bound = bind_and_classify(outer, filters=override)

    assert bound["filters"].kind == "clause"
    assert bound["filters"].value is override


def test_mixed_value_and_clause_parameters_are_classified_per_argument():
    @clause
    def inner() -> str:
        return ""

    @statement
    def outer(start_date: str, regions: list[str], filters=inner) -> str:
        return ""

    bound = bind_and_classify(
        outer, start_date="2024-01-01", regions=["EU", "US"]
    )

    assert bound["start_date"] == BoundParameter("start_date", "value", "2024-01-01")
    assert bound["regions"].kind == "value"
    assert bound["regions"].value == ["EU", "US"]
    assert bound["filters"].kind == "clause"
    assert bound["filters"].value is inner


# --- Classifying identifier parameters ---


def test_table_annotated_parameter_is_classified_as_identifier():
    from writesql import statement
    from writesql._identifier import Table

    @statement
    def q(table: Table) -> str:
        return ""

    bound = bind_and_classify(q, table="orders")

    assert bound["table"].kind == "identifier"
    assert bound["table"].value == "orders"


def test_column_annotated_parameter_is_classified_as_identifier():
    from writesql import statement
    from writesql._identifier import Column

    @statement
    def q(metric: Column) -> str:
        return ""

    bound = bind_and_classify(q, metric="revenue")

    assert bound["metric"].kind == "identifier"


def test_renderable_value_with_table_annotation_still_classified_as_clause():
    from writesql import clause, statement
    from writesql._identifier import Table

    @clause
    def inner() -> str:
        return ""

    @statement
    def q(table: Table = inner) -> str:
        return ""

    bound = bind_and_classify(q)

    assert bound["table"].kind == "clause"
    assert bound["table"].value is inner
