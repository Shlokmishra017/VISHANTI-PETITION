import os
import secrets
import base64
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import select, func, or_
from app.config import settings
from app.db import get_db
from app.models import Case, CaseEvent, Attachment, Category, SLAPolicy, User, Notification
from app.schemas import (
    CaseResponse, CaseDetailResponse, CaseCreateResponse, CaseEventResponse,
    TransitionRequest, AssignRequest, CommentRequest, VerificationResult
)
from app.auth import get_current_user, require_roles
from app.scope import can_access_case, scope_case_query
from app.state_machine import transition_case, InvalidTransitionError, PermissionDeniedError
from app.ledger import append_event, verify_chain, get_actor_ref, compute_content_hash
from app.sse import broadcast_event

router = APIRouter(prefix="/cases", tags=["cases"])

# allowed attachment mime types and max 5mb size
ALLOWED_MIME_TYPES = {"application/pdf", "image/png", "image/jpeg"}
MAX_FILE_SIZE = 5 * 1024 * 1024

# optional auth dependency allowing both authenticated and guest submissions
def get_optional_user(db: Session = Depends(get_db), response: Response = None) -> Optional[User]:
    # helper to get user if present without throwing 401
    from fastapi import Request
    # handled inside endpoint with request inspection
    return None

# compute remaining sla seconds
def get_remaining_sla_seconds(sla_due_at: Optional[datetime]) -> Optional[int]:
    if not sla_due_at:
        return None
    now = datetime.now(timezone.utc)
    if sla_due_at.tzinfo is None:
        sla_due_at = sla_due_at.replace(tzinfo=timezone.utc)
    remaining = int((sla_due_at - now).total_seconds())
    return max(0, remaining)

# derive allowed actions based on current user role and case state
def calculate_allowed_actions(user: User, case: Case) -> List[str]:
    actions = []
    role = user.role

    if case.state == "Filed" and role in ("official", "admin"):
        actions.append("assign")

    if case.state == "Assigned" and (user.id == case.assignee_id or role == "admin"):
        actions.append("start_review")

    if case.state in ("Assigned", "In Review") and role in ("authority", "admin"):
        actions.append("escalate")

    if case.state == "In Review" and (user.id == case.assignee_id or role == "admin"):
        actions.append("resolve")

    if case.state == "Escalated" and role in ("authority", "admin"):
        actions.append("claim")

    if can_access_case(user, case):
        actions.append("add_comment")

    return actions

# create a new case (authenticated student or anonymous)
@router.post("", response_model=CaseCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_case(
    title: str = Form(...),
    description: str = Form(...),
    category_id: str = Form(...),
    priority: str = Form("medium"),
    is_anonymous: bool = Form(False),
    files: List[UploadFile] = File([]),
    db: Session = Depends(get_db)
):
    # check category existence
    cat = db.execute(select(Category).where(Category.id == category_id)).scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=400, detail="Invalid category_id")

    # generate 128-bit random base32 claim code for anonymous submissions
    claim_code = None
    claim_code_hash = None
    if is_anonymous:
        raw_token = secrets.token_bytes(16)
        claim_code = base64.b32encode(raw_token).decode("utf-8").rstrip("=")
        claim_code_hash = hashlib.sha256(claim_code.encode("utf-8")).hexdigest()

    # calculate sla due timestamp from policy or fallback
    now = datetime.now(timezone.utc)
    policy = db.execute(
        select(SLAPolicy).where(SLAPolicy.category_id == category_id, SLAPolicy.priority == priority)
    ).scalar_one_or_none()
    duration = policy.duration_seconds if policy else settings.DEMO_SLA_SECONDS
    sla_due_at = now + timedelta(seconds=duration)

    # generate sequential case reference
    total_cases = db.execute(select(func.count(Case.id))).scalar() or 0
    ref_id = f"VP-2026-{(total_cases + 1):04d}"

    case = Case(
        ref_id=ref_id,
        title=title,
        description=description,
        category_id=category_id,
        priority=priority,
        state="Filed",
        petitioner_id=None, # anonymous or unauthenticated default
        is_anonymous=is_anonymous,
        claim_code_hash=claim_code_hash,
        sla_due_at=sla_due_at,
        created_at=now,
        updated_at=now
    )
    db.add(case)
    db.flush()

    # process and validate file attachments
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    for upload in files:
        if not upload.filename:
            continue
        if upload.content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(status_code=400, detail=f"File type '{upload.content_type}' not allowed")
        
        content = await upload.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"File '{upload.filename}' exceeds 5MB size limit")

        sha256_hash = hashlib.sha256(content).hexdigest()
        save_path = os.path.join(settings.UPLOAD_DIR, f"{case.id}_{upload.filename}")
        with open(save_path, "wb") as f:
            f.write(content)

        attachment = Attachment(
            case_id=case.id,
            filename=upload.filename,
            mime=upload.content_type,
            size=len(content),
            sha256=sha256_hash,
            storage_path=save_path
        )
        db.add(attachment)

    # append genesis event to immutable ledger
    actor_ref = get_actor_ref(None, case.id)
    append_event(
        db=db,
        case_id=case.id,
        event_type="CASE_FILED",
        actor_ref=actor_ref,
        payload={
            "ref_id": case.ref_id,
            "title": case.title,
            "category_id": case.category_id,
            "priority": case.priority,
            "is_anonymous": case.is_anonymous
        },
        content_text=description
    )

    db.commit()
    return CaseCreateResponse(case_id=case.id, ref_id=case.ref_id, claim_code=claim_code)

# list scoped cases with query filters
@router.get("", response_model=List[CaseResponse])
def list_cases(
    state: Optional[str] = None,
    mine: Optional[bool] = None,
    needs_action: Optional[bool] = None,
    overdue: Optional[bool] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = select(Case)
    # apply department and role visibility scope
    query = scope_case_query(query, current_user)

    if state:
        query = query.filter(Case.state == state)

    if mine:
        if current_user.role == "student":
            query = query.filter(Case.petitioner_id == current_user.id)
        else:
            query = query.filter(Case.assignee_id == current_user.id)

    if needs_action:
        if current_user.role == "official":
            query = query.filter(
                or_(
                    (Case.state == "Filed"),
                    (Case.state == "In Review") & (Case.assignee_id == current_user.id)
                )
            )
        elif current_user.role == "authority":
            query = query.filter(Case.state == "Escalated")

    if overdue:
        now = datetime.now(timezone.utc)
        query = query.filter(Case.sla_due_at < now, Case.state.notin_(["Resolved"]))

    cases = db.execute(query.order_by(Case.created_at.desc())).scalars().all()
    return cases

# get case details with allowed actions and timeline
@router.get("/{id}", response_model=CaseDetailResponse)
def get_case(
    id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    case = db.execute(select(Case).where(Case.id == id)).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if not can_access_case(current_user, case):
        raise HTTPException(status_code=403, detail="Access denied for this case")

    allowed_actions = calculate_allowed_actions(current_user, case)
    remaining_sla = get_remaining_sla_seconds(case.sla_due_at)

    return CaseDetailResponse(
        id=case.id,
        ref_id=case.ref_id,
        title=case.title,
        description=case.description,
        category_id=case.category_id,
        priority=case.priority,
        state=case.state,
        petitioner_id=case.petitioner_id,
        is_anonymous=case.is_anonymous,
        assignee_id=case.assignee_id,
        escalation_level=case.escalation_level,
        sla_due_at=case.sla_due_at,
        version=case.version,
        created_at=case.created_at,
        updated_at=case.updated_at,
        allowed_actions=allowed_actions,
        events=case.events,
        attachments=case.attachments,
        sla_seconds_remaining=remaining_sla
    )

# get timeline events for a case
@router.get("/{id}/events", response_model=List[CaseEventResponse])
def get_case_events(
    id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    case = db.execute(select(Case).where(Case.id == id)).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if not can_access_case(current_user, case):
        raise HTTPException(status_code=403, detail="Access denied for this case")

    events = db.execute(
        select(CaseEvent).where(CaseEvent.case_id == id).order_by(CaseEvent.seq.asc())
    ).scalars().all()
    return events

# assign case to an official
@router.post("/{id}/assign")
def assign_case(
    id: str,
    body: AssignRequest,
    current_user: User = Depends(require_roles("official", "admin")),
    db: Session = Depends(get_db)
):
    # verify assignee user exists
    assignee = db.execute(select(User).where(User.id == body.assignee_id)).scalar_one_or_none()
    if not assignee:
        raise HTTPException(status_code=400, detail="Assignee user not found")

    # execute state transition to assigned
    case = transition_case(
        db=db,
        case_id=id,
        target_state="Assigned",
        user=current_user,
        assignee_id=body.assignee_id
    )
    db.commit()

    # push realtime notification after successful commit
    broadcast_event(event_id=case.id, case_id=case.id, kind="CASE_ASSIGNED")
    return {"status": "ok", "state": case.state, "assignee_id": case.assignee_id}

# transition case state
@router.post("/{id}/transition")
def execute_transition(
    id: str,
    body: TransitionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    case = transition_case(
        db=db,
        case_id=id,
        target_state=body.to_state,
        user=current_user,
        note=body.note,
        reason=body.reason
    )
    db.commit()

    # push realtime update
    broadcast_event(event_id=case.id, case_id=case.id, kind=f"STATE_{case.state.upper()}")
    return {"status": "ok", "state": case.state, "version": case.version}

# post comment on a case
@router.post("/{id}/comments")
def add_comment(
    id: str,
    body: CommentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    case = db.execute(select(Case).where(Case.id == id)).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if not can_access_case(current_user, case):
        raise HTTPException(status_code=403, detail="Access denied for this case")

    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Comment cannot be empty")

    actor_ref = get_actor_ref(current_user.id, case.id)
    content_hash = compute_content_hash(body.text)

    # append comment event to ledger without plaintext in chain digest
    event = append_event(
        db=db,
        case_id=case.id,
        event_type="COMMENT_ADDED",
        actor_ref=actor_ref,
        payload={"author_name": current_user.name, "role": current_user.role, "content_hash": content_hash},
        content_text=body.text
    )

    # queue notification for relevant party
    recipient_id = case.assignee_id if current_user.id == case.petitioner_id else case.petitioner_id
    if recipient_id:
        notif = Notification(
            user_id=recipient_id,
            case_id=case.id,
            kind="COMMENT_ADDED",
            body=f"New comment on case {case.ref_id} by {current_user.name}"
        )
        db.add(notif)

    db.commit()
    broadcast_event(event_id=event.id, case_id=case.id, kind="COMMENT_ADDED")
    return {"status": "ok", "event_id": event.id, "seq": event.seq}

# verify cryptographic hash chain for a case
@router.get("/{id}/verify", response_model=VerificationResult)
def verify_case_integrity(
    id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    case = db.execute(select(Case).where(Case.id == id)).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if not can_access_case(current_user, case):
        raise HTTPException(status_code=403, detail="Access denied for this case")

    # execute chain verification
    result = verify_chain(db, case.id)
    return result

# authorized download of attachment
@router.get("/{id}/attachments/{aid}")
def download_attachment(
    id: str,
    aid: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    case = db.execute(select(Case).where(Case.id == id)).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if not can_access_case(current_user, case):
        raise HTTPException(status_code=403, detail="Access denied for this case")

    attachment = db.execute(
        select(Attachment).where(Attachment.id == aid, Attachment.case_id == id)
    ).scalar_one_or_none()
    if not attachment or not os.path.exists(attachment.storage_path):
        raise HTTPException(status_code=404, detail="Attachment not found")

    return FileResponse(
        path=attachment.storage_path,
        media_type=attachment.mime,
        filename=attachment.filename
    )

