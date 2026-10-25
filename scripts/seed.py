import uuid
from app.db import SessionLocal, engine, Base
from app.models import Department, User, Category, SLAPolicy, EscalationChain
from app.auth import hash_password

# seed initial database fixtures for local dev and testing
def seed():
    # ensure tables exist
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # check if already seeded
        if db.query(Department).first():
            print("Database already contains data, skipping seed.")
            return

        print("Seeding initial data...")

        # seed departments
        dept_academic = Department(id=str(uuid.uuid4()), name="Academic Affairs")
        dept_hostel = Department(id=str(uuid.uuid4()), name="Hostel & Facilities")
        dept_finance = Department(id=str(uuid.uuid4()), name="Finance & Accounts")
        dept_admin = Department(id=str(uuid.uuid4()), name="General Administration")
        db.add_all([dept_academic, dept_hostel, dept_finance, dept_admin])
        db.flush()

        # seed standard users across all roles
        users = [
            User(
                email="student@univ.edu",
                name="Rahul Sharma",
                password_hash=hash_password("student123"),
                role="student",
                department_id=None
            ),
            User(
                email="official@univ.edu",
                name="Prof. Verma (Academic Official)",
                password_hash=hash_password("official123"),
                role="official",
                department_id=dept_academic.id
            ),
            User(
                email="authority@univ.edu",
                name="Dean Academic (Authority)",
                password_hash=hash_password("authority123"),
                role="authority",
                department_id=dept_academic.id
            ),
            User(
                email="admin@univ.edu",
                name="Ledger Admin",
                password_hash=hash_password("admin123"),
                role="admin",
                department_id=None
            ),
        ]
        db.add_all(users)
        db.flush()

        # seed categories
        cat_grading = Category(
            id=str(uuid.uuid4()),
            name="Grading & Evaluation",
            department_id=dept_academic.id
        )
        cat_hostel = Category(
            id=str(uuid.uuid4()),
            name="Room Maintenance",
            department_id=dept_hostel.id
        )
        cat_fees = Category(
            id=str(uuid.uuid4()),
            name="Tuition Fee Error",
            department_id=dept_finance.id
        )
        db.add_all([cat_grading, cat_hostel, cat_fees])
        db.flush()

        # seed sla policies (duration in seconds)
        sla_policies = [
            SLAPolicy(category_id=cat_grading.id, priority="low", duration_seconds=86400),
            SLAPolicy(category_id=cat_grading.id, priority="medium", duration_seconds=43200),
            SLAPolicy(category_id=cat_grading.id, priority="high", duration_seconds=14400),
            SLAPolicy(category_id=cat_grading.id, priority="urgent", duration_seconds=3600),
            SLAPolicy(category_id=cat_hostel.id, priority="medium", duration_seconds=43200),
            SLAPolicy(category_id=cat_fees.id, priority="high", duration_seconds=14400),
        ]
        db.add_all(sla_policies)

        # seed escalation chain
        authority_user = next(u for u in users if u.role == "authority")
        admin_user = next(u for u in users if u.role == "admin")

        esc_level_1 = EscalationChain(
            department_id=dept_academic.id,
            level=1,
            user_id=authority_user.id
        )
        esc_level_2 = EscalationChain(
            department_id=dept_academic.id,
            level=2,
            user_id=admin_user.id
        )
        db.add_all([esc_level_1, esc_level_2])

        db.commit()
        print("Database seeding completed successfully.")

    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    seed()

