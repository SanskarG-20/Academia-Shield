"""
Authentication & Authorization Business Logic Service.
"""

from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..core.security import (
    hash_password,
    verify_password,
    hash_token,
    create_access_token,
    create_refresh_token,
    create_device_access_token,
    decode_token
)
from ..core.config import settings
from ..models.user import User
from ..models.token import RefreshToken
from ..models.device import AgentDevice
from ..schemas.auth import RegisterRequest, LoginRequest, TokenResponse

_FAILED_ATTEMPTS: dict[str, list[datetime]] = {}
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_WINDOW_SECONDS = 300

class AuthService:
    """Manages user registration, secure authentication, and token rotation."""

    @staticmethod
    def register_user(req: RegisterRequest, db: Session) -> User:
        email_clean = req.email.strip().lower()
        if db.query(User).filter(User.email == email_clean).first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An account with this email address already exists."
            )

        hashed_pwd = hash_password(req.password)
        user = User(
            email=email_clean,
            password_hash=hashed_pwd,
            full_name=req.full_name.strip(),
            role=req.role,
            institutional_id=(req.student_id or req.employee_id or None),
            department=req.department.strip() if req.department else None,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def login_user(req: LoginRequest, db: Session) -> TokenResponse:
        email_raw = req.email or req.email_or_id or ""
        email_clean = email_raw.strip().lower()
        if not email_clean:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email or user identifier is required."
            )
        now = datetime.now(timezone.utc)

        # Check rate limiting / failed attempts
        attempts = _FAILED_ATTEMPTS.get(email_clean, [])
        attempts = [t for t in attempts if (now - t).total_seconds() < LOCKOUT_WINDOW_SECONDS]
        _FAILED_ATTEMPTS[email_clean] = attempts

        if len(attempts) >= MAX_FAILED_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed login attempts. Account temporarily locked. Please try again in 5 minutes."
            )

        user = db.query(User).filter(User.email == email_clean).first()
        if not user or not verify_password(req.password, user.password_hash):
            _FAILED_ATTEMPTS.setdefault(email_clean, []).append(now)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid institutional credentials or password."
            )

        # Clear failed attempts on successful login
        _FAILED_ATTEMPTS.pop(email_clean, None)

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive. Please contact administrator."
            )

        # Handle device binding if provided
        device_id = None
        if req.device_identifier:
            device = db.query(AgentDevice).filter(AgentDevice.device_identifier == req.device_identifier).first()
            if device:
                device_id = device.id

        return AuthService._issue_tokens(user, device_id, db)

    @staticmethod
    def refresh_tokens(raw_refresh_token: str, db: Session) -> TokenResponse:
        tok_hash = hash_token(raw_refresh_token)

        # 1. Locate session in DB by token hash
        db_token = db.query(RefreshToken).filter(
            RefreshToken.token_hash == tok_hash
        ).first()

        user_id = None
        device_id = None

        if db_token:
            if db_token.revoked_at is not None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Refresh token has been revoked"
                )
            user_id = db_token.user_id
            device_id = db_token.device_id
        else:
            # 2. Check if it's a valid JWT refresh token not recorded by hash
            try:
                payload = decode_token(raw_refresh_token)
                if payload.get("type") != "refresh":
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Token provided is not a refresh token"
                    )
                user_id = payload.get("sub")
                device_id = payload.get("device_id")
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired refresh token"
                )

            if user_id:
                db_token = db.query(RefreshToken).filter(
                    RefreshToken.user_id == user_id,
                    RefreshToken.revoked_at.is_(None)
                ).order_by(RefreshToken.created_at.desc()).first()

        if not db_token or not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token is revoked or unrecognized"
            )

        now = datetime.now(timezone.utc)
        tok_expire = db_token.expires_at.replace(tzinfo=timezone.utc) if db_token.expires_at.tzinfo is None else db_token.expires_at

        if tok_expire < now:
            db_token.revoked_at = now
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has expired"
            )

        # Rotate refresh token: revoke current token
        db_token.revoked_at = now
        db.commit()

        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account inactive or deleted"
            )

        return AuthService._issue_tokens(user, device_id or db_token.device_id, db)

    @staticmethod
    def logout_user(raw_refresh_token: str, user_id: str, db: Session) -> bool:
        if raw_refresh_token:
            tok_hash = hash_token(raw_refresh_token)
            db.query(RefreshToken).filter(RefreshToken.token_hash == tok_hash).update({"revoked_at": datetime.now(timezone.utc)})
        else:
            db.query(RefreshToken).filter(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)).update({"revoked_at": datetime.now(timezone.utc)})
        
        db.commit()
        return True

    @staticmethod
    def _issue_tokens(user: User, device_id: Optional[str], db: Session) -> TokenResponse:
        if device_id:
            device = db.query(AgentDevice).filter(AgentDevice.id == device_id).first()
            platform_name = device.platform if device else "windows"
            access_token = create_device_access_token(device_id, user.id, platform_name)
        else:
            access_token = create_access_token(data={"sub": user.id, "role": user.role})

        refresh_token = create_refresh_token(data={"sub": user.id, "role": user.role, "device_id": device_id})

        ref_hash = hash_token(refresh_token)
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        token_record = RefreshToken(
            user_id=user.id,
            device_id=device_id,
            token_hash=ref_hash,
            expires_at=expires_at
        )
        db.add(token_record)
        db.commit()

        from ..schemas.auth import UserResponse
        user_dto = UserResponse.model_validate(user)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user_id=user.id,
            role=user.role,
            user=user_dto
        )
