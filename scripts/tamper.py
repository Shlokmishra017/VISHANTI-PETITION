import sys
import json
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import text, select
from app.db import SessionLocal, engine
from app.models import Case, CaseEvent

# demonstrate tamper evidence by secretly altering an event payload in the ledger
def tamper_case_event(
    case_ref_or_id: str,
    target_seq: int,
    modified_text: str = "TAMPERED: Grade approved without review",
    db: Optional[Session] = None
):
    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True

    is_postgres = db.bind and db.bind.dialect.name == "postgresql"

    try:
        # find target case
        case = db.execute(
            select(Case).where((Case.id == case_ref_or_id) | (Case.ref_id == case_ref_or_id))
        ).scalar_one_or_none()

        if not case:
            print(f"Error: Case '{case_ref_or_id}' not found.")
            return False

        # locate target event
        event = db.execute(
            select(CaseEvent).where(CaseEvent.case_id == case.id, CaseEvent.seq == target_seq)
        ).scalar_one_or_none()

        if not event:
            print(f"Error: Event with sequence {target_seq} not found for case {case.ref_id}.")
            return False

        print(f"Found Case: {case.ref_id} ({case.id})")
        print(f"Targeting Seq {target_seq}: current hash = {event.hash[:16]}...")

        # temporarily disable trigger on postgres to simulate unauthorized database access
        if is_postgres:
            print("Disabling PostgreSQL immutability trigger...")
            db.execute(text("ALTER TABLE case_events DISABLE TRIGGER trg_protect_case_events;"))
            db.commit()

        # alter payload directly without recalculating sha256 hash chain
        payload = json.loads(event.payload_json)
        payload["tampered_note"] = modified_text
        payload["unauthorized_edit"] = True
        tampered_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))

        # execute direct raw update to simulate low level tamper
        db.execute(
            text("UPDATE case_events SET payload_json = :new_payload WHERE id = :event_id"),
            {"new_payload": tampered_json, "event_id": event.id}
        )
        db.commit()
        print(f"SUCCESS: Tampered payload for case {case.ref_id} at seq {target_seq}.")

    finally:
        # restore immutability trigger
        if is_postgres:
            print("Re-enabling PostgreSQL immutability trigger...")
            db.execute(text("ALTER TABLE case_events ENABLE TRIGGER trg_protect_case_events;"))
            db.commit()
        if own_session:
            db.close()

    return True

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python scripts/tamper.py <case_ref_or_id> <seq_number> [optional_tamper_text]")
        sys.exit(1)

    ref = sys.argv[1]
    seq = int(sys.argv[2])
    msg = sys.argv[3] if len(sys.argv) > 3 else "TAMPERED: Grade approved without review"
    tamper_case_event(ref, seq, msg)
