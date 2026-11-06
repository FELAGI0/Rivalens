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


class UnsafeURLError(ValueError):
    """The URL points at (or could point at) a blocked network target."""

    def __init__(self, reason: str):
        super().__init__(f"unsafe url: {reason}")
        self.reason = reason


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

    if _ip_is_blocked(ip):
        raise UnsafeURLError(f"private or reserved address {ip} not allowed")


def resolve_and_check_host(hostname: str) -> None:
    """Resolve the hostname now and verify every address is public.

    Call on every fetch, right before the request: this is what defeats
    DNS rebinding (a domain re-resolved to an internal address between
    registration and check).
    """
    try:
        infos = socket.getaddrinfo(
            hostname, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM
        )
    except socket.gaierror as e:
        raise UnsafeURLError(f"cannot resolve {hostname!r}: {e}") from e

    addresses = {info[4][0] for info in infos}
    if not addresses:
        raise UnsafeURLError(f"{hostname!r} resolved to no addresses")

    for addr in addresses:
        try:
            ip = ipaddress.ip_address(addr.split("%")[0])  # strip zone id
        except ValueError:
            raise UnsafeURLError(f"{hostname!r} resolved to {addr!r}")
        if _ip_is_blocked(ip):
            raise UnsafeURLError(
                f"{hostname!r} resolves to blocked address {ip}"
            )
