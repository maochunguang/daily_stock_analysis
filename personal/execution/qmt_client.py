"""Stdlib HTTP client for the Windows QMT bridge.

The bridge runs on the Windows QMT machine. This client is used by the macOS
personal layer and intentionally depends only on the standard library.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional


class QmtBridgeError(RuntimeError):
    pass


@dataclass
class QmtBridgeClient:
    base_url: str
    token: str = ""
    timeout: float = 10.0

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        body: Optional[dict[str, Any]] = None,
    ) -> Any:
        url = self.base_url.rstrip("/") + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise QmtBridgeError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise QmtBridgeError(f"bridge unreachable: {exc}") from exc
        return json.loads(payload) if payload else None

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def quote(self, codes: list[str]) -> dict[str, Any]:
        return self._request("GET", "/quote", params={"codes": ",".join(codes)})

    def positions(self) -> dict[str, Any]:
        return self._request("GET", "/positions")

    def orders(self) -> dict[str, Any]:
        return self._request("GET", "/orders")

    def trades(self) -> dict[str, Any]:
        return self._request("GET", "/trades")

    def place_order(
        self,
        *,
        account_id: str,
        code: str,
        side: str,
        quantity: int,
        price: Optional[float] = None,
        price_type: str = "limit",
        idempotency_key: str,
        strategy: str = "dsa_personal",
        remark: str = "",
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/orders",
            body={
                "account_id": account_id,
                "code": code,
                "side": side,
                "quantity": quantity,
                "price": price,
                "price_type": price_type,
                "idempotency_key": idempotency_key,
                "strategy": strategy,
                "remark": remark,
            },
        )

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        return self._request("POST", f"/orders/{urllib.parse.quote(order_id)}/cancel")

    def reconcile(self) -> dict[str, Any]:
        return self._request("POST", "/reconcile")
