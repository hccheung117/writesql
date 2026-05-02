"""SQL value primitives and render-time parameter resolution.

`render_value` turns a raw Python value into SQL-literal text. `render_renderable`
walks a renderable's signature and resolves each parameter using the order
specified in the design: explicit caller arguments first, then the propagated
top-level caller pool, then clause-dependency defaults declared on the
signature, then shared runtime context bound via `share()`, then ordinary
Python defaults, then a `MissingParameter` error. Value parameters are wrapped
as SQL literals before the user function runs; clause parameters are rendered
recursively into raw SQL fragments; identifier parameters (annotated `Table`
or `Column`) are validated and emitted verbatim. Value parameters render either
literal SQL text or parameter tokens depending on global configuration, and the
top-level render finalizes into `CompiledSQL`. Cycles in clause dependencies are
detected via the render stack.
"""

from __future__ import annotations

from contextvars import ContextVar
import inspect
import re
from dataclasses import dataclass
from typing import Any

from ._context import shared_values_for
from ._errors import (
    ConfigurationError,
    CycleDetected,
    InvalidIdentifier,
    InvalidReturn,
    MissingParameter,
    UnsupportedValue,
)
from ._identifier import Columns, render_identifier
from ._parameterization import (
    CompiledSQL,
    Parameterization,
    Params,
    build_param,
    current_parameterization,
)
from ._renderable import Renderable, RenderableFragment

_MISSING = inspect.Parameter.empty
_TOKEN_RE = re.compile(r"\x00writesql_param_[0-9]+\x00")


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


class _RenderContext:
    def __init__(self, parameterization: Parameterization | None) -> None:
        self.parameterization = parameterization
        self._next_token = 1
        self._tokens: dict[str, tuple[str, Any]] = {}

    def render_value(self, name: str, value: Any) -> str:
        if self.parameterization is None:
            return render_value(value)

        # Validate the whole value before adding any render tokens.
        render_value(value)
        return self._render_tokenized_value(name, value)

    def finalize(self, sql: str) -> CompiledSQL:
        if self.parameterization is None:
            return CompiledSQL(sql)

        params: Params
        if self.parameterization.style == "sequence":
            params = []
        else:
            params = {}

        final_sql_parts: list[str] = []
        debug_sql_parts: list[str] = []
        next_index = 1
        last_end = 0

        for match in _TOKEN_RE.finditer(sql):
            token = match.group(0)
            if token not in self._tokens:
                continue

            literal_text = sql[last_end : match.start()]
            final_sql_parts.append(literal_text)
            debug_sql_parts.append(literal_text)

            name, value = self._tokens[token]
            param = build_param(name, next_index, value)
            placeholder = self.parameterization.placeholder(param)
            if not isinstance(placeholder, str):
                raise ConfigurationError(
                    "parameterization placeholder must return str, "
                    f"got {type(placeholder).__name__} for parameter {name!r} "
                    f"at index {param.index}"
                )

            final_sql_parts.append(placeholder)
            debug_sql_parts.append(render_value(value))
            if self.parameterization.style == "sequence":
                assert isinstance(params, list)
                params.append(value)
            else:
                assert isinstance(params, dict)
                params[param.key] = value
            next_index += 1
            last_end = match.end()

        final_sql_parts.append(sql[last_end:])
        debug_sql_parts.append(sql[last_end:])
        return CompiledSQL(
            "".join(final_sql_parts),
            params=params,
            debug_sql="".join(debug_sql_parts),
        )

    def _render_tokenized_value(self, name: str, value: Any) -> str:
        if isinstance(value, (list, tuple)):
            return (
                "("
                + ", ".join(
                    self._render_tokenized_value(name, item)
                    for item in value
                )
                + ")"
            )
        return self._add_token(name, value)

    def _add_token(self, name: str, value: Any) -> str:
        token = f"\x00writesql_param_{self._next_token}\x00"
        self._next_token += 1
        self._tokens[token] = (name, value)
        return token


@dataclass(frozen=True)
class _ActiveRenderState:
    context: _RenderContext
    stack: tuple[Renderable[...], ...]
    caller_pool: dict[str, Any]


_active_render_state: ContextVar[_ActiveRenderState | None] = ContextVar(
    "writesql_active_render_state", default=None
)


class _RenderableValue:
    def __init__(
        self,
        *,
        name: str,
        value: Any,
        renderable: Renderable[...],
        context: _RenderContext,
    ) -> None:
        self._name = name
        self._value = value
        self._renderable = renderable
        self._context = context

    @property
    def raw_value(self) -> Any:
        return self._value

    def __str__(self) -> str:
        try:
            return self._context.render_value(self._name, self._value)
        except UnsupportedValue as exc:
            raise UnsupportedValue(
                f"{exc} for parameter {self._name!r} of "
                f"@{self._renderable.kind} {self._renderable.func.__name__}"
            ) from exc

    def __format__(self, format_spec: str) -> str:
        return format(str(self), format_spec)


def render_renderable(
    renderable: Renderable[...],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    _stack: tuple[Renderable[...], ...] = (),
    _caller_pool: dict[str, Any] | None = None,
    _columns: dict[str, Any] | None = None,
    _context: _RenderContext | None = None,
) -> CompiledSQL | str:
    if _context is not None:
        return _render_renderable_with_context(
            renderable, args, kwargs, _stack, _caller_pool, _columns, _context
        )

    active_state = _active_render_state.get()
    if active_state is not None:
        return _render_renderable_with_context(
            renderable,
            args,
            kwargs,
            _stack or active_state.stack,
            _caller_pool or active_state.caller_pool,
            _columns,
            active_state.context,
        )

    parameterization = current_parameterization()
    context = _RenderContext(parameterization)
    sql = _render_renderable_with_context(
        renderable, args, kwargs, _stack, _caller_pool, _columns, context
    )
    return context.finalize(sql)


def _render_renderable_with_context(
    renderable: Renderable[...],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    _stack: tuple[Renderable[...], ...],
    _caller_pool: dict[str, Any] | None,
    _columns: dict[str, Any] | None,
    _context: _RenderContext,
) -> str:
    if renderable in _stack:
        chain = " -> ".join(r.func.__name__ for r in _stack + (renderable,))
        raise CycleDetected(f"cycle detected in clause dependencies: {chain}")

    resolved = _resolve_parameters(
        renderable, args, kwargs, _caller_pool, _columns
    )

    if _caller_pool is None:
        _caller_pool = {
            name: value
            for name, value in resolved.items()
            if not isinstance(value, (Renderable, RenderableFragment, Columns))
        }

    call_kwargs: dict[str, Any] = {}
    for name, value in resolved.items():
        if isinstance(value, Renderable):
            call_kwargs[name] = RenderableFragment(
                value,
                stack=_stack + (renderable,),
                caller_pool=_caller_pool,
                context=_context,
            )
        elif isinstance(value, RenderableFragment):
            call_kwargs[name] = RenderableFragment(
                value.renderable,
                value.columns,
                value.stack or _stack + (renderable,),
                value.caller_pool or _caller_pool,
                _context,
            )
        elif name == renderable.columns_param:
            call_kwargs[name] = value
        elif name in renderable.identifier_params:
            try:
                call_kwargs[name] = render_identifier(value)
            except (UnsupportedValue, InvalidIdentifier) as exc:
                raise type(exc)(
                    f"{exc} for parameter {name!r} of "
                    f"@{renderable.kind} {renderable.func.__name__}"
                ) from exc
        else:
            try:
                render_value(value)
            except UnsupportedValue as exc:
                raise UnsupportedValue(
                    f"{exc} for parameter {name!r} of "
                    f"@{renderable.kind} {renderable.func.__name__}"
                ) from exc
            call_kwargs[name] = _RenderableValue(
                name=name,
                value=value,
                renderable=renderable,
                context=_context,
            )

    active_token = _active_render_state.set(
        _ActiveRenderState(
            context=_context,
            stack=_stack + (renderable,),
            caller_pool=_caller_pool,
        )
    )
    try:
        result = renderable.func(**call_kwargs)
    finally:
        _active_render_state.reset(active_token)
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
    columns: dict[str, Any] | None,
) -> dict[str, Any]:
    sig = renderable.signature
    bound = sig.bind_partial(*args, **kwargs)
    arguments = {
        name: _unwrap_render_value(value)
        for name, value in bound.arguments.items()
    }

    shared = shared_values_for(renderable)

    for name, param in sig.parameters.items():
        if name == renderable.columns_param:
            if name in arguments:
                continue
            if columns is None:
                raise MissingParameter(
                    "missing column mapping for "
                    f"@{renderable.kind} {renderable.func.__name__}; "
                    "call .on(...) at the clause interpolation site"
                )
            arguments[name] = Columns(columns, renderable.func.__name__)
            continue
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


def _unwrap_render_value(value: Any) -> Any:
    if isinstance(value, _RenderableValue):
        return value.raw_value
    if isinstance(value, list):
        return [_unwrap_render_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_unwrap_render_value(item) for item in value)
    return value
