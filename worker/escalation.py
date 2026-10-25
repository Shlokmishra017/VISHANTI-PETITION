import time
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_
from app.db import SessionLocal, engine
from app.models import Case, Escalation, User
from app.state_machine import transition_case

# execute a single escalation check cycle across overdue active cases
def run_escalation_tick(db: Session) -> int:
    now = datetime.now(timezone.utc)

    # find cases in assigned or in review with expired sla
    query = (
        select(Case)
        .where(
            Case.state.in_(["Assigned", "In Review"]),
            Case.sla_due_at.is_not(None),
            Case.sla_due_at < now
        )
    )
    # lock rows when supported to avoid concurrent escalation collisions
    if db.bind and db.bind.dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)

    overdue_cases = db.execute(query).scalars().all()
    escalated_count = 0

    # system user mock for audit attribution
    system_user = User(
        id="system-worker",
        email="system@vishanti.internal",
        name="Automated Escalation Daemon",
        role="system"
    )

    for case in overdue_cases:
        target_level = case.escalation_level + 1
        cycle = 1

        # check if already recorded in escalations to guarantee idempotency
        existing = db.execute(
            select(Escalation).where(
                and_(
                    Escalation.case_id == case.id,
                    Escalation.level == target_level,
                    Escalation.sla_cycle == cycle
                )
            )
        ).scalar_one_or_none()

        if existing:
            continue

        try:
            # record escalation record
            esc_record = Escalation(
                case_id=case.id,
                level=target_level,
                sla_cycle=cycle,
                created_at=now
            )
            db.add(esc_record)
            db.flush()

            # transition case to escalated state with ledger append
            transition_case(
                db=db,
                case_id=case.id,
                target_state="Escalated",
                user=system_user,
                reason=f"Automated SLA breach: deadline was {case.sla_due_at.isoformat()}"
            )
            db.commit()
            escalated_count += 1
            print(f"[Worker] Escalated case {case.ref_id} to level {target_level}")

        except Exception as e:
            db.rollback()
            print(f"[Worker] Failed escalating case {case.ref_id}: {e}")

    return escalated_count

# main continuous worker polling loop
def run_worker(poll_interval: int = 10):
    print(f"[Worker] Starting SLA escalation worker (polling every {poll_interval}s)...")
    while True:
        db = SessionLocal()
        try:
            run_escalation_tick(db)
        except Exception as e:
            print(f"[Worker] Error in escalation tick: {e}")
        finally:
            db.close()
        time.sleep(poll_interval)

if __name__ == "__main__":
    run_worker()

