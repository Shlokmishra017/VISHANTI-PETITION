from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.config import settings
from app.db import get_db
from app.schemas import DevTamperRequest
from scripts.tamper import tamper_case_event
from worker.escalation import run_escalation_tick

router = APIRouter(prefix="/dev", tags=["dev"])

# ensure dev endpoints are strictly disabled in production
def verify_dev_mode():
    if settings.ENV == "production":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dev endpoints are disabled in production environment"
        )

# manually trigger an escalation worker cycle
@router.post("/tick")
def trigger_escalation_tick(db: Session = Depends(get_db)):
    verify_dev_mode()
    escalated_count = run_escalation_tick(db)
    return {"status": "ok", "escalated_cases": escalated_count}

# trigger payload tamper to demonstrate tamper-evident detection
@router.post("/tamper")
def trigger_tamper(body: DevTamperRequest, db: Session = Depends(get_db)):
    verify_dev_mode()
    success = tamper_case_event(
        case_ref_or_id=body.case_ref_or_id,
        target_seq=body.target_seq,
        modified_text=body.modified_text,
        db=db
    )
    if not success:
        raise HTTPException(status_code=400, detail="Failed to tamper target event")
    return {"status": "tampered", "case": body.case_ref_or_id, "seq": body.target_seq}

