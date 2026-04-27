"""Call binding and value-vs-clause-vs-identifier parameter classification.

`bind_and_classify` maps caller-supplied positional and keyword arguments to
the renderable's named parameters (applying defaults for omissions) and tags
each bound parameter as a value parameter (raw Python data destined for
SQL-literal rendering), a clause parameter (a `Renderable` to be rendered
recursively), or an identifier parameter (annotated `Table`/`Column`,
validated and emitted verbatim).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from ._renderable import Renderable

ParamKind = Literal["value", "clause", "identifier"]


@dataclass(frozen=True)
class BoundParameter:
    name: str
    kind: ParamKind
    value: Any


def bind_and_classify(
    renderable: Renderable[...], *args: Any, **kwargs: Any
) -> dict[str, BoundParameter]:
    bound = renderable.signature.bind(*args, **kwargs)
    bound.apply_defaults()

    classified: dict[str, BoundParameter] = {}
    for name, value in bound.arguments.items():
        kind: ParamKind
        if isinstance(value, Renderable):
            kind = "clause"
        elif name in renderable.identifier_params:
            kind = "identifier"
        else:
            kind = "value"
        classified[name] = BoundParameter(name=name, kind=kind, value=value)
    return classified
