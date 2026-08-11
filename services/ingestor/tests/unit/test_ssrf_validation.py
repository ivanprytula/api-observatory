"""Unit tests for SSRF validation in source_registry.

Covers:
- Scheme rejection (file://, gopher://, dict://, http)
- Domain allow-list enforcement (when configured)
- Port restriction (non-443 rejection)
- Private/loopback/link-local/multicast IP rejection
- DNS rebinding: validation called again at request time catches IPs that
  were public at registration but private at probe time
"""

from __future__ import annotations

import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.ingestor.config import Settings
from services.ingestor.repositories import source_registry as sr


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# DNS resolution mocks
# ---------------------------------------------------------------------------
def _make_dns_result(ip: str, port: int = 443) -> list[tuple]:
    return [
        (socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, port)),
    ]


@pytest.fixture
def settings_no_allowlist():
    """Settings with no domain allow-list (allows all external domains)."""
    s = Settings(
        environment="testing",
        jwt_secret="test-secret-key-32-chars-minimum!!",
        ssrf_allowed_domains=None,
        ssrf_strict_ports=True,
    )
    with patch.object(sr, "settings", s):
        yield s


@pytest.fixture
def settings_with_allowlist():
    """Settings with a configured domain allow-list."""
    s = Settings(
        environment="testing",
        jwt_secret="test-secret-key-32-chars-minimum!!",
        ssrf_allowed_domains="api.example.com,health.check.io",
        ssrf_strict_ports=True,
    )
    with patch.object(sr, "settings", s):
        yield s


@pytest.fixture
def settings_loose_ports():
    """Settings with strict_ports disabled (any port allowed)."""
    s = Settings(
        environment="testing",
        jwt_secret="test-secret-key-32-chars-minimum!!",
        ssrf_allowed_domains=None,
        ssrf_strict_ports=False,
    )
    with patch.object(sr, "settings", s):
        yield s


# ---------------------------------------------------------------------------
# Scheme validation
# ---------------------------------------------------------------------------
class TestSchemeValidation:
    """Dangerous protocols (file://, gopher://, dict://) and bare HTTP are rejected."""

    async def test_file_scheme_rejected(self, settings_no_allowlist) -> None:
        with pytest.raises(ValueError, match="https"):
            await sr.validate_source_base_url("file:///etc/passwd")

    async def test_gopher_scheme_rejected(self, settings_no_allowlist) -> None:
        with pytest.raises(ValueError, match="https"):
            await sr.validate_source_base_url("gopher://127.0.0.1:6379/x")

    async def test_dict_scheme_rejected(self, settings_no_allowlist) -> None:
        with pytest.raises(ValueError, match="https"):
            await sr.validate_source_base_url("dict://127.0.0.1:11211/stats")

    async def test_ftp_scheme_rejected(self, settings_no_allowlist) -> None:
        with pytest.raises(ValueError, match="https"):
            await sr.validate_source_base_url("ftp://example.com/file")

    async def test_http_rejected_by_default(self, settings_no_allowlist) -> None:
        with pytest.raises(ValueError, match="https"):
            await sr.validate_source_base_url("http://example.com")

    async def test_http_allowed_when_allow_http_true(self) -> None:
        s = Settings(
            environment="testing",
            jwt_secret="test-secret-key-32-chars-minimum!!",
            ssrf_allowed_domains=None,
            ssrf_strict_ports=False,
        )
        with (
            patch.object(sr, "settings", s),
            patch("asyncio.get_running_loop") as mock_loop,
        ):
            mock_loop.return_value.getaddrinfo = AsyncMock(
                return_value=_make_dns_result("1.1.1.1", 80)
            )
            await sr.validate_source_base_url("http://example.com", allow_http=True)

    async def test_https_accepted(self, settings_no_allowlist) -> None:
        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.getaddrinfo = AsyncMock(
                return_value=_make_dns_result("1.1.1.1")
            )
            await sr.validate_source_base_url("https://example.com")


# ---------------------------------------------------------------------------
# Domain allow-list enforcement
# ---------------------------------------------------------------------------
class TestDomainAllowList:
    """When ssrf_allowed_domains is set, only listed hostnames are accepted."""

    async def test_allowed_domain_accepted(self, settings_with_allowlist) -> None:
        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.getaddrinfo = AsyncMock(
                return_value=_make_dns_result("1.1.1.1")
            )
            await sr.validate_source_base_url("https://api.example.com/health")

    async def test_unlisted_domain_rejected(self, settings_with_allowlist) -> None:
        with pytest.raises(ValueError, match="allow-list"):
            await sr.validate_source_base_url("https://evil.attacker.com")

    async def test_localhost_rejected_by_allowlist(
        self, settings_with_allowlist
    ) -> None:
        with pytest.raises(ValueError, match="allow-list"):
            await sr.validate_source_base_url("https://localhost")

    async def test_no_allowlist_allows_any_domain(self, settings_no_allowlist) -> None:
        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.getaddrinfo = AsyncMock(
                return_value=_make_dns_result("1.1.1.1")
            )
            await sr.validate_source_base_url("https://any-external.com")


# ---------------------------------------------------------------------------
# Port restriction
# ---------------------------------------------------------------------------
class TestPortRestriction:
    """When ssrf_strict_ports=True, only port 443 is allowed for HTTPS."""

    async def test_non_standard_https_port_rejected(
        self, settings_no_allowlist
    ) -> None:
        with pytest.raises(ValueError, match="port 443"):
            await sr.validate_source_base_url("https://example.com:8080")

    async def test_port_443_explicit_accepted(self, settings_no_allowlist) -> None:
        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.getaddrinfo = AsyncMock(
                return_value=_make_dns_result("1.1.1.1", 443)
            )
            await sr.validate_source_base_url("https://example.com:443")

    async def test_default_port_accepted(self, settings_no_allowlist) -> None:
        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.getaddrinfo = AsyncMock(
                return_value=_make_dns_result("1.1.1.1")
            )
            await sr.validate_source_base_url("https://example.com")

    async def test_non_standard_port_allowed_when_not_strict(
        self, settings_loose_ports
    ) -> None:
        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.getaddrinfo = AsyncMock(
                return_value=_make_dns_result("1.1.1.1", 8080)
            )
            await sr.validate_source_base_url("https://example.com:8080")

    async def test_redis_port_6379_rejected(self, settings_no_allowlist) -> None:
        """Redis port on an HTTPS URL must be rejected."""
        with pytest.raises(ValueError, match="port 443"):
            await sr.validate_source_base_url("https://evil.com:6379")


# ---------------------------------------------------------------------------
# Private / local IP rejection
# ---------------------------------------------------------------------------
class TestPrivateIPRejection:
    """Resolved IPs in private ranges are rejected."""

    @pytest.mark.parametrize(
        "ip,reason",
        [
            ("127.0.0.1", "loopback"),
            ("127.1.2.3", "loopback"),
            ("10.0.0.1", "private"),
            ("10.255.255.255", "private"),
            ("172.16.0.1", "private"),
            ("172.31.255.255", "private"),
            ("192.168.1.1", "private"),
            ("169.254.169.254", "link-local"),
            ("169.254.1.1", "link-local"),
            ("0.0.0.0", "unspecified"),
            ("224.0.0.1", "multicast"),
            ("255.255.255.255", "reserved"),
            ("::1", "loopback"),
            ("fc00::1", "private"),
            ("fe80::1", "link-local"),
        ],
    )
    async def test_forbidden_ip_rejected(
        self, ip, reason, settings_no_allowlist
    ) -> None:
        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.getaddrinfo = AsyncMock(
                return_value=_make_dns_result(ip)
            )
            with pytest.raises(ValueError, match="private or local"):
                await sr.validate_source_base_url("https://example.com")

    async def test_public_ip_accepted(self, settings_no_allowlist) -> None:
        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.getaddrinfo = AsyncMock(
                return_value=_make_dns_result("1.1.1.1")
            )
            await sr.validate_source_base_url("https://example.com")


# ---------------------------------------------------------------------------
# DNS rebinding / TOCTOU
# ---------------------------------------------------------------------------
class TestDNSTOBAT:
    """The validation function itself is reusable at request-time: calling it
    a second time (with mocked DNS returning a private IP) correctly blocks
    the rebinding attack."""

    async def test_revalidation_catches_dns_rebinding(
        self, settings_no_allowlist
    ) -> None:
        """Simulate: DNS returns public IP at registration, private IP at probe time."""
        call_count = 0

        async def mock_getaddrinfo(host, port, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_dns_result("1.1.1.1")
            return _make_dns_result("169.254.169.254")

        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.getaddrinfo = mock_getaddrinfo

            # Registration-style call — passes
            await sr.validate_source_base_url("https://evil.example.com")

            # Probe-style call — DNS now returns private/metadata IP — must fail
            with pytest.raises(ValueError, match="private or local"):
                await sr.validate_source_base_url("https://evil.example.com")


# ---------------------------------------------------------------------------
# Internal _is_forbidden_ip unit tests
# ---------------------------------------------------------------------------
class TestIsForbiddenIp:
    @pytest.mark.parametrize(
        "ip",
        [
            "127.0.0.1",
            "127.255.255.255",
            "10.0.0.1",
            "172.16.0.1",
            "192.168.1.1",
            "169.254.169.254",
            "0.0.0.0",
            "224.0.0.1",
            "255.255.255.255",
            "::1",
            "fc00::1",
            "fe80::1",
            "ff02::1",
        ],
    )
    def test_forbidden(self, ip):
        assert sr._is_forbidden_ip(ip) is True

    @pytest.mark.parametrize("ip", ["1.1.1.1", "8.8.8.8", "140.82.112.3"])
    def test_not_forbidden(self, ip):
        assert sr._is_forbidden_ip(ip) is False


# ---------------------------------------------------------------------------
# probe_source_health runtime re-validation
# ---------------------------------------------------------------------------
class TestProbeSourceHealthSSRF:
    """probe_source_health must re-validate the URL before the outbound HTTP call
    and return an unreachable response when validation fails."""

    async def test_revalidation_blocks_dns_rebinding(self) -> None:
        """When runtime SSRF validation fails (DNS rebinding), probe_source_health
        must return unreachable=False and never make the HTTP request."""
        from services.ingestor.models import SourceProfile

        profile = SourceProfile(
            id=1,
            name="ssrf-test",
            base_url="https://evil.example.com",
            health_check_path="/health",
            probe_interval_seconds=60,
            is_active=True,
        )

        with patch.object(
            sr, "validate_source_base_url", new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.side_effect = ValueError(
                "base_url resolves to private or local IP space."
            )
            with patch.object(sr.httpx, "AsyncClient") as mock_client_cls:
                mock_http = MagicMock()
                mock_client_cls.return_value.__aenter__ = AsyncMock(
                    return_value=mock_http
                )
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
                mock_http.head = AsyncMock(return_value=MagicMock(status_code=200))

                result = await sr.probe_source_health(MagicMock(), profile)

        assert result.reachable is False
        assert "private or local" in (result.error or "")
        assert result.sla_breach is True
        mock_validate.assert_called_once()
        # No HTTP request was made
        mock_http.head.assert_not_called()
