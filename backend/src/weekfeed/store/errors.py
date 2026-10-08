"""Store errors. The API maps these to HTTP status codes."""


class StoreError(Exception):
    pass


class NotFound(StoreError):
    """-> 404"""


class Conflict(StoreError):
    """-> 409"""


class Invalid(StoreError):
    """-> 422"""
