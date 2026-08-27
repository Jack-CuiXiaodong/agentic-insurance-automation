"""Insurance-domain backend, isolated behind a provider abstraction.

Why this file exists
--------------------
Every carrier-specific detail lives *here* and nowhere else. The Agent and tools
depend only on the :class:`InsuranceProvider` interface, so the backend can be
swapped (offline mock -> a carrier's core policy/claims system) without touching
agent logic.

This public proof-of-concept ships with a :class:`MockCarrierProvider` backed by
synthetic motor-claim data. :class:`CoreSystemProvider` is the skeleton showing
exactly where a real carrier core system plugs in. No credentials are ever
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
    """Domain-level error (报案/保单 not found, backend unavailable...)."""


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


class MockCarrierProvider(InsuranceProvider):
    """Synthetic, fully offline provider used by the public PoC.

    The data is intentionally not tied to any real carrier, policy, vehicle or
    invoice -- see the README disclaimer. It is deterministic, which is exactly
    what a reliable demo needs.
    """

    name = "mock"

    def __init__(self, data_path: str = _DATA_PATH):
        with open(os.path.abspath(data_path), "r", encoding="utf-8") as fh:
            self._data = json.load(fh)

    def get_claim(self, claim_id: str) -> Dict[str, Any]:
        claim = self._data["claims"].get(claim_id)
        if claim is None:
            raise InsuranceError(f"报案不存在：{claim_id}")
        return dict(claim)

    def get_policy(self, policy_id: str) -> Dict[str, Any]:
        policy = self._data["policies"].get(policy_id)
        if policy is None:
            raise InsuranceError(f"保单不存在：{policy_id}")
        return dict(policy)

    def get_claim_history(self, policy_id: str) -> List[Dict[str, Any]]:
        return list(self._data.get("claim_history", {}).get(policy_id, []))


class CoreSystemProvider(InsuranceProvider):
    """Skeleton adapter for a carrier's core policy/claims system.

    This is the plug-in point for a real backend. It is deliberately thin: the
    moment an endpoint + credential are available, implement the request/response
    mapping here and set ``INSURANCE_PROVIDER=core`` in ``.env``. Until then it
    fails loudly rather than pretending to work.

    Note that a carrier core system may expose no HTTP API at all. In that case
    this is *not* the seam to force it through -- implement a provider that
    drives the system's own screens with the shared Playwright helper in
    ``browser/driver.py`` instead. The interface below stays identical either
    way, which is the whole point of putting it here.
    """

    name = "core"

    def __init__(self) -> None:
        self.base_url = settings.core_api_base_url.rstrip("/")
        self.api_key = settings.core_api_key
        if not self.api_key:
            raise InsuranceError(
                "INSURANCE_PROVIDER=core 需要设置 CORE_API_KEY。"
                "请在 .env 中配置，或改用默认的 mock provider。"
            )

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}

    def _get(self, path: str) -> Dict[str, Any]:  # pragma: no cover - network
        import requests  # local import keeps requests optional for the mock path

        resp = requests.get(f"{self.base_url}{path}", headers=self._headers(), timeout=15)
        if resp.status_code == 404:
            raise InsuranceError(f"核心系统未找到：{path}")
        resp.raise_for_status()
        return resp.json()

    def get_claim(self, claim_id: str) -> Dict[str, Any]:  # pragma: no cover - network
        # TODO: map the core system's response schema onto our canonical shape.
        return self._get(f"/claims/{claim_id}")

    def get_policy(self, policy_id: str) -> Dict[str, Any]:  # pragma: no cover - network
        return self._get(f"/policies/{policy_id}")

    def get_claim_history(self, policy_id: str) -> List[Dict[str, Any]]:  # pragma: no cover
        data = self._get(f"/policies/{policy_id}/claims")
        return data.get("items", []) if isinstance(data, dict) else list(data)


_PROVIDER_SINGLETON: Optional[InsuranceProvider] = None


def get_provider() -> InsuranceProvider:
    """Return the configured provider (cached).

    ``INSURANCE_PROVIDER=core`` selects the core-system adapter; anything else
    (the default) selects the offline mock.
    """
    global _PROVIDER_SINGLETON
    if _PROVIDER_SINGLETON is not None:
        return _PROVIDER_SINGLETON

    if settings.insurance_provider == "core":
        _PROVIDER_SINGLETON = CoreSystemProvider()
    else:
        _PROVIDER_SINGLETON = MockCarrierProvider()
    return _PROVIDER_SINGLETON
