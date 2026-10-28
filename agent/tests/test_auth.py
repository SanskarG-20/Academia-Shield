"""
Unit tests for Auth, Keyring Store, Crypto, and Token Manager.
"""

import time
import pytest
from agent.auth.keyring_store import SecureStorageManager
from agent.auth.crypto import Ed25519KeyManager
from agent.auth.token_manager import TokenManager

def test_secure_storage_manager(tmp_path):
    storage = SecureStorageManager(service_name="TestService", storage_dir=str(tmp_path))
    
    assert storage.store_credential("test_key", "secret_value_123") is True
    assert storage.get_credential("test_key") == "secret_value_123"
    
    assert storage.delete_credential("test_key") is True
    assert storage.get_credential("test_key") is None

def test_ed25519_key_manager():
    km = Ed25519KeyManager()
    priv_pem, pub_hex = km.get_private_key_pem(), km.get_public_key_hex()
    
    assert priv_pem is not None
    assert len(pub_hex) > 0
    
    # Test signing
    payload = b"Hello Academia Shield"
    signature_b64 = km.sign(payload)
    assert len(signature_b64) > 0

    # Test loading
    km2 = Ed25519KeyManager(private_key_pem=priv_pem)
    assert km2.get_public_key_hex() == pub_hex

def test_token_manager(tmp_path):
    storage = SecureStorageManager(service_name="TestService", storage_dir=str(tmp_path))
    tm = TokenManager(storage=storage)
    
    # Fake JWT token header.payload.signature where payload has exp
    now = int(time.time())
    payload = f'{{"sub":"user123","exp":{now + 3600}}}'
    import base64
    b64_payload = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    fake_access_token = f"eyJhbGciOiJIUzI1NiJ9.{b64_payload}.fake_signature"
    fake_refresh_token = "ref_123456789"
    
    assert tm.save_tokens(fake_access_token, fake_refresh_token, device_id="dev_001") is True
    assert tm.get_access_token() == fake_access_token
    assert tm.get_refresh_token() == fake_refresh_token
    assert tm.get_device_id() == "dev_001"
    
    assert tm.is_access_token_expired(buffer_seconds=30) is False
    
    # Clear session
    assert tm.clear_session() is True
    assert tm.get_access_token() is None

from unittest.mock import patch, MagicMock
import urllib.error
import io

def test_api_client_refresh_on_401(tmp_path):
    from agent.api.client import APIClientAdapter
    storage = SecureStorageManager(service_name="TestService", storage_dir=str(tmp_path))
    tm = TokenManager(storage=storage)
    tm.save_tokens("expired_tok", "valid_ref_tok", "dev_001")
    
    client = APIClientAdapter(token_manager=tm)
    
    # Mock refresh call succeeding and active policy succeeding
    refresh_response = io.BytesIO(b'{"access_token": "new_access_tok", "refresh_token": "new_ref_tok"}')
    policy_response = io.BytesIO(b'{"policy_version": 1, "domain_rules": []}')
    
    # Sequence of urlopen responses:
    # 1. First policy request -> raises HTTPError(401)
    # 2. Refresh request -> returns refresh_response
    # 3. Retried policy request -> returns policy_response
    http_401 = urllib.error.HTTPError(
        url="http://127.0.0.1:8000/api/v1/agent/policies/active",
        code=401,
        msg="Unauthorized",
        hdrs={},
        fp=io.BytesIO(b'{"detail":"Unauthorized"}')
    )
    
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = [
            http_401,
            refresh_response,
            policy_response
        ]
        
        result = client._make_request("/api/v1/agent/policies/active", method="GET", auth_required=True)
        assert result.get("policy_version") == 1
        assert tm.get_access_token() == "new_access_tok"
        assert tm.get_refresh_token() == "new_ref_tok"

def test_api_client_auto_reenroll_on_refresh_failure(tmp_path):
    from agent.api.client import APIClientAdapter
    storage = SecureStorageManager(service_name="TestService", storage_dir=str(tmp_path))
    tm = TokenManager(storage=storage)
    # Stale token that is expired locally
    tm.save_tokens("stale_access_tok", "revoked_ref_tok", "dev_001")
    
    client = APIClientAdapter(token_manager=tm)
    
    http_401_refresh = urllib.error.HTTPError(
        url="http://127.0.0.1:8000/api/v1/auth/refresh",
        code=401,
        msg="Unauthorized",
        hdrs={},
        fp=io.BytesIO(b'{"detail":"Refresh token has been revoked"}')
    )
    enroll_response = io.BytesIO(b'{"access_token": "re_enrolled_access_tok", "refresh_token": "re_enrolled_ref_tok"}')
    policy_response = io.BytesIO(b'{"policy_version": 2, "domain_rules": []}')
    
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = [
            http_401_refresh,  # 1. Pre-flight token expiration triggers refresh -> 401
            enroll_response,   # 2. Re-enrollment fallback succeeds -> new tokens saved
            policy_response    # 3. Policy fetch proceeds with new access token
        ]
        
        result = client._make_request("/api/v1/agent/policies/active", method="GET", auth_required=True)
        assert result.get("policy_version") == 2
        assert tm.get_access_token() == "re_enrolled_access_tok"
        assert tm.get_refresh_token() == "re_enrolled_ref_tok"

