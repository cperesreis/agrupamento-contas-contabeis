"""
Cliente de autenticacao e consumo de servicos CISSPoder via INTEGRIM.

Este modulo foi preservado como modo legado de login humano quando
AUTH_PROVIDER=integrim. Com AUTH_PROVIDER=authentik, o login do usuario passa
a ser feito por OIDC no authentik e este cliente deve ser usado apenas se a
aplicacao precisar de integracao tecnica futura com servicos CISS/INTEGRIM.

As credenciais sensiveis sao lidas do ambiente e nunca devem ser registradas
em logs. O token retornado deve ser mantido apenas em memoria/sessao.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import logging
import os
from typing import Any

from dotenv import load_dotenv
import requests
from requests import Response


load_dotenv()

logger = logging.getLogger(__name__)


class IntegrimError(Exception):
    """Erro base para falhas de comunicacao com o INTEGRIM."""

    user_message = "Nao foi possivel concluir a autenticacao no momento."


class IntegrimConfigError(IntegrimError):
    """Configuracao incompleta para autenticar no INTEGRIM."""

    user_message = "Configuracao de autenticacao incompleta."


class InvalidCredentialsError(IntegrimError):
    """Credenciais recusadas pelo INTEGRIM."""

    user_message = "Usuario ou senha incorretos"


class IntegrimUnavailableError(IntegrimError):
    """Timeout ou falha de conexao com o INTEGRIM."""

    user_message = "Servico de autenticacao indisponivel no momento. Tente novamente em instantes."


class InvalidIntegrimResponseError(IntegrimError):
    """Resposta ausente, invalida ou nao JSON do INTEGRIM."""

    user_message = "Nao foi possivel concluir a autenticacao no momento."


@dataclass(frozen=True)
class IntegrimConfig:
    cim_host: str
    client_id: str
    client_secret: str
    timeout_seconds: float = 15

    @classmethod
    def from_env(cls) -> "IntegrimConfig":
        cim_host = os.getenv("CIM_HOST", "").strip().rstrip("/")
        client_id = os.getenv("CISS_CLIENT_ID", "").strip()
        client_secret = os.getenv("CISS_CLIENT_SECRET", "").strip()
        timeout_raw = os.getenv("REQUEST_TIMEOUT_SECONDS", "15").strip()

        faltando = [
            nome
            for nome, valor in {
                "CIM_HOST": cim_host,
                "CISS_CLIENT_ID": client_id,
                "CISS_CLIENT_SECRET": client_secret,
            }.items()
            if not valor
        ]
        if faltando:
            raise IntegrimConfigError(
                "Variaveis de ambiente ausentes para autenticacao INTEGRIM: "
                f"{', '.join(faltando)}."
            )

        try:
            timeout_seconds = float(timeout_raw)
        except ValueError as exc:
            raise IntegrimConfigError(
                "REQUEST_TIMEOUT_SECONDS deve ser um numero."
            ) from exc

        return cls(
            cim_host=cim_host,
            client_id=client_id,
            client_secret=client_secret,
            timeout_seconds=timeout_seconds,
        )


def _username_hash(username: str) -> str:
    return hashlib.sha256(username.strip().lower().encode("utf-8")).hexdigest()[:12]


def _json_response(response: Response, endpoint: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        logger.warning(
            "Resposta nao JSON do INTEGRIM: status=%s endpoint=%s",
            response.status_code,
            endpoint,
        )
        raise InvalidIntegrimResponseError("Resposta nao JSON do INTEGRIM.") from exc

    if not isinstance(payload, dict):
        logger.warning(
            "Resposta JSON inesperada do INTEGRIM: status=%s endpoint=%s tipo=%s",
            response.status_code,
            endpoint,
            type(payload).__name__,
        )
        raise InvalidIntegrimResponseError("Resposta JSON inesperada do INTEGRIM.")

    return payload


class IntegrimClient:
    def __init__(self, config: IntegrimConfig | None = None, access_token: str | None = None):
        self.config = config or IntegrimConfig.from_env()
        self.access_token = access_token

    @property
    def auth_url(self) -> str:
        return f"{self.config.cim_host}/cisspoder-auth/oauth/token"

    def service_url(self, nome_servico: str) -> str:
        nome_servico = nome_servico.strip().lstrip("/")
        if not nome_servico:
            raise ValueError("Nome do servico INTEGRIM nao informado.")
        return f"{self.config.cim_host}/cisspoder-service/{nome_servico}"

    def authenticate(self, username: str, password: str) -> dict[str, Any]:
        endpoint = "/cisspoder-auth/oauth/token"
        data = {
            "username": username,
            "password": password,
            "grant_type": "password",
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        try:
            response = requests.post(
                self.auth_url,
                data=data,
                headers=headers,
                timeout=self.config.timeout_seconds,
            )
        except requests.Timeout as exc:
            logger.warning(
                "Timeout ao conectar no CIM: host=%s timeout=%ss",
                self.config.cim_host,
                self.config.timeout_seconds,
            )
            raise IntegrimUnavailableError("Timeout ao conectar no CIM.") from exc
        except requests.ConnectionError as exc:
            logger.warning("Falha de conexao com o CIM: host=%s", self.config.cim_host)
            raise IntegrimUnavailableError("Falha de conexao com o CIM.") from exc
        except requests.RequestException as exc:
            logger.warning("Falha HTTP ao autenticar no INTEGRIM: endpoint=%s", endpoint)
            raise IntegrimUnavailableError("Falha HTTP ao autenticar no INTEGRIM.") from exc

        if response.status_code in (400, 401):
            logger.info(
                "Falha de autenticacao INTEGRIM: status=%s endpoint=%s username_hash=%s",
                response.status_code,
                endpoint,
                _username_hash(username),
            )
            raise InvalidCredentialsError("Credenciais invalidas.")

        if not response.ok:
            logger.warning(
                "Erro HTTP do INTEGRIM na autenticacao: status=%s endpoint=%s",
                response.status_code,
                endpoint,
            )
            raise IntegrimError("Erro HTTP do INTEGRIM.")

        payload = _json_response(response, endpoint)
        access_token = payload.get("access_token")
        if not access_token:
            logger.warning("Token nao retornado pelo INTEGRIM: endpoint=%s", endpoint)
            raise InvalidIntegrimResponseError("Token nao retornado pelo INTEGRIM.")

        self.access_token = str(access_token)
        return payload

    def post_service(self, nome_servico: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.access_token:
            raise IntegrimConfigError("Token de acesso nao informado para consumo de servico.")

        endpoint = f"/cisspoder-service/{nome_servico.strip().lstrip('/')}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        }

        try:
            response = requests.post(
                self.service_url(nome_servico),
                json=body or {},
                headers=headers,
                timeout=self.config.timeout_seconds,
            )
        except requests.Timeout as exc:
            logger.warning(
                "Timeout ao consumir servico INTEGRIM: endpoint=%s timeout=%ss",
                endpoint,
                self.config.timeout_seconds,
            )
            raise IntegrimUnavailableError("Timeout ao consumir servico INTEGRIM.") from exc
        except requests.ConnectionError as exc:
            logger.warning("Falha de conexao ao consumir servico INTEGRIM: endpoint=%s", endpoint)
            raise IntegrimUnavailableError("Falha de conexao ao consumir servico INTEGRIM.") from exc
        except requests.RequestException as exc:
            logger.warning("Falha HTTP ao consumir servico INTEGRIM: endpoint=%s", endpoint)
            raise IntegrimUnavailableError("Falha HTTP ao consumir servico INTEGRIM.") from exc

        if response.status_code in (400, 401):
            raise InvalidCredentialsError("Credenciais invalidas.")

        if not response.ok:
            logger.warning(
                "Erro HTTP do INTEGRIM no servico: status=%s endpoint=%s",
                response.status_code,
                endpoint,
            )
            raise IntegrimError("Erro HTTP do INTEGRIM.")

        return _json_response(response, endpoint)
