"""
Policy Rule Sets Router.
Provides authenticated, RBAC-protected endpoints for batches, rule sets, website rules, application rules,
device compliance requirements, publishing, revocation, and session assignment.
"""

from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.dependencies import get_current_user, require_professor
from ..core.security import sign_policy_payload
from ..core.sockets import broadcast_socket_event
from ..models.user import User
from ..models.rule import RuleSet, WebsiteRule, DomainRule, ApplicationRule, DevicePolicyRequirement
from ..models.batch import Batch
from ..models.session import SessionModel
from ..schemas.rule import (
    RuleSetCreate,
    RuleSetUpdate,
    RuleSetResponse,
    WebsiteRuleCreate,
    WebsiteRuleUpdate,
    WebsiteRuleResponse,
    DomainRuleCreate,
    DomainRuleResponse,
    ApplicationRuleCreate,
    ApplicationRuleUpdate,
    ApplicationRuleResponse,
    DevicePolicyRequirementUpdate,
    DevicePolicyRequirementResponse,
    PROTECTED_ALLOWLIST
)
from ..services.policy_service import PolicyService, SYSTEM_PROTECTED_PROCESSES

router = APIRouter(tags=["Rules"])


# ==============================================================================
# BATCH POLICY RULE SET MANAGEMENT
# ==============================================================================

@router.post("/batches/{batch_id}/rule-sets", response_model=RuleSetResponse, status_code=status.HTTP_201_CREATED)
def create_batch_rule_set(
    batch_id: str,
    req: RuleSetCreate,
    professor: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Create a new versioned policy rule set for a batch (Professor/Admin only)."""
    return PolicyService.create_batch_rule_set(batch_id, req, professor, db)

@router.get("/batches/{batch_id}/rule-sets", response_model=List[RuleSetResponse])
def list_batch_rule_sets(
    batch_id: str,
    professor: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """List policy rule sets for a batch (Professor/Admin only)."""
    return PolicyService.get_batch_rule_sets(batch_id, professor, db)

@router.get("/rule-sets/{rule_set_id}", response_model=RuleSetResponse)
def get_rule_set_by_id(
    rule_set_id: str,
    professor: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Retrieve full details of a policy rule set (Professor/Admin only)."""
    return PolicyService.get_rule_set(rule_set_id, professor, db)

@router.patch("/rule-sets/{rule_set_id}", response_model=RuleSetResponse)
def update_rule_set(
    rule_set_id: str,
    req: RuleSetUpdate,
    professor: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Update rule set parameters. If published, generates a new draft version."""
    return PolicyService.update_rule_set(rule_set_id, req, professor, db)

@router.post("/rule-sets/{rule_set_id}/publish", response_model=RuleSetResponse)
def publish_rule_set(
    rule_set_id: str,
    professor: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Publish and cryptographically sign a policy rule set (Professor/Admin only)."""
    return PolicyService.publish_rule_set(rule_set_id, professor, db)

@router.post("/rule-sets/{rule_set_id}/revoke", response_model=RuleSetResponse)
def revoke_rule_set(
    rule_set_id: str,
    professor: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Revoke an active policy rule set (Professor/Admin only)."""
    return PolicyService.revoke_rule_set(rule_set_id, professor, db)

@router.post("/sessions/{session_id}/assign-rule-set")
def assign_rule_set_to_session(
    session_id: str,
    payload: dict,
    professor: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Assign a published policy rule set to an academic session."""
    rule_set_id = payload.get("rule_set_id")
    if not rule_set_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="rule_set_id is required")
    session_obj = PolicyService.assign_rule_set_to_session(session_id, rule_set_id, professor, db)
    return {
        "status": "success",
        "message": "Policy assigned to session successfully",
        "session_id": session_obj.id,
        "rule_set_id": session_obj.rule_set_id,
        "policy_version": session_obj.policy_version
    }


# ==============================================================================
# WEBSITE RULES ENDPOINTS
# ==============================================================================

@router.post("/rule-sets/{rule_set_id}/website-rules", response_model=WebsiteRuleResponse, status_code=status.HTTP_201_CREATED)
def add_website_rule(
    rule_set_id: str,
    req: WebsiteRuleCreate,
    professor: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Add an allowed or blocked website rule to a rule set (Professor/Admin only)."""
    return PolicyService.add_website_rule(rule_set_id, req, professor, db)

@router.patch("/website-rules/{rule_id}", response_model=WebsiteRuleResponse)
def update_website_rule(
    rule_id: str,
    req: WebsiteRuleUpdate,
    professor: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Update website rule parameters (Professor/Admin only)."""
    return PolicyService.update_website_rule(rule_id, req, professor, db)

@router.delete("/website-rules/{rule_id}")
def delete_website_rule(
    rule_id: str,
    professor: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Delete a website rule from a rule set (Professor/Admin only)."""
    return PolicyService.delete_website_rule(rule_id, professor, db)


# ==============================================================================
# APPLICATION RULES ENDPOINTS
# ==============================================================================

@router.post("/rule-sets/{rule_set_id}/application-rules", response_model=ApplicationRuleResponse, status_code=status.HTTP_201_CREATED)
def add_application_rule(
    rule_set_id: str,
    req: ApplicationRuleCreate,
    professor: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Add an allowed or blocked application rule to a rule set (Professor/Admin only)."""
    return PolicyService.add_application_rule(rule_set_id, req, professor, db)

@router.get("/rule-sets/{rule_set_id}/application-rules", response_model=List[ApplicationRuleResponse])
def get_application_rules(
    rule_set_id: str,
    professor: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """List application rules for a rule set (Professor/Admin only)."""
    return PolicyService.get_application_rules(rule_set_id, professor, db)

@router.patch("/application-rules/{rule_id}", response_model=ApplicationRuleResponse)
def update_application_rule(
    rule_id: str,
    req: ApplicationRuleUpdate,
    professor: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Update application rule parameters (Professor/Admin only)."""
    return PolicyService.update_application_rule(rule_id, req, professor, db)

@router.delete("/application-rules/{rule_id}")
def delete_application_rule(
    rule_id: str,
    professor: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Delete an application rule from a rule set (Professor/Admin only)."""
    return PolicyService.delete_application_rule(rule_id, professor, db)


# ==============================================================================
# DEVICE COMPLIANCE REQUIREMENTS ENDPOINTS
# ==============================================================================

@router.patch("/rule-sets/{rule_set_id}/device-requirements", response_model=DevicePolicyRequirementResponse)
def update_device_requirements(
    rule_set_id: str,
    req: DevicePolicyRequirementUpdate,
    professor: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Update device compliance requirements including USB-storage restriction (Professor/Admin only)."""
    return PolicyService.update_device_requirements(rule_set_id, req, professor, db)


# ==============================================================================
# LEGACY & FRONTEND COMPATIBILITY ROUTES
# ==============================================================================

@router.post("/rule-sets/{rule_set_id}/domain-rules", response_model=DomainRuleResponse, status_code=status.HTTP_201_CREATED)
def add_domain_rule(
    rule_set_id: str,
    req: DomainRuleCreate,
    professor: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Backward-compatible domain rule addition."""
    return PolicyService.add_domain_rule(rule_set_id, req, professor, db)

@router.post("/classes/{class_id}/rule-sets", response_model=RuleSetResponse, status_code=status.HTTP_201_CREATED)
def create_class_rule_set_alias(
    class_id: str,
    req: RuleSetCreate,
    professor: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    return PolicyService.create_rule_set(class_id, req, professor, db)

@router.get("/classes/{class_id}/rule-sets", response_model=List[RuleSetResponse])
def list_class_rule_sets_alias(
    class_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return db.query(RuleSet).filter(RuleSet.class_id == class_id).all()

@router.get("/rules", response_model=List[dict])
def get_all_rules_frontend(
    batch_id: str = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all policy rule sets formatted for the professor dashboard rules page."""
    if current_user.role == "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Students cannot access professor policy rules.")

    query = db.query(RuleSet)
    if batch_id and batch_id != "all":
        query = query.filter(RuleSet.batch_id == batch_id)
    if current_user.role and current_user.role.lower() == "professor":
        query = query.filter((RuleSet.created_by == current_user.id) | (RuleSet.created_by == None))
    rules = query.order_by(RuleSet.issued_at.desc()).all()

    result = []
    now_iso = datetime.now(timezone.utc).isoformat()
    for r in rules:
        # Collect allowed vs blocked
        w_rules = r.website_rules or []
        allowed_sites = [w.domain_pattern for w in w_rules if w.rule_mode == "allowed"]
        blocked_sites = [w.domain_pattern for w in w_rules if w.rule_mode == "blocked"]
        if not w_rules and r.domain_rules:
            allowed_sites = [d.domain_pattern for d in r.domain_rules if d.action in ("allow", "log")]
            blocked_sites = [d.domain_pattern for d in r.domain_rules if d.action == "block"]

        a_rules = r.application_rules or []
        allowed_apps = [a.executable_name for a in a_rules if a.rule_mode == "allowed"]
        blocked_apps = [a.executable_name for a in a_rules if a.rule_mode != "allowed"]

        all_sites = allowed_sites + blocked_sites
        all_apps = allowed_apps + blocked_apps

        dev_req = r.device_requirements
        req_usb = dev_req.require_usb_storage_restriction if dev_req else False
        enforcement_lvl = dev_req.required_enforcement_level if dev_req else "development"

        result.append({
            "_id": r.id,
            "id": r.id,
            "name": r.name or "Policy Rule Set",
            "mode": "Custom",
            "status": r.status or "draft",
            "version": r.version or 1,
            "integrityHash": r.integrity_hash or "",
            "signature": r.signature or "",
            "is_active": bool(r.is_active),
            "batch_id": r.batch_id,
            "session_id": r.session_id,
            "websites": all_sites,
            "applications": all_apps,
            "allowed_websites": allowed_sites,
            "blocked_websites": blocked_sites,
            "allowed_applications": allowed_apps,
            "blocked_applications": blocked_apps,
            "require_usb_storage_restriction": req_usb,
            "required_enforcement_level": enforcement_lvl,
            "created_at": r.issued_at.isoformat() if r.issued_at else now_iso
        })
    return result

@router.post("/rules", status_code=status.HTTP_201_CREATED)
def create_rule_generic(
    req: dict,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Create a new rule set with structured allowed/blocked websites, applications, and device requirements."""
    try:
        raw_name = req.get("name")
        name = str(raw_name).strip() if raw_name and str(raw_name).strip() else "New Session Policy"

        batch_id = req.get("batch_id") or req.get("batchId")
        if batch_id and batch_id != "all":
            batch_obj = db.query(Batch).filter(Batch.id == batch_id).first()
            if not batch_obj:
                batch_id = None
        else:
            batch_id = None

        session_id = req.get("session_id") or req.get("sessionId")
        if session_id:
            sess_obj = db.query(SessionModel).filter(SessionModel.id == session_id).first()
            if not sess_obj:
                session_id = None
            elif batch_id and sess_obj.batch_id != batch_id:
                raise HTTPException(status_code=400, detail="Assigned session does not belong to the selected batch.")

        now = datetime.now(timezone.utc)
        rule_set = RuleSet(
            name=name,
            batch_id=batch_id,
            session_id=session_id,
            created_by=current_user.id,
            version=1,
            status="draft",
            is_active=True,
            integrity_hash=""
        )
        db.add(rule_set)
        db.flush()

        # Device requirements
        dev_req = DevicePolicyRequirement(
            rule_set_id=rule_set.id,
            require_agent_enrolled=req.get("require_agent_enrolled", True),
            require_dns_or_content_filter=req.get("require_dns_or_content_filter", True),
            require_application_control=req.get("require_application_control", True),
            require_managed_browser_policy=req.get("require_managed_browser_policy", False),
            require_usb_storage_restriction=req.get("require_usb_storage_restriction", False),
            required_enforcement_level=req.get("required_enforcement_level", "development")
        )
        db.add(dev_req)

        # Allowed websites
        for site in req.get("allowed_websites", []):
            if site and isinstance(site, str) and site.strip():
                clean_s = site.strip().lower()
                PolicyService.validate_domain_rule(clean_s, "allowed")
                db.add(WebsiteRule(rule_set_id=rule_set.id, domain_pattern=clean_s, rule_mode="allowed", category="academic"))
                db.add(DomainRule(rule_set_id=rule_set.id, domain_pattern=clean_s, action="allow", reason="Allowed academic website"))

        # Blocked websites
        for site in req.get("blocked_websites", req.get("websites", [])):
            if site and isinstance(site, str) and site.strip():
                clean_s = site.strip().lower()
                PolicyService.validate_domain_rule(clean_s, "blocked")
                db.add(WebsiteRule(rule_set_id=rule_set.id, domain_pattern=clean_s, rule_mode="blocked", category="general"))
                db.add(DomainRule(rule_set_id=rule_set.id, domain_pattern=clean_s, action="block", reason="Restricted during session"))

        # Allowed applications
        for app in req.get("allowed_applications", []):
            if app and isinstance(app, str) and app.strip():
                clean_a = app.strip().lower()
                PolicyService.validate_application_rule(clean_a, "log")
                db.add(ApplicationRule(rule_set_id=rule_set.id, executable_name=clean_a, rule_mode="allowed", category="academic", action="log"))

        # Blocked applications
        blocked_action = req.get("blocked_app_action", "warn")
        if blocked_action not in ("log", "warn", "close"):
            blocked_action = "warn"
        for app in req.get("blocked_applications", req.get("applications", [])):
            if app and isinstance(app, str) and app.strip():
                clean_a = app.strip().lower()
                PolicyService.validate_application_rule(clean_a, blocked_action)
                db.add(ApplicationRule(rule_set_id=rule_set.id, executable_name=clean_a, rule_mode="blocked", category="general", action=blocked_action))

        db.commit()
        PolicyService.recalculate_integrity_hash(rule_set.id, db)
        db.refresh(rule_set)

        return {
            "_id": rule_set.id,
            "id": rule_set.id,
            "name": rule_set.name,
            "status": rule_set.status,
            "version": rule_set.version,
            "integrityHash": rule_set.integrity_hash,
            "is_active": rule_set.is_active,
            "batch_id": rule_set.batch_id,
            "session_id": rule_set.session_id,
            "created_at": rule_set.issued_at.isoformat() if rule_set.issued_at else now.isoformat()
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create policy rule set: {str(e)}"
        )

@router.put("/rules/{rule_id}")
def update_rule_generic(
    rule_id: str,
    req: dict,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    try:
        rule_set = db.query(RuleSet).filter(RuleSet.id == rule_id).first()
        if not rule_set:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule set not found")

        PolicyService._verify_rule_set_ownership(rule_set, current_user, db)

        # If published, edits create a new draft version
        target_rule_set = PolicyService._branch_new_draft_if_published(rule_set, current_user, db)

        name = req.get("name")
        if name and str(name).strip():
            target_rule_set.name = str(name).strip()

        session_id = req.get("session_id") or req.get("sessionId")
        if session_id is not None:
            if session_id:
                sess = db.query(SessionModel).filter(SessionModel.id == session_id).first()
                if not sess or sess.batch_id != target_rule_set.batch_id:
                    raise HTTPException(status_code=400, detail="Assigned session must belong to the same batch")
            target_rule_set.session_id = session_id or None

        # Overwrite website and app rules if explicitly provided
        if "allowed_websites" in req or "blocked_websites" in req or "websites" in req:
            db.query(WebsiteRule).filter(WebsiteRule.rule_set_id == target_rule_set.id).delete()
            db.query(DomainRule).filter(DomainRule.rule_set_id == target_rule_set.id).delete()

            for site in req.get("allowed_websites", []):
                if site and isinstance(site, str) and site.strip():
                    clean_s = site.strip().lower()
                    PolicyService.validate_domain_rule(clean_s, "allowed")
                    db.add(WebsiteRule(rule_set_id=target_rule_set.id, domain_pattern=clean_s, rule_mode="allowed", category="academic"))
                    db.add(DomainRule(rule_set_id=target_rule_set.id, domain_pattern=clean_s, action="allow", reason="Allowed academic website"))

            for site in req.get("blocked_websites", req.get("websites", [])):
                if site and isinstance(site, str) and site.strip():
                    clean_s = site.strip().lower()
                    PolicyService.validate_domain_rule(clean_s, "blocked")
                    db.add(WebsiteRule(rule_set_id=target_rule_set.id, domain_pattern=clean_s, rule_mode="blocked", category="general"))
                    db.add(DomainRule(rule_set_id=target_rule_set.id, domain_pattern=clean_s, action="block", reason="Restricted during session"))

        if "allowed_applications" in req or "blocked_applications" in req or "applications" in req:
            db.query(ApplicationRule).filter(ApplicationRule.rule_set_id == target_rule_set.id).delete()

            for app in req.get("allowed_applications", []):
                if app and isinstance(app, str) and app.strip():
                    clean_a = app.strip().lower()
                    PolicyService.validate_application_rule(clean_a, "log")
                    db.add(ApplicationRule(rule_set_id=target_rule_set.id, executable_name=clean_a, rule_mode="allowed", category="academic", action="log"))

            blocked_action = req.get("blocked_app_action", "warn")
            if blocked_action not in ("log", "warn", "close"):
                blocked_action = "warn"
            for app in req.get("blocked_applications", req.get("applications", [])):
                if app and isinstance(app, str) and app.strip():
                    clean_a = app.strip().lower()
                    PolicyService.validate_application_rule(clean_a, blocked_action)
                    db.add(ApplicationRule(rule_set_id=target_rule_set.id, executable_name=clean_a, rule_mode="blocked", category="general", action=blocked_action))

        # Device requirements
        dev_req = db.query(DevicePolicyRequirement).filter(DevicePolicyRequirement.rule_set_id == target_rule_set.id).first()
        if not dev_req:
            dev_req = DevicePolicyRequirement(rule_set_id=target_rule_set.id)
            db.add(dev_req)
        if "require_agent_enrolled" in req:
            dev_req.require_agent_enrolled = req["require_agent_enrolled"]
        if "require_dns_or_content_filter" in req:
            dev_req.require_dns_or_content_filter = req["require_dns_or_content_filter"]
        if "require_application_control" in req:
            dev_req.require_application_control = req["require_application_control"]
        if "require_managed_browser_policy" in req:
            dev_req.require_managed_browser_policy = req["require_managed_browser_policy"]
        if "require_usb_storage_restriction" in req:
            dev_req.require_usb_storage_restriction = req["require_usb_storage_restriction"]
        if "required_enforcement_level" in req:
            dev_req.required_enforcement_level = req["required_enforcement_level"]

        target_rule_set.updated_at = datetime.now(timezone.utc)
        db.commit()
        PolicyService.recalculate_integrity_hash(target_rule_set.id, db)
        db.refresh(target_rule_set)

        return {
            "_id": target_rule_set.id,
            "id": target_rule_set.id,
            "name": target_rule_set.name,
            "status": target_rule_set.status,
            "version": target_rule_set.version,
            "integrityHash": target_rule_set.integrity_hash,
            "is_active": target_rule_set.is_active,
            "batch_id": target_rule_set.batch_id,
            "session_id": target_rule_set.session_id
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update policy rule set: {str(e)}"
        )

@router.patch("/rules/{rule_id}/quick-update")
def quick_update_rule(
    rule_id: str,
    req: dict,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Quick live rule modification for live sessions."""
    try:
        rule_set = db.query(RuleSet).filter(RuleSet.id == rule_id).first()
        if not rule_set:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule set not found")
        PolicyService._verify_rule_set_ownership(rule_set, current_user, db)

        action = req.get("action")
        target_type = req.get("type", "website")
        raw_mode = str(req.get("rule_mode") or req.get("mode") or "blocked").strip().lower()
        rule_mode = "allowed" if raw_mode in ("allow", "allowed", "allowlist") else "blocked"
        item = str(req.get("item", "")).strip()
        if not item:
            raise HTTPException(status_code=400, detail="Item string cannot be empty")

        clean_item = item.strip().lower()
        if clean_item.endswith(".exe") or clean_item.endswith(".app"):
            target_type = "application"
        elif "://" in clean_item or any(clean_item.endswith(tld) for tld in [".com", ".org", ".net", ".io", ".ai", ".edu", ".in", ".gov", ".co"]):
            target_type = "website"

        if target_type == "website":
            clean_domain = clean_item
            if "://" in clean_domain:
                from urllib.parse import urlparse
                clean_domain = urlparse(clean_domain).netloc or clean_domain
            clean_domain = clean_domain.split("/")[0].split("?")[0].split("#")[0].split(":")[0].strip()
            PolicyService.validate_domain_rule(clean_domain, rule_mode)

            if action == "add":
                existing = db.query(WebsiteRule).filter(
                    WebsiteRule.rule_set_id == rule_id,
                    WebsiteRule.domain_pattern == clean_domain
                ).first()
                if not existing:
                    db.add(WebsiteRule(rule_set_id=rule_id, domain_pattern=clean_domain, rule_mode=rule_mode, category="general"))
                    db.add(DomainRule(rule_set_id=rule_id, domain_pattern=clean_domain, action="allow" if rule_mode == "allowed" else "block"))
                else:
                    existing.rule_mode = rule_mode
                    dom_rule = db.query(DomainRule).filter(
                        DomainRule.rule_set_id == rule_id,
                        DomainRule.domain_pattern == clean_domain
                    ).first()
                    if dom_rule:
                        dom_rule.action = "allow" if rule_mode == "allowed" else "block"
            elif action == "remove":
                db.query(WebsiteRule).filter(
                    WebsiteRule.rule_set_id == rule_id,
                    WebsiteRule.domain_pattern == clean_domain
                ).delete()
                db.query(DomainRule).filter(
                    DomainRule.rule_set_id == rule_id,
                    DomainRule.domain_pattern == clean_domain
                ).delete()

        elif target_type == "application":
            clean_exe = clean_item
            if not clean_exe.endswith(".exe") and not clean_exe.endswith(".app"):
                clean_exe = f"{clean_exe}.exe"
            PolicyService.validate_application_rule(clean_exe, "log" if rule_mode == "allowed" else "close")

            if action == "add":
                existing = db.query(ApplicationRule).filter(
                    ApplicationRule.rule_set_id == rule_id,
                    ApplicationRule.executable_name == clean_exe
                ).first()
                if not existing:
                    db.add(ApplicationRule(rule_set_id=rule_id, executable_name=clean_exe, rule_mode=rule_mode, action="log" if rule_mode == "allowed" else "close"))
                else:
                    existing.rule_mode = rule_mode
                    existing.action = "log" if rule_mode == "allowed" else "close"
            elif action == "remove":
                db.query(ApplicationRule).filter(
                    ApplicationRule.rule_set_id == rule_id,
                    ApplicationRule.executable_name == clean_exe
                ).delete()

        rule_set.version += 1
        rule_set.status = "published"
        rule_set.is_active = True
        rule_set.updated_at = datetime.now(timezone.utc)
        db.commit()

        # Recalculate hash and sign payload
        PolicyService.recalculate_integrity_hash(rule_id, db)
        canonical = PolicyService.get_canonical_policy_payload(rule_set, db)
        hash_val, signature_hex = sign_policy_payload(canonical)
        rule_set.integrity_hash = hash_val
        rule_set.signature = signature_hex
        db.commit()
        db.refresh(rule_set)

        # Update all active sessions using this rule set or batch
        active_sessions = []
        if rule_set.session_id:
            s = db.query(SessionModel).filter(SessionModel.id == rule_set.session_id).first()
            if s:
                active_sessions.append(s)
        if rule_set.batch_id:
            batch_sessions = db.query(SessionModel).filter(
                SessionModel.batch_id == rule_set.batch_id,
                SessionModel.status == "active"
            ).all()
            for bs in batch_sessions:
                if bs not in active_sessions:
                    active_sessions.append(bs)

        for sess in active_sessions:
            sess.rule_set_id = rule_set.id
            sess.policy_version = (sess.policy_version or 1) + 1
            sess.updated_at = datetime.now(timezone.utc)
            db.commit()
            broadcast_socket_event("policy_updated", {"session_id": sess.id, "policy_version": sess.policy_version}, sess.id)

        if not active_sessions and rule_set.session_id:
            broadcast_socket_event("policy_updated", {"session_id": rule_set.session_id, "policy_version": rule_set.version}, rule_set.session_id)

        from ..schemas.rule import RuleSetResponse
        full_response = RuleSetResponse.model_validate(rule_set).model_dump()
        full_response["_id"] = rule_set.id

        w_rules = rule_set.website_rules or []
        allowed_sites = [w.domain_pattern for w in w_rules if w.rule_mode == "allowed"]
        blocked_sites = [w.domain_pattern for w in w_rules if w.rule_mode == "blocked"]
        if not w_rules and rule_set.domain_rules:
            allowed_sites = [d.domain_pattern for d in rule_set.domain_rules if d.action in ("allow", "log")]
            blocked_sites = [d.domain_pattern for d in rule_set.domain_rules if d.action == "block"]

        a_rules = rule_set.application_rules or []
        allowed_apps = [a.executable_name for a in a_rules if a.rule_mode == "allowed"]
        blocked_apps = [a.executable_name for a in a_rules if a.rule_mode != "allowed"]

        full_response["websites"] = allowed_sites + blocked_sites
        full_response["applications"] = allowed_apps + blocked_apps
        full_response["allowed_websites"] = allowed_sites
        full_response["blocked_websites"] = blocked_sites
        full_response["allowed_applications"] = allowed_apps
        full_response["blocked_applications"] = blocked_apps

        return full_response
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to quick-update rule set: {str(e)}"
        )

@router.delete("/rules/{rule_id}")
def delete_rule_generic(
    rule_id: str,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    try:
        rule_set = db.query(RuleSet).filter(RuleSet.id == rule_id).first()
        if not rule_set:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule set not found")
        PolicyService._verify_rule_set_ownership(rule_set, current_user, db)
        db.delete(rule_set)
        db.commit()
        return {"status": "success", "message": "Rule set deleted successfully"}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to delete rule set: {str(e)}"
        )
