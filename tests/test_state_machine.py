import pytest
from app.state_machine import transition_case, InvalidTransitionError, PermissionDeniedError

def test_full_successful_transition_lifecycle(db_session, fixtures):
    case = fixtures["case"]
    official = fixtures["official"]

    # 1. transition filed -> assigned
    transition_case(
        db=db_session,
        case_id=case.id,
        target_state="Assigned",
        user=official,
        assignee_id=official.id
    )
    db_session.commit()
    assert case.state == "Assigned"
    assert case.assignee_id == official.id
    assert case.version == 2

    # 2. transition assigned -> in review
    transition_case(
        db=db_session,
        case_id=case.id,
        target_state="In Review",
        user=official
    )
    db_session.commit()
    assert case.state == "In Review"
    assert case.version == 3

    # 3. transition in review -> resolved
    transition_case(
        db=db_session,
        case_id=case.id,
        target_state="Resolved",
        user=official,
        note="Re-evaluation complete, 5 marks awarded for page 3."
    )
    db_session.commit()
    assert case.state == "Resolved"
    assert case.version == 4

def test_illegal_state_jump_rejected(db_session, fixtures):
    case = fixtures["case"]
    official = fixtures["official"]

    # attempt illegal transition from filed directly to resolved
    with pytest.raises(InvalidTransitionError) as exc_info:
        transition_case(
            db=db_session,
            case_id=case.id,
            target_state="Resolved",
            user=official,
            note="Premature resolution"
        )
    assert "Illegal state transition" in str(exc_info.value)

def test_student_cannot_resolve_case(db_session, fixtures):
    case = fixtures["case"]
    student = fixtures["student"]
    official = fixtures["official"]

    # move to in review first
    transition_case(db_session, case.id, "Assigned", official, assignee_id=official.id)
    transition_case(db_session, case.id, "In Review", official)
    db_session.commit()

    # verify student cannot mark case resolved
    with pytest.raises(PermissionDeniedError):
        transition_case(
            db=db_session,
            case_id=case.id,
            target_state="Resolved",
            user=student,
            note="I resolve my own case"
        )

def test_resolution_requires_note(db_session, fixtures):
    case = fixtures["case"]
    official = fixtures["official"]

    # prepare case in review
    transition_case(db_session, case.id, "Assigned", official, assignee_id=official.id)
    transition_case(db_session, case.id, "In Review", official)
    db_session.commit()

    # verify missing resolution note is rejected
    with pytest.raises(InvalidTransitionError) as exc_info:
        transition_case(
            db=db_session,
            case_id=case.id,
            target_state="Resolved",
            user=official,
            note=""
        )
    assert "resolution note is required" in str(exc_info.value)

def test_escalation_flow(db_session, fixtures):
    case = fixtures["case"]
    official = fixtures["official"]
    authority = fixtures["authority"]

    # move to assigned
    transition_case(db_session, case.id, "Assigned", official, assignee_id=official.id)
    db_session.commit()

    # escalate with authority user
    transition_case(
        db=db_session,
        case_id=case.id,
        target_state="Escalated",
        user=authority,
        reason="SLA threshold exceeded without response"
    )
    db_session.commit()

    assert case.state == "Escalated"
    assert case.escalation_level == 1

    # authority takes over escalated ticket
    transition_case(
        db=db_session,
        case_id=case.id,
        target_state="In Review",
        user=authority
    )
    db_session.commit()
    assert case.state == "In Review"

