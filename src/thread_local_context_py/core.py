"""Thread-local request-scoped value carrier.

The problem this solves: request-scoped values (request IDs, auth tokens,
logging metadata) naturally live in a ``threading.local``. But when work is
dispatched to a worker thread or a child task, the worker starts with an empty
local. Copying values implicitly through closures is noisy and easy to forget.

This module provides :class:`ThreadLocalContext`, a small carrier that stores a
flat mapping of string keys to arbitrary values in thread-local storage and can
produce an explicit snapshot of the current thread's mapping. That snapshot can
be handed to another thread, which restores it into its own thread-local slot.

Design decision: propagation is *explicit*. We do not hook into threading or
asyncio to copy context automatically, because automatic propagation silently
leaks values across unrelated tasks and makes ownership of cleanup ambiguous.
The trade-off is one extra line at dispatch time (``snapshot``/``restore``)
in exchange for predictable, inspectable state.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, Mapping, Optional

__all__ = ["ThreadLocalContext"]


class ThreadLocalContext:
    """A carrier for request-scoped values backed by ``threading.local``.

    Each thread that touches the context sees its own independent mapping.
    Values set on one thread are not visible on another until the first thread
    produces a :meth:`snapshot` and the second thread :meth:`restore`\\s it.

    Example::

        ctx = ThreadLocalContext()
        ctx.set("request_id", "abc")
        snap = ctx.snapshot()

        def worker():
            ctx.restore(snap)
            assert ctx.get("request_id") == "abc"

    A snapshot is a plain ``dict`` copy, so later mutations of the source
    thread's context do not affect a snapshot already taken. This is deliberate:
    a child task should see the values as they were at dispatch time, not a
    moving target.
    """

    def __init__(self) -> None:
        # ``threading.local`` gives us one storage slot per thread. We use a
        # single attribute holding a dict rather than one attribute per key,
        # because keys are dynamic and per-attribute storage would require
        # bookkeeping to clear them.
        self._local = threading.local()

    def _store(self) -> Dict[str, Any]:
        """Return this thread's backing dict, creating it on first use.

        ``threading.local`` does not run ``__init__`` per thread, so the dict
        must be created lazily. Using ``getattr`` with a default avoids a
        race-free check-then-set dance: each thread only ever sees its own
        attribute namespace.
        """
        store = getattr(self._local, "data", None)
        if store is None:
            store = {}
            self._local.data = store
        return store

    def set(self, key: str, value: Any) -> None:
        """Store ``value`` under ``key`` for the current thread.

        Overwrites any previous value for the same key.
        """
        self._store()[key] = value

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        """Return the value for ``key`` on the current thread.

        Returns ``default`` when the key is absent. The default is ``None``
        rather than a sentinel so that ``ctx.get(\"k\") is None`` reads
        naturally; callers that need to distinguish a stored ``None`` from an
        absent key should use :meth:`contains`.
        """
        return self._store().get(key, default)

    def contains(self, key: str) -> bool:
        """Return whether ``key`` is present on the current thread.

        This exists so that a stored ``None`` is distinguishable from an
        absent key, which :meth:`get` alone cannot express.
        """
        return key in self._store()

    def remove(self, key: str) -> None:
        """Delete ``key`` from the current thread's mapping.

        Removing an absent key is a no-op, matching ``dict.pop(key, None)``
        semantics and sparing callers a membership check.
        """
        self._store().pop(key, None)

    def clear(self) -> None:
        """Remove every value from the current thread's mapping.

        Other threads are unaffected.
        """
        self._store().clear()

    def snapshot(self) -> Dict[str, Any]:
        """Return a shallow copy of the current thread's mapping.

        The copy is a fresh ``dict``, so mutating it does not touch the live
        context and vice versa. Values themselves are shared by reference;
        deep-copying arbitrary objects would be surprising and expensive.
        """
        return dict(self._store())

    def restore(self, values: Mapping[str, Any]) -> None:
        """Replace the current thread's mapping with a copy of ``values``.

        This is a full replacement, not a merge: after ``restore``, the current
        thread's mapping contains exactly the keys in ``values``. Replacement
        is chosen over merging because a child task should inherit a clean,
        known context rather than accidentally retain values from whatever the
        worker thread did previously.

        An empty mapping is a valid input and clears the context.
        """
        # ``dict(values)`` copies and also normalises any Mapping (including
        # another snapshot) into a plain dict, so later mutation of the caller's
        # object cannot leak in.
        self._local.data = dict(values)

    def as_dict(self) -> Dict[str, Any]:
        """Return a copy of the current thread's mapping.

        Alias-like convenience for inspection and logging. Equivalent to
        :meth:`snapshot`; kept separate so that call sites read as either
        \"hand this to another thread\" or \"show me what is here\".
        """
        return dict(self._store())
