"""Renderable unit wrapper for decorated functions.

A `Renderable` records everything the rendering pipeline needs about a
decorated function: the original callable, whether it is a statement or
clause, its signature, and which default parameters point to other
renderables (clause dependencies). The class is generic over the wrapped
function's parameter spec so editor tooling preserves call-site autocomplete:
`@statement def get_orders(start_date: str) -> str` becomes a value whose
`__call__` accepts `(start_date: str)` and returns `str`.
"""

from __future__ import annotations

import inspect
from functools import update_wrapper
from typing import Any, Callable, Generic, Literal, ParamSpec

Kind = Literal["statement", "clause"]
P = ParamSpec("P")


class Renderable(Generic[P]):
    def __init__(self, func: Callable[P, str], kind: Kind) -> None:
        self.func: Callable[P, str] = func
        self.kind: Kind = kind
        self.signature: inspect.Signature = inspect.signature(func)
        self.clause_dependencies: dict[str, "Renderable[...]"] = {
            name: param.default
            for name, param in self.signature.parameters.items()
            if isinstance(param.default, Renderable)
        }
        update_wrapper(self, func)

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> str:
        from ._render import render_renderable

        return render_renderable(self, args, kwargs)

    def __repr__(self) -> str:
        return f"<Renderable {self.kind} {self.func.__name__}>"


def statement(func: Callable[P, str]) -> Renderable[P]:
    return Renderable(func, "statement")


def clause(func: Callable[P, str]) -> Renderable[P]:
    return Renderable(func, "clause")
