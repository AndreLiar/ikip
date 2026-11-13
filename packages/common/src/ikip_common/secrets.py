"""Secrets provider port + adapters (Story 6.4, ADR 0003 ports-and-adapters).

Where a secret VALUE comes from is an environment concern: locally from `.env` / the
process env; in prod from **Azure Key Vault via managed identity** (no secrets in code or
images). `Settings` stays the typed local loader; this port is the prod seam used by the
deployment (Story 6.6) to fetch/rotate secrets without code changes.

`build_secrets_provider` returns the Key Vault adapter when `AZURE_KEY_VAULT_URL` is set
(lazy SDK + managed identity), else the env adapter. Values are never logged.
"""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable


@runtime_checkable
class SecretsProvider(Protocol):
    def get_secret(self, name: str) -> str | None:
        """Return the secret's value, or None if absent. `name` is the logical key
        (e.g. 'AZURE_OPENAI_API_KEY'); adapters map it to their backend's naming."""
        ...


class EnvSecretsProvider:
    """Reads secrets from the process environment (populated from `.env` locally)."""

    def get_secret(self, name: str) -> str | None:
        return os.environ.get(name)


class KeyVaultSecretsProvider:
    """Azure Key Vault via managed identity (lazy SDK; needs the `keyvault` group + a
    `DefaultAzureCredential` in the environment). Key Vault names can't contain `_`, so the
    logical `A_B` maps to the secret `a-b`. [untested live] — exercised via EnvSecretsProvider
    in CI; a real fetch needs an Azure identity + a vault.
    """

    def __init__(self, vault_url: str) -> None:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient

        self._client = SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())

    @staticmethod
    def _to_vault_name(name: str) -> str:
        return name.replace("_", "-").lower()

    def get_secret(self, name: str) -> str | None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            return self._client.get_secret(self._to_vault_name(name)).value
        except ResourceNotFoundError:
            return None


def build_secrets_provider(settings=None) -> SecretsProvider:  # noqa: ANN001
    """Key Vault when `AZURE_KEY_VAULT_URL` is configured (+ SDK installed), else env."""
    from ikip_common.config import get_settings

    s = settings or get_settings()
    vault_url = getattr(s, "azure_key_vault_url", None)
    if vault_url:
        try:
            return KeyVaultSecretsProvider(vault_url)
        except ImportError:
            import logging

            logging.getLogger("ikip_common").warning(
                "AZURE_KEY_VAULT_URL set but azure-keyvault SDK not installed "
                "(install the 'keyvault' group); falling back to env secrets."
            )
    return EnvSecretsProvider()
