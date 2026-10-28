"""
Token Manager for Academia Shield Local Agent.
Stores and rotates short-lived access tokens and refresh tokens using PlatformSecureStorage.
"""

import time
import json
import logging
from typing import Optional, Dict, Any

from ...platforms.base import PlatformSecureStorage

logger = logging.getLogger(__name__)

KEY_ACCESS_TOKEN = "access_token"
KEY_REFRESH_TOKEN = "refresh_token"
KEY_TOKEN_EXPIRY = "token_expires_at"

class TokenManager:
    def __init__(self, storage: PlatformSecureStorage):
        self.storage = storage

    def save_tokens(self, access_token: str, refresh_token: Optional[str] = None, expires_in_seconds: int = 3600):
        self.storage.store_secret(KEY_ACCESS_TOKEN, access_token)
        if refresh_token:
            self.storage.store_secret(KEY_REFRESH_TOKEN, refresh_token)
        expiry_ts = str(int(time.time()) + expires_in_seconds)
        self.storage.store_secret(KEY_TOKEN_EXPIRY, expiry_ts)

    def get_access_token(self) -> Optional[str]:
        return self.storage.retrieve_secret(KEY_ACCESS_TOKEN)

    def get_refresh_token(self) -> Optional[str]:
        return self.storage.retrieve_secret(KEY_REFRESH_TOKEN)

    def is_token_expired(self) -> bool:
        expiry_str = self.storage.retrieve_secret(KEY_TOKEN_EXPIRY)
        if not expiry_str:
            return True
        try:
            exp = int(expiry_str)
            # 60-second safety margin
            return time.time() >= (exp - 60)
        except Exception:
            return True

    def clear_tokens(self):
        self.storage.delete_secret(KEY_ACCESS_TOKEN)
        self.storage.delete_secret(KEY_REFRESH_TOKEN)
        self.storage.delete_secret(KEY_TOKEN_EXPIRY)
