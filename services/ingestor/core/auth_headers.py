"""Outbound auth header builder for source probes."""

import base64


def build_auth_headers(
    auth_type: str,
    api_key: str | None,
    auth_header_name: str,
    auth_username: str | None,
) -> dict[str, str]:
    """Build outbound auth headers from a source profile's auth config."""
    if auth_type == "none" or not api_key:
        return {}
    if auth_type == "bearer":
        return {"Authorization": f"Bearer {api_key}"}
    if auth_type == "header":
        return {auth_header_name: api_key}
    if auth_type == "basic":
        username = auth_username or ""
        credentials = base64.b64encode(f"{username}:{api_key}".encode()).decode()
        return {"Authorization": f"Basic {credentials}"}
    return {}
