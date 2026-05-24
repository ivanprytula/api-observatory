"""Rate limiting configuration using slowapi."""

from slowapi import Limiter
from slowapi.util import get_remote_address


# Create a single limiter instance (imported everywhere needed)
limiter = Limiter(key_func=get_remote_address)


__all__ = ["limiter"]
