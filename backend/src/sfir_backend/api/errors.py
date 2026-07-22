import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from sfir_backend.shared.exceptions.base import BaseAppException

logger = structlog.get_logger(__name__)


def _correlation_id(request: Request) -> str | None:
    return getattr(request.state, "correlation_id", None)


def _problem_response(
    status: int,
    title: str,
    detail: str,
    request: Request,
    errors: list[dict] | None = None,
) -> JSONResponse:
    body: dict = {
        "type": f"https://api.sfir.dev/errors/{status}",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": str(request.url.path),
        "correlation_id": _correlation_id(request),
    }
    if errors:
        body["errors"] = errors
    return JSONResponse(status_code=status, content=body)


def add_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(BaseAppException)
    async def base_app_exception_handler(
        request: Request,
        exc: BaseAppException,
    ) -> JSONResponse:
        logger.warning(
            "application_error",
            code=exc.code,
            detail=exc.detail,
            status_code=exc.status_code,
            context=exc.context,
            path=str(request.url.path),
        )
        return _problem_response(
            status=exc.status_code,
            title=exc.code.replace("_", " ").title(),
            detail=exc.detail,
            request=request,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        errors = []
        for error in exc.errors():
            errors.append({
                "field": ".".join(str(loc) for loc in error.get("loc", [])),
                "code": error.get("type", "VALIDATION_ERROR"),
                "message": error.get("msg", "Invalid value"),
            })
        logger.warning("validation_error", errors=errors, path=str(request.url.path))
        return _problem_response(
            status=422,
            title="Validation Error",
            detail="Request validation failed",
            request=request,
            errors=errors,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        return _problem_response(
            status=exc.status_code,
            title="HTTP Error",
            detail=str(exc.detail),
            request=request,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.exception(
            "unhandled_exception",
            path=str(request.url.path),
            error=str(exc),
        )
        return _problem_response(
            status=500,
            title="Internal Server Error",
            detail="An unexpected error occurred.",
            request=request,
        )
