class ResourceDoesNotExistError(Exception):
    pass


class ResourceAlreadyExistsError(Exception):
    pass


class DuplicateResourceError(Exception):
    pass


class ResourceInUseError(Exception):
    pass


class InvalidVerificationCodeError(Exception):
    pass


class VerificationCodeCooldownError(Exception):
    pass


class CancellationNotAllowedError(Exception):
    pass


class InvalidAttendanceTokenError(Exception):
    pass


class AppointmentNotActiveError(Exception):
    pass
