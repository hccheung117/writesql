"""Tests for share()-based runtime context.

`share(renderable, values)` binds runtime values to a specific renderable for
the current execution context. Values are scoped to the renderable's identity
(not to a global parameter name) and isolated per `contextvars.Context` so
async tasks or per-request bindings do not leak across each other.
"""

from __future__ import annotations

import contextvars

import pytest

from writesql import clause, share, statement


def test_shared_value_resolves_a_clause_called_directly():
    @clause
    def tenant_filter(tenant_id: int) -> str:
        return f"tenant = {tenant_id}"

    share(tenant_filter, {"tenant_id": 99})

    assert tenant_filter() == "tenant = 99"


def test_shared_value_is_scoped_to_the_targeted_renderable():
    @clause
    def a(tenant_id: int) -> str:
        return f"a={tenant_id}"

    @clause
    def b(tenant_id: int) -> str:
        return f"b={tenant_id}"

    share(a, {"tenant_id": 1})

    assert a() == "a=1"
    with pytest.raises(TypeError):
        b()


def test_explicit_caller_argument_takes_precedence_over_shared_value():
    @clause
    def f(tenant_id: int) -> str:
        return f"t={tenant_id}"

    share(f, {"tenant_id": 10})

    assert f(tenant_id=99) == "t=99"


def test_shared_value_takes_precedence_over_python_default():
    @clause
    def f(tenant_id: int = 0) -> str:
        return f"t={tenant_id}"

    share(f, {"tenant_id": 7})

    assert f() == "t=7"


def test_shared_value_resolves_for_a_nested_clause_dependency():
    @clause
    def tenant_filter(tenant_id: int) -> str:
        return f"AND tenant = {tenant_id}"

    @statement
    def q(filt=tenant_filter) -> str:
        return f"SELECT * FROM t WHERE 1=1 {filt}"

    share(tenant_filter, {"tenant_id": 42})

    assert q() == "SELECT * FROM t WHERE 1=1 AND tenant = 42"


def test_shared_values_isolate_across_contextvars_contexts():
    @clause
    def f(tenant_id: int) -> str:
        return f"t={tenant_id}"

    def render_with(tid: int) -> str:
        share(f, {"tenant_id": tid})
        return f()

    ctx_a = contextvars.copy_context()
    ctx_b = contextvars.copy_context()

    assert ctx_a.run(render_with, 1) == "t=1"
    assert ctx_b.run(render_with, 2) == "t=2"

    # Bindings from copied contexts must not leak back to the parent.
    with pytest.raises(TypeError):
        f()
