from typing import Optional, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models import Case, User, Category, Notification
from app.ledger import append_event, get_actor_ref

class InvalidTransitionError(Exception):
    def __init__(self, message: str, code: str = "INVALID_TRANSITION"):
        self.message = message
        self.code = code
        super().__init__(message)

class PermissionDeniedError(Exception):
    def __init__(self, message: str, code: str = "FORBIDDEN"):
        self.message = message
        self.code = code
        super().__init__(message)

# check if transition from current to target state is allowed by role
def validate_transition(
    case: Case,
    user: Optional[User],
    target_state: str,
    note: Optional[str] = None,
    reason: Optional[str] = None,
    assignee_id: Optional[str] = None
) -> None:
    current = case.state
    role = user.role if user else "anonymous"

    # allow filing new cases
    if current == "Filed" and target_state == "Filed":
        return

    # filed -> assigned: officials in department or admin
    if current == "Filed" and target_state == "Assigned":
        if role not in ("official", "admin"):
            raise PermissionDeniedError("Only officials or admins can assign cases")
        if not assignee_id and not case.assignee_id:
            raise InvalidTransitionError("Assignee is required to transition to Assigned")
        return

    # assigned -> in review: assigned official or admin
    if current == "Assigned" and target_state == "In Review":
        if role == "admin":
            return
        if role == "official" and user and user.id == case.assignee_id:
            return
        raise PermissionDeniedError("Only the assigned official or an admin can start review")

    # in review -> resolved: assigned official or admin with resolution note
    if current == "In Review" and target_state == "Resolved":
        if role not in ("official", "admin"):
            raise PermissionDeniedError("Only assigned officials or admins can resolve cases")
        if role == "official" and user and user.id != case.assignee_id:
            raise PermissionDeniedError("Only the assigned official can resolve this case")
        if not note or not note.strip():
            raise InvalidTransitionError("A resolution note is required to mark resolved")
        return

    # assigned/in review -> escalated: authority, system, or admin with reason
    if current in ("Assigned", "In Review") and target_state == "Escalated":
        if role not in ("authority", "admin", "system"):
            raise PermissionDeniedError("Only authorities, admins, or system can escalate cases")
        if not reason or not reason.strip():
            raise InvalidTransitionError("An escalation reason is required")
        return

    # escalated -> in review: authority taking over
    if current == "Escalated" and target_state == "In Review":
        if role not in ("authority", "admin"):
            raise PermissionDeniedError("Only authorities or admins can claim escalated cases")
        return

    raise InvalidTransitionError(f"Illegal state transition from {current} to {target_state}")

# execute state transition under row lock within single transaction
def transition_case(
    db: Session,
    case_id: str,
    target_state: str,
    user: Optional[User] = None,
    note: Optional[str] = None,
    reason: Optional[str] = None,
    assignee_id: Optional[str] = None
) -> Case:
    # acquire row lock on case record to prevent race conditions
    query = select(Case).where(Case.id == case_id)
    if db.bind and db.bind.dialect.name != "sqlite":
        query = query.with_for_update()
    
    case = db.execute(query).scalar_one_or_none()
    if not case:
        raise InvalidTransitionError("Case not found", code="NOT_FOUND")

    # validate transition rules and permissions
    validate_transition(
        case=case,
        user=user,
        target_state=target_state,
        note=note,
        reason=reason,
        assignee_id=assignee_id
    )

    old_state = case.state
    case.state = target_state
    case.version += 1
    case.updated_at = datetime.now(timezone.utc)

    # update assignee if provided
    if assignee_id:
        case.assignee_id = assignee_id

    # increment escalation level if escalated
    if target_state == "Escalated":
        case.escalation_level += 1

    # record payload metadata for the immutable ledger
    actor_ref = get_actor_ref(user.id if user else None, case.id)
    payload = {
        "from_state": old_state,
        "to_state": target_state,
        "version": case.version,
    }
    if note:
        payload["note"] = note
    if reason:
        payload["reason"] = reason
    if assignee_id:
        payload["assignee_id"] = assignee_id

    # append event to hash chain
    append_event(
        db=db,
        case_id=case.id,
        event_type=f"STATE_TRANSITION_{target_state.upper().replace(' ', '_')}",
        actor_ref=actor_ref,
        payload=payload,
        content_text=note or reason or ""
    )

    # queue notification for petitioner
    if case.petitioner_id:
        notif = Notification(
            user_id=case.petitioner_id,
            case_id=case.id,
            kind="STATE_CHANGED",
            body=f"Case {case.ref_id} transitioned from {old_state} to {target_state}"
        )
        db.add(notif)

    db.flush()
    return case

