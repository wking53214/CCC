"""The permission check an application can put in front of CCC's record-creating methods.

CCC is independent: it imports nothing from CNS and names no repository. This module is the whole of what CCC
offers an application that wants a decision made elsewhere to stand between a caller and a new record. The
application hands ``CCCSystem`` a callable (``write_permission``). Before ``ingest``, ``record``, ``derive``,
``infer`` or ``interpret`` does anything, CCC calls it once with a :class:`WriteRequest` and goes on only if the
answer is exactly ``True``.

WHAT THE CHECK SEES

A :class:`WriteRequest` says which method was called (``operation``) and carries the caller's own arguments
(``args`` and ``kwargs``), exactly as given, with no defaults filled in. They are a deep copy, so a check cannot
change what is about to be written by changing the request. If the arguments cannot be copied, the call is refused.

WHAT COUNTS AS A NO

Anything other than the value ``True``: ``False``, ``None``, a truthy object, an exception from the check, a
request that cannot be built. A no raises :class:`ccc.errors.WritePermissionRefused` before CCC touches its store,
its rules or its audit trail, so a refused call leaves every one of them as it was.

WHAT IS NOT GATED

Only the five methods above ask. Recording a human decision (``decide``), making a corrected, amended or
superseding version, accepting, rejecting, classifying, redacting and erasing do not, so a human's action is never
held up by a machine's roster. The methods that do ask call each other (``interpret`` calls ``derive``, which
creates the record); the permission is asked once, at the public call, never again beneath it.

WHAT THIS DOES NOT DO

A system built without a check is not stopped, and nothing here can see that. The check is given to the
constructor and is not saved with the store, so a system reloaded or copied from a snapshot has none unless it is
given one again.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Mapping

__all__ = ["WriteRequest", "WritePermission", "build_request"]


@dataclass(frozen=True)
class WriteRequest:
    """One call a permission check is asked about: the method and the caller's arguments."""

    operation: str
    args: tuple[Any, ...] = ()
    kwargs: Mapping[str, Any] = field(default_factory=dict)


#: A permission check: gets the request, permits only by returning exactly ``True``.
WritePermission = Callable[[WriteRequest], bool]


def build_request(operation: str, args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> WriteRequest:
    """A request holding deep copies of the caller's arguments. Raises ``TypeError`` if they cannot be copied."""
    try:
        return WriteRequest(
            operation=operation,
            args=copy.deepcopy(tuple(args)),
            kwargs=MappingProxyType(copy.deepcopy(dict(kwargs))),
        )
    except Exception as exc:
        raise TypeError(f"cannot copy the arguments of {operation}: {exc}") from exc
