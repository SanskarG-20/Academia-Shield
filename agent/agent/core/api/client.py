"""
Backend API Client for Academia Shield Agent.
Handles authentication header injection, retry logic, token refresh, and endpoint interaction.
"""

import requests
import json
import logging
from typing import Optional, Dict, Any, Union

logger = logging.getLogger(__name__)

DEFAULT_API_URL = "http://127.0.0.1:8000"

class ApiClient:
    def __init__(
        self,
        base_url: str = DEFAULT_API_URL,
        token_manager=None,
        device_identifier: Optional[str] = None
    ):
        self.base_url = base_url.rstrip("/")
        self.token_manager = token_manager
        self.device_identifier = device_identifier
        self.session = requests.Session()

    def _get_headers(self, custom_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        if self.device_identifier:
            headers["X-Device-Identifier"] = self.device_identifier

        if self.token_manager:
            token = self.token_manager.get_access_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"

        if custom_headers:
            headers.update(custom_headers)
        return headers

    def request(
        self,
        method: str,
        path: str,
        json_data: Optional[Any] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 10.0
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{path}" if path.startswith("/") else f"{self.base_url}/{path}"
        req_headers = self._get_headers(headers)

        try:
            resp = self.session.request(
                method=method,
                url=url,
                json=json_data,
                params=params,
                headers=req_headers,
                timeout=timeout
            )

            # Handle 401 Unauthorized by attempting token refresh
            if resp.status_code == 401 and self.token_manager:
                refresh_token = self.token_manager.get_refresh_token()
                if refresh_token:
                    refresh_resp = self.session.post(
                        f"{self.base_url}/api/v1/auth/refresh",
                        json={"refresh_token": refresh_token},
                        timeout=5.0
                    )
                    if refresh_resp.status_code == 200:
                        new_data = refresh_resp.json()
                        self.token_manager.save_tokens(
                            new_data.get("access_token"),
                            new_data.get("refresh_token") or refresh_token,
                            new_data.get("expires_in", 3600)
                        )
                        # Retry original request with refreshed token
                        req_headers = self._get_headers(headers)
                        resp = self.session.request(
                            method=method,
                            url=url,
                            json=json_data,
                            params=params,
                            headers=req_headers,
                            timeout=timeout
                        )

            try:
                data = resp.json()
            except Exception:
                data = {"raw": resp.text}

            return {
                "status_code": resp.status_code,
                "data": data,
                "ok": resp.ok
            }
        except requests.exceptions.RequestException as e:
            logger.debug(f"API Request to {url} failed: {e}")
            return {
                "status_code": 0,
                "error": str(e),
                "ok": False,
                "data": {}
            }

    def get(self, path: str, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        return self.request("GET", path, params=params, headers=headers)

    def post(self, path: str, json: Optional[Any] = None, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        return self.request("POST", path, json_data=json, headers=headers)

    def put(self, path: str, json: Optional[Any] = None, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        return self.request("PUT", path, json_data=json, headers=headers)

    def delete(self, path: str, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        return self.request("DELETE", path, headers=headers)
