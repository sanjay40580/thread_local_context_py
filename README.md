# thread_local_context_py

A carrier object that stores request-scoped values in `threading.local` and propagates them to other threads through explicit snapshots.

## Usage

```python
from thread_local_context_py import ThreadLocalContext

ctx = ThreadLocalContext()
ctx.set("request_id", "abc")
ctx.set("user", "alice")

snap = ctx.snapshot()

def worker():
    ctx.restore(snap)
    print(ctx.get("request_id"))  # abc
```

The public API is exactly one class:

- `ThreadLocalContext()`
  - `set(key, value)` — store a value on the current thread.
  - `get(key, default=None)` — read a value; returns `default` if absent.
  - `contains(key)` — `True` if the key is present, so a stored `None` is distinguishable from a missing key.
  - `remove(key)` — delete a key; no-op if absent.
  - `clear()` — drop every value on the current thread.
  - `snapshot()` — return a fresh `dict` copy of the current thread's values.
  - `restore(mapping)` — replace the current thread's values with a copy of `mapping`.
  - `as_dict()` — copy of the current thread's values, for logging or inspection.

## Why this exists

Request-scoped values (request IDs, auth tokens, log metadata) fit naturally in a `threading.local`. The trouble starts when work is handed to a worker thread: the worker begins with an empty local, and the usual workarounds — passing a context object through every call signature, or capturing values in a closure — are noisy and easy to forget.

`ThreadLocalContext` makes propagation explicit. A thread takes a `snapshot()` and hands it to the worker, which calls `restore()`. The library deliberately does *not* hook into `threading` or `asyncio` to copy context automatically. Automatic propagation silently leaks values into unrelated tasks and makes it unclear who owns cleanup. The trade-off is one extra line at dispatch time in exchange for state that is predictable and inspectable.

## The edge worth knowing

`restore()` **replaces** the current thread's mapping; it does not merge. A worker that has already set its own values will lose them when it restores a snapshot. This is intentional — a child task should inherit a clean, known context rather than accidentally retain values from whatever the worker thread did previously — but it is the behaviour most likely to surprise someone coming from a merge-based implementation. If you need to combine, snapshot first and merge the dicts yourself before calling `restore()`.

Snapshots are shallow: values are shared by reference, not deep-copied. Deep-copying arbitrary objects would be both surprising and expensive, so the library leaves that decision to the caller.
