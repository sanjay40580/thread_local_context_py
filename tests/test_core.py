"""Tests for thread_local_context_py.

Run with::

    PYTHONPATH=src python -m unittest discover -s tests

The tests avoid wall-clock time and sleeps entirely. Thread coordination uses
``threading.Event`` and ``join`` with an explicit timeout, and every assertion
is on data the test itself placed in the context.
"""

import threading
import unittest

from thread_local_context_py import ThreadLocalContext


class TestBasicOperations(unittest.TestCase):
    def test_set_and_get(self) -> None:
        ctx = ThreadLocalContext()
        ctx.set("request_id", "abc")
        self.assertEqual(ctx.get("request_id"), "abc")

    def test_get_missing_returns_default(self) -> None:
        ctx = ThreadLocalContext()
        self.assertIsNone(ctx.get("nope"))
        self.assertEqual(ctx.get("nope", 7), 7)

    def test_stored_none_is_distinguishable_from_absent(self) -> None:
        ctx = ThreadLocalContext()
        ctx.set("k", None)
        self.assertTrue(ctx.contains("k"))
        self.assertIsNone(ctx.get("k"))
        self.assertFalse(ctx.contains("other"))

    def test_overwrite(self) -> None:
        ctx = ThreadLocalContext()
        ctx.set("k", 1)
        ctx.set("k", 2)
        self.assertEqual(ctx.get("k"), 2)

    def test_remove(self) -> None:
        ctx = ThreadLocalContext()
        ctx.set("k", 1)
        ctx.remove("k")
        self.assertFalse(ctx.contains("k"))
        # Removing an absent key must not raise.
        ctx.remove("k")

    def test_clear(self) -> None:
        ctx = ThreadLocalContext()
        ctx.set("a", 1)
        ctx.set("b", 2)
        ctx.clear()
        self.assertEqual(ctx.as_dict(), {})


class TestSnapshotRestore(unittest.TestCase):
    def test_snapshot_is_a_copy(self) -> None:
        ctx = ThreadLocalContext()
        ctx.set("k", "v")
        snap = ctx.snapshot()
        self.assertEqual(snap, {"k": "v"})
        # Mutating the snapshot must not affect the live context.
        snap["k"] = "changed"
        self.assertEqual(ctx.get("k"), "v")

    def test_snapshot_reflects_later_changes_independently(self) -> None:
        ctx = ThreadLocalContext()
        ctx.set("k", "v")
        snap = ctx.snapshot()
        ctx.set("k", "later")
        self.assertEqual(snap, {"k": "v"})
        self.assertEqual(ctx.get("k"), "later")

    def test_restore_replaces_not_merges(self) -> None:
        ctx = ThreadLocalContext()
        ctx.set("stale", "old")
        ctx.restore({"fresh": "new"})
        self.assertFalse(ctx.contains("stale"))
        self.assertEqual(ctx.get("fresh"), "new")

    def test_restore_empty_clears(self) -> None:
        ctx = ThreadLocalContext()
        ctx.set("k", "v")
        ctx.restore({})
        self.assertEqual(ctx.as_dict(), {})

    def test_restore_copies_input(self) -> None:
        ctx = ThreadLocalContext()
        source = {"k": "v"}
        ctx.restore(source)
        source["k"] = "mutated"
        self.assertEqual(ctx.get("k"), "v")

    def test_as_dict_matches_snapshot(self) -> None:
        ctx = ThreadLocalContext()
        ctx.set("a", 1)
        ctx.set("b", 2)
        self.assertEqual(ctx.as_dict(), ctx.snapshot())


class TestThreadIsolation(unittest.TestCase):
    def test_values_do_not_leak_between_threads(self) -> None:
        ctx = ThreadLocalContext()
        ctx.set("k", "main")
        observed: dict = {}
        done = threading.Event()

        def worker() -> None:
            observed["value"] = ctx.get("k", "missing")
            observed["contains"] = ctx.contains("k")
            done.set()

        t = threading.Thread(target=worker)
        t.start()
        self.assertTrue(done.wait(timeout=5.0))
        t.join(timeout=5.0)
        self.assertFalse(t.is_alive())
        self.assertEqual(observed["value"], "missing")
        self.assertFalse(observed["contains"])
        # Main thread is untouched by the worker.
        self.assertEqual(ctx.get("k"), "main")

    def test_worker_writes_do_not_affect_main(self) -> None:
        ctx = ThreadLocalContext()
        done = threading.Event()

        def worker() -> None:
            ctx.set("k", "worker")
            done.set()

        t = threading.Thread(target=worker)
        t.start()
        self.assertTrue(done.wait(timeout=5.0))
        t.join(timeout=5.0)
        self.assertFalse(ctx.contains("k"))

    def test_restore_propagates_snapshot_to_worker(self) -> None:
        ctx = ThreadLocalContext()
        ctx.set("request_id", "abc")
        ctx.set("user", "alice")
        snap = ctx.snapshot()
        observed: dict = {}
        done = threading.Event()

        def worker() -> None:
            ctx.restore(snap)
            observed["request_id"] = ctx.get("request_id")
            observed["user"] = ctx.get("user")
            done.set()

        t = threading.Thread(target=worker)
        t.start()
        self.assertTrue(done.wait(timeout=5.0))
        t.join(timeout=5.0)
        self.assertFalse(t.is_alive())
        self.assertEqual(observed["request_id"], "abc")
        self.assertEqual(observed["user"], "alice")

    def test_worker_restore_does_not_touch_main(self) -> None:
        ctx = ThreadLocalContext()
        ctx.set("k", "main")
        done = threading.Event()

        def worker() -> None:
            ctx.restore({"k": "worker"})
            done.set()

        t = threading.Thread(target=worker)
        t.start()
        self.assertTrue(done.wait(timeout=5.0))
        t.join(timeout=5.0)
        self.assertEqual(ctx.get("k"), "main")


class TestSeparateInstances(unittest.TestCase):
    def test_instances_are_independent(self) -> None:
        a = ThreadLocalContext()
        b = ThreadLocalContext()
        a.set("k", "a")
        b.set("k", "b")
        self.assertEqual(a.get("k"), "a")
        self.assertEqual(b.get("k"), "b")


if __name__ == "__main__":
    unittest.main()
