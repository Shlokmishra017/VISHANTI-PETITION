from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, EmailStr, ConfigDict

# auth schemas
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    department_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

# state machine transition schema
class TransitionRequest(BaseModel):
    to_state: str
    note: Optional[str] = None
    reason: Optional[str] = None

# case assignment schema
class AssignRequest(BaseModel):
    assignee_id: str

# comments schema
class CommentRequest(BaseModel):
    text: str

# anonymous tracking schemas
class TrackRequest(BaseModel):
    claim_code: str

class TrackCommentRequest(BaseModel):
    claim_code: str
    text: str

# ledger event schema
class CaseEventResponse(BaseModel):
    id: str
    case_id: str
    seq: int
    type: str
    actor_ref: str
    payload_json: str
    content_hash: str
    prev_hash: str
    hash: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# attachment metadata response
class AttachmentResponse(BaseModel):
    id: str
    case_id: str
    filename: str
    mime: str
    size: int
    sha256: str

    model_config = ConfigDict(from_attributes=True)

# case summary response
class CaseResponse(BaseModel):
    id: str
    ref_id: str
    title: str
    description: str
    category_id: str
    priority: str
    state: str
    petitioner_id: Optional[str] = None
    is_anonymous: bool
    assignee_id: Optional[str] = None
    escalation_level: int
    sla_due_at: Optional[datetime] = None
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

# detailed case view with allowed actions and timeline
class CaseDetailResponse(CaseResponse):
    allowed_actions: List[str] = []
    events: List[CaseEventResponse] = []
    attachments: List[AttachmentResponse] = []
    sla_seconds_remaining: Optional[int] = None

# case creation response
class CaseCreateResponse(BaseModel):
    case_id: str
    ref_id: str
    claim_code: Optional[str] = None

# verification response
class VerificationResult(BaseModel):
    valid: bool
    checked: int
    first_broken_seq: Optional[int] = None
    expected: Optional[str] = None
    found: Optional[str] = None

# category response
class CategoryResponse(BaseModel):
    id: str
    name: str
    department_id: str

    model_config = ConfigDict(from_attributes=True)

# notification response
class NotificationResponse(BaseModel):
    id: str
    case_id: str
    kind: str
    body: str
    seen: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# dev tamper request
class DevTamperRequest(BaseModel):
    case_ref_or_id: str
    target_seq: int
    modified_text: Optional[str] = "TAMPERED: Grade approved without review"
