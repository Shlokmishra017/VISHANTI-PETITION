import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, ForeignKey, Text, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.db import Base

# generate standard utc timestamp
def utc_now():
    return datetime.now(timezone.utc)

# generate string uuid for cross db portability
def new_uuid():
    return str(uuid.uuid4())

class Department(Base):
    __tablename__ = "departments"

    id = Column(String(36), primary_key=True, default=new_uuid)
    name = Column(String(100), unique=True, nullable=False)

    # relationships
    categories = relationship("Category", back_populates="department")
    officials = relationship("User", back_populates="department")

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=new_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(100), nullable=False)
    role = Column(String(20), nullable=False) # student, official, authority, admin
    department_id = Column(String(36), ForeignKey("departments.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    department = relationship("Department", back_populates="officials")
    cases = relationship("Case", foreign_keys="Case.petitioner_id", back_populates="petitioner")

class Category(Base):
    __tablename__ = "categories"

    id = Column(String(36), primary_key=True, default=new_uuid)
    name = Column(String(100), nullable=False)
    department_id = Column(String(36), ForeignKey("departments.id"), nullable=False)

    department = relationship("Department", back_populates="categories")
    sla_policies = relationship("SLAPolicy", back_populates="category")

class SLAPolicy(Base):
    __tablename__ = "sla_policies"

    id = Column(String(36), primary_key=True, default=new_uuid)
    category_id = Column(String(36), ForeignKey("categories.id"), nullable=False)
    priority = Column(String(20), nullable=False) # low, medium, high, urgent
    duration_seconds = Column(Integer, nullable=False)

    category = relationship("Category", back_populates="sla_policies")

    __table_args__ = (
        UniqueConstraint("category_id", "priority", name="uq_category_priority"),
    )

class EscalationChain(Base):
    __tablename__ = "escalation_chain"

    id = Column(String(36), primary_key=True, default=new_uuid)
    department_id = Column(String(36), ForeignKey("departments.id"), nullable=False)
    level = Column(Integer, nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("department_id", "level", name="uq_department_level"),
    )

class Case(Base):
    __tablename__ = "cases"

    id = Column(String(36), primary_key=True, default=new_uuid)
    ref_id = Column(String(32), unique=True, nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    category_id = Column(String(36), ForeignKey("categories.id"), nullable=False)
    priority = Column(String(20), default="medium", nullable=False)
    state = Column(String(30), default="Filed", nullable=False)
    petitioner_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    is_anonymous = Column(Boolean, default=False, nullable=False)
    claim_code_hash = Column(String(64), unique=True, nullable=True, index=True)
    assignee_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    escalation_level = Column(Integer, default=0, nullable=False)
    sla_due_at = Column(DateTime(timezone=True), nullable=True)
    version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    category = relationship("Category")
    petitioner = relationship("User", foreign_keys=[petitioner_id], back_populates="cases")
    assignee = relationship("User", foreign_keys=[assignee_id])
    events = relationship("CaseEvent", back_populates="case", order_by="CaseEvent.seq")
    attachments = relationship("Attachment", back_populates="case")

class CaseEvent(Base):
    # append only ledger table
    __tablename__ = "case_events"

    id = Column(String(36), primary_key=True, default=new_uuid)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False, index=True)
    seq = Column(Integer, nullable=False)
    type = Column(String(50), nullable=False)
    actor_ref = Column(String(100), nullable=False)
    payload_json = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False)
    prev_hash = Column(String(64), nullable=False)
    hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    case = relationship("Case", back_populates="events")

    __table_args__ = (
        UniqueConstraint("case_id", "seq", name="uq_case_seq"),
    )

class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(String(36), primary_key=True, default=new_uuid)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    mime = Column(String(100), nullable=False)
    size = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    storage_path = Column(String(500), nullable=False)

    case = relationship("Case", back_populates="attachments")

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, default=new_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False)
    kind = Column(String(50), nullable=False)
    body = Column(Text, nullable=False)
    seen = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

class Escalation(Base):
    __tablename__ = "escalations"

    id = Column(String(36), primary_key=True, default=new_uuid)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False)
    level = Column(Integer, nullable=False)
    sla_cycle = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("case_id", "level", "sla_cycle", name="uq_case_level_cycle"),
    )

class Checkpoint(Base):
    __tablename__ = "checkpoints"

    id = Column(String(36), primary_key=True, default=new_uuid)
    global_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

