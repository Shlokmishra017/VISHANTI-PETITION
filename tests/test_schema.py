import pytest
from sqlalchemy.exc import IntegrityError
from app.models import Department, User, Category, SLAPolicy, Case, CaseEvent
from app.auth import hash_password

def test_user_email_unique_constraint(db_session):
    # ensure duplicate email raises integrity error
    u1 = User(email="test@univ.edu", name="A", password_hash=hash_password("pw"), role="student")
    u2 = User(email="test@univ.edu", name="B", password_hash=hash_password("pw"), role="official")
    db_session.add(u1)
    db_session.commit()

    db_session.add(u2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

def test_case_events_unique_seq_per_case(db_session, fixtures):
    # ensure same seq for the same case raises unique constraint violation
    case = fixtures["case"]
    ev1 = CaseEvent(
        case_id=case.id,
        seq=99,
        type="TEST",
        actor_ref="user1",
        payload_json="{}",
        content_hash="a" * 64,
        prev_hash="0" * 64,
        hash="b" * 64
    )
    ev2 = CaseEvent(
        case_id=case.id,
        seq=99,
        type="TEST_DUP",
        actor_ref="user2",
        payload_json="{}",
        content_hash="c" * 64,
        prev_hash="b" * 64,
        hash="d" * 64
    )
    db_session.add(ev1)
    db_session.commit()

    db_session.add(ev2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

def test_sla_policy_unique_category_priority(db_session, fixtures):
    # ensure duplicate priority on same category fails
    cat = fixtures["category"]
    p1 = SLAPolicy(category_id=cat.id, priority="high", duration_seconds=3600)
    p2 = SLAPolicy(category_id=cat.id, priority="high", duration_seconds=7200)
    db_session.add(p1)
    db_session.commit()

    db_session.add(p2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

