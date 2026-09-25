from enum import Enum


class UserRole(str, Enum):
    USER = "User"
    SUPER_ADMIN = "Super_admin"


class Service(str, Enum):
    APPLICATION = "Application"
    MAINTENANCE = "Maintenance"
    REMOVAL = "Removal"
    REMOVAL_MANICURE = "Removal and Manicure"


class NailSize(str, Enum):
    SMALL = "S"
    MEDIUM = "M"
    LARGE = "L"
    XLARGE = "XL"
    XXLARGE = "XXL"


class AppointmentStatus(str, Enum):
    SCHEDULED = "Scheduled"
    CONFIRMED = "Confirmed"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"
    NO_SHOW = "No_show"
