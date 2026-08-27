"""Insurance-domain backend, isolated behind a provider abstraction.

Why this file exists
--------------------
Every insurance-provider-specific detail lives *here* and nowhere else. The
Agent and tools depend only on the :class:`InsuranceProvider` interface, so the
backend can be swapped (mock -> Facio sandbox -> a real carrier API) without
touching agent logic.

This public proof-of-concept ships with a :class:`MockInsuranceProvider` backed
by synthetic data. A :class:`FacioInsuranceProvider` skeleton shows exactly
where a public insurance sandbox would plug in. No credentials are ever
hard-coded; everything comes from environment variables via ``config.settings``.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from config import settings

_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "demo_claims.json")


class InsuranceError(Exception):
    """Domain-level error (claim/policy not found, backend unavailable...)."""


class InsuranceProvider(ABC):
    """The only insurance contract the rest of the system knows about."""

    name: str = "abstract"

    @abstractmethod
    def get_claim(self, claim_id: str) -> Dict[str, Any]:
        ...

    @abstractmethod
    def get_policy(self, policy_id: str) -> Dict[str, Any]:
        ...

    @abstractmethod
    def get_claim_history(self, policy_id: str) -> List[Dict[str, Any]]:
        ...


class MockInsuranceProvider(InsuranceProvider):
    """Synthetic, fully offline provider used by the public PoC.

    The data is intentionally not tied to any real carrier -- see the README
    disclaimer. It is deterministic, which is exactly what a reliable demo
    needs.
    """

    name = "mock"

    def __init__(self, data_path: str = _DATA_PATH):
        with open(os.path.abspath(data_path), "r", encoding="utf-8") as fh:
            self._data = json.load(fh)

    def get_claim(self, claim_id: str) -> Dict[str, Any]:
        claim = self._data["claims"].get(claim_id)
        if claim is None:
            raise InsuranceError(f"Claim not found: {claim_id}")
        return dict(claim)

    def get_policy(self, policy_id: str) -> Dict[str, Any]:
        policy = self._data["policies"].get(policy_id)
        if policy is None:
            raise InsuranceError(f"Policy not found: {policy_id}")
        return dict(policy)

    def get_claim_history(self, policy_id: str) -> List[Dict[str, Any]]:
        return list(self._data.get("claim_history", {}).get(policy_id, []))


class FacioInsuranceProvider(InsuranceProvider):
    """Skeleton adapter for Facio's public insurance sandbox.

    This is the plug-in point for a real sandbox. It is deliberately thin: the
    moment a sandbox endpoint + key are available, implement the request/response
    mapping here and set ``INSURANCE_PROVIDER=facio`` in ``.env``. Until then it
    fails loudly rather than pretending to work.

    Docs: https://developers.facio.io/
    """

    name = "facio"

    def __init__(self) -> None:
        self.base_url = settings.facio_base_url.rstrip("/")
        self.api_key = settings.facio_api_key
        if not self.api_key:
            raise InsuranceError(
                "INSURANCE_PROVIDER=facio requires FACIO_API_KEY. "
                "Set it in .env, or use the default mock provider."
            )

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}

    def _get(self, path: str) -> Dict[str, Any]:  # pragma: no cover - network
        import requests  # local import keeps requests optional for the mock path

        resp = requests.get(f"{self.base_url}{path}", headers=self._headers(), timeout=15)
        if resp.status_code == 404:
            raise InsuranceError(f"Not found via Facio: {path}")
        resp.raise_for_status()
        return resp.json()

    def get_claim(self, claim_id: str) -> Dict[str, Any]:  # pragma: no cover - network
        # TODO: map the sandbox response schema onto our canonical claim shape.
        return self._get(f"/claims/{claim_id}")

    def get_policy(self, policy_id: str) -> Dict[str, Any]:  # pragma: no cover - network
        return self._get(f"/policies/{policy_id}")

    def get_claim_history(self, policy_id: str) -> List[Dict[str, Any]]:  # pragma: no cover
        data = self._get(f"/policies/{policy_id}/claims")
        return data.get("items", []) if isinstance(data, dict) else list(data)


_PROVIDER_SINGLETON: Optional[InsuranceProvider] = None


def get_provider() -> InsuranceProvider:
    """Return the configured provider (cached).

    ``INSURANCE_PROVIDER=facio`` selects the sandbox adapter; anything else
    (the default) selects the offline mock.
    """
    global _PROVIDER_SINGLETON
    if _PROVIDER_SINGLETON is not None:
        return _PROVIDER_SINGLETON

    if settings.insurance_provider == "facio":
        _PROVIDER_SINGLETON = FacioInsuranceProvider()
    else:
        _PROVIDER_SINGLETON = MockInsuranceProvider()
    return _PROVIDER_SINGLETON
