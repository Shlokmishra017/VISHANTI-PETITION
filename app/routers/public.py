from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from app.db import get_db
from app.models import Case, Department, Category
from app.ledger import verify_chain

router = APIRouter(prefix="/public", tags=["public"])

# public overall integrity pass/fail check
@router.get("/verify")
def public_verify_ledger(db: Session = Depends(get_db)):
    case_ids = db.execute(select(Case.id)).scalars().all()
    all_valid = True
    first_broken = None

    for cid in case_ids:
        res = verify_chain(db, cid)
        if not res["valid"]:
            all_valid = False
            first_broken = {"case_id": cid, "seq": res["first_broken_seq"]}
            break

    return {
        "tamper_evident_status": "VALID" if all_valid else "COMPROMISED",
        "all_valid": all_valid,
        "total_cases_verified": len(case_ids),
        "compromised_case": first_broken
    }

# public aggregate metrics with n < 5 group suppression
@router.get("/metrics")
def public_metrics(db: Session = Depends(get_db)):
    total_cases = db.execute(select(func.count(Case.id))).scalar() or 0
    total_resolved = db.execute(select(func.count(Case.id)).where(Case.state == "Resolved")).scalar() or 0
    total_in_review = db.execute(select(func.count(Case.id)).where(Case.state == "In Review")).scalar() or 0
    total_escalated = db.execute(select(func.count(Case.id)).where(Case.state == "Escalated")).scalar() or 0

    # aggregate by department, suppressing any bucket with count < 5
    dept_rows = db.execute(
        select(Department.name, func.count(Case.id))
        .join(Category, Category.department_id == Department.id)
        .join(Case, Case.category_id == Category.id)
        .group_by(Department.name)
    ).all()

    department_stats = {}
    suppressed_count = 0
    for name, count in dept_rows:
        if count >= 5:
            department_stats[name] = count
        else:
            suppressed_count += count

    if suppressed_count > 0:
        department_stats["Other / Suppressed (<5)"] = suppressed_count

    return {
        "total_cases": total_cases,
        "total_resolved": total_resolved,
        "total_in_review": total_in_review,
        "total_escalated": total_escalated,
        "departments": department_stats
    }

