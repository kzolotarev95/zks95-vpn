"""Adapters for 3x-ui v3/legacy v2 and Remnawave v3 HTTP contracts.

The panel owns protocol configuration and connection URLs. No fabricated VLESS links.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote

import httpx


class PanelError(Exception):
    def __init__(self, message="Панель VPN недоступна или отклонила запрос"):
        super().__init__(message)


@dataclass
class RemoteAccess:
    url: str | None
    status: str
    expires_at: datetime | None = None
    used_bytes: int = 0


class Panel:
    def __init__(self, kind: str, base_url: str, credentials: dict, options: dict):
        self.kind, self.options, self.credentials = kind, options, credentials
        self.client = httpx.Client(
            base_url=base_url.rstrip("/") + "/", timeout=15, follow_redirects=False
        )

    def __enter__(self):
        token = self.credentials.get("token")
        if token:
            self.client.headers["Authorization"] = f"Bearer {token}"
        elif self.kind == "3x-ui":
            self.request(
                "POST",
                "login",
                json={
                    "username": self.credentials.get("username"),
                    "password": self.credentials.get("password"),
                },
            )
        else:
            raise PanelError("Укажите API-токен панели")
        return self

    def __exit__(self, *_):
        self.client.close()

    def request(self, method, path, *, missing=False, **kwargs):
        try:
            response = self.client.request(method, path, **kwargs)
            if missing and response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()
            if self.kind == "3x-ui":
                if not data.get("success"):
                    # Missing client is the sole tolerated semantic failure.
                    if missing and "not found" in str(data.get("msg", "")).lower():
                        return None
                    raise PanelError()
                return data.get("obj")
            return data["response"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            # Never expose an upstream URL, credential or response body.
            raise PanelError() from None

    def check(self):
        if self.kind == "remnawave":
            return self.request("GET", "api/users?size=1")
        for inbound_id in self.options["inbound_ids"]:
            inbound = self.request("GET", f"panel/api/inbounds/get/{inbound_id}")
            if not inbound.get("enable"):
                raise PanelError("Выбранный inbound выключен")
            if self.options.get("api_mode") == "legacy" and inbound.get("protocol") not in {
                "vless",
                "vmess",
            }:
                raise PanelError("Legacy-режим поддерживает VLESS/VMess inbound")
        return True

    def lookup(self, username):
        if self.kind == "remnawave":
            return self.request("GET", f"api/users/by-username/{quote(username)}", missing=True)
        if self.options.get("api_mode") != "legacy":
            return self.request("GET", f"panel/api/clients/get/{quote(username)}", missing=True)
        inbound_id = self.options["inbound_ids"][0]
        inbound = self.request("GET", f"panel/api/inbounds/get/{inbound_id}")
        settings = inbound.get("settings") or {}
        if isinstance(settings, str):
            settings = json.loads(settings)
        client = next((c for c in settings.get("clients", []) if c.get("email") == username), None)
        if not client:
            return None
        traffic = next(
            (c for c in inbound.get("clientStats", []) if c.get("email") == username), {}
        )
        return {"client": client, "usedTraffic": traffic.get("up", 0) + traffic.get("down", 0)}

    def ensure(self, username, identity, expires_at, devices):
        existing = self.lookup(username)
        expiry = expires_at.isoformat()
        if self.kind == "remnawave":
            payload = {
                "username": username,
                "status": "ACTIVE",
                "expireAt": expiry,
                "hwidDeviceLimit": devices,
                "trafficLimitBytes": self.options.get("traffic_limit_bytes", 0),
                "activeInternalSquads": self.options["squad_ids"],
            }
            if existing:
                result = self.request("PATCH", "api/users", json={**payload, "username": username})
            else:
                result = self.request(
                    "POST",
                    "api/users",
                    json={
                        **payload,
                        "vlessUuid": identity["id"],
                        "description": "ZKS95 VPN",
                    },
                )
            return self.parse(result)
        client = {
            "email": username,
            "id": identity["id"],
            "password": identity["password"],
            "subId": identity["sub_id"],
            "enable": True,
            "expiryTime": int(expires_at.timestamp() * 1000),
            "limitIp": devices,
            "limitHwid": devices,
            "totalGB": self.options.get("traffic_limit_bytes", 0),
            "flow": self.options.get("flow", ""),
        }
        if existing:
            # Preserve protocol secrets generated or normalized by the panel.
            stored = existing["client"]
            client = {
                **stored,
                **client,
                **{
                    key: stored[key]
                    for key in (
                        "id",
                        "password",
                        "auth",
                        "secret",
                        "subId",
                        "privateKey",
                        "publicKey",
                        "preSharedKey",
                        "allowedIPs",
                        "keepAlive",
                    )
                    if key in stored
                },
            }
        if self.options.get("api_mode") == "legacy":
            if existing:
                client = {**existing["client"], **client}
            inbound_id = self.options["inbound_ids"][0]
            path = f"updateClient/{identity['id']}" if existing else "addClient"
            self.request(
                "POST",
                "panel/api/inbounds/" + path,
                json={
                    "id": inbound_id,
                    "settings": json.dumps({"clients": [client]}),
                },
            )
        elif existing:
            self.request("POST", f"panel/api/clients/update/{quote(username)}", json=client)
        else:
            self.request(
                "POST",
                "panel/api/clients/add",
                json={
                    "client": client,
                    "inboundIds": self.options["inbound_ids"],
                },
            )
        result = self.lookup(username)
        if not result:
            raise PanelError("Клиент не появился в панели после создания")
        return self.parse(result)

    def disable(self, username):
        existing = self.lookup(username)
        if not existing:
            return
        if self.kind == "remnawave":
            self.request("PATCH", "api/users", json={"username": username, "status": "DISABLED"})
        elif self.options.get("api_mode") == "legacy":
            client = {**existing["client"], "enable": False}
            # Legacy support is deliberately restricted to UUID-based VLESS/VMess.
            self.request(
                "POST",
                f"panel/api/inbounds/updateClient/{client['id']}",
                json={
                    "id": self.options["inbound_ids"][0],
                    "settings": json.dumps({"clients": [client]}),
                },
            )
        else:
            # The modern endpoint replaces the full record, rather than patching it.
            self.request(
                "POST",
                f"panel/api/clients/update/{quote(username)}",
                json={**existing["client"], "enable": False},
            )

    def parse(self, data):
        if self.kind == "remnawave":
            return RemoteAccess(
                data.get("subscriptionUrl"),
                str(data["status"]).lower(),
                datetime.fromisoformat(data["expireAt"].replace("Z", "+00:00")),
                int(data.get("userTraffic", {}).get("usedTrafficBytes", 0)),
            )
        client = data["client"]
        sub_id = client.get("subId")
        url = (
            self.options["subscription_base_url"].rstrip("/") + "/" + quote(sub_id)
            if sub_id
            else None
        )
        expiry = client.get("expiryTime", 0)
        from datetime import UTC

        return RemoteAccess(
            url,
            "active" if client.get("enable") else "disabled",
            datetime.fromtimestamp(expiry / 1000, UTC) if expiry > 0 else None,
            int(data.get("usedTraffic", 0)),
        )
