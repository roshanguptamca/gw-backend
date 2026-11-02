"""Mocked passive transport tests; no real target, worker, or database is used."""

import hashlib
import json
import socket
import stat
from types import SimpleNamespace
from unittest.mock import Mock, mock_open

import dns.resolver
import pytest

from apps.securewise.services import url_security


@pytest.mark.parametrize("host", ["bad..example", "-bad.example", "bad_.example"])
def test_parse_url_rejects_invalid_dns_labels(host):
    with pytest.raises(url_security.URLSecurityError, match="valid HTTPS"):
        url_security.parse_https_url(f"https://{host}/")


@pytest.mark.parametrize("path", ["relative", "/bad\\path", "/bad\x00path", "/%252e%252e/private"])
def test_normalize_path_rejects_encoded_traversal_and_invalid_paths(path):
    with pytest.raises(url_security.URLSecurityError):
        url_security.normalize_request_path(path)


@pytest.mark.parametrize("addresses", [[], ["not-an-ip"], ["::ffff:127.0.0.1"]])
def test_dns_resolution_rejects_empty_invalid_and_mapped_private_addresses(monkeypatch, addresses):
    records = [(socket.AF_INET6, socket.SOCK_STREAM, 0, "", (address, 0)) for address in addresses]
    monkeypatch.setattr(url_security.socket, "getaddrinfo", Mock(return_value=records))
    with pytest.raises(url_security.URLSecurityError):
        url_security.resolve_public_addresses("example.test")


def test_dns_failure_is_reported_as_url_security_error(monkeypatch):
    monkeypatch.setattr(url_security.socket, "getaddrinfo", Mock(side_effect=socket.gaierror("offline")))
    with pytest.raises(url_security.URLSecurityError, match="did not resolve"):
        url_security.resolve_public_addresses("example.test")


@pytest.fixture
def pinned_transport(monkeypatch):
    raw_socket, tls_socket = Mock(), Mock()
    context = Mock()
    context.wrap_socket.return_value = tls_socket
    response = Mock(status=200)
    response.getheaders.return_value = [("Content-Type", "text/plain")]
    response.read1.side_effect = [b"hello", b""]
    create_connection = Mock(return_value=raw_socket)
    monkeypatch.setattr(url_security.socket, "create_connection", create_connection)
    monkeypatch.setattr(url_security.ssl, "create_default_context", Mock(return_value=context))

    request_mock = Mock()

    def request(connection, *args, **kwargs):
        request_mock(*args, **kwargs)
        connection.connect()

    monkeypatch.setattr(url_security.http.client.HTTPSConnection, "request", request)
    monkeypatch.setattr(url_security.http.client.HTTPSConnection, "getresponse", Mock(return_value=response))
    monkeypatch.setattr(url_security.time, "monotonic", lambda: 100)
    return SimpleNamespace(
        raw=raw_socket,
        tls=tls_socket,
        context=context,
        response=response,
        connect=create_connection,
        request=request_mock,
    )


@pytest.mark.parametrize("port", [443, 8443])
def test_pinned_transport_uses_public_ip_but_preserves_tls_hostname(pinned_transport, port):
    authority = "example.test" if port == 443 else f"example.test:{port}"
    result = url_security._pinned_get_once(f"https://{authority}/approved", "93.184.216.34")

    assert result == (200, {"content-type": "text/plain"}, b"hello")
    pinned_transport.connect.assert_called_once_with(("93.184.216.34", port), timeout=8)
    pinned_transport.context.wrap_socket.assert_called_once_with(pinned_transport.raw, server_hostname="example.test")
    assert pinned_transport.request.call_args.kwargs["headers"]["Host"] == authority
    pinned_transport.tls.close.assert_called_once()


def test_pinned_transport_can_skip_body_reads(pinned_transport):
    assert url_security._pinned_get_once("https://example.test/", "93.184.216.34", max_body_bytes=0)[2] == b""
    pinned_transport.response.read1.assert_not_called()
    pinned_transport.tls.close.assert_called_once()


def test_pinned_transport_enforces_body_limit_and_closes_socket(pinned_transport):
    pinned_transport.response.read1.side_effect = [b"abcd"]
    with pytest.raises(url_security.URLSecurityError, match="byte limit"):
        url_security._pinned_get_once("https://example.test/", "93.184.216.34", max_body_bytes=3)
    pinned_transport.tls.close.assert_called_once()


def test_pinned_transport_enforces_total_read_deadline(monkeypatch, pinned_transport):
    monkeypatch.setattr(url_security.time, "monotonic", Mock(side_effect=[100, 109]))
    with pytest.raises(url_security.URLSecurityError, match="read timeout"):
        url_security._pinned_get_once("https://example.test/", "93.184.216.34")
    pinned_transport.response.read1.assert_not_called()
    pinned_transport.tls.close.assert_called_once()


def test_pinned_transport_closes_socket_when_response_fails(monkeypatch, pinned_transport):
    monkeypatch.setattr(
        url_security.http.client.HTTPSConnection, "getresponse", Mock(side_effect=OSError("response failed"))
    )
    with pytest.raises(OSError, match="response failed"):
        url_security._pinned_get_once("https://example.test/", "93.184.216.34")
    pinned_transport.tls.close.assert_called_once()


@pytest.fixture
def egress_proof(monkeypatch):
    monkeypatch.setenv("SECUREWISE_URL_EGRESS_ENFORCED", "true")
    monkeypatch.setenv("SECUREWISE_URL_EGRESS_PROOF_FILE", "/synthetic/egress-proof.json")
    monkeypatch.setattr(url_security.socket, "gethostname", lambda: "worker-test")
    monkeypatch.setattr(url_security.time, "time", lambda: 1000)
    monkeypatch.setattr(
        url_security.os, "stat", Mock(return_value=SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=0))
    )
    return {"verified": True, "hostname": "worker-test", "ruleset_sha256": "a" * 64, "checked_at": 999}


def test_egress_proof_accepts_fresh_root_owned_evidence(monkeypatch, egress_proof):
    opened = mock_open(read_data=json.dumps(egress_proof))
    monkeypatch.setattr("builtins.open", opened)
    assert url_security.url_egress_enforced()
    opened.assert_called_once_with("/synthetic/egress-proof.json", encoding="utf-8")
    url_security.os.stat.assert_called_once_with("/synthetic/egress-proof.json", follow_symlinks=False)


@pytest.mark.parametrize(
    ("mode", "uid"),
    [(stat.S_IFLNK | 0o600, 0), (stat.S_IFREG | 0o600, 1000), (stat.S_IFREG | 0o620, 0), (stat.S_IFREG | 0o602, 0)],
)
def test_egress_proof_rejects_untrusted_file_permissions(monkeypatch, egress_proof, mode, uid):
    monkeypatch.setattr(url_security.os, "stat", Mock(return_value=SimpleNamespace(st_mode=mode, st_uid=uid)))
    opened = mock_open(read_data=json.dumps(egress_proof))
    monkeypatch.setattr("builtins.open", opened)
    assert not url_security.url_egress_enforced()
    opened.assert_not_called()


@pytest.mark.parametrize(
    "update",
    [
        {"verified": False},
        {"hostname": "other-worker"},
        {"ruleset_sha256": "short"},
        {"checked_at": 699},
        {"checked_at": 1001},
        {"checked_at": "invalid"},
    ],
)
def test_egress_proof_rejects_stale_or_mismatched_evidence(monkeypatch, egress_proof, update):
    monkeypatch.setattr("builtins.open", mock_open(read_data=json.dumps({**egress_proof, **update})))
    assert not url_security.url_egress_enforced()


@pytest.mark.parametrize("content", ["not-json", "{}", '{"checked_at": null}'])
def test_egress_proof_rejects_malformed_evidence(monkeypatch, egress_proof, content):
    monkeypatch.setattr("builtins.open", mock_open(read_data=content))
    assert not url_security.url_egress_enforced()


def test_egress_proof_missing_file_fails_closed(monkeypatch, egress_proof):
    monkeypatch.setattr(url_security.os, "stat", Mock(side_effect=FileNotFoundError("missing")))
    assert not url_security.url_egress_enforced()


def test_dns_ownership_verification_joins_txt_chunks(monkeypatch):
    resolve = Mock(return_value=[SimpleNamespace(strings=[b"challenge-", b"value"])])
    monkeypatch.setattr(dns.resolver, "resolve", resolve)
    digest = hashlib.sha256(b"challenge-value").hexdigest()
    assert url_security.verify_dns_txt("example.test", digest)
    assert not url_security.verify_dns_txt("example.test", "wrong-digest")
    resolve.assert_called_with("_securewise-verification.example.test", "TXT", lifetime=5)


@pytest.mark.parametrize("port", [443, 8443])
def test_https_ownership_verification_is_bounded_and_disallows_redirects(monkeypatch, port):
    get = Mock(return_value=(200, {}, b"challenge-value\n", ""))
    monkeypatch.setattr(url_security, "safe_https_get", get)
    digest = hashlib.sha256(b"challenge-value").hexdigest()
    assert url_security.verify_https_well_known("example.test", digest, port=port)
    assert get.call_args.kwargs == {
        "allowed_hosts": {"example.test"},
        "allowed_ports": {port},
        "allowed_paths": ["/.well-known/securewise-verification.txt"],
        "excluded_paths": [],
        "max_redirects": 0,
        "max_body_bytes": 1024,
    }
    assert not url_security.verify_https_well_known("example.test", "wrong-digest", port=port)
    get.return_value = (404, {}, b"challenge-value", "")
    assert not url_security.verify_https_well_known("example.test", digest, port=port)
