"""수집 URL SSRF 방어 (§12.3, AT-14).

수집기는 운영자가 등록한 임의의 URL을 서버에서 직접 요청한다. 방어가 없으면
공격자가 사내망·클라우드 메타데이터 엔드포인트를 대신 읽게 만들 수 있다.

검사는 4단계이며 **리다이렉트 매 홉마다 전부 다시 수행한다.**
첫 요청만 검사하고 리다이렉트를 따라가면 방어가 무력화된다.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

ALLOWED_SCHEMES = frozenset({"http", "https"})


class SsrfBlocked(Exception):
    """URL이 SSRF 검사를 통과하지 못했다."""

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"{reason} (url={url})")
        self.url = url
        self.reason = reason


@dataclass(frozen=True)
class UrlPolicy:
    """출처 레지스트리에서 파생된 허용 정책."""

    allowed_hosts: frozenset[str] = frozenset()
    """canonical_domain 목록. 비어 있으면 호스트 허용목록 검사를 건너뛴다."""

    allow_subdomains: bool = True
    allow_private_ips: bool = False
    max_redirects: int = 3


def _is_disallowed_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
    """사설·예약 대역이면 사유를 반환한다."""
    if ip.is_private:
        return "사설 IP 대역"
    if ip.is_loopback:
        return "루프백 주소"
    if ip.is_link_local:
        return "링크 로컬 주소 (클라우드 메타데이터 포함)"
    if ip.is_reserved:
        return "예약된 IP 대역"
    if ip.is_multicast:
        return "멀티캐스트 주소"
    if ip.is_unspecified:
        return "미지정 주소"
    # IPv4-mapped IPv6 (::ffff:10.0.0.1) 로 우회하는 경로를 막는다.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return _is_disallowed_ip(ip.ipv4_mapped)
    return None


def _host_allowed(host: str, policy: UrlPolicy) -> bool:
    if not policy.allowed_hosts:
        return True
    host = host.lower().rstrip(".")
    if host in policy.allowed_hosts:
        return True
    if policy.allow_subdomains:
        return any(host.endswith("." + allowed) for allowed in policy.allowed_hosts)
    return False


def _resolve(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """호스트의 모든 A/AAAA 레코드를 얻는다.

    하나라도 사설 대역이면 차단한다. DNS rebinding 을 완전히 막지는 못하지만,
    단순 리졸브 우회는 차단한다.
    """
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return [ipaddress.ip_address(host)]

    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise SsrfBlocked(host, f"호스트를 해석할 수 없습니다: {exc}") from exc

    return [ipaddress.ip_address(info[4][0]) for info in infos]


def check_url(url: str, policy: UrlPolicy | None = None) -> None:
    """URL 하나를 검사한다. 통과하지 못하면 SsrfBlocked 를 던진다.

    1. 스킴이 http/https
    2. 호스트가 허용 목록에 포함
    3. DNS 해석 결과가 사설·예약 대역이 아님
    """
    policy = policy or UrlPolicy()
    parsed = urlparse(url)

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise SsrfBlocked(url, f"허용되지 않는 스킴입니다: {parsed.scheme or '(없음)'}")

    host = parsed.hostname
    if not host:
        raise SsrfBlocked(url, "호스트가 없습니다.")

    if not _host_allowed(host, policy):
        raise SsrfBlocked(url, f"허용된 출처 도메인이 아닙니다: {host}")

    if policy.allow_private_ips:
        return

    for ip in _resolve(host):
        reason = _is_disallowed_ip(ip)
        if reason is not None:
            raise SsrfBlocked(url, f"{reason}으로 해석됩니다: {ip}")


def check_redirect_chain(urls: list[str], policy: UrlPolicy | None = None) -> None:
    """리다이렉트 체인 전체를 검사한다 (AT-14).

    공격 시나리오: 허용된 공식 도메인이 302로 http://169.254.169.254/ 를 가리킨다.
    첫 URL만 검사하면 통과하므로, 모든 홉을 같은 기준으로 검사해야 한다.
    """
    policy = policy or UrlPolicy()
    if len(urls) - 1 > policy.max_redirects:
        raise SsrfBlocked(urls[-1], f"리다이렉트가 {policy.max_redirects}회를 초과했습니다.")

    for index, url in enumerate(urls):
        # 리다이렉트 대상은 원래 출처와 다른 도메인일 수 있으므로 호스트 허용목록은
        # 첫 홉에만 적용하고, IP·스킴 검사는 모든 홉에 적용한다.
        hop_policy = policy if index == 0 else UrlPolicy(
            allowed_hosts=frozenset(),
            allow_subdomains=policy.allow_subdomains,
            allow_private_ips=policy.allow_private_ips,
            max_redirects=policy.max_redirects,
        )
        check_url(url, hop_policy)
