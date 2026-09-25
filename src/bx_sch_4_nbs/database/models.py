from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import Column, DateTime, Numeric, Text, UniqueConstraint
from sqlmodel import Field, SQLModel

from bx_sch_4_nbs.database.types import AppointmentStatus, NailSize, Service, UserRole


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email_hash", name="uc_users_email_hash"),)

    id: int | None = Field(default=None, primary_key=True)
    instagram: str | None = Field(max_length=255, nullable=True)
    name: str = Field(max_length=255, nullable=False)
    last_name: str = Field(max_length=255, nullable=False)
    email_encrypted: str = Field(max_length=512, nullable=False)
    email_hash: str = Field(max_length=64, nullable=False, index=True)
    role: UserRole = Field(default=UserRole.USER, nullable=False)
    password_hash: str = Field(max_length=255, nullable=False)
    is_active: bool = Field(default=False, nullable=False)
    created_at: datetime = Field(
        sa_column=Column(DateTime, nullable=False, default=datetime.now(tz=UTC))
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime, nullable=False, default=datetime.now(tz=UTC))
    )


class PhoneNumber(SQLModel, table=True):
    __tablename__ = "phone_numbers"
    __table_args__ = (UniqueConstraint("phone_hash", name="uc_phone_numbers_phone_hash"),)

    id: int | None = Field(default=None, primary_key=True)
    phone_encrypted: str = Field(nullable=False)
    phone_hash: str = Field(max_length=64, nullable=False, index=True)
    user_id: int = Field(foreign_key="users.id", nullable=False, ondelete="CASCADE")


class Appointment(SQLModel, table=True):
    __tablename__ = "appointments"
    __table_args__ = (UniqueConstraint("scheduled_at", name="uc_appointments_schedule_at"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", nullable=False, ondelete="RESTRICT")
    scheduled_at: datetime = Field(nullable=False)
    is_deposit_paid: bool = Field(default=False, nullable=False)
    status: AppointmentStatus = Field(nullable=False, default=AppointmentStatus.SCHEDULED)
    service: Service = Field(nullable=False)
    nail_size: NailSize | None = Field(nullable=True)
    final_price: Decimal = Field(sa_column=Column(Numeric(10, 2), nullable=False))
    notes: str | None = Field(sa_column=Column(Text, nullable=True, default=None))
    updated_at: datetime = Field(
        sa_column=Column(DateTime, nullable=False, default=datetime.now(tz=UTC))
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime, nullable=False, default=datetime.now(tz=UTC))
    )


class UserProfile(SQLModel, table=True):
    __tablename__ = "user_profiles"

    user_id: int = Field(foreign_key="users.id", nullable=False, unique=True, primary_key=True, ondelete="CASCADE")
    nail_type: str| None = Field(default=None, max_length=255, nullable=True)
    cuticle_type: str | None = Field(default=None, max_length=255, nullable=True)
    notes: str | None = Field(sa_column=Column(Text, nullable=True, default=None))
    appointment_frequency_weeks: Decimal | None = Field(default=None, nullable=True)
