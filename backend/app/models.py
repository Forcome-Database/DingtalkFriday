"""
SQLAlchemy ORM models for all database tables.
"""

from datetime import datetime

from sqlalchemy import (
    Column, DateTime, Float, Index, Integer, String, Text, UniqueConstraint,
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
    mobile = Column(String, nullable=True, comment="Mobile phone number")
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


class TripRecord(Base):
    """Business trip / out-of-office records from getupdatedata API."""
    __tablename__ = "trip_record"

    id = Column(Integer, primary_key=True, autoincrement=True)
    userid = Column(String, nullable=False, comment="DingTalk user ID")
    work_date = Column(String, nullable=False, comment="Work date YYYY-MM-DD")
    tag_name = Column(String, nullable=False, comment="出差 or 外出")
    sub_type = Column(String, nullable=True, comment="Sub-type name")
    begin_time = Column(String, nullable=False, comment="Approval begin time")
    end_time = Column(String, nullable=False, comment="Approval end time")
    duration_hours = Column(Float, nullable=False, default=0, comment="Hours for this work_date (8=full day)")
    proc_inst_id = Column(String, nullable=False, comment="Approval instance ID")
    last_synced_at = Column(DateTime, nullable=False, comment="Last sync timestamp")
    created_at = Column(DateTime, default=datetime.utcnow, comment="Record creation time")

    __table_args__ = (
        UniqueConstraint("userid", "work_date", "proc_inst_id", name="uq_trip_record"),
        Index("ix_trip_work_date_tag", "work_date", "tag_name"),
    )


class TripSyncCursor(Base):
    """Tracks which (userid, work_date) pairs have been synced."""
    __tablename__ = "trip_sync_cursor"

    userid = Column(String, primary_key=True, comment="DingTalk user ID")
    work_date = Column(String, primary_key=True, comment="Date YYYY-MM-DD")
    last_synced_at = Column(DateTime, nullable=False, comment="Last sync timestamp")


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


class AllowedUser(Base):
    """Allowed users table - stores phone numbers permitted to access the system."""
    __tablename__ = "allowed_user"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mobile = Column(String, unique=True, nullable=False, comment="Phone number")
    name = Column(String, nullable=True, comment="Display name")
    userid = Column(String, nullable=True, comment="DingTalk user ID (filled on login)")
    created_at = Column(DateTime, default=datetime.utcnow, comment="Creation time")


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
