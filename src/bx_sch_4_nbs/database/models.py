from datetime import datetime
from decimal import Decimal

from sqlalchemy import Column, DateTime, Numeric, Text, UniqueConstraint, func
from sqlmodel import Field, SQLModel

from bx_sch_4_nbs.database.types import AppointmentStatus, NailSize, Service, UserRole


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email_hash", name="uc_users_email_hash"),
        UniqueConstraint("phone_hash", name="uc_users_phone_hash"),
        UniqueConstraint("instagram", name="uc_users_instagram"),
    )

    id: int | None = Field(description="Primary key", default=None, primary_key=True)
    instagram: str | None = Field(
        description="Instagram handle, normalized (lowercase, without @)",
        default=None,
        max_length=255,
        nullable=True,
    )
    name: str = Field(description="First name", max_length=255, nullable=False)
    last_name: str = Field(description="Last name", max_length=255, nullable=False)
    email_encrypted: str = Field(description="Email encrypted with Fernet", max_length=512, nullable=False)
    email_hash: str = Field(
        description="Deterministic hash of the email, used for lookup", max_length=64, nullable=False
    )
    phone_encrypted: str = Field(description="Phone encrypted with Fernet", max_length=512, nullable=False)
    phone_hash: str = Field(
        description="Deterministic hash of the phone, used for lookup", max_length=64, nullable=False
    )
    role: UserRole = Field(description="User or super admin", default=UserRole.USER, nullable=False)
    password_hash: str | None = Field(
        description="Password hash; null until the client becomes regular",
        default=None,
        max_length=255,
        nullable=True,
    )
    is_active: bool = Field(description="True for regular clients (with password)", default=False, nullable=False)
    created_at: datetime | None = Field(
        description="Timestamp of when the record was created",
        default=None,
        sa_column=Column(DateTime, nullable=False, server_default=func.current_timestamp()),
    )
    updated_at: datetime | None = Field(
        description="Timestamp of when the record was last updated",
        default=None,
        sa_column=Column(
            DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
        ),
    )


class PreApprovedInstagram(SQLModel, table=True):
    __tablename__ = "pre_approved_instagrams"
    __table_args__ = (UniqueConstraint("instagram", name="uc_pre_approved_instagram"),)

    id: int | None = Field(default=None, primary_key=True)
    instagram: str = Field(max_length=255, nullable=False)
    created_at: datetime | None = Field(
        description="Timestamp of when the record was created",
        default=None,
        sa_column=Column(DateTime, nullable=False, server_default=func.current_timestamp()),
    )


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
    created_at: datetime | None = Field(
        description="Timestamp of when the record was created",
        default=None,
        sa_column=Column(DateTime, nullable=False, server_default=func.current_timestamp()),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
        ),
    )


class UserProfile(SQLModel, table=True):
    __tablename__ = "user_profiles"

    user_id: int = Field(foreign_key="users.id", nullable=False, primary_key=True, ondelete="CASCADE")
    nail_type: str | None = Field(default=None, max_length=255, nullable=True)
    cuticle_type: str | None = Field(default=None, max_length=255, nullable=True)
    notes: str | None = Field(sa_column=Column(Text, nullable=True, default=None))
    appointment_frequency_weeks: Decimal | None = Field(default=None, nullable=True)
