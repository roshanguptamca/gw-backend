"""Port-related helpers for the discovery/runtime packages."""

from __future__ import annotations

import re
import socket

_EXPOSE_RE = re.compile(r"^\s*EXPOSE\s+([0-9 /a-zA-Z]+)", re.IGNORECASE | re.MULTILINE)
_COMPOSE_PORT_RE = re.compile(r"""^\s*-\s*["']?(\d{2,5}):(\d{2,5})["']?\s*$""", re.MULTILINE)


def parse_dockerfile_exposed_ports(dockerfile_text: str) -> list[int]:
    """Extract port numbers from `EXPOSE` instructions in a Dockerfile."""
    ports: list[int] = []
    for match in _EXPOSE_RE.finditer(dockerfile_text):
        for token in match.group(1).split():
            token = token.split("/")[0]
            if token.isdigit():
                port = int(token)
                if port not in ports:
                    ports.append(port)
    return ports


def parse_compose_host_ports(compose_text: str) -> list[int]:
    """Extract host-side port numbers from a docker-compose `ports:` list, e.g. "8000:8000"."""
    ports: list[int] = []
    for match in _COMPOSE_PORT_RE.finditer(compose_text):
        port = int(match.group(1))
        if port not in ports:
            ports.append(port)
    return ports


def find_free_host_port() -> int:
    """Ask the OS for an unused ephemeral port to bind the runtime container to."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
