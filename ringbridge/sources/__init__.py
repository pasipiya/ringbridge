"""Message sources. Importing this package registers all built-in sources."""

from ringbridge.sources.base import SOURCES, Source, register
from ringbridge.sources import desktop, webhook  # noqa: F401  (registration)

__all__ = ["SOURCES", "Source", "register"]
