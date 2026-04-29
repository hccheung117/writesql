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
from dataclasses import dataclass
from typing import Any, Callable, Generic, Literal, Mapping, ParamSpec

Kind = Literal["statement", "clause"]
P = ParamSpec("P")


class Renderable(Generic[P]):
    def __init__(self, func: Callable[P, str], kind: Kind) -> None:
        from ._identifier import Column, Columns, Table

        self.func: Callable[P, str] = func
        self.kind: Kind = kind
        # Combine function's globals with locally imported identifier types
        # so eval_str=True can resolve annotations like Table and Column
        eval_globals = {
            **func.__globals__,
            "Table": Table,
            "Column": Column,
            "Columns": Columns,
        }
        self.signature: inspect.Signature = inspect.signature(
            func, eval_str=True, globals=eval_globals
        )
        columns_params = [
            name
            for name, param in self.signature.parameters.items()
            if param.annotation is Columns
        ]
        if len(columns_params) > 1:
            raise TypeError(
                f"@{kind} {func.__name__} may declare at most one "
                "Columns parameter"
            )
        self.columns_param: str | None = (
            columns_params[0] if columns_params else None
        )
        self.clause_dependencies: dict[str, "Renderable[...]"] = {
            name: param.default
            for name, param in self.signature.parameters.items()
            if isinstance(param.default, Renderable)
        }
        self.identifier_params: frozenset[str] = frozenset(
            name
            for name, param in self.signature.parameters.items()
            if param.annotation is Table or param.annotation is Column
        )
        update_wrapper(self, func)

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> str:
        from ._render import render_renderable

        return render_renderable(self, args, kwargs)

    def on(self, **columns: Any) -> "RenderableFragment":
        if self.kind != "clause":
            raise TypeError(".on() is only supported for @clause renderables")
        return RenderableFragment(self).on(**columns)

    def __repr__(self) -> str:
        return f"<Renderable {self.kind} {self.func.__name__}>"


@dataclass(frozen=True)
class RenderableFragment:
    renderable: Renderable[...]
    columns: Mapping[str, Any] | None = None
    stack: tuple[Renderable[...], ...] = ()
    caller_pool: Mapping[str, Any] | None = None

    def on(self, **columns: Any) -> "RenderableFragment":
        if self.renderable.kind != "clause":
            raise TypeError(".on() is only supported for @clause renderables")
        return RenderableFragment(
            self.renderable,
            dict(columns),
            self.stack,
            self.caller_pool,
        )

    def __str__(self) -> str:
        from ._render import render_renderable

        caller_pool = (
            None if self.caller_pool is None else dict(self.caller_pool)
        )
        return render_renderable(
            self.renderable,
            (),
            {},
            self.stack,
            caller_pool,
            dict(self.columns) if self.columns is not None else None,
        )

    def __format__(self, format_spec: str) -> str:
        return format(str(self), format_spec)

    def __call__(self, *args: Any, **kwargs: Any) -> str:
        from ._render import render_renderable

        caller_pool = (
            None if self.caller_pool is None else dict(self.caller_pool)
        )
        return render_renderable(
            self.renderable,
            args,
            kwargs,
            self.stack,
            caller_pool,
            dict(self.columns) if self.columns is not None else None,
        )


def statement(func: Callable[P, str]) -> Renderable[P]:
    return Renderable(func, "statement")


def clause(func: Callable[P, str]) -> Renderable[P]:
    return Renderable(func, "clause")
