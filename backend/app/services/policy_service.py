"""
Policy & RuleSet Synchronization Service.
"""

import json
import hashlib
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..models.rule import RuleSet, WebsiteRule, DomainRule, ApplicationRule, DevicePolicyRequirement, ProtectedProcess
from ..models.session import SessionModel, SessionParticipant
from ..models.class_model import ClassModel, ClassMember
from ..models.batch import Batch, BatchMember
from ..models.device import AgentDevice, AgentPolicyAssignment, AgentPolicy
from ..models.user import User
from ..models.audit_log import AuditLog
from .schedule_evaluator import ScheduleEvaluator
from ..schemas.rule import (
    RuleSetCreate,
    RuleSetUpdate,
    WebsiteRuleCreate,
    WebsiteRuleUpdate,
    DomainRuleCreate,
    ApplicationRuleCreate,
    ApplicationRuleUpdate,
    DevicePolicyRequirementUpdate,
    PROTECTED_ALLOWLIST
)
from ..core.security import sign_policy_payload
from ..core.sockets import broadcast_socket_event

DISALLOWED_SHELLS = {
    "cmd.exe", "powershell.exe", "pwsh.exe", "bash.exe", "bash", "sh.exe", "sh",
    "wscript.exe", "cscript.exe", "cmd", "powershell", "pwsh",
    "reg.exe", "regedit.exe", "netsh.exe", "sc.exe", "iptables", "pfctl", "mstsc.exe",
    "osascript", "launchctl", "sudo", "su", "zsh"
}
DISALLOWED_EXTENSIONS = (
    ".bat", ".cmd", ".ps1", ".vbs", ".js", ".sh", ".rb", ".pl",
    ".dll", ".sys", ".kext", ".drv", ".inf", ".reg"
)
INJECTION_CHARACTERS = {";", "|", "&", ">", "<", "`", "$", "(", ")", "\n", "\r", "\\"}
SYSTEM_PROTECTED_PROCESSES = {
    "explorer.exe", "svchost.exe", "csrss.exe", "lsass.exe", "services.exe",
    "winlogon.exe", "smss.exe", "system", "msmpeng.exe", "securityhealthservice.exe",
    "narrator.exe", "osk.exe", "magnify.exe", "acad_agent.exe", "academiashield.exe",
    "launchd", "kernel_task", "windowserver", "loginwindow"
}

class PolicyService:
    """Manages Policy RuleSets, SHA-256 integrity hashing, cryptographic signing, security guardrails, and active policy resolution."""

    @staticmethod
    def _verify_class_ownership(class_id: str, user: User, db: Session) -> ClassModel:
        class_obj = db.query(ClassModel).filter(ClassModel.id == class_id).first()
        if not class_obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")
        if user.role != "admin" and class_obj.professor_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only class owner can manage policy rule sets")
        return class_obj

    @staticmethod
    def _verify_batch_ownership(batch_id: str, user: User, db: Session) -> Batch:
        batch = db.query(Batch).filter(Batch.id == batch_id).first()
        if not batch:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")
        if user.role != "admin" and batch.professor_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only batch owner can manage policy rule sets")
        return batch

    @staticmethod
    def _verify_rule_set_ownership(rule_set: RuleSet, user: User, db: Session):
        if user.role == "admin":
            return
        if rule_set.created_by == user.id:
            return
        if rule_set.batch_id:
            PolicyService._verify_batch_ownership(rule_set.batch_id, user, db)
        elif rule_set.class_id:
            PolicyService._verify_class_ownership(rule_set.class_id, user, db)
        else:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied to manage this rule set")

    @staticmethod
    def _branch_new_draft_if_published(rule_set: RuleSet, user: User, db: Session) -> RuleSet:
        """
        Published policies are immutable; edits create a new draft version.
        If the policy is published, clones all rules into a new draft RuleSet.
        """
        if rule_set.status != "published":
            return rule_set

        now = datetime.now(timezone.utc)
        new_version = rule_set.version + 1
        new_rule_set = RuleSet(
            batch_id=rule_set.batch_id,
            session_id=rule_set.session_id,
            class_id=rule_set.class_id,
            name=f"{rule_set.name} (v{new_version} Draft)",
            version=new_version,
            status="draft",
            is_active=False,
            issued_at=now,
            expires_at=rule_set.expires_at,
            created_by=user.id,
            integrity_hash=""
        )
        db.add(new_rule_set)
        db.flush()

        # Clone website rules
        w_rules = db.query(WebsiteRule).filter(WebsiteRule.rule_set_id == rule_set.id).all()
        for wr in w_rules:
            db.add(WebsiteRule(
                rule_set_id=new_rule_set.id,
                domain_pattern=wr.domain_pattern,
                rule_mode=wr.rule_mode,
                category=wr.category,
                priority=wr.priority,
                is_enabled=wr.is_enabled,
                reason=wr.reason
            ))

        # Clone domain rules
        d_rules = db.query(DomainRule).filter(DomainRule.rule_set_id == rule_set.id).all()
        for dr in d_rules:
            db.add(DomainRule(
                rule_set_id=new_rule_set.id,
                domain_pattern=dr.domain_pattern,
                rule_type=dr.rule_type,
                action=dr.action,
                priority=dr.priority,
                is_enabled=dr.is_enabled,
                reason=dr.reason
            ))

        # Clone app rules
        a_rules = db.query(ApplicationRule).filter(ApplicationRule.rule_set_id == rule_set.id).all()
        for ar in a_rules:
            db.add(ApplicationRule(
                rule_set_id=new_rule_set.id,
                application_name=ar.application_name,
                executable_name=ar.executable_name,
                executable_path_pattern=ar.executable_path_pattern,
                trusted_hash=ar.trusted_hash,
                rule_mode=ar.rule_mode,
                category=ar.category,
                action=ar.action,
                priority=ar.priority,
                is_enabled=ar.is_enabled,
                reason=ar.reason,
                cooldown_seconds=ar.cooldown_seconds
            ))

        # Clone device requirements
        dev_req = db.query(DevicePolicyRequirement).filter(DevicePolicyRequirement.rule_set_id == rule_set.id).first()
        if dev_req:
            db.add(DevicePolicyRequirement(
                rule_set_id=new_rule_set.id,
                require_agent_enrolled=dev_req.require_agent_enrolled,
                require_dns_or_content_filter=dev_req.require_dns_or_content_filter,
                require_application_control=dev_req.require_application_control,
                require_managed_browser_policy=dev_req.require_managed_browser_policy,
                require_usb_storage_restriction=dev_req.require_usb_storage_restriction,
                required_enforcement_level=dev_req.required_enforcement_level
            ))

        db.commit()
        PolicyService.recalculate_integrity_hash(new_rule_set.id, db)
        db.refresh(new_rule_set)
        return new_rule_set

    @staticmethod
    def validate_application_rule(clean_exe: str, action: str):
        action_clean = action.strip().lower() if action else ""
        if action_clean not in ("log", "warn", "close"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Action '{action}' is disallowed. Permitted application actions: log, warn, close."
            )

        if not clean_exe or len(clean_exe.strip()) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Executable name cannot be empty."
            )

        # Reject shell metacharacters or command injection attempts
        if any(char in clean_exe for char in INJECTION_CHARACTERS):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Arbitrary commands, pipe operators, and shell syntax are strictly forbidden in application rules."
            )

        if clean_exe in DISALLOWED_SHELLS or any(clean_exe.endswith(ext) for ext in DISALLOWED_EXTENSIONS):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Shell commands, interpreters, registry utilities, drivers, and script files cannot be targeted in application rules."
            )

        if action_clean in ("close", "warn") and (clean_exe in PROTECTED_ALLOWLIST or clean_exe in SYSTEM_PROTECTED_PROCESSES):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Executable '{clean_exe}' is a protected system process and cannot be blocked or closed."
            )

    @staticmethod
    def validate_domain_rule(domain_pattern: str, action_or_mode: str):
        mode_clean = action_or_mode.strip().lower() if action_or_mode else ""
        if mode_clean not in ("allow", "allowed", "block", "blocked", "log"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Mode/action '{action_or_mode}' is disallowed. Permitted values: allowed, blocked, log."
            )
        if not domain_pattern or len(domain_pattern.strip()) < 3:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid domain pattern."
            )
        if any(char in domain_pattern for char in INJECTION_CHARACTERS or char in (" ", "\t", "\\")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid characters or command injection syntax in domain pattern."
            )

    @staticmethod
    def create_batch_rule_set(batch_id: str, req: RuleSetCreate, user: User, db: Session) -> RuleSet:
        batch = PolicyService._verify_batch_ownership(batch_id, user, db)

        # If session_id provided, verify session belongs to same batch
        session_id = req.session_id
        if session_id:
            sess = db.query(SessionModel).filter(SessionModel.id == session_id).first()
            if not sess or sess.batch_id != batch_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assigned session must belong to the specified batch.")

        now = datetime.now(timezone.utc)
        rule_set = RuleSet(
            batch_id=batch_id,
            session_id=session_id,
            name=req.name.strip(),
            version=1,
            status="draft",
            is_active=True,
            issued_at=now,
            expires_at=req.expires_at,
            created_by=user.id,
            created_at=now,
            updated_at=now,
            integrity_hash=""
        )
        db.add(rule_set)
        db.flush()

        # Create default device policy requirements
        dev_req = DevicePolicyRequirement(
            rule_set_id=rule_set.id,
            require_agent_enrolled=True,
            require_dns_or_content_filter=True,
            require_application_control=True,
            require_managed_browser_policy=False,
            require_usb_storage_restriction=False,
            required_enforcement_level="development"
        )
        db.add(dev_req)
        db.commit()

        PolicyService.recalculate_integrity_hash(rule_set.id, db)
        db.refresh(rule_set)

        # Audit log
        db.add(AuditLog(
            actor_user_id=user.id,
            action="RULE_SET_CREATED",
            entity_type="RULE_SET",
            entity_id=rule_set.id,
            metadata_json={"name": rule_set.name, "batch_id": batch_id, "status": "draft"}
        ))
        db.commit()

        return rule_set

    @staticmethod
    def create_rule_set(class_id: str, req: RuleSetCreate, user: User, db: Session) -> RuleSet:
        class_obj = PolicyService._verify_class_ownership(class_id, user, db)

        now = datetime.now(timezone.utc)
        rule_set = RuleSet(
            class_id=class_id,
            name=req.name.strip(),
            version=1,
            status="draft",
            is_active=True,
            issued_at=now,
            expires_at=req.expires_at,
            created_by=user.id,
            created_at=now,
            updated_at=now,
            integrity_hash=""
        )
        db.add(rule_set)
        db.flush()

        dev_req = DevicePolicyRequirement(
            rule_set_id=rule_set.id,
            require_agent_enrolled=True,
            require_dns_or_content_filter=True,
            require_application_control=True,
            require_managed_browser_policy=False,
            require_usb_storage_restriction=False,
            required_enforcement_level="development"
        )
        db.add(dev_req)
        db.commit()

        PolicyService.recalculate_integrity_hash(rule_set.id, db)
        db.refresh(rule_set)
        return rule_set

    @staticmethod
    def get_batch_rule_sets(batch_id: str, user: User, db: Session) -> List[RuleSet]:
        PolicyService._verify_batch_ownership(batch_id, user, db)
        return db.query(RuleSet).filter(RuleSet.batch_id == batch_id).order_by(RuleSet.created_at.desc()).all()

    @staticmethod
    def get_rule_set(rule_set_id: str, user: User, db: Session) -> RuleSet:
        rule_set = db.query(RuleSet).filter(RuleSet.id == rule_set_id).first()
        if not rule_set:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule set not found")
        PolicyService._verify_rule_set_ownership(rule_set, user, db)
        return rule_set

    @staticmethod
    def update_rule_set(rule_set_id: str, req: RuleSetUpdate, user: User, db: Session) -> RuleSet:
        rule_set = db.query(RuleSet).filter(RuleSet.id == rule_set_id).first()
        if not rule_set:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule set not found")
        PolicyService._verify_rule_set_ownership(rule_set, user, db)

        # Immutability check: if published, branch to new draft version
        rule_set = PolicyService._branch_new_draft_if_published(rule_set, user, db)

        if req.name is not None:
            rule_set.name = req.name.strip()
        if req.session_id is not None:
            if req.session_id:
                sess = db.query(SessionModel).filter(SessionModel.id == req.session_id).first()
                if not sess or sess.batch_id != rule_set.batch_id:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assigned session must belong to the same batch")
            rule_set.session_id = req.session_id or None
        if req.expires_at is not None:
            rule_set.expires_at = req.expires_at
        if req.is_active is not None:
            rule_set.is_active = req.is_active

        rule_set.updated_at = datetime.now(timezone.utc)
        db.commit()
        PolicyService.recalculate_integrity_hash(rule_set.id, db)
        db.refresh(rule_set)

        db.add(AuditLog(
            actor_user_id=user.id,
            action="RULE_SET_UPDATED",
            entity_type="RULE_SET",
            entity_id=rule_set.id,
            metadata_json={"name": rule_set.name, "version": rule_set.version, "status": rule_set.status}
        ))
        db.commit()
        return rule_set

    @staticmethod
    def publish_rule_set(rule_set_id: str, user: User, db: Session) -> RuleSet:
        rule_set = db.query(RuleSet).filter(RuleSet.id == rule_set_id).first()
        if not rule_set:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule set not found")

        PolicyService._verify_rule_set_ownership(rule_set, user, db)

        # Deactivate previously published active rule sets for this batch or session
        if rule_set.batch_id:
            db.query(RuleSet).filter(
                RuleSet.batch_id == rule_set.batch_id,
                RuleSet.id != rule_set.id,
                RuleSet.is_active == True,
                RuleSet.status == "published"
            ).update({"is_active": False})

        rule_set.status = "published"
        rule_set.is_active = True
        rule_set.issued_at = datetime.now(timezone.utc)
        rule_set.updated_at = datetime.now(timezone.utc)

        # Recalculate hash and sign payload
        PolicyService.recalculate_integrity_hash(rule_set.id, db)
        canonical = PolicyService.get_canonical_policy_payload(rule_set, db)
        hash_val, signature_hex = sign_policy_payload(canonical)
        rule_set.integrity_hash = hash_val
        rule_set.signature = signature_hex
        db.commit()
        db.refresh(rule_set)

        # If rule set is assigned to a session, update session policy_version
        if rule_set.session_id:
            sess = db.query(SessionModel).filter(SessionModel.id == rule_set.session_id).first()
            if sess:
                sess.policy_version = (sess.policy_version or 1) + 1
                db.commit()
                broadcast_socket_event("policy_updated", {"session_id": sess.id, "policy_version": sess.policy_version}, sess.id)

        db.add(AuditLog(
            actor_user_id=user.id,
            action="RULE_SET_PUBLISHED",
            entity_type="RULE_SET",
            entity_id=rule_set.id,
            metadata_json={"name": rule_set.name, "version": rule_set.version, "integrity_hash": hash_val}
        ))
        db.commit()

        broadcast_socket_event("policy_published", {"rule_set_id": rule_set.id, "version": rule_set.version, "batch_id": rule_set.batch_id})
        return rule_set

    @staticmethod
    def revoke_rule_set(rule_set_id: str, user: User, db: Session) -> RuleSet:
        rule_set = db.query(RuleSet).filter(RuleSet.id == rule_set_id).first()
        if not rule_set:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule set not found")

        PolicyService._verify_rule_set_ownership(rule_set, user, db)

        rule_set.status = "revoked"
        rule_set.is_active = False
        rule_set.updated_at = datetime.now(timezone.utc)
        db.commit()

        if rule_set.session_id:
            sess = db.query(SessionModel).filter(SessionModel.id == rule_set.session_id).first()
            if sess:
                sess.policy_version = (sess.policy_version or 1) + 1
                db.commit()
                broadcast_socket_event("policy_updated", {"session_id": sess.id, "policy_version": sess.policy_version}, sess.id)

        db.add(AuditLog(
            actor_user_id=user.id,
            action="RULE_SET_REVOKED",
            entity_type="RULE_SET",
            entity_id=rule_set.id,
            metadata_json={"name": rule_set.name, "version": rule_set.version}
        ))
        db.commit()

        broadcast_socket_event("policy_revoked", {"rule_set_id": rule_set.id, "version": rule_set.version})
        return rule_set

    @staticmethod
    def assign_rule_set_to_session(session_id: str, rule_set_id: str, user: User, db: Session) -> SessionModel:
        session_obj = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not session_obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        if user.role != "admin" and session_obj.created_by != user.id:
            batch = db.query(Batch).filter(Batch.id == session_obj.batch_id).first() if session_obj.batch_id else None
            if not batch or batch.professor_id != user.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied to assign policy to this session")

        rule_set = db.query(RuleSet).filter(RuleSet.id == rule_set_id).first()
        if not rule_set:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule set not found")

        PolicyService._verify_rule_set_ownership(rule_set, user, db)

        # Batch validation
        if rule_set.batch_id and session_obj.batch_id and rule_set.batch_id != session_obj.batch_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rule set belongs to a different batch than the session")

        # Must be published
        if rule_set.status != "published":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only published policy rule sets can be assigned to a session")

        session_obj.rule_set_id = rule_set.id
        rule_set.session_id = session_obj.id
        session_obj.policy_version = (session_obj.policy_version or 1) + 1
        session_obj.updated_at = datetime.now(timezone.utc)
        db.commit()

        db.add(AuditLog(
            actor_user_id=user.id,
            action="SESSION_RULE_SET_ASSIGNED",
            entity_type="SESSION",
            entity_id=session_obj.id,
            metadata_json={"session_id": session_obj.id, "rule_set_id": rule_set.id, "policy_version": session_obj.policy_version}
        ))
        db.commit()

        broadcast_socket_event("policy_updated", {"session_id": session_obj.id, "policy_version": session_obj.policy_version}, session_obj.id)
        return session_obj

    @staticmethod
    def add_website_rule(rule_set_id: str, req: WebsiteRuleCreate, user: User, db: Session) -> WebsiteRule:
        rule_set = db.query(RuleSet).filter(RuleSet.id == rule_set_id).first()
        if not rule_set:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule set not found")

        PolicyService._verify_rule_set_ownership(rule_set, user, db)
        PolicyService.validate_domain_rule(req.domain_pattern, req.rule_mode)

        # Immutability check
        target_rule_set = PolicyService._branch_new_draft_if_published(rule_set, user, db)

        clean_domain = req.domain_pattern.strip().lower()
        rule_mode = req.rule_mode.strip().lower()
        if rule_mode in ("allow", "allowed"):
            rule_mode = "allowed"
        else:
            rule_mode = "blocked"

        w_rule = WebsiteRule(
            rule_set_id=target_rule_set.id,
            domain_pattern=clean_domain,
            rule_mode=rule_mode,
            category=req.category,
            priority=req.priority,
            is_enabled=req.is_enabled,
            reason=req.reason
        )
        db.add(w_rule)

        # Also add backward-compatible DomainRule
        db.add(DomainRule(
            rule_set_id=target_rule_set.id,
            domain_pattern=clean_domain,
            action="allow" if rule_mode == "allowed" else "block",
            priority=req.priority,
            reason=req.reason
        ))

        target_rule_set.version += 1
        target_rule_set.updated_at = datetime.now(timezone.utc)
        db.commit()
        PolicyService.recalculate_integrity_hash(target_rule_set.id, db)
        db.refresh(w_rule)
        return w_rule

    @staticmethod
    def update_website_rule(rule_id: str, req: WebsiteRuleUpdate, user: User, db: Session) -> WebsiteRule:
        w_rule = db.query(WebsiteRule).filter(WebsiteRule.id == rule_id).first()
        if not w_rule:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Website rule not found")

        rule_set = db.query(RuleSet).filter(RuleSet.id == w_rule.rule_set_id).first()
        PolicyService._verify_rule_set_ownership(rule_set, user, db)

        # Immutability check
        target_rule_set = PolicyService._branch_new_draft_if_published(rule_set, user, db)
        if target_rule_set.id != rule_set.id:
            # Find cloned rule
            w_rule = db.query(WebsiteRule).filter(
                WebsiteRule.rule_set_id == target_rule_set.id,
                WebsiteRule.domain_pattern == w_rule.domain_pattern
            ).first()

        if req.domain_pattern is not None:
            clean_dom = req.domain_pattern.strip().lower()
            PolicyService.validate_domain_rule(clean_dom, req.rule_mode or w_rule.rule_mode)
            w_rule.domain_pattern = clean_dom

        if req.rule_mode is not None:
            mode_clean = req.rule_mode.strip().lower()
            w_rule.rule_mode = "allowed" if mode_clean in ("allow", "allowed") else "blocked"

        if req.category is not None:
            w_rule.category = req.category
        if req.priority is not None:
            w_rule.priority = req.priority
        if req.is_enabled is not None:
            w_rule.is_enabled = req.is_enabled
        if req.reason is not None:
            w_rule.reason = req.reason

        w_rule.updated_at = datetime.now(timezone.utc)
        target_rule_set.version += 1
        target_rule_set.updated_at = datetime.now(timezone.utc)
        db.commit()
        PolicyService.recalculate_integrity_hash(target_rule_set.id, db)
        db.refresh(w_rule)
        return w_rule

    @staticmethod
    def delete_website_rule(rule_id: str, user: User, db: Session):
        w_rule = db.query(WebsiteRule).filter(WebsiteRule.id == rule_id).first()
        if not w_rule:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Website rule not found")

        rule_set = db.query(RuleSet).filter(RuleSet.id == w_rule.rule_set_id).first()
        PolicyService._verify_rule_set_ownership(rule_set, user, db)

        target_rule_set = PolicyService._branch_new_draft_if_published(rule_set, user, db)
        if target_rule_set.id != rule_set.id:
            w_rule = db.query(WebsiteRule).filter(
                WebsiteRule.rule_set_id == target_rule_set.id,
                WebsiteRule.domain_pattern == w_rule.domain_pattern
            ).first()

        if w_rule:
            # Delete corresponding DomainRule as well
            db.query(DomainRule).filter(
                DomainRule.rule_set_id == target_rule_set.id,
                DomainRule.domain_pattern == w_rule.domain_pattern
            ).delete()
            db.delete(w_rule)

        target_rule_set.version += 1
        target_rule_set.updated_at = datetime.now(timezone.utc)
        db.commit()
        PolicyService.recalculate_integrity_hash(target_rule_set.id, db)
        return {"status": "ok", "message": "Website rule deleted successfully"}

    @staticmethod
    def add_domain_rule(rule_set_id: str, req: DomainRuleCreate, user: User, db: Session) -> DomainRule:
        rule_set = db.query(RuleSet).filter(RuleSet.id == rule_set_id).first()
        if not rule_set:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule set not found")

        PolicyService._verify_rule_set_ownership(rule_set, user, db)
        PolicyService.validate_domain_rule(req.domain_pattern, req.action)

        target_rule_set = PolicyService._branch_new_draft_if_published(rule_set, user, db)

        domain_rule = DomainRule(
            rule_set_id=target_rule_set.id,
            domain_pattern=req.domain_pattern.strip().lower(),
            rule_type=req.rule_type,
            action=req.action,
            priority=req.priority,
            reason=req.reason
        )
        db.add(domain_rule)

        # Also add to WebsiteRule
        db.add(WebsiteRule(
            rule_set_id=target_rule_set.id,
            domain_pattern=req.domain_pattern.strip().lower(),
            rule_mode="allowed" if req.action in ("allow", "log") else "blocked",
            category="academic" if req.action in ("allow", "log") else "general",
            priority=req.priority,
            reason=req.reason
        ))

        target_rule_set.version += 1
        target_rule_set.updated_at = datetime.now(timezone.utc)
        db.commit()
        PolicyService.recalculate_integrity_hash(target_rule_set.id, db)
        db.refresh(domain_rule)
        return domain_rule

    @staticmethod
    def add_application_rule(rule_set_id: str, req: ApplicationRuleCreate, user: User, db: Session) -> ApplicationRule:
        rule_set = db.query(RuleSet).filter(RuleSet.id == rule_set_id).first()
        if not rule_set:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule set not found")

        PolicyService._verify_rule_set_ownership(rule_set, user, db)

        clean_exe = req.executable_name.strip().lower()
        PolicyService.validate_application_rule(clean_exe, req.action)

        target_rule_set = PolicyService._branch_new_draft_if_published(rule_set, user, db)

        existing = db.query(ApplicationRule).filter(
            ApplicationRule.rule_set_id == target_rule_set.id,
            ApplicationRule.executable_name == clean_exe
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"An application rule for executable '{clean_exe}' already exists in this rule set"
            )

        app_rule = ApplicationRule(
            rule_set_id=target_rule_set.id,
            application_name=req.application_name,
            executable_name=clean_exe,
            executable_path_pattern=req.executable_path_pattern,
            trusted_hash=req.trusted_hash,
            rule_mode=req.rule_mode,
            category=req.category,
            action=req.action,
            priority=req.priority,
            reason=req.reason,
            cooldown_seconds=req.cooldown_seconds
        )
        db.add(app_rule)

        target_rule_set.version += 1
        target_rule_set.updated_at = datetime.now(timezone.utc)
        db.commit()
        PolicyService.recalculate_integrity_hash(target_rule_set.id, db)
        db.refresh(app_rule)
        return app_rule

    @staticmethod
    def get_application_rules(rule_set_id: str, user: User, db: Session) -> List[ApplicationRule]:
        rule_set = db.query(RuleSet).filter(RuleSet.id == rule_set_id).first()
        if not rule_set:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule set not found")
        PolicyService._verify_rule_set_ownership(rule_set, user, db)
        return db.query(ApplicationRule).filter(ApplicationRule.rule_set_id == rule_set_id).all()

    @staticmethod
    def update_application_rule(rule_id: str, req: ApplicationRuleUpdate, user: User, db: Session) -> ApplicationRule:
        app_rule = db.query(ApplicationRule).filter(ApplicationRule.id == rule_id).first()
        if not app_rule:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application rule not found")

        rule_set = db.query(RuleSet).filter(RuleSet.id == app_rule.rule_set_id).first()
        PolicyService._verify_rule_set_ownership(rule_set, user, db)

        target_rule_set = PolicyService._branch_new_draft_if_published(rule_set, user, db)
        if target_rule_set.id != rule_set.id:
            app_rule = db.query(ApplicationRule).filter(
                ApplicationRule.rule_set_id == target_rule_set.id,
                ApplicationRule.executable_name == app_rule.executable_name
            ).first()

        if req.executable_name is not None:
            clean_exe = req.executable_name.strip().lower()
            PolicyService.validate_application_rule(clean_exe, req.action or app_rule.action)
            app_rule.executable_name = clean_exe

        if req.action is not None:
            PolicyService.validate_application_rule(app_rule.executable_name, req.action)
            app_rule.action = req.action

        if req.application_name is not None:
            app_rule.application_name = req.application_name
        if req.rule_mode is not None:
            app_rule.rule_mode = req.rule_mode
        if req.category is not None:
            app_rule.category = req.category
        if req.executable_path_pattern is not None:
            app_rule.executable_path_pattern = req.executable_path_pattern
        if req.trusted_hash is not None:
            app_rule.trusted_hash = req.trusted_hash
        if req.priority is not None:
            app_rule.priority = req.priority
        if req.is_enabled is not None:
            app_rule.is_enabled = req.is_enabled
        if req.reason is not None:
            app_rule.reason = req.reason
        if req.cooldown_seconds is not None:
            app_rule.cooldown_seconds = req.cooldown_seconds

        app_rule.updated_at = datetime.now(timezone.utc)
        target_rule_set.version += 1
        target_rule_set.updated_at = datetime.now(timezone.utc)
        db.commit()
        PolicyService.recalculate_integrity_hash(target_rule_set.id, db)
        db.refresh(app_rule)
        return app_rule

    @staticmethod
    def delete_application_rule(rule_id: str, user: User, db: Session):
        app_rule = db.query(ApplicationRule).filter(ApplicationRule.id == rule_id).first()
        if not app_rule:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application rule not found")

        rule_set = db.query(RuleSet).filter(RuleSet.id == app_rule.rule_set_id).first()
        PolicyService._verify_rule_set_ownership(rule_set, user, db)

        target_rule_set = PolicyService._branch_new_draft_if_published(rule_set, user, db)
        if target_rule_set.id != rule_set.id:
            app_rule = db.query(ApplicationRule).filter(
                ApplicationRule.rule_set_id == target_rule_set.id,
                ApplicationRule.executable_name == app_rule.executable_name
            ).first()

        if app_rule:
            db.delete(app_rule)

        target_rule_set.version += 1
        target_rule_set.updated_at = datetime.now(timezone.utc)
        db.commit()
        PolicyService.recalculate_integrity_hash(target_rule_set.id, db)
        return {"status": "ok", "message": "Application rule deleted successfully"}

    @staticmethod
    def update_device_requirements(rule_set_id: str, req: DevicePolicyRequirementUpdate, user: User, db: Session) -> DevicePolicyRequirement:
        rule_set = db.query(RuleSet).filter(RuleSet.id == rule_set_id).first()
        if not rule_set:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule set not found")

        PolicyService._verify_rule_set_ownership(rule_set, user, db)
        target_rule_set = PolicyService._branch_new_draft_if_published(rule_set, user, db)

        dev_req = db.query(DevicePolicyRequirement).filter(DevicePolicyRequirement.rule_set_id == target_rule_set.id).first()
        if not dev_req:
            dev_req = DevicePolicyRequirement(rule_set_id=target_rule_set.id)
            db.add(dev_req)

        if req.require_agent_enrolled is not None:
            dev_req.require_agent_enrolled = req.require_agent_enrolled
        if req.require_dns_or_content_filter is not None:
            dev_req.require_dns_or_content_filter = req.require_dns_or_content_filter
        if req.require_application_control is not None:
            dev_req.require_application_control = req.require_application_control
        if req.require_managed_browser_policy is not None:
            dev_req.require_managed_browser_policy = req.require_managed_browser_policy
        if req.require_usb_storage_restriction is not None:
            dev_req.require_usb_storage_restriction = req.require_usb_storage_restriction
        if req.required_enforcement_level is not None:
            dev_req.required_enforcement_level = req.required_enforcement_level

        dev_req.updated_at = datetime.now(timezone.utc)
        target_rule_set.version += 1
        target_rule_set.updated_at = datetime.now(timezone.utc)
        db.commit()
        PolicyService.recalculate_integrity_hash(target_rule_set.id, db)
        db.refresh(dev_req)
        return dev_req

    @staticmethod
    def get_canonical_policy_payload(rule_set: RuleSet, db: Session) -> Dict[str, Any]:
        """Construct deterministic canonical dictionary for hashing and signing."""
        w_rules = db.query(WebsiteRule).filter(WebsiteRule.rule_set_id == rule_set.id, WebsiteRule.is_enabled == True).all()
        a_rules = db.query(ApplicationRule).filter(ApplicationRule.rule_set_id == rule_set.id, ApplicationRule.is_enabled == True).all()
        dev_req = db.query(DevicePolicyRequirement).filter(DevicePolicyRequirement.rule_set_id == rule_set.id).first()

        # Fallback to domain_rules if no website_rules
        if not w_rules:
            d_rules = db.query(DomainRule).filter(DomainRule.rule_set_id == rule_set.id, DomainRule.is_enabled == True).all()
            allowed_sites = [{"rule_id": d.id, "domain_pattern": d.domain_pattern, "category": "academic"} for d in d_rules if d.action in ("allow", "log")]
            blocked_sites = [{"rule_id": d.id, "domain_pattern": d.domain_pattern, "reason": d.reason or "Not allowed"} for d in d_rules if d.action == "block"]
        else:
            allowed_sites = [{"rule_id": w.id, "domain_pattern": w.domain_pattern, "category": w.category} for w in w_rules if w.rule_mode == "allowed"]
            blocked_sites = [{"rule_id": w.id, "domain_pattern": w.domain_pattern, "reason": w.reason or "Not allowed"} for w in w_rules if w.rule_mode == "blocked"]

        allowed_apps = [{"rule_id": a.id, "executable_name": a.executable_name, "category": a.category} for a in a_rules if a.rule_mode == "allowed"]
        blocked_apps = [{"rule_id": a.id, "executable_name": a.executable_name, "action": a.action} for a in a_rules if a.rule_mode != "allowed"]

        device_requirements_data = {
            "require_agent_enrolled": dev_req.require_agent_enrolled if dev_req else True,
            "require_dns_or_content_filter": dev_req.require_dns_or_content_filter if dev_req else True,
            "require_application_control": dev_req.require_application_control if dev_req else True,
            "require_managed_browser_policy": dev_req.require_managed_browser_policy if dev_req else False,
            "require_usb_storage_restriction": dev_req.require_usb_storage_restriction if dev_req else False,
            "required_enforcement_level": dev_req.required_enforcement_level if dev_req else "development"
        }

        return {
            "policy_id": rule_set.id,
            "policy_version": rule_set.version,
            "batch_id": rule_set.batch_id or "",
            "session_id": rule_set.session_id or "",
            "name": rule_set.name,
            "status": rule_set.status,
            "issued_at": rule_set.issued_at.isoformat() if rule_set.issued_at else "",
            "expires_at": rule_set.expires_at.isoformat() if rule_set.expires_at else "",
            "allowed_websites": sorted(allowed_sites, key=lambda x: x["domain_pattern"]),
            "blocked_websites": sorted(blocked_sites, key=lambda x: x["domain_pattern"]),
            "allowed_applications": sorted(allowed_apps, key=lambda x: x["executable_name"]),
            "blocked_applications": sorted(blocked_apps, key=lambda x: x["executable_name"]),
            "device_requirements": device_requirements_data
        }

    @staticmethod
    def recalculate_integrity_hash(rule_set_id: str, db: Session) -> str:
        """Calculate SHA-256 integrity hash over all active rules and device requirements in the rule set."""
        rule_set = db.query(RuleSet).filter(RuleSet.id == rule_set_id).first()
        if not rule_set:
            return ""

        canonical = PolicyService.get_canonical_policy_payload(rule_set, db)
        canonical_json = json.dumps(canonical, sort_keys=True).encode("utf-8")
        calc_hash = hashlib.sha256(canonical_json).hexdigest()
        rule_set.integrity_hash = calc_hash
        db.commit()
        return calc_hash

    @staticmethod
    def get_active_policy_for_device(device: AgentDevice, db: Session) -> Dict[str, Any]:
        """
        Find current active session for the student owning the device,
        validate authorization, check capability compatibility, and return signed policy.
        """
        now = datetime.now(timezone.utc)

        # 1. Device Enrollment & Status Check
        if not device.is_active or getattr(device, "enrollment_status", "enrolled") == "revoked":
            return {
                "policy_active": False,
                "reason": "Device enrollment is revoked or inactive"
            }

        user = db.query(User).filter(User.id == device.user_id).first()
        active_session = None

        if user and user.role in ("professor", "admin"):
            active_session = db.query(SessionModel).filter(
                SessionModel.created_by == user.id,
                SessionModel.status.in_(["active", "Active"]),
                SessionModel.is_active == True
            ).first()

            if not active_session:
                return {"policy_active": False, "reason": "No active session created by professor"}
        else:
            # 2. Check student memberships across BatchMember and ClassMember
            batch_memberships = db.query(BatchMember).filter(BatchMember.student_id == device.user_id, BatchMember.status == "active").all()
            joined_batch_ids = [b.batch_id for b in batch_memberships]

            class_memberships = db.query(ClassMember).filter(ClassMember.student_id == device.user_id).all()
            joined_class_ids = [c.class_id for c in class_memberships]

            # 3. Check sessions where student enrolled/joined at least once
            joined_session_participants = db.query(SessionParticipant).filter(
                SessionParticipant.student_id == device.user_id
            ).all()
            joined_session_ids = [p.session_id for p in joined_session_participants]

            if not joined_session_ids:
                return {
                    "policy_active": False,
                    "reason": "Student has not manually joined an active class session"
                }

            if joined_batch_ids:
                active_session = db.query(SessionModel).filter(
                    SessionModel.id.in_(joined_session_ids),
                    SessionModel.batch_id.in_(joined_batch_ids),
                    SessionModel.status.in_(["active", "Active"]),
                    SessionModel.is_active == True,
                ).first()

            if not active_session and joined_class_ids:
                active_session = db.query(SessionModel).filter(
                    SessionModel.id.in_(joined_session_ids),
                    SessionModel.class_id.in_(joined_class_ids),
                    SessionModel.status.in_(["active", "Active"]),
                    SessionModel.is_active == True,
                ).first()

            if not active_session:
                return {
                    "policy_active": False,
                    "reason": "No active session found for student's enrolled batches/classes"
                }

        # Check emergency stop or session termination
        if getattr(active_session, 'emergency_stopped_at', None) or active_session.status.lower() in ("scheduled", "ended", "cancelled"):
            return {
                "policy_active": False,
                "session_id": active_session.id,
                "reason": f"Session status is {active_session.status}" + (" (Emergency Stopped)" if getattr(active_session, 'emergency_stopped_at', None) else "")
            }

        # Check / update AgentPolicyAssignment
        assignment = db.query(AgentPolicyAssignment).filter(
            AgentPolicyAssignment.session_id == active_session.id,
            AgentPolicyAssignment.student_id == device.user_id,
            AgentPolicyAssignment.device_id == device.id
        ).first()

        if assignment:
            if assignment.state in ("revoked", "restored", "failed"):
                return {
                    "policy_active": False,
                    "session_id": active_session.id,
                    "reason": f"Policy assignment is {assignment.state}"
                }
            if assignment.state == "pending":
                assignment.state = "active"
                assignment.activated_at = datetime.now(timezone.utc)
            assignment.last_heartbeat_at = datetime.now(timezone.utc)
            db.commit()
        else:
            assignment = AgentPolicyAssignment(
                session_id=active_session.id,
                student_id=device.user_id,
                device_id=device.id,
                state="active",
                assigned_at=datetime.now(timezone.utc),
                activated_at=datetime.now(timezone.utc),
                last_heartbeat_at=datetime.now(timezone.utc)
            )
            db.add(assignment)
            db.commit()

        # 4. Find RuleSet bound to session or batch/class
        rule_set = None
        if active_session.rule_set_id:
            rule_set = db.query(RuleSet).filter(RuleSet.id == active_session.rule_set_id).first()

        if not rule_set and active_session.batch_id:
            rule_set = db.query(RuleSet).filter(
                RuleSet.batch_id == active_session.batch_id,
                RuleSet.is_active == True,
                RuleSet.status == "published"
            ).first() or db.query(RuleSet).filter(
                RuleSet.batch_id == active_session.batch_id,
                RuleSet.is_active == True
            ).first()

        if not rule_set and active_session.class_id:
            rule_set = db.query(RuleSet).filter(RuleSet.class_id == active_session.class_id, RuleSet.is_active == True).first()

        if not rule_set and active_session.created_by:
            rule_set = db.query(RuleSet).filter(RuleSet.created_by == active_session.created_by, RuleSet.is_active == True).order_by(RuleSet.updated_at.desc()).first()

        if not rule_set:
            rule_set = db.query(RuleSet).filter(RuleSet.is_active == True).order_by(RuleSet.updated_at.desc()).first()

        if rule_set and active_session.rule_set_id != rule_set.id:
            active_session.rule_set_id = rule_set.id
            db.commit()

        if not rule_set or (rule_set.expires_at and rule_set.expires_at.replace(tzinfo=timezone.utc) < now):
            return {
                "policy_active": False,
                "session_id": active_session.id,
                "reason": "Rule set not found or expired"
            }

        # 5. Device compliance requirements
        dev_req = db.query(DevicePolicyRequirement).filter(DevicePolicyRequirement.rule_set_id == rule_set.id).first()
        required_compliance = dev_req.required_enforcement_level if dev_req else getattr(rule_set, "compliance_level", "development") or "development"
        device_comp_level = getattr(device, "compliance_level", "personal") or "personal"

        if required_compliance == "strict" and device_comp_level not in ("strict", "managed"):
            return {
                "policy_active": False,
                "session_id": active_session.id,
                "reason": "Session requires institution-managed strict compliance level; personal devices are not authorized for strict enforcement"
            }

        if required_compliance == "managed" and device_comp_level not in ("strict", "managed"):
            return {
                "policy_active": False,
                "session_id": active_session.id,
                "reason": "Session requires institution-managed compliance level"
            }

        device_platform = (device.platform or "windows").lower()
        dev_caps = device.capabilities_json or {}
        if dev_caps.get("unsupported_capability") is True or dev_caps.get("platform_supported") is False:
            return {
                "policy_active": False,
                "session_id": active_session.id,
                "reason": "Device platform does not support required enforcement capabilities"
            }

        # Extract rules
        w_rules = db.query(WebsiteRule).filter(WebsiteRule.rule_set_id == rule_set.id, WebsiteRule.is_enabled == True).all()
        d_rules = db.query(DomainRule).filter(DomainRule.rule_set_id == rule_set.id, DomainRule.is_enabled == True).all()
        a_rules = db.query(ApplicationRule).filter(ApplicationRule.rule_set_id == rule_set.id, ApplicationRule.is_enabled == True).all()

        allowed_websites = []
        blocked_websites = []
        if w_rules:
            for w in w_rules:
                if w.rule_mode == "allowed":
                    allowed_websites.append(w.domain_pattern)
                else:
                    blocked_websites.append(w.domain_pattern)
        elif d_rules:
            for d in d_rules:
                if d.action in ("allow", "log"):
                    allowed_websites.append(d.domain_pattern)
                else:
                    blocked_websites.append(d.domain_pattern)

        allowed_apps = []
        blocked_apps = []
        formatted_app_rules = []
        for a in a_rules:
            clean_name = (a.executable_name or "").strip().lower()
            is_allowed = getattr(a, "rule_mode", "blocked") == "allowed" or (a.action or "").lower() in ("allow", "allowed")
            if not is_allowed and (a.action or "").lower() == "close" and (clean_name in PROTECTED_ALLOWLIST or clean_name in SYSTEM_PROTECTED_PROCESSES):
                continue
            if is_allowed:
                allowed_apps.append(a.executable_name)
                act = "allow"
            else:
                blocked_apps.append(a.executable_name)
                act = a.action or "close"
            formatted_app_rules.append({
                "rule_id": a.id,
                "id": a.id,
                "rule_set_id": a.rule_set_id,
                "executable_name": a.executable_name,
                "application": a.executable_name,
                "action": act,
                "rule_mode": "allowed" if is_allowed else "blocked",
                "priority": a.priority,
                "is_enabled": a.is_enabled,
                "reason": a.reason,
                "cooldown_seconds": a.cooldown_seconds
            })

        formatted_domain_rules = []
        for d in (d_rules if d_rules else w_rules):
            pattern = getattr(d, "domain_pattern", "")
            action = getattr(d, "action", "block" if getattr(d, "rule_mode", "blocked") == "blocked" else "allow")
            formatted_domain_rules.append({
                "id": d.id,
                "rule_id": d.id,
                "rule_set_id": d.rule_set_id,
                "domain_pattern": pattern,
                "domain": pattern,
                "rule_type": getattr(d, "rule_type", "exact"),
                "action": action,
                "priority": d.priority,
                "is_enabled": d.is_enabled,
                "reason": d.reason
            })

        device_reqs_dict = {
            "require_agent_enrolled": dev_req.require_agent_enrolled if dev_req else True,
            "require_dns_or_content_filter": dev_req.require_dns_or_content_filter if dev_req else True,
            "require_application_control": dev_req.require_application_control if dev_req else True,
            "require_managed_browser_policy": dev_req.require_managed_browser_policy if dev_req else False,
            "require_usb_storage_restriction": dev_req.require_usb_storage_restriction if dev_req else False,
            "required_enforcement_level": required_compliance
        }

        policy_id = f"pol_{active_session.id}_v{rule_set.version}"

        # 6. Canonical payload and signature
        canonical_for_signing = {
            "policy_id": policy_id,
            "policy_version": rule_set.version,
            "student_id": device.user_id,
            "device_id": device.id,
            "batch_id": active_session.batch_id or "",
            "session_id": active_session.id,
            "target_platform": device_platform,
            "issued_at": rule_set.issued_at.isoformat() if rule_set.issued_at else now.isoformat(),
            "expires_at": rule_set.expires_at.isoformat() if rule_set.expires_at else None,
            "allowed_websites": allowed_websites,
            "blocked_websites": blocked_websites,
            "allowed_applications": allowed_apps,
            "blocked_applications": blocked_apps,
            "idle_threshold_seconds": getattr(active_session, "idle_threshold_seconds", 60) or 60,
            "device_requirements": device_reqs_dict
        }

        canonical_json_str = json.dumps(canonical_for_signing, sort_keys=True)
        integrity_hash, server_signature = sign_policy_payload(canonical_for_signing)

        device.policy_delivery_state = "delivered"
        device.last_policy_id = policy_id

        agent_policy = db.query(AgentPolicy).filter(AgentPolicy.id == policy_id).first()
        if not agent_policy:
            agent_policy = AgentPolicy(
                id=policy_id,
                policy_version=rule_set.version,
                batch_id=active_session.batch_id,
                session_id=active_session.id,
                target_platform=device_platform,
                enforcement_level=required_compliance,
                issued_at=rule_set.issued_at or now,
                expires_at=rule_set.expires_at,
                integrity_hash=integrity_hash,
                signature=server_signature,
                payload_json=canonical_for_signing
            )
            db.add(agent_policy)

        db.commit()

        curr_occ, _ = ScheduleEvaluator.calculate_occurrences(
            start_at_utc=active_session.start_at_utc,
            end_at_utc=active_session.end_at_utc,
            tz_name=active_session.timezone or "UTC",
            recurrence_type=active_session.recurrence_type or "none",
            recurrence_interval=active_session.recurrence_interval or 1,
            recurrence_days_of_week=active_session.recurrence_days_of_week,
            recurrence_until_utc=active_session.recurrence_until_utc,
            now_utc=now
        )
        current_occ_start = curr_occ.start_utc if curr_occ else active_session.start_at_utc
        current_occ_end = curr_occ.end_utc if curr_occ else active_session.end_at_utc

        protected_procs = db.query(ProtectedProcess).filter(ProtectedProcess.is_enabled == True).all()
        formatted_protected = [
            {"executable_name": p.executable_name, "description": p.description or "System core protected process"}
            for p in protected_procs
        ] if protected_procs else [
            {"executable_name": name, "description": "System core protected process"}
            for name in sorted(list(PROTECTED_ALLOWLIST))
        ]

        return {
            "policy_active": True,
            "policy_id": policy_id,
            "policy_version": rule_set.version,
            "student_id": device.user_id,
            "device_id": device.id,
            "batch_id": active_session.batch_id,
            "session_id": active_session.id,
            "target_platform": device_platform,
            "enforcement_mode": "development",
            "required_capabilities": ["dns_enforcement", "application_control"],
            "session_status": active_session.status,
            "timezone": active_session.timezone or "UTC",
            "start_at_utc": active_session.start_at_utc,
            "end_at_utc": active_session.end_at_utc,
            "current_occurrence_start_utc": current_occ_start,
            "current_occurrence_end_utc": current_occ_end,
            "issued_at": rule_set.issued_at if rule_set.issued_at else now,
            "expires_at": rule_set.expires_at if rule_set.expires_at else None,
            "integrity_hash": integrity_hash,
            "signature": server_signature,
            "canonical_payload": canonical_json_str,
            "server_time_utc": now.isoformat(),
            "allowed_websites": allowed_websites,
            "blocked_websites": blocked_websites,
            "allowed_applications": allowed_apps,
            "blocked_applications": blocked_apps,
            "idle_threshold_seconds": getattr(active_session, "idle_threshold_seconds", 60) or 60,
            "device_requirements": device_reqs_dict,
            # Legacy compatibility fields
            "domains": [d["domain_pattern"] if isinstance(d, dict) else d for d in blocked_websites],
            "apps": [{"executable_name": a, "action": "close"} if isinstance(a, str) else {"executable_name": a["executable_name"], "action": a.get("action", "close")} for a in blocked_apps],
            "domain_rules": formatted_domain_rules,
            "application_rules": formatted_app_rules,
            "protected_processes": formatted_protected,
            "upstream_dns": ["8.8.8.8", "1.1.1.1"]
        }
