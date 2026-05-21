import json
import re
from functools import wraps
from typing import Any, Callable, Optional

from asgiref.sync import async_to_sync as _async_to_sync
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


def async_to_sync():
    """
    Decorator factory that wraps an async function returning a sync function
    using asgiref.sync.async_to_sync. Accepts the same `timeout` kwarg.
    Usage:
      @async_to_sync()               # default (no timeout passed)
      @async_to_sync(timeout=5.0)
      async def my_async(...): ...
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        # apply asgiref.async_to_sync with the supplied kwarg(s)
        wrapped = _async_to_sync(func)  # use default behavior

        # preserve metadata and signature
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            return wrapped(*args, **kwargs)

        return sync_wrapper

    return decorator


def clean_string_value(value: Any) -> Any:
    """Remove common LLM quoting mistakes from string values."""
    if not isinstance(value, str):
        return value

    # Remove outer quotes if the whole string is wrapped
    # e.g. "\"actual-value\"" → "actual-value"
    value = value.strip()

    # Remove leading and trailing escaped quotes
    if value.startswith('"') and value.endswith('"') and len(value) > 1:
        value = value[1:-1].strip()
    if value.startswith("'") and value.endswith("'") and len(value) > 1:
        value = value[1:-1].strip()

    # Fix double-escaped quotes inside
    value = value.replace('\\"', '"').replace("\\'", "'")

    return value


def clean_inputs(func: Callable) -> Callable:
    """
    Decorator to clean JSON inputs coming from LLMs.
    Should be used on tools that receive `data`, `goal`, `session_id`, etc.
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Clean common top-level fields
        for key in ["goal", "session_id", "action"]:
            if key in kwargs and isinstance(kwargs[key], str):
                kwargs[key] = clean_string_value(kwargs[key])

        # Deep clean the `data` dict (most common source of issues)
        if "data" in kwargs and isinstance(kwargs["data"], dict):
            kwargs["data"] = _clean_dict_recursively(kwargs["data"])

        return await func(*args, **kwargs)

    return wrapper


def _clean_dict_recursively(d: dict) -> dict:
    """Recursively clean all string values in a dict (including nested)."""
    cleaned = {}
    for k, v in d.items():
        if isinstance(v, str):
            cleaned[k] = clean_string_value(v)
        elif isinstance(v, dict):
            cleaned[k] = _clean_dict_recursively(v)
        elif isinstance(v, list):
            cleaned[k] = [_clean_value_recursively(item) for item in v]
        else:
            cleaned[k] = v
    return cleaned


def _clean_value_recursively(value: Any) -> Any:
    if isinstance(value, str):
        return clean_string_value(value)
    elif isinstance(value, dict):
        return _clean_dict_recursively(value)
    elif isinstance(value, list):
        return [_clean_value_recursively(item) for item in value]
    return value
