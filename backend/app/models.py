"""
SQLAlchemy ORM models for all database tables.
"""

from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    UniqueConstraint,
)

from app.database import Base


class Department(Base):
    """Department table - synced from DingTalk."""
    __tablename__ = "department"

    dept_id = Column(Integer, primary_key=True, comment="DingTalk department ID")
    name = Column(String, nullable=False, comment="Department name")
    parent_id = Column(Integer, nullable=True, comment="Parent department ID")
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,
        comment="Last update timestamp",
    )


class Employee(Base):
    """Employee table - synced from DingTalk."""
    __tablename__ = "employee"

    userid = Column(String, primary_key=True, comment="DingTalk user ID")
    name = Column(String, nullable=False, comment="Employee name")
    dept_id = Column(Integer, nullable=False, comment="Primary department ID")
    dept_name = Column(String, nullable=True, comment="Primary department name")
    avatar = Column(String, nullable=True, comment="Avatar URL")
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,
        comment="Last update timestamp",
    )


class LeaveRecord(Base):
    """Leave record table - synced from DingTalk attendance API."""
    __tablename__ = "leave_record"

    id = Column(Integer, primary_key=True, autoincrement=True)
    userid = Column(String, nullable=False, comment="DingTalk user ID")
    start_time = Column(Integer, nullable=False, comment="Start time (Unix ms)")
    end_time = Column(Integer, nullable=False, comment="End time (Unix ms)")
    duration_percent = Column(
        Integer, nullable=False,
        comment="Duration * 100 (e.g. 100 = 1 day, 650 = 6.5 hours)",
    )
    duration_unit = Column(
        String, nullable=False,
        comment="percent_day or percent_hour",
    )
    leave_type = Column(String, default="请假", comment="Leave type name")
    leave_code = Column(String, nullable=True, comment="Leave type code")
    status = Column(String, default="已审批", comment="Approval status")
    created_at = Column(DateTime, default=datetime.utcnow, comment="Record creation time")

    __table_args__ = (
        UniqueConstraint("userid", "start_time", "end_time", name="uq_leave_record"),
    )


class LeaveType(Base):
    """Leave type table - synced from DingTalk vacation API."""
    __tablename__ = "leave_type"

    leave_code = Column(String, primary_key=True, comment="Leave type code")
    leave_name = Column(String, nullable=False, comment="Leave type display name")
    leave_view_unit = Column(
        String, nullable=True,
        comment="Display unit: day / halfDay / hour",
    )
    hours_in_per_day = Column(
        Integer, default=800,
        comment="Working hours per day * 100 (e.g. 800 = 8h)",
    )
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,
        comment="Last update timestamp",
    )


class SyncLog(Base):
    """Sync log table - tracks data synchronization runs."""
    __tablename__ = "sync_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sync_type = Column(
        String, nullable=False,
        comment="Sync type: department / employee / leave_type / leave_record / full",
    )
    status = Column(
        String, nullable=False,
        comment="Status: running / success / failed",
    )
    message = Column(Text, nullable=True, comment="Status message or error details")
    started_at = Column(DateTime, nullable=True, comment="Sync start time")
    finished_at = Column(DateTime, nullable=True, comment="Sync finish time")
