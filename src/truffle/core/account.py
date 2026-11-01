"""LeanCloud 账号客户端（直接调 REST，无第三方依赖）。

需要三个凭据（LeanCloud 控制台 → 设置 → 应用凭证 / 域名）：
  - lc_app_id     AppID
  - lc_app_key    AppKey
  - lc_server_url API 域名（如 https://xxxx.api.lncldglobal.com）
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from ..config import AppSettings


class AccountError(Exception):
    pass


class Account:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def configured(self) -> bool:
        return bool(
            self.settings.lc_app_id and self.settings.lc_app_key and self.settings.lc_server_url
        )

    @property
    def username(self) -> str:
        return self.settings.account_username

    def logged_in(self) -> bool:
        return bool(self.settings.account_token)

    # ---------- 内部 ----------
    def _headers(self, with_session: bool = False) -> dict[str, str]:
        headers = {
            "X-LC-Id": self.settings.lc_app_id,
            "X-LC-Key": self.settings.lc_app_key,
            "Content-Type": "application/json",
        }
        if with_session and self.settings.account_token:
            headers["X-LC-Session"] = self.settings.account_token
        return headers

    def _request(self, method: str, path: str, data: dict | None = None, session: bool = False) -> dict:
        if not self.configured():
            raise AccountError("尚未配置 LeanCloud（设置 → 常规设置）。")
        url = self.settings.lc_server_url.rstrip("/") + path
        body = json.dumps(data).encode("utf-8") if data is not None else None
        request = urllib.request.Request(url, data=body, headers=self._headers(session), method=method)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
            except Exception:  # noqa: BLE001
                payload = {}
            raise AccountError(payload.get("error") or f"HTTP {exc.code}") from exc
        except Exception as exc:  # noqa: BLE001
            raise AccountError(str(exc)) from exc

    # ---------- 对外 ----------
    def signup(self, username: str, password: str) -> dict:
        return self._request("POST", "/1.1/users", {"username": username, "password": password})

    def login(self, username: str, password: str) -> dict:
        query = urllib.parse.urlencode({"username": username, "password": password})
        return self._request("GET", "/1.1/login?" + query)

    def me(self) -> dict:
        return self._request("GET", "/1.1/users/me", session=True)

    def logout(self) -> None:
        try:
            self._request("POST", "/1.1/logout", session=True)
        except AccountError:
            pass

    def save_session(self, result: dict) -> None:
        self.settings.account_token = str(result.get("sessionToken", ""))
        self.settings.account_username = str(result.get("username", ""))
        self.settings.save()

    def clear_session(self) -> None:
        self.settings.account_token = ""
        self.settings.account_username = ""
        self.settings.save()
