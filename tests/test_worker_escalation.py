from datetime import datetime, timezone, timedelta
from app.models import Case, Escalation
from worker.escalation import run_escalation_tick

def test_escalation_worker_tick_and_idempotency(db_session, fixtures):
    case = fixtures["case"]
    official = fixtures["official"]

    # set case in assigned state with expired sla
    case.state = "Assigned"
    case.assignee_id = official.id
    case.sla_due_at = datetime.now(timezone.utc) - timedelta(hours=2)
    db_session.commit()

    # run initial escalation cycle
    escalated_count = run_escalation_tick(db_session)
    assert escalated_count == 1

    # refresh case and assert state changed to escalated
    db_session.refresh(case)
    assert case.state == "Escalated"
    assert case.escalation_level == 1

    # verify escalation record inserted
    esc_entry = db_session.query(Escalation).filter_by(case_id=case.id, level=1).scalar()
    assert esc_entry is not None

    # run second tick immediately to verify idempotency
    second_run_count = run_escalation_tick(db_session)
    assert second_run_count == 0

    # ensure no duplicate escalation row created
    total_escalations = db_session.query(Escalation).filter_by(case_id=case.id).count()
    assert total_escalations == 1

