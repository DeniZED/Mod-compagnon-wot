"""Client de l'API publique Wargaming (GAR-006, section 9).

Optionnel : cache, timeouts, retry borne. Le compagnon reste utilisable hors
ligne sans l'API. La cle API n'est jamais ecrite dans les logs (section 10.2).

`requests` est une dependance FACULTATIVE (extra "api"). Le module s'importe
sans elle ; seul un appel reseau effectif la requiert.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

logger = logging.getLogger("wot_companion.wgapi")

DEFAULT_BASE_URL = "https://api.worldoftanks.eu/wot"


class WargamingAPIError(RuntimeError):
    pass


class WargamingAPIClient:
    def __init__(
        self,
        application_id: str | None,
        base_url: str = DEFAULT_BASE_URL,
        timeout_s: float = 5.0,
        max_retries: int = 2,
        cache_ttl_s: float = 3600.0,
        enabled: bool = False,
    ) -> None:
        self.application_id = application_id
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.cache_ttl_s = cache_ttl_s
        self.enabled = enabled and bool(application_id)
        self._cache: dict[str, tuple[float, Any]] = {}

    def is_available(self) -> bool:
        return self.enabled

    # ---- Endpoints usuels (profil garage) ----------------------------------
    def account_info(self, account_id: int) -> dict[str, Any]:
        return self._get("/account/info/", {"account_id": account_id})

    def vehicle_stats(self, account_id: int, tank_id: int) -> dict[str, Any]:
        return self._get("/tanks/stats/", {"account_id": account_id, "tank_id": tank_id})

    def tankopedia_vehicle(self, tank_id: int) -> dict[str, Any]:
        return self._get("/encyclopedia/vehicles/", {"tank_id": tank_id})

    # ---- Transport ---------------------------------------------------------
    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            raise WargamingAPIError("API Wargaming desactivee (local-first par defaut).")

        cache_key = path + "?" + json.dumps(params, sort_keys=True)
        cached = self._cache.get(cache_key)
        now = time.time()
        if cached and now - cached[0] < self.cache_ttl_s:
            return cached[1]

        try:
            import requests  # dependance facultative
        except ImportError as exc:  # pragma: no cover
            raise WargamingAPIError(
                "Le module 'requests' est requis pour l'API (extra 'api')."
            ) from exc

        url = self.base_url + path
        query = {"application_id": self.application_id, **params}
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = requests.get(url, params=query, timeout=self.timeout_s)
                resp.raise_for_status()
                data = resp.json()
                if data.get("status") != "ok":
                    raise WargamingAPIError(f"Reponse API en erreur: {data.get('error')}")
                result = data.get("data", {})
                self._cache[cache_key] = (now, result)
                return result
            except Exception as exc:  # retry borne avec backoff
                last_exc = exc
                # Ne jamais loguer la cle API : on log l'URL sans query.
                logger.warning("API WoT echec (tentative %d): %s", attempt + 1, exc)
                if attempt < self.max_retries:
                    time.sleep(min(2 ** attempt, 4))
        raise WargamingAPIError(f"Echec API apres retries: {last_exc}")
