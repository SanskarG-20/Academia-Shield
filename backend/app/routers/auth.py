"""
Authentication Router (/api/v1/auth).
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.dependencies import get_current_user
from ..models.user import User
from ..schemas.auth import RegisterRequest, LoginRequest, TokenResponse, RefreshRequest, UserResponse, UserUpdateRequest
from ..services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """Register a new student, professor, or administrator account."""
    user = AuthService.register_user(req, db)
    return user

@router.post("/register/student", status_code=status.HTTP_201_CREATED)
def register_student_alias(req: RegisterRequest, db: Session = Depends(get_db)):
    """Student registration endpoint alias."""
    req.role = "student"
    user = AuthService.register_user(req, db)
    token_resp = AuthService.login_user(LoginRequest(email=req.email, password=req.password), db)
    return token_resp

@router.post("/register/professor", status_code=status.HTTP_201_CREATED)
def register_professor_alias(req: RegisterRequest, db: Session = Depends(get_db)):
    """Professor registration endpoint alias."""
    req.role = "professor"
    user = AuthService.register_user(req, db)
    token_resp = AuthService.login_user(LoginRequest(email=req.email, password=req.password), db)
    return token_resp

@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate with institutional email & password to receive access & refresh tokens."""
    return AuthService.login_user(req, db)

@router.post("/refresh", response_model=TokenResponse)
def refresh(req: RefreshRequest, db: Session = Depends(get_db)):
    """Rotate JWT refresh token and receive a new access token."""
    return AuthService.refresh_tokens(req.refresh_token, db)

@router.post("/logout")
def logout(
    req: RefreshRequest = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Revoke refresh session for current device."""
    raw_token = req.refresh_token if req else None
    AuthService.logout_user(raw_token, current_user.id, db)
    return {"status": "ok", "message": "Successfully logged out and revoked refresh token."}

@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Fetch current authenticated user profile."""
    return current_user


@router.patch("/me", response_model=UserResponse)
def update_me(
    req: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the signed-in user's profile without allowing role or email changes."""
    full_name = req.full_name if req.full_name is not None else req.name
    if full_name is not None:
        current_user.full_name = full_name.strip()

    for field in ("department", "institutional_id", "roll_number", "year", "designation"):
        value = getattr(req, field)
        if value is not None:
            setattr(current_user, field, value.strip() or None)

    db.commit()
    db.refresh(current_user)
    return current_user
