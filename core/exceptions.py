from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, ValidationError


class ContractAPIException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "VALIDATION_ERROR"
    default_detail = "Bad or invalid request"

    def __init__(self, code="VALIDATION_ERROR", message="Validation error", details=None, status_code=400):
        self.code = code
        self.message = message
        self.details = details if details is not None else []
        self.status_code = status_code
        super().__init__(detail=message, code=code)


def custom_exception_handler(exc, context):
    """Formats all exceptions into the contract shape:
    {"error": {"code": "...", "message": "...", "details": []}}
    """
    if isinstance(exc, ContractAPIException):
        return Response(
            {
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
            status=exc.status_code,
        )

    if isinstance(exc, NotFound):
        return Response(
            {
                "error": {
                    "code": "NOT_FOUND",
                    "message": str(exc.detail) if hasattr(exc, "detail") else "Resource not found",
                    "details": [],
                }
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    if isinstance(exc, ValidationError):
        msg = str(exc.detail)
        details = []
        if isinstance(exc.detail, dict):
            for k, v in exc.detail.items():
                details.append(f"{k}: {v}")
        elif isinstance(exc.detail, list):
            details = [str(x) for x in exc.detail]
        return Response(
            {
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": msg,
                    "details": details,
                }
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Call REST framework's default exception handler to get the standard response
    response = exception_handler(exc, context)
    if response is not None:
        code = "VALIDATION_ERROR"
        if response.status_code == 404:
            code = "NOT_FOUND"
        elif response.status_code == 409:
            code = "DUPLICATE"

        return Response(
            {
                "error": {
                    "code": code,
                    "message": str(response.data) if hasattr(response, "data") else "An error occurred",
                    "details": [response.data] if isinstance(response.data, (str, list)) else [],
                }
            },
            status=response.status_code,
        )

    return Response(
        {
            "error": {
                "code": "SERVER_ERROR",
                "message": str(exc),
                "details": [],
            }
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
