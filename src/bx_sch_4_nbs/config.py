from datetime import time
from decimal import Decimal

from pydantic_settings import BaseSettings, SettingsConfigDict

from bx_sch_4_nbs.database.types import NailSize, Service


class Settings(BaseSettings):
    database_url: str
    encryption_key: str
    hash_pepper: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = False
    email_from: str = "Nails by Scooby <no-reply@nailsbyscooby.com>"
    studio_notification_email: str = "studio@nailsbyscooby.local"
    cors_origins: list[str] = ["http://localhost:4200"]
    appointments_timezone: str = "Europe/Lisbon"
    # The default slots of a day; a given day can have its own (table day_slots).
    appointment_slots: list[time] = [time(10, 0), time(14, 0), time(17, 0)]
    open_weekdays: list[int] = [1, 2, 3, 4]
    restricted_nail_sizes: list[NailSize] = [NailSize.XLARGE, NailSize.XXLARGE]
    maintenance_max_days: int = 35
    free_cancellation_hours: int = 48
    reminder_hours_before: int = 24
    confirmation_deadline_hours_before: int = 4
    frontend_url: str = "http://localhost:4200"
    min_booking_advance_hours: int = 24
    deposit_overdue_days: int = 2
    # Expected duration of each service, in minutes: draws the agenda and counts the hours
    # worked when the real duration was not recorded at completion.
    service_durations_minutes: dict[Service, int] = {
        Service.APPLICATION: 180,
        Service.MAINTENANCE: 150,
        Service.REMOVAL: 60,
        Service.OTHER: 60,
    }
    # The deposit (also written in the policies). Counted as income when the studio keeps it.
    deposit_amount: Decimal = Decimal("10.00")

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
