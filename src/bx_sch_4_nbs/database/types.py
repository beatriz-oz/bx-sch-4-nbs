from enum import Enum


class UserRole(str, Enum):
    USER = "User"
    SUPER_ADMIN = "Super_admin"


class Service(str, Enum):
    APPLICATION = "Application"
    MAINTENANCE = "Maintenance"
    REMOVAL = "Removal"
    OTHER = "Other"
    PRESS_ON = "Press-on"
    TRADING = "Trading"


class TradeItem(str, Enum):
    """What the studio gives in a trade (a service in exchange for something else, not money)."""

    NAILS = "Nails"
    PRESS_ONS = "Press-ons"


# Booked only by the studio, at the price she sets: no price table and no deposit.
# A trade (TRADING) is one of them, at no price at all.
STUDIO_ONLY_SERVICES = (Service.OTHER, Service.PRESS_ON, Service.TRADING)


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


class VerificationPurpose(str, Enum):
    CHECKIN = "Checkin"
    ACTIVATION = "Activation"
    PASSWORD_RESET = "Password reset"


class NailArtLevel(str, Enum):
    LEVEL_1 = "Level 1"
    LEVEL_2 = "Level 2"
    LEVEL_3 = "Level 3"


class Addon(str, Enum):
    BROKEN_NAIL = "Broken nail"
    EXTRA_CHARM = "Extra charm"


class CancellationReason(str, Enum):
    CLIENT_EARLY = "Cancelled by the client, more than 48h before"
    CLIENT_LATE = "Cancelled by the client, less than 48h before"
    NOT_CONFIRMED = "Attendance not confirmed in time"
    BY_STUDIO = "Cancelled by the studio"


class ExpenseCategory(str, Enum):
    PRODUCTS = "Products"
    MATERIAL = "Material"
    BILLS = "Bills"
    PRESS_ONS = "Press-ons"
    OTHER = "Other"
