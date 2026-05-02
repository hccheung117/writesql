"""Parameterization configuration and compiled SQL primitives."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from ._errors import ConfigurationError

ParameterizationStyle = Literal["sequence", "mapping"]
Params = list[Any] | dict[str, Any]


@dataclass(frozen=True)
class Param:
    name: str
    index: int
    key: str
    value: Any


@dataclass(frozen=True)
class Parameterization:
    style: ParameterizationStyle
    placeholder: Callable[[Param], str]


_parameterization: Parameterization | None = None


def parameterize(
    style: ParameterizationStyle,
    placeholder: Callable[[Param], str],
) -> None:
    global _parameterization

    if style not in ("sequence", "mapping"):
        raise ConfigurationError(
            "parameterization style must be 'sequence' or 'mapping'"
        )
    if not callable(placeholder):
        raise ConfigurationError("parameterization placeholder must be callable")

    _parameterization = Parameterization(style=style, placeholder=placeholder)


def current_parameterization() -> Parameterization | None:
    return _parameterization


def _reset_parameterization() -> None:
    global _parameterization

    _parameterization = None


def build_param(name: str, index: int, value: Any) -> Param:
    return Param(
        name=name,
        index=index,
        key=f"{name}_{index}",
        value=value,
    )


def render_placeholder(name: str, index: int, value: Any) -> str:
    config = current_parameterization()
    if config is None:
        raise ConfigurationError("parameterization is not configured")

    param = build_param(name, index, value)
    placeholder = config.placeholder(param)
    if not isinstance(placeholder, str):
        raise ConfigurationError(
            "parameterization placeholder must return str, "
            f"got {type(placeholder).__name__}"
        )
    return placeholder


class CompiledSQL(str):
    params: Params
    debug_sql: str

    def __new__(
        cls,
        sql: str,
        *,
        params: Params | None = None,
        debug_sql: str | None = None,
    ) -> "CompiledSQL":
        compiled = super().__new__(cls, sql)
        compiled.params = [] if params is None else params
        compiled.debug_sql = sql if debug_sql is None else debug_sql
        return compiled
