"""WriteSQL public API.

Exports the v0.0 PoC surface: `statement`, `clause`, `share`, the identifier
markers `Table` and `Column`, and the `InvalidIdentifier` error. Internal
machinery (renderable units, value primitives, runtime context) lives in
underscore-prefixed modules and is not part of the public contract.
"""

from __future__ import annotations

from ._context import share
from ._errors import InvalidIdentifier
from ._identifier import Column, Table
from ._renderable import clause, statement

__all__ = [
    "statement",
    "clause",
    "share",
    "Table",
    "Column",
    "InvalidIdentifier",
]
