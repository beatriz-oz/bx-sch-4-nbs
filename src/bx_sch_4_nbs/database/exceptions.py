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
