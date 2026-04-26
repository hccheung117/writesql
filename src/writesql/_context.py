"""Request-local runtime context for `share()`.

Shared values are stored in a `ContextVar`-backed mapping keyed by renderable
identity. This gives the API its global-looking ergonomics while isolating
bindings per async task or request: `share()` in one context does not leak to
sibling contexts. The store always replaces its value with a fresh dict on
update so the `ContextVar` default mapping is never mutated in place.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Mapping

from ._renderable import Renderable

_shared_context: ContextVar[dict[Renderable[...], dict[str, Any]]] = ContextVar(
    "writesql_shared_context", default={}
)


def share(renderable: Renderable[...], values: Mapping[str, Any]) -> None:
    current = _shared_context.get()
    existing = current.get(renderable, {})
    updated = {renderable: {**existing, **dict(values)}}
    _shared_context.set({**current, **updated})


def shared_values_for(renderable: Renderable[...]) -> dict[str, Any]:
    return _shared_context.get().get(renderable, {})
