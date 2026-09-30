"""Durable event delivery and merged attendance refresh work."""

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.database import Base


class EventInbox(Base):
    __tablename__ = "event_inbox"

    event_id = Column(String, primary_key=True)
    event_type = Column(String, nullable=False)
    payload = Column(Text, nullable=False)
    received_at = Column(DateTime, nullable=False)
    processed_at = Column(DateTime, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime, nullable=False)
    error = Column(String, nullable=True)


class ApprovalScope(Base):
    __tablename__ = "approval_scope"

    instance_id = Column(String, primary_key=True)
    userid = Column(String, nullable=True)
    dates = Column(Text, nullable=False, default="[]")
    attached_ids = Column(Text, nullable=False, default="[]")
    status = Column(String, nullable=True)
    result = Column(String, nullable=True)
    updated_at = Column(DateTime, nullable=False)


class AttendanceRefresh(Base):
    __tablename__ = "attendance_refresh"

    domain = Column(String, primary_key=True)
    userid = Column(String, primary_key=True)
    date_key = Column(String, primary_key=True)
    attempts = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime, nullable=False)
    error = Column(String, nullable=True)
