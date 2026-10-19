"""Phone alert channels. Importing this package registers all built-in channels."""

from ringbridge.channels.base import CHANNELS, Channel, Outcome, register
from ringbridge.channels import callmebot, ntfy, pushover, sip  # noqa: F401  (registration)

__all__ = ["CHANNELS", "Channel", "Outcome", "register"]
