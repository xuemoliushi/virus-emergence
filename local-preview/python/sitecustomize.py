"""Local Maker resource downloads: prefer IPv4, preserving IPv6 fallback.

Loaded by start-game.ps1's isolated preview Python environment. The official
resource CDN can resolve to unreachable IPv6 addresses on this connection;
urllib tries each address serially, exceeding Maker's preparation deadline.
Keep DNS, hostname/TLS verification and every returned address intact.
"""
import socket

_original_getaddrinfo = socket.getaddrinfo
_resource_host = "tapcode-sce.spark.xd.com"


def _resource_ipv4_first(host, port, family=0, type=0, proto=0, flags=0):
    addresses = _original_getaddrinfo(host, port, family, type, proto, flags)
    name = host.decode("ascii", errors="ignore") if isinstance(host, bytes) else host
    if family == socket.AF_UNSPEC and isinstance(name, str) and name.rstrip(".").lower() == _resource_host:
        # Stable ordering preserves the original order within each family.
        return sorted(addresses, key=lambda address: address[0] != socket.AF_INET)
    return addresses


socket.getaddrinfo = _resource_ipv4_first
