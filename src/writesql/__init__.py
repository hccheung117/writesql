"""WriteSQL public API.

Exports decorators, runtime configuration helpers, identifier markers, and
public errors. Internal machinery lives in underscore-prefixed modules and is
not part of the public contract.
"""

from __future__ import annotations

from ._context import share
from ._errors import ConfigurationError, InvalidIdentifier
from ._identifier import Column, Columns, Table
from ._parameterization import CompiledSQL, Param, parameterize
from ._renderable import clause, statement

__all__ = [
    "statement",
    "clause",
    "share",
    "parameterize",
    "Param",
    "CompiledSQL",
    "Table",
    "Column",
    "Columns",
    "ConfigurationError",
    "InvalidIdentifier",
]
