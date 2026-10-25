import json
import hashlib
import hmac
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple, List
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from app.config import settings
from app.models import CaseEvent, Case

GENESIS_PREV_HASH = "0" * 64

# format timestamp consistently to prevent microsecond drift
def format_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

# canonical json string with sorted keys and tight separators
def to_canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

# compute sha256 hash of arbitrary content string
def compute_content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

# generate pseudonymous actor ref for anonymous cases
def get_actor_ref(user_id: Optional[str], case_id: str) -> str:
    if user_id:
        return user_id
    digest = hmac.new(settings.SECRET_KEY.encode(), case_id.encode(), hashlib.sha256).hexdigest()
    return f"anon_{digest[:16]}"

# compute event hash across canonicalized tuple
def calculate_event_hash(
    case_id: str,
    seq: int,
    event_type: str,
    actor_ref: str,
    payload: Dict[str, Any],
    created_at_iso: str,
    prev_hash: str
) -> str:
    # pack structure for deterministic canonical representation
    raw_dict = {
        "actor_ref": actor_ref,
        "case_id": case_id,
        "created_at_iso": created_at_iso,
        "payload": payload,
        "prev_hash": prev_hash,
        "seq": seq,
        "type": event_type
    }
    canonical_repr = to_canonical_json(raw_dict)
    return hashlib.sha256(canonical_repr.encode("utf-8")).hexdigest()

# append event under active transaction with locked case row
def append_event(
    db: Session,
    case_id: str,
    event_type: str,
    actor_ref: str,
    payload: Dict[str, Any],
    content_text: str = ""
) -> CaseEvent:
    # lookup previous event to get last sequence and hash
    last_event = db.execute(
        select(CaseEvent)
        .where(CaseEvent.case_id == case_id)
        .order_by(CaseEvent.seq.desc())
        .limit(1)
    ).scalar_one_or_none()

    seq = 1 if last_event is None else last_event.seq + 1
    prev_hash = GENESIS_PREV_HASH if last_event is None else last_event.hash

    now = datetime.now(timezone.utc)
    created_at_iso = format_iso(now)
    content_hash = compute_content_hash(content_text if content_text else to_canonical_json(payload))

    event_hash = calculate_event_hash(
        case_id=case_id,
        seq=seq,
        event_type=event_type,
        actor_ref=actor_ref,
        payload=payload,
        created_at_iso=created_at_iso,
        prev_hash=prev_hash
    )

    event = CaseEvent(
        case_id=case_id,
        seq=seq,
        type=event_type,
        actor_ref=actor_ref,
        payload_json=to_canonical_json(payload),
        content_hash=content_hash,
        prev_hash=prev_hash,
        hash=event_hash,
        created_at=now
    )
    db.add(event)
    db.flush()
    return event

# verify full sequence and hash integrity for a case
def verify_chain(db: Session, case_id: str) -> Dict[str, Any]:
    events = db.execute(
        select(CaseEvent)
        .where(CaseEvent.case_id == case_id)
        .order_by(CaseEvent.seq.asc())
    ).scalars().all()

    if not events:
        return {
            "valid": True,
            "checked": 0,
            "first_broken_seq": None,
            "expected": None,
            "found": None
        }

    expected_prev = GENESIS_PREV_HASH
    for idx, ev in enumerate(events, start=1):
        # verify sequence continuity
        if ev.seq != idx:
            return {
                "valid": False,
                "checked": idx - 1,
                "first_broken_seq": ev.seq,
                "expected": f"seq={idx}",
                "found": f"seq={ev.seq}"
            }

        # check link to previous hash
        if ev.prev_hash != expected_prev:
            return {
                "valid": False,
                "checked": idx - 1,
                "first_broken_seq": ev.seq,
                "expected": expected_prev,
                "found": ev.prev_hash
            }

        # recalculate hash from record contents
        try:
            payload = json.loads(ev.payload_json)
        except Exception:
            return {
                "valid": False,
                "checked": idx - 1,
                "first_broken_seq": ev.seq,
                "expected": "valid json",
                "found": "corrupt json"
            }

        expected_hash = calculate_event_hash(
            case_id=ev.case_id,
            seq=ev.seq,
            event_type=ev.type,
            actor_ref=ev.actor_ref,
            payload=payload,
            created_at_iso=format_iso(ev.created_at),
            prev_hash=ev.prev_hash
        )

        if ev.hash != expected_hash:
            return {
                "valid": False,
                "checked": idx - 1,
                "first_broken_seq": ev.seq,
                "expected": expected_hash,
                "found": ev.hash
            }

        expected_prev = ev.hash

    return {
        "valid": True,
        "checked": len(events),
        "first_broken_seq": None,
        "expected": None,
        "found": None
    }

