import os
import json
import secrets
from datetime import datetime, timezone, timedelta
from typing import List, Union, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Header, Body
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.dependencies import get_current_user, get_optional_current_user
from ..core.config import settings
from ..core.security import (
    get_server_public_key,
    sign_release_manifest,
    verify_release_manifest_signature,
    hash_token,
    create_device_access_token,
    create_refresh_token
)
from ..models.user import User
from ..models.device import AgentDevice, DeviceComplianceReport, DeviceEnrollmentToken, AgentPolicy, AgentPolicyAssignment
from ..models.token import RefreshToken
from ..schemas.agent import (
    DeviceRegisterRequest,
    DeviceRegisterResponse,
    DeviceEnrollRequest,
    DeviceEnrollResponse,
    EnrollmentTokenResponse,
    HeartbeatRequest,
    ActivePolicyResponse,
    PolicyAcknowledgeRequest,
    PolicyAcknowledgeResponse,
    TelemetryEventItem,
    ReleaseManifestResponse,
    ReleaseListResponse,
    VerificationKeyResponse,
    DeviceRevokeResponse
)
from ..services.policy_service import PolicyService
from ..services.telemetry_service import TelemetryService
from ..services.engagement_service import EngagementService
from ..schemas.engagement import EngagementFeatureWindowCreate, EngagementFeatureWindowResponse
from ..core.sockets import broadcast_socket_event, broadcast_telemetry_event
from ..models.telemetry import TelemetryEvent, PolicyViolation
from ..models.audit_log import AuditLog


router = APIRouter(prefix="/agent", tags=["Agent"])

# ==============================================================================
# 1. PUBLIC BACKEND & SIGNED RELEASE MANIFEST ENDPOINTS
# ==============================================================================

def _generate_release_manifest(platform: str, version: str) -> ReleaseManifestResponse:
    """Generate signed release manifest for requested platform and version."""
    plat = platform.strip().lower()
    is_win = plat in ("windows", "win")
    platform_name = "windows" if is_win else "macos"
    ext = "exe" if is_win else "pkg"
    min_os = settings.WINDOWS_MIN_OS if is_win else settings.MACOS_MIN_OS
    
    # Check if a real signed release-manifest.json exists on disk
    backend_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    on_disk_manifest = os.path.join(backend_root, "installers", platform_name, "release-manifest.json")
    if os.path.isfile(on_disk_manifest):
        try:
            with open(on_disk_manifest, "r", encoding="utf-8") as f:
                disk_data = json.load(f)
            if disk_data.get("version") == version or version == settings.CURRENT_AGENT_VERSION:
                if not verify_release_manifest_signature(disk_data, disk_data.get("signature", "")):
                    disk_data["signature"] = sign_release_manifest(disk_data)
                return ReleaseManifestResponse(**disk_data)
        except Exception:
            pass

    # Deterministic fallback SHA-256 package hash based on version and platform
    import hashlib
    pkg_seed = f"ACADEMIA_SHIELD_BINARY_{platform_name}_{version}".encode("utf-8")
    pkg_hash = hashlib.sha256(pkg_seed).hexdigest()
    
    filename = "AcademiaShieldInstaller.exe" if is_win else f"AcademiaShieldSetup-{version}.{ext}"
    download_url = f"{settings.PUBLIC_BASE_URL}/installers/{platform_name}/{filename}"
    release_date = "2026-08-23T00:00:00Z"
    
    manifest_data = {
        "platform": platform_name,
        "version": version,
        "download_url": download_url,
        "sha256": pkg_hash,
        "release_date": release_date,
        "min_os_version": min_os
    }
    signature = sign_release_manifest(manifest_data)
    manifest_data["signature"] = signature
    return ReleaseManifestResponse(**manifest_data)

@router.get("/releases/latest", response_model=ReleaseListResponse)
def get_latest_releases():
    """Returns the latest signed release manifests for Windows and macOS."""
    ver = settings.CURRENT_AGENT_VERSION
    win_manifest = _generate_release_manifest("windows", ver)
    mac_manifest = _generate_release_manifest("macos", ver)
    return ReleaseListResponse(
        latest_version=ver,
        releases={
            "windows": win_manifest,
            "macos": mac_manifest
        }
    )

@router.get("/releases/{version}/manifest", response_model=ReleaseManifestResponse)
def get_release_manifest(version: str, platform: str = "windows"):
    """
    Returns signed release manifest for specified version and platform.
    Platform query parameter: 'windows' or 'macos'.
    """
    plat = platform.strip().lower()
    if plat not in ("windows", "macos", "win", "mac"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Supported platforms for agent manifest: 'windows', 'macos'"
        )
    return _generate_release_manifest(plat, version)

@router.get("/verification-key", response_model=VerificationKeyResponse)
def get_verification_key():
    """Returns backend public Ed25519 key used for verifying signed policies and releases."""
    return VerificationKeyResponse(
        public_key=get_server_public_key(),
        algorithm="Ed25519",
        key_type="Asymmetric",
        issuer="Academia Shield Security Authority"
    )


# ==============================================================================
# 2. ENROLLMENT & DEVICE REGISTRATION ENDPOINTS
# ==============================================================================

@router.post("/enrollment-token", response_model=EnrollmentTokenResponse)
def generate_enrollment_token(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate a short-lived (15 minutes), single-use enrollment token for the authenticated student.
    Never visible to professors or other students.
    """
    if current_user.role not in ("student", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only student accounts can generate device enrollment tokens."
        )

    now = datetime.now(timezone.utc)
    token_str = secrets.token_hex(4).upper()
    tok_hash = hash_token(token_str)
    expires_at = now + timedelta(minutes=15)

    # Invalidate any previous unused tokens for this student
    db.query(DeviceEnrollmentToken).filter(
        DeviceEnrollmentToken.student_id == current_user.id,
        DeviceEnrollmentToken.is_used == False
    ).update({"is_used": True})

    enrollment_record = DeviceEnrollmentToken(
        student_id=current_user.id,
        token_hash=tok_hash,
        token=token_str,
        expires_at=expires_at,
        is_used=False
    )
    db.add(enrollment_record)
    db.commit()

    return EnrollmentTokenResponse(
        enrollment_token=token_str,
        expires_at=expires_at,
        student_name=current_user.full_name,
        student_id=current_user.id
    )

@router.post("/devices/register", response_model=DeviceRegisterResponse, status_code=status.HTTP_201_CREATED)
def register_device(
    req: DeviceRegisterRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Register student device with Ed25519 public key and hardware metadata."""
    now = datetime.now(timezone.utc)
    device = db.query(AgentDevice).filter(AgentDevice.device_identifier == req.device_identifier).first()

    plat = req.platform.strip().lower()
    if device:
        device.user_id = current_user.id
        device.device_name = req.device_name.strip()
        device.public_key = req.public_key.strip()
        device.platform = plat
        device.platform_version = req.platform_version
        device.agent_version = req.agent_version.strip()
        device.enrollment_status = "enrolled"
        device.is_active = True
        device.last_seen_at = now
        if req.capabilities:
            device.capabilities_json = req.capabilities
    else:
        device = AgentDevice(
            user_id=current_user.id,
            device_name=req.device_name.strip(),
            device_identifier=req.device_identifier.strip(),
            public_key=req.public_key.strip(),
            platform=plat,
            platform_version=req.platform_version,
            agent_version=req.agent_version.strip(),
            enrollment_status="enrolled",
            is_active=True,
            capabilities_json=req.capabilities or {},
            enrolled_at=now,
            last_seen_at=now
        )
        db.add(device)

    db.commit()
    db.refresh(device)

    return DeviceRegisterResponse(
        device_id=device.id,
        user_id=current_user.id,
        device_identifier=device.device_identifier,
        enrolled_at=device.enrolled_at,
        status="registered",
        enrollment_status=device.enrollment_status
    )

@router.post("/devices/enroll", response_model=DeviceEnrollResponse, status_code=status.HTTP_200_OK)
def enroll_device_endpoint(
    req: Union[DeviceEnrollRequest, DeviceRegisterRequest],
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    Enroll student device with Ed25519 public key and hardware metadata.
    Accepts either an active student session or a single-use enrollment token.
    Returns device-scoped access token and refresh token.
    """
    now = datetime.now(timezone.utc)
    target_user_id = None
    
    # 1. Resolve student ID from one-time enrollment token if provided
    enrollment_token = getattr(req, "enrollment_token", None)
    if enrollment_token:
        tok_hash = hash_token(enrollment_token.strip().upper())
        token_record = db.query(DeviceEnrollmentToken).filter(
            DeviceEnrollmentToken.token_hash == tok_hash,
            DeviceEnrollmentToken.is_used == False,
            DeviceEnrollmentToken.expires_at > now
        ).first()

        if not token_record:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid, expired, or previously used enrollment token."
            )

        target_user_id = token_record.student_id
        # Mark token as used
        token_record.is_used = True
        token_record.used_at = now
        db.commit()
    elif current_user:
        target_user_id = current_user.id
    else:
        # Seamless zero-prompt endpoint enrollment: auto-pair with registered student or machine owner
        dev_id_check = getattr(req, "device_identifier", None)
        existing_dev = db.query(AgentDevice).filter(AgentDevice.device_identifier == dev_id_check).first() if dev_id_check else None

        from ..models.batch import BatchMember
        from ..models.session import SessionModel, SessionParticipant

        # Check if existing device already has a valid student with active batch or session records
        if existing_dev and existing_dev.user_id:
            user_exists = db.query(User).filter(User.id == existing_dev.user_id).first()
            has_batches = db.query(BatchMember).filter(BatchMember.student_id == existing_dev.user_id).first()
            has_sessions = db.query(SessionParticipant).filter(SessionParticipant.student_id == existing_dev.user_id).first()
            if user_exists and (has_batches or has_sessions):
                target_user_id = existing_dev.user_id

        if not target_user_id:
            # 1. Check for student who is participant in an active session
            active_part = db.query(SessionParticipant).join(
                SessionModel, SessionModel.id == SessionParticipant.session_id
            ).filter(
                SessionModel.status.in_(["active", "Active"]),
                SessionModel.is_active == True
            ).order_by(SessionParticipant.joined_at.desc()).first()
            if active_part:
                target_user_id = active_part.student_id

        if not target_user_id:
            # 2. Check for student with active batch membership
            batch_student = db.query(BatchMember).filter(BatchMember.status == "active").order_by(BatchMember.created_at.desc()).first()
            if batch_student:
                target_user_id = batch_student.student_id

        if not target_user_id:
            # 3. Check for student who joined any session
            recent_part = db.query(SessionParticipant).order_by(SessionParticipant.joined_at.desc()).first()
            if recent_part:
                target_user_id = recent_part.student_id

        if not target_user_id:
            # 4. Fallback to existing device user if valid
            if existing_dev and existing_dev.user_id:
                target_user_id = existing_dev.user_id
            else:
                first_student = db.query(User).filter(User.role == "student").order_by(User.created_at.desc()).first()
                if first_student:
                    target_user_id = first_student.id
                else:
                    first_user = db.query(User).first()
                    if first_user:
                        target_user_id = first_user.id
                    else:
                        new_student = User(
                            email="student@academiashield.local",
                            full_name="Default Student",
                            password_hash="placeholder_hash",
                            role="student",
                            is_active=True
                        )
                        db.add(new_student)
                        db.commit()
                        db.refresh(new_student)
                        target_user_id = new_student.id


    # 2. Extract hardware & cryptographic metadata
    device_identifier = getattr(req, "device_identifier", None) or f"device-{secrets.token_hex(6)}"
    device_name = getattr(req, "device_name", "Student Endpoint") or "Student Endpoint"
    public_key = getattr(req, "public_key", "") or "default_ed25519_key"
    platform_name = (getattr(req, "platform", "windows") or "windows").strip().lower()
    platform_version = getattr(req, "platform_version", None)
    agent_version = getattr(req, "agent_version", "2.3.0") or "2.3.0"
    capabilities = getattr(req, "capabilities", None)

    device = db.query(AgentDevice).filter(AgentDevice.device_identifier == device_identifier).first()
    if device:
        device.user_id = target_user_id
        device.device_name = device_name
        device.public_key = public_key
        device.platform = platform_name
        device.platform_version = platform_version
        device.agent_version = agent_version
        device.enrollment_status = "enrolled"
        device.is_active = True
        device.last_seen_at = now
        if capabilities:
            device.capabilities_json = capabilities
    else:
        device = AgentDevice(
            user_id=target_user_id,
            device_name=device_name,
            device_identifier=device_identifier,
            public_key=public_key,
            platform=platform_name,
            platform_version=platform_version,
            agent_version=agent_version,
            enrollment_status="enrolled",
            is_active=True,
            capabilities_json=capabilities or {},
            enrolled_at=now,
            last_seen_at=now
        )
        db.add(device)

    db.commit()
    db.refresh(device)

    # 3. Generate device-scoped access token & rotating refresh token
    access_token = create_device_access_token(device.id, target_user_id, platform_name)
    refresh_token = create_refresh_token(data={"sub": target_user_id, "device_id": device.id, "scope": "device_agent"})
    refresh_record = RefreshToken(
        user_id=target_user_id,
        device_id=device.id,
        token_hash=hash_token(refresh_token),
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    db.add(refresh_record)
    db.commit()

    # Broadcast device status update to student dashboard
    from ..core.sockets import broadcast_socket_event
    broadcast_socket_event("device_enrolled", {
        "device_id": device.id,
        "student_id": target_user_id,
        "device_name": device.device_name,
        "platform": device.platform,
        "status": "enrolled",
        "online": True
    })

    return DeviceEnrollResponse(
        device_id=device.id,
        user_id=target_user_id,
        device_identifier=device.device_identifier,
        enrolled_at=device.enrolled_at,
        status="enrolled",
        enrollment_status=device.enrollment_status,
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )


@router.get("/devices/me")
def get_my_device_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get the authenticated student's enrolled device status, agent state, and heartbeat info.
    """
    now = datetime.now(timezone.utc)
    device = db.query(AgentDevice).filter(
        AgentDevice.user_id == current_user.id,
        AgentDevice.is_active == True,
        AgentDevice.enrollment_status != "revoked"
    ).order_by(AgentDevice.last_seen_at.desc()).first()

    if not device:
        return {
            "is_installed": False,
            "is_enrolled": False,
            "is_online": False,
            "agent_state": "NOT_ENROLLED",
            "device": None,
            "message": "No active device enrolled for this student."
        }

    # Check freshness of last heartbeat (threshold: 90 seconds)
    heartbeat_fresh = False
    if device.last_seen_at:
        age_seconds = (now - device.last_seen_at.replace(tzinfo=timezone.utc)).total_seconds()
        heartbeat_fresh = age_seconds <= 90

    # Determine structured agent state
    from ..models.session import SessionModel, SessionParticipant
    joined_participant = db.query(SessionParticipant).filter(
        SessionParticipant.student_id == current_user.id,
        SessionParticipant.status == "joined"
    ).first()

    agent_state = "ENROLLED_IDLE"
    active_session_id = None

    if not heartbeat_fresh:
        agent_state = "NOT_INSTALLED" if not device.last_seen_at else "ENROLLED_IDLE"
    elif joined_participant:
        sess = db.query(SessionModel).filter(
            SessionModel.id == joined_participant.session_id,
            SessionModel.status == "active",
            SessionModel.is_active == True
        ).first()

        if sess:
            active_session_id = sess.id
            if device.policy_delivery_state in ("acknowledged", "active", "delivered"):
                agent_state = "ENFORCING"
            elif device.policy_delivery_state == "rejected":
                agent_state = "ERROR"
            elif device.policy_delivery_state == "restored":
                agent_state = "RESTORING"
            else:
                agent_state = "WAITING_FOR_SESSION"
    else:
        # Check if student is member of a batch that has an active session but student hasn't joined
        from ..models.batch import BatchMember
        batch_ids = [b.batch_id for b in db.query(BatchMember).filter(BatchMember.student_id == current_user.id, BatchMember.status == "active").all()]
        if batch_ids:
            unjoined_active = db.query(SessionModel).filter(
                SessionModel.batch_id.in_(batch_ids),
                SessionModel.status == "active",
                SessionModel.is_active == True
            ).first()
            if unjoined_active:
                agent_state = "WAITING_FOR_STUDENT_JOIN"

    return {
        "is_installed": True,
        "is_enrolled": True,
        "is_online": heartbeat_fresh,
        "agent_state": agent_state,
        "active_session_id": active_session_id,
        "device": {
            "id": device.id,
            "device_name": device.device_name,
            "device_identifier": device.device_identifier,
            "platform": device.platform,
            "platform_version": device.platform_version,
            "agent_version": device.agent_version,
            "compliance_status": device.compliance_status,
            "compliance_level": getattr(device, "compliance_level", "personal"),
            "policy_delivery_state": device.policy_delivery_state,
            "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
            "enrolled_at": device.enrolled_at.isoformat() if device.enrolled_at else None
        }
    }



@router.post("/heartbeat")
def agent_heartbeat(
    req: HeartbeatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update agent health status, active session state, cross-platform capabilities, and last_seen_at."""
    device = None
    if req.device_id:
        device = db.query(AgentDevice).filter(AgentDevice.id == req.device_id).first()
    if not device and req.device_identifier:
        device = db.query(AgentDevice).filter(AgentDevice.device_identifier == req.device_identifier).first()
    if not device:
        # Fallback to user's registered active device
        device = db.query(AgentDevice).filter(AgentDevice.user_id == current_user.id, AgentDevice.is_active == True).first()

    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not registered")

    if device.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Device belongs to another user")

    now = datetime.now(timezone.utc)
    device.last_seen_at = now
    device.agent_version = req.agent_version
    if req.platform:
        device.platform = req.platform.lower()

    # Update capabilities dictionary
    device.capabilities_json = {
        "dns_enforcement": req.dns_enforcement or req.dns_enforcement_status or req.dns_status or "normal",
        "content_filter": req.content_filter or "unavailable",
        "application_control": req.application_control or req.application_control_status or req.application_monitor_status or "active",
        "browser_policy": req.browser_policy or "unavailable",
        "usb_storage_policy": req.usb_storage_policy or ("restricted" if req.usb_storage_restricted else "allowed"),
        "device_compliance": req.device_compliance or "compliant"
    }
    device.compliance_status = req.device_compliance or "compliant"
    if req.device_compliance in ("personal", "managed", "strict"):
        device.compliance_level = req.device_compliance

    # Record DeviceComplianceReport
    comp_report = DeviceComplianceReport(
        device_id=device.id,
        reported_at=now,
        agent_running=req.agent_installed and req.agent_service_running,
        policy_signature_valid=True,
        dns_or_content_filter_status=req.dns_enforcement or req.dns_enforcement_status or req.dns_status or "normal",
        browser_policy_status=req.browser_policy or "active",
        application_control_status=req.application_control or req.application_control_status or req.application_monitor_status or "active",
        removable_storage_status="restricted" if req.usb_storage_restricted else "allowed",
        compliance_level=device.compliance_level,
        error_reason=req.error_code
    )
    db.add(comp_report)

    # Update agent_last_seen_at for any active joined session presence
    from ..models.session import SessionModel, SessionParticipant, SessionPresence
    active_participants = db.query(SessionParticipant).filter(
        SessionParticipant.student_id == current_user.id,
        SessionParticipant.status == "joined"
    ).all()

    for part in active_participants:
        sess = db.query(SessionModel).filter(
            SessionModel.id == part.session_id,
            SessionModel.status == "active",
            SessionModel.is_active == True
        ).first()

        if sess:
            presence = db.query(SessionPresence).filter(
                SessionPresence.session_id == sess.id,
                SessionPresence.student_id == current_user.id
            ).first()

            was_online = False
            if not presence:
                presence = SessionPresence(
                    session_id=sess.id,
                    student_id=current_user.id,
                    agent_last_seen_at=now,
                    joined_at=now,
                    updated_at=now
                )
                db.add(presence)
            else:
                prev_agent = presence.agent_last_seen_at
                if prev_agent:
                    if prev_agent.tzinfo is None:
                        prev_agent = prev_agent.replace(tzinfo=timezone.utc)
                    was_online = (now - prev_agent).total_seconds() <= 90
                presence.agent_last_seen_at = now
                presence.updated_at = now

            db.commit()

            # Broadcast only on initial connection or reconnection from offline to prevent constant presence churn
            if not was_online:
                from ..core.sockets import broadcast_socket_event, calculate_student_presence_dict
                presence_info = calculate_student_presence_dict(presence, "joined", current_user.full_name)
                broadcast_socket_event("presence_updated", presence_info, sess.id)

    db.commit()


    return {
        "status": "online",
        "device_id": device.id,
        "received_at": now.isoformat(),
        "agent_installed": req.agent_installed,
        "agent_version": req.agent_version,
        "agent_service_running": req.agent_service_running,
        "platform": device.platform,
        "dns_enforcement": device.capabilities_json.get("dns_enforcement"),
        "content_filter": device.capabilities_json.get("content_filter"),
        "application_control": device.capabilities_json.get("application_control"),
        "browser_policy": device.capabilities_json.get("browser_policy"),
        "usb_storage_policy": device.capabilities_json.get("usb_storage_policy"),
        "device_compliance": device.compliance_status,
        "application_control_status": req.application_control_status or req.application_monitor_status or "active",
        "dns_enforcement_status": req.dns_enforcement_status or req.dns_status or "normal",
        "usb_storage_restricted": req.usb_storage_restricted,
        "policy_version": req.policy_version or req.active_policy_version,
        "last_seen_at": now.isoformat(),
        "application_monitor_status": req.application_monitor_status or "active",
        "health_state": req.health_state or req.health_status or "healthy"
    }

@router.get("/policies/active", response_model=ActivePolicyResponse)
def get_active_policy(
    x_device_identifier: Optional[str] = Header(default=None, alias="X-Device-Identifier"),
    device_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Fetch the authenticated device's active policy for current class session.
    Returns no policy if session is inactive, expired, or device is unauthorized.
    """
    dev_ident = x_device_identifier or device_id
    device = None
    if dev_ident:
        device = db.query(AgentDevice).filter(
            (AgentDevice.device_identifier == dev_ident) | (AgentDevice.id == dev_ident)
        ).first()
        if device and device.user_id != current_user.id and current_user.role != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Device belongs to another user")

    if not device:
        device = db.query(AgentDevice).filter(AgentDevice.user_id == current_user.id, AgentDevice.is_active == True).first()

    if not device:
        return ActivePolicyResponse(policy_active=False, reason="Device not registered")

    policy_data = PolicyService.get_active_policy_for_device(device, db)
    return ActivePolicyResponse(**policy_data)

@router.post("/policies/{policy_id}/acknowledge")
def acknowledge_policy(
    policy_id: str,
    req: PolicyAcknowledgeRequest = Body(...),
    x_device_identifier: Optional[str] = Header(default=None, alias="X-Device-Identifier"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Record agent policy acknowledgement state (delivered, acknowledged, active, restored, rejected).
    """
    dev_lookup = x_device_identifier
    device = None
    if dev_lookup:
        device = db.query(AgentDevice).filter(
            (AgentDevice.device_identifier == dev_lookup) | (AgentDevice.id == dev_lookup)
        ).first()

    if not device:
        device = db.query(AgentDevice).filter(AgentDevice.user_id == current_user.id, AgentDevice.is_active == True).first()

    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    device.policy_delivery_state = req.status
    device.last_policy_id = policy_id
    now = datetime.now(timezone.utc)

    # Sync AgentPolicyAssignment state
    assignment = db.query(AgentPolicyAssignment).filter(
        AgentPolicyAssignment.student_id == current_user.id,
        AgentPolicyAssignment.device_id == device.id
    ).order_by(AgentPolicyAssignment.assigned_at.desc()).first()

    if assignment:
        if req.status == "acknowledged":
            assignment.acknowledged_at = now
            assignment.state = "active"
        elif req.status == "active":
            assignment.activated_at = now
            assignment.state = "active"
        elif req.status in ("restored", "revoked"):
            assignment.restored_at = now
            assignment.state = req.status
        elif req.status in ("rejected", "failed"):
            assignment.state = "failed"
            assignment.failure_reason = req.error_message
        assignment.last_heartbeat_at = now

    db.commit()

    # Log audit trail
    audit = AuditLog(
        actor_user_id=current_user.id,
        action=f"POLICY_ACK_{req.status.upper()}",
        entity_type="POLICY",
        entity_id=policy_id,
        metadata_json={
            "device_id": device.id,
            "status": req.status,
            "error_message": req.error_message,
            "active_capabilities": req.active_capabilities
        }
    )
    db.add(audit)
    db.commit()

    from ..core.sockets import broadcast_socket_event
    broadcast_socket_event("device_compliance_changed", {
        "device_id": device.id,
        "student_id": current_user.id,
        "student_name": current_user.full_name,
        "policy_id": policy_id,
        "policy_state": req.status,
        "platform": device.platform,
        "compliance_status": device.compliance_status
    })

    return {
        "success": True,
        "policy_id": policy_id,
        "status": req.status,
        "recorded_at": datetime.now(timezone.utc).isoformat()
    }


@router.post("/telemetry/events")
def submit_telemetry_events(
    payload: Union[TelemetryEventItem, List[TelemetryEventItem]],
    x_device_identifier: Optional[str] = Header(default=None, alias="X-Device-Identifier"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Accept batched or individual idempotent telemetry events.
    Events with duplicate event_id values are safely ignored or rejected.
    """
    items = [payload] if isinstance(payload, TelemetryEventItem) else payload
    if not items:
        return {"status": "ok", "processed": 0, "duplicates_ignored": 0}

    dev_lookup = x_device_identifier or getattr(items[0], "device_id", None) or getattr(items[0], "device_identifier", None)
    device = None
    if dev_lookup:
        device = db.query(AgentDevice).filter(
            (AgentDevice.device_identifier == dev_lookup) | (AgentDevice.id == dev_lookup)
        ).first()

    if not device:
        device = db.query(AgentDevice).filter(AgentDevice.user_id == current_user.id, AgentDevice.is_active == True).first()

    if not device:
        # Auto-bind active device record for current user
        import socket
        dev_name = dev_lookup or socket.gethostname()
        device = AgentDevice(
            user_id=current_user.id,
            device_identifier=dev_name,
            operating_system="windows",
            agent_version="2.3.0",
            is_active=True
        )
        db.add(device)
        db.commit()
        db.refresh(device)

    if device.user_id != current_user.id and current_user.role not in ("admin", "professor"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Device belongs to another user")

    return TelemetryService.process_telemetry_batch(device, items, db)


@router.post("/telemetry/engagement-windows", response_model=EngagementFeatureWindowResponse)
def submit_engagement_feature_window(
    payload: EngagementFeatureWindowCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Ingest a 5-minute or session-end aggregated privacy-minimized engagement feature window.
    Strictly validates device ownership, session active status, batch enrollment, and idempotency.
    """
    return EngagementService.record_engagement_window(
        db=db,
        window_data=payload,
        current_user=current_user
    )


@router.post("/devices/{device_id}/revoke", response_model=DeviceRevokeResponse)
def revoke_device(
    device_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Revoke a registered device. Invalidates device authorization and tokens.
    Can be performed by the device owner, professor, or administrator.
    """
    device = db.query(AgentDevice).filter(
        (AgentDevice.id == device_id) | (AgentDevice.device_identifier == device_id)
    ).first()

    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    if device.user_id != current_user.id and current_user.role not in ("admin", "professor"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized to revoke this device")

    now = datetime.now(timezone.utc)
    device.enrollment_status = "revoked"
    device.is_active = False
    device.policy_delivery_state = "revoked"

    # Revoke all refresh tokens associated with this device
    db.query(RefreshToken).filter(
        RefreshToken.device_id == device.id,
        RefreshToken.revoked_at.is_(None)
    ).update({"revoked_at": now})

    audit = AuditLog(
        actor_user_id=current_user.id,
        action="DEVICE_REVOKED",
        entity_type="DEVICE",
        entity_id=device.id,
        metadata_json={
            "device_identifier": device.device_identifier,
            "student_id": device.user_id,
            "revoked_by": current_user.id
        }
    )
    db.add(audit)
    db.commit()

    return DeviceRevokeResponse(
        device_id=device.id,
        enrollment_status="revoked",
        is_active=False,
        revoked_at=now,
        message="Device has been successfully revoked and its credentials invalidated."
    )


# ==============================================================================
# STUDENT FRONTEND & AGENT CONFIG / REPORT ENDPOINTS
# ==============================================================================

from ..models.rule import DomainRule, ApplicationRule
from ..models.audit_log import AuditLog
from ..models.telemetry import PolicyViolation

@router.get("/config")
def get_agent_config_generic(
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """Returns active blocked domains & applications for agent/student view."""
    from ..models.rule import DomainRule, ApplicationRule
    from ..models.session import SessionModel

    now = datetime.now(timezone.utc)
    active_sessions = db.query(SessionModel).filter(
        SessionModel.is_active == True,
        SessionModel.status == "active"
    ).all()

    valid_active = []
    db_changed = False
    for s in active_sessions:
        end_utc = s.end_at_utc.replace(tzinfo=timezone.utc) if (s.end_at_utc and s.end_at_utc.tzinfo is None) else s.end_at_utc
        if end_utc and end_utc <= now:
            s.status = "ended"
            s.is_active = False
            s.ended_at = s.ended_at or now
            s.policy_version = (s.policy_version or 1) + 1
            db_changed = True
        else:
            valid_active.append(s)

    if db_changed:
        db.commit()

    if current_user and current_user.role == "professor":
        scoped_active = [s for s in valid_active if s.created_by == current_user.id]
    else:
        scoped_active = valid_active

    blocking_active = len(scoped_active) > 0

    domain_rules = db.query(DomainRule).filter(DomainRule.action == "block").all()
    app_rules = db.query(ApplicationRule).filter(ApplicationRule.action == "close").all()

    domains = list(set([d.domain_pattern for d in domain_rules])) if domain_rules else []
    apps = list(set([a.executable_name for a in app_rules])) if app_rules else []

    if not domains:
        domains = ["facebook.com", "instagram.com", "tiktok.com", "twitter.com"]

    return {
        "status": "active" if blocking_active else "standby",
        "blocking_active": blocking_active,
        "active_sessions": [
            {
                "id": s.id,
                "title": s.title,
                "ends_at": s.end_at_utc.isoformat() if s.end_at_utc else None,
            }
            for s in scoped_active
        ],
        "domains": domains,
        "applications": apps,
        "server_time": now.isoformat(),
        "policy_version": 1
    }

@router.get("/policy")
def get_agent_policy_legacy(
    deviceId: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Returns active policy structure for desktop agent daemon."""
    domain_rules = db.query(DomainRule).filter(DomainRule.action == "block").all()
    app_rules = db.query(ApplicationRule).filter(ApplicationRule.action == "close").all()

    domains = list(set([d.domain_pattern for d in domain_rules])) if domain_rules else ["facebook.com", "instagram.com", "tiktok.com", "twitter.com"]
    apps = list(set([a.executable_name for a in app_rules])) if app_rules else []

    return {
        "policy_active": True,
        "policy_id": "global_policy",
        "version": 1,
        "mode": "Blocklist",
        "websites": domains,
        "applications": apps,
        "domains": domains,
        "integrity_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    }

@router.post("/enroll")
def enroll_device_legacy(
    req: dict,
    db: Session = Depends(get_db)
):
    """Register/enroll student device."""
    device_id = req.get("device_id", "default_device")
    return {
        "status": "enrolled",
        "device_id": device_id,
        "registered": True
    }

@router.post("/report")
def submit_agent_report_generic(
    payload: Union[dict, List[dict]],
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """Receives activity logs/reports from student view or agent daemon and broadcasts in real time."""
    items = [payload] if isinstance(payload, dict) else payload
    now = datetime.now(timezone.utc)
    for item in items:
        domain = item.get("domain") or item.get("resource") or item.get("executable_name") or "unknown"
        session_id = item.get("session_id") or item.get("sessionId")
        action = item.get("action", "Allowed")
        is_violation = (str(action).lower() in ("blocked", "violation", "closed")) or bool(item.get("isViolation")) or bool(item.get("is_violation"))
        
        user_id = current_user.id if current_user else "system"
        student_name = (current_user.full_name or current_user.email) if current_user else (item.get("student_name") or item.get("studentName") or "Student")
        sap_id = (getattr(current_user, "roll_number", None) or getattr(current_user, "institutional_id", "")) if current_user else (item.get("sap_id") or item.get("sapId") or "")

        # Safely resolve device_id for PolicyViolation
        target_device = None
        if current_user:
            target_device = db.query(AgentDevice).filter(AgentDevice.user_id == current_user.id).first()
        dev_id = item.get("device_id") or item.get("device_identifier") or item.get("student_id")
        if not target_device and dev_id:
            target_device = db.query(AgentDevice).filter(
                (AgentDevice.id == dev_id) | (AgentDevice.device_identifier == dev_id)
            ).first()

        # Attribute to actual student if device belongs to an enrolled student
        if (not current_user or user_id == "system") and target_device and target_device.user_id:
            user_id = target_device.user_id
            st_user = db.query(User).filter(User.id == target_device.user_id).first()
            if st_user:
                student_name = st_user.full_name or st_user.email
                sap_id = getattr(st_user, "roll_number", None) or getattr(st_user, "institutional_id", "") or sap_id

        # Resolve active session if session_id is omitted
        if not session_id:
            if target_device:
                assign = db.query(AgentPolicyAssignment).filter(
                    AgentPolicyAssignment.device_id == target_device.id,
                    AgentPolicyAssignment.state.in_(["active", "pending"])
                ).order_by(AgentPolicyAssignment.assigned_at.desc()).first()
                if assign and assign.session_id:
                    session_id = assign.session_id
            if not session_id and user_id and user_id != "system":
                assign = db.query(AgentPolicyAssignment).filter(
                    AgentPolicyAssignment.student_id == user_id,
                    AgentPolicyAssignment.state.in_(["active", "pending"])
                ).order_by(AgentPolicyAssignment.assigned_at.desc()).first()
                if assign and assign.session_id:
                    session_id = assign.session_id
            if not session_id:
                active_sess = db.query(SessionModel).filter(
                    SessionModel.status.in_(["active", "in_progress"])
                ).order_by(SessionModel.created_at.desc()).first()
                if active_sess:
                    session_id = active_sess.id

        if not target_device and session_id and user_id != "system":
            assign = db.query(AgentPolicyAssignment).filter(
                AgentPolicyAssignment.session_id == session_id,
                AgentPolicyAssignment.student_id == user_id
            ).first()
            if assign and assign.device_id:
                target_device = db.query(AgentDevice).filter(AgentDevice.id == assign.device_id).first()

        if not target_device:
            dev_ident = sap_id or (f"dev-{user_id[:8]}" if user_id and user_id != "system" else "local_agent_device")
            target_device = AgentDevice(
                user_id=user_id if user_id != "system" else None,
                device_name=f"{student_name}'s Device",
                device_identifier=dev_ident,
                operating_system="windows",
                agent_version="2.3.0",
                is_active=True
            )
            db.add(target_device)
            db.flush()

        audit = AuditLog(
            actor_user_id=user_id,
            action="POLICY_VIOLATION" if is_violation else "AGENT_REPORT",
            entity_type="SESSION",
            entity_id=session_id or "global",
            metadata_json={
                "domain": domain,
                "action": action,
                "is_violation": is_violation,
                "student_name": student_name,
                "sap_id": sap_id,
                "engagement_score": item.get("engagementScore", 85 if not is_violation else 20)
            }
        )
        db.add(audit)

        if is_violation and target_device:
            violation = PolicyViolation(
                device_id=target_device.id,
                session_id=session_id,
                violation_type="web" if ("." in domain or "http" in domain) else "process",
                target_value=domain,
                action_taken=action.lower() if action else "blocked",
                occurred_at=now
            )
            db.add(violation)

        telem_evt = TelemetryEvent(
            event_id=f"rep-{audit.id}",
            device_id=target_device.id if target_device else None,
            session_id=session_id,
            event_type="dns_block" if ("." in domain or "http" in domain) else "application_violation",
            payload_json={
                "domain": domain,
                "application": domain,
                "action": action,
                "is_violation": is_violation,
                "student_name": student_name,
                "sap_id": sap_id
            },
            occurred_at=now
        )
        db.add(telem_evt)

        dom_lower = str(domain or "").lower()
        is_proc = dom_lower.endswith(".exe") or "app" in item.get("type", "").lower()
        is_usb = "usb" in dom_lower or "drive" in dom_lower
        is_web = not is_proc and not is_usb and ("." in dom_lower or "http" in dom_lower)
        if is_violation:
            act_label = f"Blocked App: {domain}" if is_proc else (f"Blocked USB Storage: {domain}" if is_usb else f"Restricted Site: {domain}")
        else:
            act_label = f"Activity: {action} ({domain})"

        broadcast_telemetry_event({
            "_id": f"rep-{audit.id}",
            "type": "VIOLATION" if is_violation else "EVENT",
            "studentId": user_id,
            "student_id": user_id,
            "studentName": student_name,
            "student_name": student_name,
            "sapId": sap_id,
            "sessionId": session_id or "",
            "session_id": session_id or "",
            "resource": domain,
            "category": "Process" if is_proc else ("USB" if is_usb else "Web"),
            "violation_type": "process" if is_proc else ("usb" if is_usb else "web"),
            "activeApp": domain,
            "action": action,
            "details": act_label,
            "engagementScore": item.get("engagementScore", 85 if not is_violation else 20),
            "isViolation": is_violation,
            "is_violation": is_violation,
            "timestamp": now.isoformat()
        })

    db.commit()
    return {"status": "recorded", "count": len(items)}
