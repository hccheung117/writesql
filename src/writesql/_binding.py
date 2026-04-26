"""Call binding and value-vs-clause parameter classification.

`bind_and_classify` maps caller-supplied positional and keyword arguments to
the renderable's named parameters (applying defaults for omissions) and tags
each bound parameter as either a value parameter (raw Python data destined
for SQL-literal rendering) or a clause parameter (a `Renderable` to be
rendered recursively).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from ._renderable import Renderable

ParamKind = Literal["value", "clause"]


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
        kind: ParamKind = "clause" if isinstance(value, Renderable) else "value"
        classified[name] = BoundParameter(name=name, kind=kind, value=value)
    return classified
