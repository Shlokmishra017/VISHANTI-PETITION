import hashlib
import time
from typing import Dict, List
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db import get_db
from app.models import Case, CaseEvent
from app.schemas import TrackRequest, TrackCommentRequest, CaseDetailResponse
from app.ledger import append_event, get_actor_ref, compute_content_hash, verify_chain
from app.sse import broadcast_event

router = APIRouter(prefix="/track", tags=["track"])

# in-memory ip rate limiter storage: ip -> list of timestamps
_rate_limit_records: Dict[str, List[float]] = defaultdict(list)
RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW = 60.0

# enforce 5 requests per minute per ip address
def check_track_rate_limit(request: Request):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    timestamps = _rate_limit_records[client_ip]

    # evict timestamps older than 60 seconds
    valid_timestamps = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]
    if len(valid_timestamps) >= RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": {"code": "RATE_LIMIT_EXCEEDED", "message": "Too many track requests. Limit is 5 per minute."}}
        )

    valid_timestamps.append(now)
    _rate_limit_records[client_ip] = valid_timestamps

# track case anonymously using claim code in request body
@router.post("")
def track_case(
    body: TrackRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    # apply per-ip rate limit
    check_track_rate_limit(request)

    # hash submitted claim code to lookup case
    code_hash = hashlib.sha256(body.claim_code.strip().encode("utf-8")).hexdigest()
    case = db.execute(select(Case).where(Case.claim_code_hash == code_hash)).scalar_one_or_none()

    # return generic 404 on miss to prevent discovery
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    events = db.execute(
        select(CaseEvent).where(CaseEvent.case_id == case.id).order_by(CaseEvent.seq.asc())
    ).scalars().all()

    verification = verify_chain(db, case.id)

    return {
        "case": {
            "id": case.id,
            "ref_id": case.ref_id,
            "title": case.title,
            "description": case.description,
            "category_id": case.category_id,
            "priority": case.priority,
            "state": case.state,
            "is_anonymous": True,
            "escalation_level": case.escalation_level,
            "sla_due_at": case.sla_due_at,
            "created_at": case.created_at,
            "updated_at": case.updated_at
        },
        "events": events,
        "verification": verification
    }

# post anonymous comment via claim code
@router.post("/comments")
def post_track_comment(
    body: TrackCommentRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    check_track_rate_limit(request)

    code_hash = hashlib.sha256(body.claim_code.strip().encode("utf-8")).hexdigest()
    case = db.execute(select(Case).where(Case.claim_code_hash == code_hash)).scalar_one_or_none()

    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Comment text cannot be empty")

    # compute pseudonymous actor reference ensuring privacy
    actor_ref = get_actor_ref(None, case.id)
    content_hash = compute_content_hash(body.text)

    # append comment to ledger
    event = append_event(
        db=db,
        case_id=case.id,
        event_type="ANONYMOUS_COMMENT_ADDED",
        actor_ref=actor_ref,
        payload={"author": "Petitioner (Anonymous)", "content_hash": content_hash},
        content_text=body.text
    )

    db.commit()
    broadcast_event(event_id=event.id, case_id=case.id, kind="ANONYMOUS_COMMENT_ADDED")
    return {"status": "ok", "event_id": event.id, "seq": event.seq}

