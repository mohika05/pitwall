class PitwallError(Exception):
    pass


class ExternalDataError(PitwallError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_text: str | None = None,
    ) -> None:
        super().__init__(message)

        self.status_code = status_code
        self.response_text = response_text


class ResourceNotFoundError(PitwallError):
    pass