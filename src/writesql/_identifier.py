"""SQL identifier markers and rendering.

`Table` and `Column` are `NewType`s over `str` used as parameter annotations
to signal that a parameter is a SQL identifier (a schema, table, or column
name) rather than a SQL value. The renderer detects these annotations and
emits the value verbatim after strict validation, since DB drivers cannot
parameter-bind identifier positions and they are the highest-risk injection
surface in a dynamic query.

`Columns` is a render-time namespace for reusable clauses whose physical
column identifiers are supplied by the statement at the interpolation site.
"""

from __future__ import annotations

import re
from typing import Any, NewType

from ._errors import InvalidIdentifier, MissingParameter, UnsupportedValue

Table = NewType("Table", str)
Column = NewType("Column", str)

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


def render_identifier(value: Any) -> str:
    if not isinstance(value, str):
        raise UnsupportedValue(
            f"identifier must be str, got {type(value).__name__!r}"
        )
    if not _IDENT_RE.match(value):
        raise InvalidIdentifier(
            f"invalid SQL identifier {value!r}; "
            "expected a name matching "
            "[A-Za-z_][A-Za-z0-9_]* with optional dotted segments"
        )
    return value


class Columns:
    """Validated SQL identifier namespace for mapped clause columns."""

    def __init__(self, columns: dict[str, Any], clause_name: str) -> None:
        self._clause_name = clause_name
        self._columns: dict[str, str] = {}
        for name, value in columns.items():
            try:
                self._columns[name] = render_identifier(value)
            except (UnsupportedValue, InvalidIdentifier) as exc:
                raise type(exc)(
                    f"{exc} for column mapping {name!r} of @clause {clause_name}"
                ) from exc

    def __getattr__(self, name: str) -> str:
        try:
            return self._columns[name]
        except KeyError as exc:
            raise MissingParameter(
                f"missing column mapping {name!r} for @clause {self._clause_name}"
            ) from exc
