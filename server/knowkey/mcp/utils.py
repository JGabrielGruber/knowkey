from functools import wraps
from typing import Any, Callable, Optional

from asgiref.sync import sync_to_async as _sync_to_async


def sync_to_async(thread_sensitive: Optional[bool] = None):
    """
    Decorator factory that wraps a sync function returning an async function
    using asgiref.sync.sync_to_async. Accepts the same thread_sensitive kwarg.
    Usage:
      @sync_to_async()            # default (no thread_sensitive passed)
      @sync_to_async(thread_sensitive=True)
      def my_sync(...): ...
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        # apply asgiref.sync_to_async with the supplied kwarg(s)
        if thread_sensitive is None:
            wrapped = _sync_to_async(func)  # use default behavior
        else:
            wrapped = _sync_to_async(func, thread_sensitive=thread_sensitive)

        # preserve metadata and signature
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await wrapped(*args, **kwargs)

        return async_wrapper

    return decorator
