import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from app.db import Base, get_db
from app.models import Department, User, Category, SLAPolicy, EscalationChain, Case
from app.auth import hash_password
from app.main import app
from app.ledger import append_event

# test in-memory database engine using StaticPool to share connection
TEST_DB_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    # recreate schema fresh for each test
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def client(db_session):
    # override database dependency with test session
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

@pytest.fixture
def fixtures(db_session):
    # seed essential test fixtures
    dept = Department(name="Academic Affairs")
    db_session.add(dept)
    db_session.flush()

    student = User(
        email="student@test.edu",
        name="Student User",
        password_hash=hash_password("pass123"),
        role="student",
        department_id=None
    )
    official = User(
        email="official@test.edu",
        name="Official User",
        password_hash=hash_password("pass123"),
        role="official",
        department_id=dept.id
    )
    other_official = User(
        email="other_official@test.edu",
        name="Other Official",
        password_hash=hash_password("pass123"),
        role="official",
        department_id="other-dept-id"
    )
    authority = User(
        email="authority@test.edu",
        name="Authority User",
        password_hash=hash_password("pass123"),
        role="authority",
        department_id=dept.id
    )
    admin = User(
        email="admin@test.edu",
        name="Admin User",
        password_hash=hash_password("pass123"),
        role="admin",
        department_id=None
    )
    db_session.add_all([student, official, other_official, authority, admin])
    db_session.flush()

    category = Category(
        name="Exam Grading",
        department_id=dept.id
    )
    db_session.add(category)
    db_session.flush()

    case = Case(
        ref_id="VP-2026-0001",
        title="Incorrect grade on Math exam",
        description="Exam sheet was evaluated with missing page 3",
        category_id=category.id,
        priority="high",
        state="Filed",
        petitioner_id=student.id,
        is_anonymous=False
    )
    db_session.add(case)
    db_session.flush()

    # append genesis event for the newly filed case
    append_event(
        db=db_session,
        case_id=case.id,
        event_type="CASE_FILED",
        actor_ref=student.id,
        payload={"title": case.title, "category_id": case.category_id},
        content_text=case.description
    )
    db_session.commit()

    return {
        "dept": dept,
        "student": student,
        "official": official,
        "other_official": other_official,
        "authority": authority,
        "admin": admin,
        "category": category,
        "case": case
    }

