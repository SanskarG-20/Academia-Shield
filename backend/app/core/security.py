"""
Security, Password Hashing, and JWT Token Management using direct bcrypt.
"""

import uuid
import bcrypt
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple, Union
import jwt
from .config import settings

def hash_password(password: str) -> str:
    """Hash plain-text password using bcrypt (max 72 bytes)."""
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password against bcrypt hashed password."""
    try:
        pwd_bytes = plain_password.encode("utf-8")[:72]
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pwd_bytes, hash_bytes)
    except Exception:
        return False

def hash_token(token: str) -> str:
    """Calculate SHA-256 hash of refresh token for zero plain-text storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token with short expiry."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "jti": str(uuid.uuid4()),
        "exp": expire,
        "iat": now,
        "type": "access",
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE
    })
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

def create_refresh_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT refresh token."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode.update({
        "jti": str(uuid.uuid4()),
        "exp": expire,
        "iat": now,
        "type": "refresh",
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE
    })
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

def decode_token(token: str) -> Dict[str, Any]:
    """Decode and validate JWT token claims (issuer, audience, expiry, signature)."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE
        )
        return payload
    except jwt.PyJWTError as e:
        raise ValueError(f"Invalid token: {e}")

# ==============================================================================
# Ed25519 Server Policy Signing
# ==============================================================================

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
import json

# Derive deterministic or random Ed25519 server key from JWT_SECRET seed or configured key
if settings.RELEASE_SIGNING_PRIVATE_KEY:
    try:
        _SERVER_PRIVATE_KEY = ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(settings.RELEASE_SIGNING_PRIVATE_KEY))
    except Exception:
        _SERVER_SEED = hashlib.sha256(f"ACADEMIA_SHIELD_SERVER_ED25519_{settings.JWT_SECRET}".encode("utf-8")).digest()
        _SERVER_PRIVATE_KEY = ed25519.Ed25519PrivateKey.from_private_bytes(_SERVER_SEED)
else:
    _SERVER_SEED = hashlib.sha256(f"ACADEMIA_SHIELD_SERVER_ED25519_{settings.JWT_SECRET}".encode("utf-8")).digest()
    _SERVER_PRIVATE_KEY = ed25519.Ed25519PrivateKey.from_private_bytes(_SERVER_SEED)

_SERVER_PUBLIC_KEY = _SERVER_PRIVATE_KEY.public_key()

def get_server_public_key() -> str:
    """Return backend Ed25519 public key as hex string."""
    pub_bytes = _SERVER_PUBLIC_KEY.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    return pub_bytes.hex()

def get_server_public_key_b64() -> str:
    """Return backend Ed25519 public key as base64 string."""
    import base64
    pub_bytes = _SERVER_PUBLIC_KEY.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    return base64.b64encode(pub_bytes).decode("utf-8")

def sign_policy_payload(canonical_data: Dict[str, Any]) -> Tuple[str, str]:
    """
    Calculate canonical SHA-256 integrity hash and sign with server Ed25519 private key.
    Returns: (integrity_hash, signature_hex)
    """
    canonical_json = json.dumps(canonical_data, sort_keys=True).encode("utf-8")
    integrity_hash = hashlib.sha256(canonical_json).hexdigest()
    signature_bytes = _SERVER_PRIVATE_KEY.sign(integrity_hash.encode("utf-8"))
    return integrity_hash, signature_bytes.hex()

def verify_policy_signature(integrity_hash_or_dict: Union[str, Dict[str, Any]], signature_hex: str, public_key_hex: Optional[str] = None) -> bool:
    """Verify Ed25519 signature over policy integrity hash or dictionary containing integrity_hash."""
    try:
        if isinstance(integrity_hash_or_dict, dict):
            hash_str = integrity_hash_or_dict.get("integrity_hash", "")
        else:
            hash_str = str(integrity_hash_or_dict)

        if not hash_str:
            return False

        if public_key_hex:
            pub_key = ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        else:
            pub_key = _SERVER_PUBLIC_KEY
        pub_key.verify(bytes.fromhex(signature_hex), hash_str.encode("utf-8"))
        return True
    except Exception:
        return False


def sign_release_manifest(manifest_dict: Dict[str, Any]) -> str:
    """Sign canonical release manifest dictionary with backend signing key."""
    # Canonicalize dictionary excluding the signature field itself
    filtered = {k: v for k, v in manifest_dict.items() if k != "signature"}
    canonical_json = json.dumps(filtered, sort_keys=True).encode("utf-8")
    manifest_hash = hashlib.sha256(canonical_json).hexdigest()
    signature_bytes = _SERVER_PRIVATE_KEY.sign(manifest_hash.encode("utf-8"))
    return signature_bytes.hex()

def verify_release_manifest_signature(manifest_dict: Dict[str, Any], signature_hex: str) -> bool:
    """Verify signature of a release manifest."""
    try:
        filtered = {k: v for k, v in manifest_dict.items() if k != "signature"}
        canonical_json = json.dumps(filtered, sort_keys=True).encode("utf-8")
        manifest_hash = hashlib.sha256(canonical_json).hexdigest()
        _SERVER_PUBLIC_KEY.verify(bytes.fromhex(signature_hex), manifest_hash.encode("utf-8"))
        return True
    except Exception:
        return False

def create_device_access_token(device_id: str, student_id: str, platform: str, expires_delta: Optional[timedelta] = None) -> str:
    """Create a device-scoped JWT access token."""
    data = {
        "sub": student_id,
        "device_id": device_id,
        "platform": platform,
        "scope": "device_agent"
    }
    return create_access_token(data, expires_delta=expires_delta)


