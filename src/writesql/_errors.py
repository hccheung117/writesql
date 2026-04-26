"""WriteSQL exception hierarchy.

All errors raised by the rendering pipeline derive from `WriteSQLError`.
Specific errors also derive from the matching standard exception so callers
that catch broad `TypeError`/`RuntimeError` still see the failure.
"""

from __future__ import annotations


class WriteSQLError(Exception):
    pass


class MissingParameter(WriteSQLError, TypeError):
    pass


class UnsupportedValue(WriteSQLError, TypeError):
    pass


class InvalidReturn(WriteSQLError, TypeError):
    pass


class CycleDetected(WriteSQLError, RuntimeError):
    pass
