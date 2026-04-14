"""Exceptions for vector store operations."""


class VectorStoreError(Exception):
    """Base exception for vector store errors."""

    pass


class VectorStoreConnectionError(VectorStoreError):
    """Raised when connection to vector store fails.

    Attributes:
        message: Error message
        backend: Backend type that failed to connect
    """

    def __init__(self, message: str, backend: str = None):
        self.backend = backend
        super().__init__(message)


class VectorStoreTimeoutError(VectorStoreError):
    """Raised when vector store operation times out.

    Attributes:
        message: Error message
        operation: Operation that timed out
    """

    def __init__(self, message: str, operation: str = None):
        self.operation = operation
        super().__init__(message)


class VectorStoreNotFoundError(VectorStoreError):
    """Raised when requested document or collection is not found."""

    pass
