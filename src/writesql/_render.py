"""SQL value primitives and render-time parameter resolution.

`render_value` turns a raw Python value into SQL-literal text. `render_renderable`
walks a renderable's signature and resolves each parameter using the order
specified in the design: explicit caller arguments first, then the propagated
top-level caller pool, then clause-dependency defaults declared on the
signature, then shared runtime context bound via `share()`, then ordinary
Python defaults, then a `MissingParameter` error. Value parameters are wrapped
as SQL literals before the user function runs; clause parameters are rendered
recursively into raw SQL fragments. Cycles in clause dependencies are
detected via the render stack.
"""

from __future__ import annotations

import inspect
from typing import Any

from ._context import shared_values_for
from ._errors import (
    CycleDetected,
    InvalidReturn,
    MissingParameter,
    UnsupportedValue,
)
from ._renderable import Renderable

_MISSING = inspect.Parameter.empty


def render_value(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        raise UnsupportedValue(
            f"unsupported SQL value type {type(value).__name__!r}"
        )
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    if isinstance(value, (list, tuple)):
        return "(" + ", ".join(render_value(item) for item in value) + ")"
    raise UnsupportedValue(
        f"unsupported SQL value type {type(value).__name__!r}"
    )


def render_renderable(
    renderable: Renderable[...],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    _stack: tuple[Renderable[...], ...] = (),
    _caller_pool: dict[str, Any] | None = None,
) -> str:
    if renderable in _stack:
        chain = " -> ".join(r.func.__name__ for r in _stack + (renderable,))
        raise CycleDetected(f"cycle detected in clause dependencies: {chain}")

    resolved = _resolve_parameters(renderable, args, kwargs, _caller_pool)

    if _caller_pool is None:
        _caller_pool = {
            name: value
            for name, value in resolved.items()
            if not isinstance(value, Renderable)
        }

    call_kwargs: dict[str, Any] = {}
    for name, value in resolved.items():
        if isinstance(value, Renderable):
            call_kwargs[name] = render_renderable(
                value, (), {}, _stack + (renderable,), _caller_pool
            )
        else:
            try:
                call_kwargs[name] = render_value(value)
            except UnsupportedValue as exc:
                raise UnsupportedValue(
                    f"{exc} for parameter {name!r} of "
                    f"@{renderable.kind} {renderable.func.__name__}"
                ) from exc

    result = renderable.func(**call_kwargs)
    if not isinstance(result, str):
        raise InvalidReturn(
            f"@{renderable.kind} {renderable.func.__name__} must return str, "
            f"got {type(result).__name__}"
        )
    return result


def _resolve_parameters(
    renderable: Renderable[...],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    caller_pool: dict[str, Any] | None,
) -> dict[str, Any]:
    sig = renderable.signature
    bound = sig.bind_partial(*args, **kwargs)
    arguments = dict(bound.arguments)

    shared = shared_values_for(renderable)

    for name, param in sig.parameters.items():
        if name in arguments:
            continue
        if caller_pool is not None and name in caller_pool:
            arguments[name] = caller_pool[name]
            continue
        if isinstance(param.default, Renderable):
            arguments[name] = param.default
            continue
        if name in shared:
            arguments[name] = shared[name]
            continue
        if param.default is not _MISSING:
            arguments[name] = param.default
            continue
        raise MissingParameter(
            f"missing required parameter {name!r} for "
            f"@{renderable.kind} {renderable.func.__name__}"
        )

    return arguments
