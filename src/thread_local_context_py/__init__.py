"""Package init for thread_local_context_py.

Only the public API is re-exported here so that users can write
``from thread_local_context_py import ThreadLocalContext`` without
reaching into the implementation module.
"""

from .core import ThreadLocalContext

__all__ = ["ThreadLocalContext"]
