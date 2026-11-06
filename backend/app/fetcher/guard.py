"""URL safety guard: the fetcher must never reach private networks.

A user-supplied competitor URL is an SSRF vector: without this check a
registered user could point the pipeline at http://127.0.0.1:8001/api,
the Postgres container, cloud metadata endpoints (169.254.169.254) or
any RFC1918 host behind the server. The guard runs:

1. At CompetitorCreate time (fast schema-level rejection of obviously
   private hosts, port and length checks).
2. At fetch time, on EVERY fetch: the hostname is resolved and each
   resulting address is checked against the blocked ranges. Resolving
   per-request (not per-stored-URL) also covers DNS rebinding: a domain
   that answers 1.2.3.4 at creation and 169.254.169.254 at check time.

Redirects: curl_cffi auto-follows redirects by default, which would let
a public URL 302 into a private one. The fetcher disables automatic
redirects and re-runs each hop through this same guard (see client.py).
"""

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

# Loopback, private (RFC1918), link-local (incl. cloud metadata
# 169.254.169.254), unique-local, unspecified, multicast, reserved,
# broadcast — everything that is not a real public internet address.
_BLOCKED_NETWORKS = tuple(
    ipaddress.ip_network(net)
    for net in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "192.168.0.0/16",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "255.255.255.255/32",
        "::/128",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
        "ff00::/8",
    )
)

ALLOWED_PORTS = (80, 443)

MAX_URL_LENGTH = 2048

# Hard timeout for DNS resolution: a slow/hanging resolver must fail the
# fetch fast, not stall the pipeline (and must never block the loop).
RESOLVE_TIMEOUT_SECONDS = 5.0


class UnsafeURLError(ValueError):
    """The URL points at (or could point at) a blocked network target."""

    def __init__(self, reason: str):
        super().__init__(f"unsafe url: {reason}")
        self.reason = reason


def _normalize_ip(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """Unwrap IPv6 forms that carry an IPv4 address inside.

    ::ffff:127.0.0.1 (IPv4-mapped) is how a browser/curl may happily
    connect to loopback while the literal "127.0.0.1" never appears.
    6to4 (2002::/16) and Teredo (2001::/32) embed an IPv4 too.
    """
    if isinstance(ip, ipaddress.IPv6Address):
        mapped = ip.ipv4_mapped
        if mapped is None and ip.sixtofour is not None:
            mapped = ip.sixtofour
        if mapped is None and ip.teredo is not None:
            # Teredo servers are a routing detail; the client IPv4 is
            # what the connection ultimately egresses from.
            mapped = ipaddress.IPv4Address(ip.teredo[1])
        if mapped is not None:
            return mapped
    return ip


def _ip_is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any(ip in net for net in _BLOCKED_NETWORKS)


def check_url_scheme_and_host(url: str) -> None:
    """Cheap, DNS-free checks usable at validation time.

    Raises UnsafeURLError (a ValueError) so Pydantic turns it into a 422.
    """
    if len(url) > MAX_URL_LENGTH:
        raise UnsafeURLError("url too long")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise UnsafeURLError("scheme must be http or https")
    hostname = parts.hostname
    if not hostname:
        raise UnsafeURLError("no hostname")

    port = parts.port  # raises ValueError on a malformed port — fine
    if port is not None and port not in ALLOWED_PORTS:
        raise UnsafeURLError(f"port {port} not allowed")

    # A literal IP host is checked immediately; a domain is only checked
    # for being a dotted form of a private literal (e.g. "127.1") at
    # fetch time after resolution — plus a cheap sanity reject of
    # obviously-local names.
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        if hostname in ("localhost",) or hostname.endswith(".localhost"):
            raise UnsafeURLError("localhost not allowed")
        return

    if _ip_is_blocked(_normalize_ip(ip)):
        raise UnsafeURLError(f"private or reserved address {ip} not allowed")


async def resolve_and_check_host(
    hostname: str, timeout: float = RESOLVE_TIMEOUT_SECONDS
) -> list[str]:
    """Resolve the hostname (async, timeout-bounded) and check it.

    Returns the list of validated public IP strings — the caller pins
    the request to these so libcurl/Chromium cannot re-resolve to a
    different (rebound) address.

    getaddrinfo is synchronous, so it runs in the event loop's executor
    via loop.getaddrinfo with a hard timeout: a slow DNS answer must
    not block the whole event loop, and a timeout is a fetch failure.
    """
    loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(
            loop.getaddrinfo(
                hostname, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError as e:
        raise UnsafeURLError(
            f"DNS resolution of {hostname!r} timed out"
        ) from e
    except socket.gaierror as e:
        raise UnsafeURLError(f"cannot resolve {hostname!r}: {e}") from e

    addresses = {info[4][0] for info in infos}
    if not addresses:
        raise UnsafeURLError(f"{hostname!r} resolved to no addresses")

    validated: list[str] = []
    for addr in addresses:
        try:
            ip = ipaddress.ip_address(addr.split("%")[0])  # zone id off
        except ValueError:
            raise UnsafeURLError(f"{hostname!r} resolved to {addr!r}")
        if _ip_is_blocked(_normalize_ip(ip)):
            raise UnsafeURLError(
                f"{hostname!r} resolves to blocked address {ip}"
            )
        validated.append(str(ip))
    return validated
