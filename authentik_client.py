"""
Cliente de autenticacao de usuario via authentik/OIDC.

Este modulo substitui o login humano via INTEGRIM quando AUTH_PROVIDER=authentik.
O INTEGRIM permanece preservado no projeto para modo legado e para eventual
integracao tecnica com servicos CISS.

Tokens e secrets nunca devem ser registrados em logs. Os tokens retornados pelo
authentik devem ficar apenas em memoria/sessao do Streamlit.
"""

from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import Any
from urllib.parse import urlencode

from dotenv import load_dotenv
import requests
from requests import Response


load_dotenv()

logger = logging.getLogger(__name__)


def _config_value(key: str, default: str = "") -> str:
    value = os.getenv(key, "").strip()
    if value:
        return value

    try:
        import streamlit as st

        candidates = [key, key.lower()]
        for candidate in candidates:
            value = st.secrets.get(candidate, "")
            if value:
                return str(value).strip()

        if "auth" in st.secrets:
            auth_secrets = st.secrets["auth"]
            short_key = key.replace("AUTHENTIK_", "").lower()
            for candidate in (short_key, short_key.upper()):
                value = auth_secrets.get(candidate, "")
                if value:
                    return str(value).strip()
    except Exception:
        pass

    return default


class AuthentikError(Exception):
    """Erro base para falhas de autenticacao via authentik."""

    user_message = "Nao foi possivel concluir a autenticacao no momento."


class AuthentikConfigError(AuthentikError):
    """Configuracao incompleta para autenticar no authentik."""

    user_message = "Configuracao de autenticacao authentik incompleta."


class InvalidAuthentikStateError(AuthentikError):
    """State ausente ou diferente do esperado no retorno OIDC."""

    user_message = "Sessao de autenticacao invalida. Tente entrar novamente."


class AuthentikUnavailableError(AuthentikError):
    """Timeout ou falha de conexao com o authentik."""

    user_message = "Servico de autenticacao indisponivel no momento. Tente novamente em instantes."


class InvalidAuthentikResponseError(AuthentikError):
    """Resposta ausente, invalida ou nao JSON do authentik."""

    user_message = "Nao foi possivel concluir a autenticacao no momento."


@dataclass(frozen=True)
class AuthentikConfig:
    base_url: str
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: str = "openid profile email"
    provider_slug: str = "contascontabeis"
    issuer: str | None = None
    timeout_seconds: float = 15
    state_ttl_seconds: int = 600

    @classmethod
    def from_env(cls) -> "AuthentikConfig":
        base_url = _config_value("AUTHENTIK_BASE_URL", "https://auth.lojaototal.com.br").rstrip("/")
        provider_slug = _config_value("AUTHENTIK_PROVIDER_SLUG", "contascontabeis").strip("/")
        issuer = _config_value("AUTHENTIK_ISSUER", "").rstrip("/") or None
        metadata_url = _config_value("AUTHENTIK_SERVER_METADATA_URL", "")
        if not issuer and metadata_url and "/.well-known/" in metadata_url:
            issuer = metadata_url.split("/.well-known/", 1)[0].rstrip("/")

        client_id = _config_value("AUTHENTIK_CLIENT_ID")
        client_secret = _config_value("AUTHENTIK_CLIENT_SECRET")
        redirect_uri = _config_value("AUTHENTIK_REDIRECT_URI", "http://localhost:8501")
        scopes = _config_value("AUTHENTIK_SCOPES", "openid profile email")
        timeout_raw = _config_value("REQUEST_TIMEOUT_SECONDS", "15")
        state_ttl_raw = _config_value("AUTHENTIK_STATE_TTL_SECONDS", "600")

        faltando = [
            nome
            for nome, valor in {
                "AUTHENTIK_BASE_URL": base_url,
                "AUTHENTIK_PROVIDER_SLUG": provider_slug,
                "AUTHENTIK_CLIENT_ID": client_id,
                "AUTHENTIK_CLIENT_SECRET": client_secret,
                "AUTHENTIK_REDIRECT_URI": redirect_uri,
                "AUTHENTIK_SCOPES": scopes,
            }.items()
            if not valor
        ]
        if faltando:
            raise AuthentikConfigError(
                "Variaveis de ambiente ausentes para autenticacao authentik: "
                f"{', '.join(faltando)}."
            )

        try:
            timeout_seconds = float(timeout_raw)
        except ValueError as exc:
            raise AuthentikConfigError("REQUEST_TIMEOUT_SECONDS deve ser um numero.") from exc

        try:
            state_ttl_seconds = int(state_ttl_raw)
        except ValueError as exc:
            raise AuthentikConfigError("AUTHENTIK_STATE_TTL_SECONDS deve ser um numero inteiro.") from exc

        return cls(
            base_url=base_url,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scopes=scopes,
            provider_slug=provider_slug,
            issuer=issuer,
            timeout_seconds=timeout_seconds,
            state_ttl_seconds=state_ttl_seconds,
        )

    @property
    def discovery_url(self) -> str:
        if self.issuer:
            return f"{self.issuer}/.well-known/openid-configuration"
        return f"{self.base_url}/application/o/{self.provider_slug}/.well-known/openid-configuration"


def _json_response(response: Response, endpoint_name: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        logger.warning(
            "Resposta nao JSON do authentik: status=%s endpoint=%s",
            response.status_code,
            endpoint_name,
        )
        raise InvalidAuthentikResponseError("Resposta nao JSON do authentik.") from exc

    if not isinstance(payload, dict):
        logger.warning(
            "Resposta JSON inesperada do authentik: status=%s endpoint=%s tipo=%s",
            response.status_code,
            endpoint_name,
            type(payload).__name__,
        )
        raise InvalidAuthentikResponseError("Resposta JSON inesperada do authentik.")

    return payload


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _base64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(f"{data}{padding}")


class AuthentikClient:
    def __init__(self, config: AuthentikConfig | None = None):
        self.config = config or AuthentikConfig.from_env()
        self._metadata: dict[str, Any] | None = None

    def _request_json(
        self,
        method: str,
        url: str,
        endpoint_name: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        try:
            response = requests.request(
                method,
                url,
                timeout=self.config.timeout_seconds,
                **kwargs,
            )
        except requests.Timeout as exc:
            logger.warning(
                "Timeout ao conectar no authentik: endpoint=%s timeout=%ss",
                endpoint_name,
                self.config.timeout_seconds,
            )
            raise AuthentikUnavailableError("Timeout ao conectar no authentik.") from exc
        except requests.ConnectionError as exc:
            logger.warning("Falha de conexao com o authentik: endpoint=%s", endpoint_name)
            raise AuthentikUnavailableError("Falha de conexao com o authentik.") from exc
        except requests.RequestException as exc:
            logger.warning("Falha HTTP ao conectar no authentik: endpoint=%s", endpoint_name)
            raise AuthentikUnavailableError("Falha HTTP ao conectar no authentik.") from exc

        if not response.ok:
            logger.warning(
                "Erro HTTP do authentik: status=%s endpoint=%s",
                response.status_code,
                endpoint_name,
            )
            raise AuthentikError("Erro HTTP do authentik.")

        return _json_response(response, endpoint_name)

    def metadata(self) -> dict[str, Any]:
        if self._metadata is None:
            self._metadata = self._request_json(
                "GET",
                self.config.discovery_url,
                "openid-configuration",
            )
        return self._metadata

    def create_state(self, nonce: str) -> str:
        payload = {
            "iat": int(time.time()),
            "nonce": nonce,
            "random": secrets.token_urlsafe(24),
        }
        payload_encoded = _base64url_encode(
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
        )
        signature = hmac.new(
            self.config.client_secret.encode("utf-8"),
            payload_encoded.encode("ascii"),
            hashlib.sha256,
        ).digest()
        return f"{payload_encoded}.{_base64url_encode(signature)}"

    def validate_state(self, state: str) -> dict[str, Any]:
        try:
            payload_encoded, signature_encoded = state.split(".", 1)
        except ValueError as exc:
            raise InvalidAuthentikStateError("Formato de state invalido.") from exc

        expected_signature = hmac.new(
            self.config.client_secret.encode("utf-8"),
            payload_encoded.encode("ascii"),
            hashlib.sha256,
        ).digest()

        try:
            received_signature = _base64url_decode(signature_encoded)
        except ValueError as exc:
            raise InvalidAuthentikStateError("Assinatura de state invalida.") from exc

        if not hmac.compare_digest(expected_signature, received_signature):
            raise InvalidAuthentikStateError("Assinatura de state nao confere.")

        try:
            payload = json.loads(_base64url_decode(payload_encoded).decode("utf-8"))
        except (ValueError, json.JSONDecodeError) as exc:
            raise InvalidAuthentikStateError("Payload de state invalido.") from exc

        iat = payload.get("iat")
        if not isinstance(iat, int):
            raise InvalidAuthentikStateError("Data de state invalida.")

        if int(time.time()) - iat > self.config.state_ttl_seconds:
            raise InvalidAuthentikStateError("State expirado.")

        return payload

    def authorization_url(self, state: str, nonce: str) -> str:
        metadata = self.metadata()
        authorization_endpoint = metadata.get("authorization_endpoint")
        if not authorization_endpoint:
            raise InvalidAuthentikResponseError("authorization_endpoint ausente no discovery.")

        params = {
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "response_type": "code",
            "scope": self.config.scopes,
            "state": state,
            "nonce": nonce,
        }
        return f"{authorization_endpoint}?{urlencode(params)}"

    def exchange_code(self, code: str) -> dict[str, Any]:
        metadata = self.metadata()
        token_endpoint = metadata.get("token_endpoint")
        if not token_endpoint:
            raise InvalidAuthentikResponseError("token_endpoint ausente no discovery.")

        payload = self._request_json(
            "POST",
            token_endpoint,
            "token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.config.redirect_uri,
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if not payload.get("access_token"):
            logger.warning("access_token nao retornado pelo authentik.")
            raise InvalidAuthentikResponseError("access_token nao retornado pelo authentik.")

        return payload

    def userinfo(self, access_token: str) -> dict[str, Any]:
        metadata = self.metadata()
        userinfo_endpoint = metadata.get("userinfo_endpoint")
        if not userinfo_endpoint:
            raise InvalidAuthentikResponseError("userinfo_endpoint ausente no discovery.")

        userinfo = self._request_json(
            "GET",
            userinfo_endpoint,
            "userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        if not userinfo:
            raise InvalidAuthentikResponseError("userinfo vazio retornado pelo authentik.")

        return userinfo

    def end_session_url(self, id_token: str | None = None) -> str | None:
        metadata = self.metadata()
        endpoint = metadata.get("end_session_endpoint")
        if not endpoint:
            return None

        params: dict[str, str] = {}
        if id_token:
            params["id_token_hint"] = id_token
        if self.config.redirect_uri:
            params["post_logout_redirect_uri"] = self.config.redirect_uri

        if not params:
            return str(endpoint)
        return f"{endpoint}?{urlencode(params)}"
