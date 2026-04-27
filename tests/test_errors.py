"""Tests for WriteSQL's error hierarchy and per-error messages.

Each error names the link in the render chain that failed: which renderable,
which parameter, and (for cycles) the chain of names visited. All WriteSQL
errors inherit from `WriteSQLError`; specific errors also inherit from the
matching standard exception (`TypeError`, `RuntimeError`) so existing
broad-except code keeps working.
"""

from __future__ import annotations

import pytest

from writesql import clause, statement
from writesql._errors import (
    CycleDetected,
    InvalidReturn,
    MissingParameter,
    UnsupportedValue,
    WriteSQLError,
)


# --- Hierarchy ---------------------------------------------------------------


def test_missing_parameter_is_a_writesql_error_and_a_type_error():
    @clause
    def f(x: int) -> str:
        return ""

    with pytest.raises(WriteSQLError):
        f()
    with pytest.raises(TypeError):
        f()


def test_unsupported_value_is_a_writesql_error_and_a_type_error():
    @statement
    def q(x) -> str:
        return ""

    with pytest.raises(WriteSQLError):
        q(x={"a": 1})
    with pytest.raises(TypeError):
        q(x={"a": 1})


def test_cycle_detected_is_a_writesql_error_and_a_runtime_error():
    @clause
    def a(x=None) -> str:
        return f"{x}"

    params = [
        p.replace(default=a) if p.name == "x" else p
        for p in a.signature.parameters.values()
    ]
    a.signature = a.signature.replace(parameters=params)

    with pytest.raises(WriteSQLError):
        a()
    # Re-arm the cycle (previous call exhausted nothing — same renderable still cyclic).
    with pytest.raises(RuntimeError):
        a()


# --- Messages ----------------------------------------------------------------


def test_missing_parameter_message_names_parameter_and_renderable():
    @clause
    def tenant_filter(tenant_id: int) -> str:
        return ""

    with pytest.raises(MissingParameter, match=r"tenant_id.*tenant_filter"):
        tenant_filter()


def test_unsupported_value_message_names_type_and_parameter():
    @statement
    def get_orders(config) -> str:
        return f"{config}"

    with pytest.raises(UnsupportedValue, match=r"dict.*config"):
        get_orders(config={"a": 1})


def test_invalid_return_message_names_renderable_and_actual_type():
    @statement
    def get_orders() -> str:
        return 42  # type: ignore[return-value]

    with pytest.raises(InvalidReturn, match=r"get_orders.*int"):
        get_orders()


def test_cycle_detected_message_reports_the_chain_of_names():
    @clause
    def a(x=None) -> str:
        return f"{x}"

    params = [
        p.replace(default=a) if p.name == "x" else p
        for p in a.signature.parameters.values()
    ]
    a.signature = a.signature.replace(parameters=params)

    with pytest.raises(CycleDetected, match=r"a -> a"):
        a()


def test_cycle_detected_across_two_clauses_reports_full_chain():
    @clause
    def first(x=None) -> str:
        return f"{x}"

    @clause
    def second(x=None) -> str:
        return f"{x}"

    first.signature = first.signature.replace(
        parameters=[
            p.replace(default=second) if p.name == "x" else p
            for p in first.signature.parameters.values()
        ]
    )
    second.signature = second.signature.replace(
        parameters=[
            p.replace(default=first) if p.name == "x" else p
            for p in second.signature.parameters.values()
        ]
    )

    with pytest.raises(CycleDetected, match=r"first -> second -> first"):
        first()


def test_invalid_identifier_is_a_writesql_error_and_value_error():
    from writesql._errors import InvalidIdentifier, WriteSQLError

    assert issubclass(InvalidIdentifier, WriteSQLError)
    assert issubclass(InvalidIdentifier, ValueError)
