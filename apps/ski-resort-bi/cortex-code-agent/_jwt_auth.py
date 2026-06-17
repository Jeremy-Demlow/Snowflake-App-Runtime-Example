"""KEYPAIR_JWT auth for the Cortex Agents REST API.

Reads connection details (account, user, private key path) from
``~/.snowflake/connections.toml`` and mints a short-lived JWT.

Mirrors the pattern from ``mcp_ski_resort.core.JWTGenerator`` — adapted to
load from connections.toml instead of environment variables.
"""
from __future__ import annotations

import base64
import hashlib
import os
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization

CONNECTIONS_TOML = Path.home() / ".snowflake" / "connections.toml"


def _load_connection(connection_name: str) -> dict[str, Any]:
    """Read one connection block from ``~/.snowflake/connections.toml``."""
    if not CONNECTIONS_TOML.exists():
        raise FileNotFoundError(f"Connections file not found: {CONNECTIONS_TOML}")
    with open(CONNECTIONS_TOML, "rb") as f:
        cfg = tomllib.load(f)
    if connection_name not in cfg:
        raise KeyError(
            f"Connection {connection_name!r} not in {CONNECTIONS_TOML}. "
            f"Available: {list(cfg)}"
        )
    return cfg[connection_name]


def _public_key_fingerprint(private_key) -> str:
    """SHA256 fingerprint of the DER-encoded public key, matching Snowflake's format."""
    pub_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return "SHA256:" + base64.b64encode(hashlib.sha256(pub_bytes).digest()).decode()


@dataclass
class AgentSessionAuth:
    """Host + bearer JWT for Cortex Agents REST calls."""
    host: str
    token: str
    role: str | None = None

    def headers(self, accept: str = "application/json") -> dict[str, str]:
        h = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": accept,
            "X-Snowflake-Authorization-Token-Type": "KEYPAIR_JWT",
        }
        if self.role:
            h["X-Snowflake-Role"] = self.role
        return h


class _JWTCache:
    """Per-process cache: one signed JWT per connection name, refreshed near expiry."""

    def __init__(self) -> None:
        self._tokens: dict[str, tuple[str, int]] = {}

    def get(self, connection_name: str, lifetime_s: int = 3600) -> AgentSessionAuth:
        now = int(time.time())
        cached = self._tokens.get(connection_name)
        if cached:
            token, exp = cached
            if now < exp - 60:
                return self._auth_from_cached(connection_name, token)

        cfg = _load_connection(connection_name)
        if cfg.get("authenticator", "").upper() != "SNOWFLAKE_JWT":
            raise ValueError(
                f"Connection {connection_name!r} uses authenticator="
                f"{cfg.get('authenticator')!r}; KEYPAIR_JWT REST auth requires "
                f"authenticator='SNOWFLAKE_JWT' with a private_key_file."
            )

        pk_path = cfg.get("private_key_file") or cfg.get("private_key_path")
        if not pk_path:
            raise ValueError(
                f"Connection {connection_name!r} is SNOWFLAKE_JWT but has no "
                f"private_key_file/private_key_path."
            )
        pk_path = os.path.expanduser(pk_path)

        with open(pk_path, "rb") as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)

        account = cfg["account"].upper().replace("-", "_")
        user = cfg["user"].upper() if "user" in cfg else os.environ.get("USER", "").upper()
        if not user:
            raise ValueError(
                f"Connection {connection_name!r} has no `user` and $USER is unset."
            )
        fingerprint = _public_key_fingerprint(private_key)
        sub = f"{account}.{user}"
        exp = now + lifetime_s
        payload = {
            "iss": f"{sub}.{fingerprint}",
            "sub": sub,
            "iat": now,
            "exp": exp,
        }
        token = jwt.encode(payload, private_key, algorithm="RS256")
        if isinstance(token, bytes):
            token = token.decode()
        self._tokens[connection_name] = (token, exp)

        host = cfg.get("host")
        if not host:
            raw_account = cfg["account"]
            host = f"https://{raw_account}.snowflakecomputing.com"
        elif not host.startswith("http"):
            host = f"https://{host}"
        return AgentSessionAuth(host=host, token=token, role=cfg.get("role"))

    def _auth_from_cached(self, connection_name: str, token: str) -> AgentSessionAuth:
        cfg = _load_connection(connection_name)
        host = cfg.get("host") or f"https://{cfg['account']}.snowflakecomputing.com"
        if not host.startswith("http"):
            host = f"https://{host}"
        return AgentSessionAuth(host=host, token=token, role=cfg.get("role"))


_CACHE = _JWTCache()


def session_from_connection(connection_name: str) -> AgentSessionAuth:
    """Mint (or reuse) a KEYPAIR_JWT bearer for the named connection."""
    return _CACHE.get(connection_name)
