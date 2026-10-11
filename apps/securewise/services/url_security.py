"""Fail-closed URL ownership and passive assessment safety controls."""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import os
import secrets
import socket
import ssl
import stat
import time
from datetime import timedelta
from urllib.parse import urljoin, urlsplit, urlunsplit

from django.utils import timezone

ALLOWED_HTTPS_PORTS = {443, 8443}
MAX_REDIRECTS = 3
MAX_RESPONSE_BYTES = 1024 * 1024


class URLSecurityError(ValueError):
    pass


def normalize_host(value: str) -> str:
    host = value.strip().rstrip(".").encode("idna").decode("ascii").lower()
    if not host or len(host) > 253 or "/" in host or "@" in host:
        raise URLSecurityError("Provide one exact valid hostname.")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        labels = host.split(".")
        if any(not label or len(label) > 63 for label in labels):
            raise URLSecurityError("Provide one exact valid hostname.")
        if any(not label[0].isalnum() or not label[-1].isalnum() for label in labels):
            raise URLSecurityError("Provide one exact valid hostname.")
        if any(not all(char.isalnum() or char == "-" for char in label) for label in labels):
            raise URLSecurityError("Provide one exact valid hostname.")
    return host


def parse_https_url(value: str) -> tuple[str, str, int, str]:
    try:
        parsed = urlsplit(value)
        host = normalize_host(parsed.hostname or "")
        port = parsed.port or 443
    except (TypeError, ValueError, UnicodeError) as exc:
        raise URLSecurityError("Provide a valid HTTPS application URL.") from exc
    if (
        parsed.scheme.lower() != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port not in ALLOWED_HTTPS_PORTS
    ):
        raise URLSecurityError("Only HTTPS targets on approved ports 443 or 8443 are supported.")
    path = normalize_request_path(parsed.path or "/")
    return "https", host, port, path


def normalize_request_path(path: str) -> str:
    from urllib.parse import unquote

    decoded = path
    for _ in range(3):
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    if not decoded.startswith("/") or "\\" in decoded or "\x00" in decoded:
        raise URLSecurityError("Target path is invalid.")
    if any(part in (".", "..") for part in decoded.split("/")):
        raise URLSecurityError("Target path traversal is not permitted.")
    return decoded


def resolve_public_addresses(host: str) -> tuple[str, ...]:
    try:
        records = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise URLSecurityError("Target hostname did not resolve.") from exc
    addresses = tuple(sorted({record[4][0].split("%", 1)[0] for record in records}))
    if not addresses:
        raise URLSecurityError("Target hostname did not resolve.")
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise URLSecurityError("Target DNS returned an invalid address.") from exc
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if not ip.is_global:
            raise URLSecurityError("Target resolves to a private or otherwise forbidden network address.")
    return addresses


def _pinned_get_once(url: str, ip: str, *, max_body_bytes: int = MAX_RESPONSE_BYTES):
    parsed = urlsplit(url)
    host = normalize_host(parsed.hostname or "")
    port = parsed.port or 443
    request_path = urlunsplit(("", "", parsed.path or "/", "", ""))
    context = ssl.create_default_context()

    class PinnedHTTPSConnection(http.client.HTTPSConnection):
        def connect(self):
            raw_socket = socket.create_connection((ip, port), timeout=8)
            self.sock = context.wrap_socket(raw_socket, server_hostname=host)

    connection = PinnedHTTPSConnection(host, port, timeout=8, context=context)
    try:
        host_header = host if port == 443 else f"{host}:{port}"
        connection.request("GET", request_path, headers={"Host": host_header, "Connection": "close"})
        response = connection.getresponse()
        body = b""
        if max_body_bytes:
            deadline = time.monotonic() + 8
            chunks = []
            total = 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise URLSecurityError("Target response exceeded the 8 second read timeout.")
                connection.sock.settimeout(remaining)
                chunk = response.read1(min(8192, max_body_bytes + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > max_body_bytes:
                    raise URLSecurityError("Target response exceeded the configured byte limit.")
            body = b"".join(chunks)
        return response.status, {key.lower(): value for key, value in response.getheaders()}, body
    finally:
        connection.close()


def safe_https_get(
    url: str,
    *,
    allowed_hosts: set[str],
    allowed_ports: set[int],
    allowed_paths: list[str],
    excluded_paths: list[str],
    max_redirects: int = MAX_REDIRECTS,
    preflight=None,
    max_body_bytes: int = MAX_RESPONSE_BYTES,
):
    """GET with validated public DNS, pinned connections, no proxies, and scoped redirects."""
    current = url
    for redirects in range(max_redirects + 1):
        if preflight:
            preflight(current)
        scheme, host, port, path = parse_https_url(current)
        if scheme != "https" or host not in allowed_hosts or port not in allowed_ports:
            raise URLSecurityError("Target or redirect is outside the approved host and port scope.")
        if not path_is_allowed(path, allowed_paths, excluded_paths):
            raise URLSecurityError("Target or redirect path is outside the approved path scope.")
        addresses = resolve_public_addresses(host)
        status_code, headers, body = _pinned_get_once(current, addresses[0], max_body_bytes=max_body_bytes)
        if status_code not in (301, 302, 303, 307, 308):
            return status_code, headers, body, current
        if redirects >= max_redirects:
            raise URLSecurityError("Target exceeded the allowed redirect limit.")
        location = headers.get("location", "")
        if not location:
            raise URLSecurityError("Target returned a redirect without a destination.")
        current = urljoin(current, location)
    raise URLSecurityError("Target exceeded the allowed redirect limit.")


def path_is_allowed(path: str, allowed_paths: list[str], excluded_paths: list[str]) -> bool:
    path = normalize_request_path(path)

    def matches(prefixes: list[str]) -> bool:
        return any(path == prefix.rstrip("/") or path.startswith(prefix.rstrip("/") + "/") for prefix in prefixes)

    return bool(allowed_paths) and matches(allowed_paths) and not matches(excluded_paths)


def url_egress_enforced() -> bool:
    if os.environ.get("SECUREWISE_URL_EGRESS_ENFORCED", "").lower() != "true":
        return False
    proof_path = os.environ.get(
        "SECUREWISE_URL_EGRESS_PROOF_FILE",
        "/etc/securewise/url-egress-verification.json",
    )
    try:
        proof_stat = os.stat(proof_path, follow_symlinks=False)
        if not stat.S_ISREG(proof_stat.st_mode) or proof_stat.st_uid != 0:
            return False
        if proof_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            return False
        with open(proof_path, encoding="utf-8") as proof_file:
            proof = json.load(proof_file)
        checked_at = float(proof["checked_at"])
        return (
            proof.get("verified") is True
            and proof.get("hostname") == socket.gethostname()
            and len(str(proof.get("ruleset_sha256", ""))) == 64
            and 0 <= time.time() - checked_at <= 300
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return False


def worker_has_url_egress(worker_id: str | None = None) -> bool:
    if not url_egress_enforced():
        return False
    from apps.securewise.models import SecureWiseWorkerRegistration

    cutoff = timezone.now() - timedelta(seconds=45)
    registrations = SecureWiseWorkerRegistration.objects.filter(
        status="online",
        last_seen_at__gte=cutoff,
    )
    if worker_id:
        registrations = registrations.filter(worker_id=worker_id)
    return any("url_egress_restricted" in (registration.capabilities or []) for registration in registrations)


def create_challenge_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, hashlib.sha256(token.encode()).hexdigest()


def verify_dns_txt(hostname: str, challenge_digest: str) -> bool:
    import dns.resolver

    answers = dns.resolver.resolve(f"_securewise-verification.{hostname}", "TXT", lifetime=5)
    return any(hashlib.sha256(b"".join(answer.strings)).hexdigest() == challenge_digest for answer in answers)


def verify_https_well_known(hostname: str, challenge_digest: str, *, port: int = 443) -> bool:
    authority = hostname if port == 443 else f"{hostname}:{port}"
    url = f"https://{authority}/.well-known/securewise-verification.txt"
    status_code, _, body, _ = safe_https_get(
        url,
        allowed_hosts={hostname},
        allowed_ports={port},
        allowed_paths=["/.well-known/securewise-verification.txt"],
        excluded_paths=[],
        max_redirects=0,
        max_body_bytes=1024,
    )
    return status_code == 200 and hashlib.sha256(body.strip()).hexdigest() == challenge_digest


def authorization_is_active(authorization, *, at=None) -> bool:
    at = at or timezone.now()
    target = authorization.target
    return (
        authorization.revoked_at is None
        and authorization.starts_at <= at < authorization.expires_at
        and target.verified_at is not None
        and target.ownership_revoked_at is None
        and authorization.authorized_hosts == [target.hostname]
        and target.port in authorization.allowed_ports
        and authorization.approved_scan_methods == ["passive_http"]
    )


def authorize_request(authorization, url: str, *, worker_id: str = "") -> tuple[int, dict[str, str], bytes, str]:
    if not authorization_is_active(authorization):
        raise URLSecurityError("Testing authorization is expired, revoked, or no longer valid.")
    if not worker_id or not worker_has_url_egress(worker_id):
        raise URLSecurityError("URL scanning is disabled because worker egress protection is unavailable.")
    _, host, port, _ = parse_https_url(url)
    if host != authorization.target.hostname or port not in authorization.allowed_ports:
        raise URLSecurityError("Target is outside the approved exact host and port scope.")
    authorization_id = authorization.id

    def revalidate_scope(current_url):
        from apps.securewise.models import SecureWiseTestingAuthorization

        try:
            current_authorization = SecureWiseTestingAuthorization.objects.select_related("target").get(
                id=authorization_id
            )
        except SecureWiseTestingAuthorization.DoesNotExist as exc:
            raise URLSecurityError("Testing authorization no longer exists.") from exc
        if not authorization_is_active(current_authorization) or not worker_has_url_egress(worker_id):
            raise URLSecurityError("Testing authorization or worker egress protection is no longer active.")
        _, current_host, current_port, current_path = parse_https_url(current_url)
        if (
            current_host not in current_authorization.authorized_hosts
            or current_port not in current_authorization.allowed_ports
            or not path_is_allowed(
                current_path,
                current_authorization.allowed_paths,
                current_authorization.excluded_paths,
            )
        ):
            raise URLSecurityError("Target or redirect is outside the approved scope.")

    return safe_https_get(
        url,
        allowed_hosts=set(authorization.authorized_hosts),
        allowed_ports=set(authorization.allowed_ports),
        allowed_paths=authorization.allowed_paths,
        excluded_paths=authorization.excluded_paths,
        preflight=revalidate_scope,
        max_body_bytes=0,
    )
