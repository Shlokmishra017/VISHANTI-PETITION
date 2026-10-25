from sqlalchemy import select, or_
from sqlalchemy.orm import Query
from app.models import User, Case, Category

# evaluate whether a user has permission to view a specific case
def can_access_case(user: User, case: Case) -> bool:
    # admins have full access across the platform
    if user.role == "admin":
        return True

    # students can only access cases they filed
    if user.role == "student":
        return case.petitioner_id == user.id

    # officials can access cases in their department
    if user.role == "official":
        if not user.department_id or not case.category:
            return False
        return case.category.department_id == user.department_id

    # authorities can access escalated or assigned cases in their department
    if user.role == "authority":
        if not user.department_id or not case.category:
            return False
        in_dept = case.category.department_id == user.department_id
        return in_dept and (case.state == "Escalated" or case.assignee_id == user.id)

    return False

# apply visibility filters to case query based on caller's role
def scope_case_query(query, user: User):
    if user.role == "admin":
        return query

    if user.role == "student":
        return query.filter(Case.petitioner_id == user.id)

    if user.role == "official":
        return query.join(Category, Case.category_id == Category.id).filter(
            Category.department_id == user.department_id
        )

    if user.role == "authority":
        return query.join(Category, Case.category_id == Category.id).filter(
            Category.department_id == user.department_id,
            or_(Case.state == "Escalated", Case.assignee_id == user.id)
        )

    # fallback to empty query on unknown role
    return query.filter(False)

