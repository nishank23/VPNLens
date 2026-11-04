"""Resolve an IPv4 visitor only from the transport peer and explicit proxy trust."""

from ipaddress import ip_address, ip_network


class VisitorAddressError(ValueError):
    def __init__(self, detail="public_ipv4_unavailable", status_code=409):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _address(value):
    try:
        # Scoped IPv6, ports, hostnames and bracketed literals are not XFF IPs.
        if not isinstance(value, str) or "%" in value:
            raise ValueError
        return ip_address(value)
    except ValueError:
        raise VisitorAddressError() from None


def client_address(peer, forwarded_for=None, trusted_proxy_cidrs=()):
    """Peel trusted XFF hops; callers must supply the unmodified transport peer.

    Trust assumes each configured proxy appends its real upstream peer to XFF,
    or replaces inbound XFF with a chain it independently validates. Validate the
    complete chain before selecting the first untrusted address from the right.
    Untrusted transport peers cannot influence selection with any header.
    """
    address = _address(peer)
    networks = tuple(ip_network(value, strict=True) for value in trusted_proxy_cidrs)

    def trusted(candidate):
        return any(candidate in network for network in networks)

    if trusted(address):
        if not isinstance(forwarded_for, str) or not forwarded_for.strip():
            raise VisitorAddressError()
        chain = [_address(value.strip()) for value in forwarded_for.split(",")]
        for candidate in reversed(chain):
            if not trusted(candidate):
                address = candidate
                break
        else:
            raise VisitorAddressError()
    return address


def visitor_ipv4(peer, forwarded_for=None, trusted_proxy_cidrs=()):
    address = client_address(peer, forwarded_for, trusted_proxy_cidrs)
    if address.version != 4:
        raise VisitorAddressError("ipv6_not_supported", 422)
    if not address.is_global or address.is_multicast:
        raise VisitorAddressError()
    return str(address)
