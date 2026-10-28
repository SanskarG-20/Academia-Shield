import re
from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

SAFE_EXECUTABLE_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.]{1,100}$")
FORBIDDEN_COMMANDS = {"rm", "del", "powershell", "cmd", "sh", "bash", "network_restrict", "sudo", "exec", "eval"}
SHELL_METACHARS = set(";&|><$`\n\r")
ALLOWED_ACTIONS = {"log", "warn", "close"}
ALLOWED_RULE_MODES = {"allowed", "blocked"}
ALLOWED_CATEGORIES = {
    "academic", "general", "documentation", "research", "learning_platform",
    "academic_portal", "social_media", "entertainment", "gaming", "ai_cheating",
    "communication", "ide_editor", "compiler_runtime", "academic_tool", "calculator", "streaming", "docs"
}
ALLOWED_DEVICE_LEVELS = {"audit", "development", "managed", "strict"}
HEX_64_REGEX = re.compile(r"^[a-fA-F0-9]{64}$")
DOMAIN_REGEX = re.compile(r"^(\*\.)?([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$")

PROTECTED_ALLOWLIST = {
    "explorer.exe", "svchost.exe", "csrss.exe", "smss.exe", "services.exe",
    "lsass.exe", "winlogon.exe", "systemd", "python.exe", "python", "python3", "pytest",
    "agent.exe", "acad_agent.exe", "academiashield.exe", "academia_shield_agent.exe", "academiashieldagent.exe",
    "cmd.exe", "powershell.exe", "taskmgr.exe", "msmpeng.exe", "securityhealthservice.exe",
    "narrator.exe", "osk.exe", "magnify.exe"
}

class DomainRuleCreate(BaseModel):
    domain_pattern: str = Field(..., min_length=1, max_length=253)
    rule_type: str = Field(default="exact")  # exact, wildcard
    action: str = Field(default="block")  # block, allow, log
    priority: int = Field(default=10)
    reason: Optional[str] = None

class DomainRuleResponse(BaseModel):
    id: str
    rule_set_id: str
    domain_pattern: str
    rule_type: str = "exact"
    action: str = "block"
    priority: int = 10
    is_enabled: bool = True
    reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class WebsiteRuleCreate(BaseModel):
    domain_pattern: str = Field(..., min_length=1, max_length=253)
    rule_mode: str = Field(default="blocked")  # allowed, blocked
    category: str = Field(default="general")  # academic, general
    priority: int = Field(default=10, ge=0, le=1000)
    is_enabled: bool = True
    reason: Optional[str] = None

    @field_validator("domain_pattern")
    @classmethod
    def validate_domain_pattern(cls, v: str) -> str:
        clean = v.strip().lower()
        if not clean:
            raise ValueError("domain_pattern cannot be empty")
        if any(c in SHELL_METACHARS or c in (" ", "\t", "\\") for c in clean):
            raise ValueError("domain_pattern contains illegal characters or shell metacharacters")
        # Strip scheme or path if accidentally provided
        if "://" in clean:
            from urllib.parse import urlparse
            clean = urlparse(clean).netloc or clean
        clean = clean.split("/")[0].split("?")[0].split("#")[0].split(":")[0]
        if not DOMAIN_REGEX.match(clean) and "." not in clean:
            raise ValueError(f"'{clean}' is not a valid domain pattern (e.g. docs.python.org or *.google.com)")
        return clean

    @field_validator("rule_mode")
    @classmethod
    def validate_rule_mode(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in ALLOWED_RULE_MODES:
            raise ValueError(f"rule_mode must be one of: {ALLOWED_RULE_MODES}")
        return clean

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in ALLOWED_CATEGORIES:
            raise ValueError(f"category must be one of: {ALLOWED_CATEGORIES}")
        return clean

class WebsiteRuleUpdate(BaseModel):
    domain_pattern: Optional[str] = None
    rule_mode: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[int] = Field(None, ge=0, le=1000)
    is_enabled: Optional[bool] = None
    reason: Optional[str] = None

    @field_validator("domain_pattern")
    @classmethod
    def validate_domain_pattern(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip().lower()
            if any(c in SHELL_METACHARS or c in (" ", "\t", "\\") for c in clean):
                raise ValueError("domain_pattern contains illegal characters or shell metacharacters")
            if "://" in clean:
                from urllib.parse import urlparse
                clean = urlparse(clean).netloc or clean
            clean = clean.split("/")[0].split("?")[0].split("#")[0].split(":")[0]
            if not DOMAIN_REGEX.match(clean) and "." not in clean:
                raise ValueError(f"'{clean}' is not a valid domain pattern")
            return clean
        return v

    @field_validator("rule_mode")
    @classmethod
    def validate_rule_mode(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip().lower()
            if clean not in ALLOWED_RULE_MODES:
                raise ValueError(f"rule_mode must be one of: {ALLOWED_RULE_MODES}")
            return clean
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip().lower()
            if clean not in ALLOWED_CATEGORIES:
                raise ValueError(f"category must be one of: {ALLOWED_CATEGORIES}")
            return clean
        return v

class WebsiteRuleResponse(BaseModel):
    id: str
    rule_id: Optional[str] = None
    rule_set_id: str
    domain_pattern: str
    rule_mode: str = "blocked"
    category: str = "general"
    priority: int = 10
    is_enabled: bool = True
    reason: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class ApplicationRuleCreate(BaseModel):
    application_name: Optional[str] = None
    executable_name: Optional[str] = None
    executable_path_pattern: Optional[str] = None
    trusted_hash: Optional[str] = None
    rule_mode: str = Field(default="blocked")  # allowed, blocked
    category: str = Field(default="general")
    action: str = Field(default="close")  # log, warn, close
    priority: int = Field(default=0, ge=0, le=1000)
    reason: Optional[str] = None
    cooldown_seconds: int = Field(default=0, ge=0, le=86400)

    @model_validator(mode="before")
    @classmethod
    def populate_names(cls, data: Any) -> Any:
        if isinstance(data, dict):
            name = data.get("executable_name") or data.get("application_name")
            if name:
                data.setdefault("executable_name", name)
                data.setdefault("application_name", name)
        return data

    @field_validator("executable_name")
    @classmethod
    def validate_executable_name(cls, v: Optional[str]) -> str:
        if not v:
            raise ValueError("executable_name or application_name is required")
        clean = v.strip().lower()
        if not clean or not SAFE_EXECUTABLE_REGEX.match(clean):
            raise ValueError("executable_name must be a safe filename-style string without path separators or shell characters")
        if clean in FORBIDDEN_COMMANDS:
            raise ValueError(f"'{clean}' is a reserved command and cannot be used as an application rule target")
        return clean

    @field_validator("executable_path_pattern")
    @classmethod
    def validate_path_pattern(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if len(v) > 255:
                raise ValueError("executable_path_pattern exceeds maximum length of 255 characters")
            if any(c in SHELL_METACHARS for c in v):
                raise ValueError("executable_path_pattern contains invalid shell metacharacters")
        return v

    @field_validator("trusted_hash")
    @classmethod
    def validate_trusted_hash(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip()
            if not HEX_64_REGEX.match(clean):
                raise ValueError("trusted_hash must be a valid 64-character SHA-256 hexadecimal string")
            return clean
        return v

    @field_validator("rule_mode")
    @classmethod
    def validate_rule_mode(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in ALLOWED_RULE_MODES:
            raise ValueError(f"rule_mode must be one of: {ALLOWED_RULE_MODES}")
        return clean

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in ALLOWED_CATEGORIES:
            raise ValueError(f"category must be one of: {ALLOWED_CATEGORIES}")
        return clean

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in ALLOWED_ACTIONS:
            raise ValueError("action must be limited to: log, warn, close")
        return clean

class ApplicationRuleUpdate(BaseModel):
    application_name: Optional[str] = None
    executable_name: Optional[str] = None
    executable_path_pattern: Optional[str] = None
    trusted_hash: Optional[str] = None
    rule_mode: Optional[str] = None
    category: Optional[str] = None
    action: Optional[str] = None
    priority: Optional[int] = Field(None, ge=0, le=1000)
    is_enabled: Optional[bool] = None
    reason: Optional[str] = None
    cooldown_seconds: Optional[int] = Field(None, ge=0, le=86400)

    @field_validator("executable_name")
    @classmethod
    def validate_executable_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip().lower()
            if not clean or not SAFE_EXECUTABLE_REGEX.match(clean):
                raise ValueError("executable_name must be a safe filename-style string without path separators or shell characters")
            if clean in FORBIDDEN_COMMANDS:
                raise ValueError(f"'{clean}' is a reserved command and cannot be used as an application rule target")
            return clean
        return v

    @field_validator("rule_mode")
    @classmethod
    def validate_rule_mode(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip().lower()
            if clean not in ALLOWED_RULE_MODES:
                raise ValueError(f"rule_mode must be one of: {ALLOWED_RULE_MODES}")
            return clean
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip().lower()
            if clean not in ALLOWED_CATEGORIES:
                raise ValueError(f"category must be one of: {ALLOWED_CATEGORIES}")
            return clean
        return v

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip().lower()
            if clean not in ALLOWED_ACTIONS:
                raise ValueError("action must be limited to: log, warn, close")
            return clean
        return v

class ApplicationRuleResponse(BaseModel):
    rule_id: Optional[str] = None
    id: Optional[str] = None
    rule_set_id: str
    application_name: Optional[str] = None
    executable_name: str
    executable_path_pattern: Optional[str] = None
    trusted_hash: Optional[str] = None
    rule_mode: str = "blocked"
    category: str = "general"
    action: str = "close"
    priority: int = 0
    is_enabled: bool = True
    reason: Optional[str] = None
    cooldown_seconds: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class DevicePolicyRequirementCreate(BaseModel):
    require_agent_enrolled: bool = True
    require_dns_or_content_filter: bool = True
    require_application_control: bool = True
    require_managed_browser_policy: bool = False
    require_usb_storage_restriction: bool = False
    required_enforcement_level: str = Field(default="development")

    @field_validator("required_enforcement_level")
    @classmethod
    def validate_enforcement_level(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in ALLOWED_DEVICE_LEVELS:
            raise ValueError(f"required_enforcement_level must be one of: {ALLOWED_DEVICE_LEVELS}")
        return clean

class DevicePolicyRequirementUpdate(BaseModel):
    require_agent_enrolled: Optional[bool] = None
    require_dns_or_content_filter: Optional[bool] = None
    require_application_control: Optional[bool] = None
    require_managed_browser_policy: Optional[bool] = None
    require_usb_storage_restriction: Optional[bool] = None
    required_enforcement_level: Optional[str] = None

    @field_validator("required_enforcement_level")
    @classmethod
    def validate_enforcement_level(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip().lower()
            if clean not in ALLOWED_DEVICE_LEVELS:
                raise ValueError(f"required_enforcement_level must be one of: {ALLOWED_DEVICE_LEVELS}")
            return clean
        return v

class DevicePolicyRequirementResponse(BaseModel):
    id: str
    rule_set_id: str
    require_agent_enrolled: bool = True
    require_dns_or_content_filter: bool = True
    require_application_control: bool = True
    require_managed_browser_policy: bool = False
    require_usb_storage_restriction: bool = False
    required_enforcement_level: str = "development"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class ProtectedProcessResponse(BaseModel):
    executable_name: str
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class RuleSetCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    session_id: Optional[str] = None
    expires_at: Optional[datetime] = None

class RuleSetUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    session_id: Optional[str] = None
    expires_at: Optional[datetime] = None
    is_active: Optional[bool] = None

class RuleSetResponse(BaseModel):
    id: str
    batch_id: Optional[str] = None
    session_id: Optional[str] = None
    class_id: Optional[str] = None
    name: str
    version: int
    status: str = "draft"
    is_active: bool = True
    issued_at: datetime
    expires_at: Optional[datetime] = None
    created_by: str
    integrity_hash: str
    policy_hash: Optional[str] = None
    signature: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    website_rules: List[WebsiteRuleResponse] = []
    domain_rules: List[DomainRuleResponse] = []
    application_rules: List[ApplicationRuleResponse] = []
    device_requirements: Optional[DevicePolicyRequirementResponse] = None

    model_config = ConfigDict(from_attributes=True)
