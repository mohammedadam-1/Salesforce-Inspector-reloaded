import pytest
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from sfir_backend.api.errors import add_error_handlers
from sfir_backend.shared.exceptions.base import BaseAppException


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    add_error_handlers(app)
    return app


class TestErrorHandlers:
    async def test_base_app_exception(self, app) -> None:
        exc = BaseAppException(
            status_code=401,
            code="authentication_failed",
            detail="Test auth error",
        )
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [],
        }
        request = Request(scope)
        request.state.correlation_id = "test-corr"

        handler = app.exception_handlers[BaseAppException]
        response = await handler(request, exc)
        assert response.status_code == 401
        body = response.body.decode()
        assert "Test auth error" in body

    async def test_authorization_error(self, app) -> None:
        exc = BaseAppException(
            status_code=403,
            code="authorization_failed",
            detail="No permission",
        )
        scope = {"type": "http", "method": "GET", "path": "/admin", "headers": []}
        request = Request(scope)

        handler = app.exception_handlers[BaseAppException]
        response = await handler(request, exc)
        assert response.status_code == 403

    async def test_rate_limit_error(self, app) -> None:
        exc = BaseAppException(
            status_code=429,
            code="rate_limit_exceeded",
            detail="Too fast",
            context={"retry_after": 30},
        )
        scope = {"type": "http", "method": "GET", "path": "/api", "headers": []}
        request = Request(scope)

        handler = app.exception_handlers[BaseAppException]
        response = await handler(request, exc)
        assert response.status_code == 429

    async def test_validation_error(self, app) -> None:
        exc = RequestValidationError(errors=[
            {"loc": ("body", "email"), "msg": "field required", "type": "value_error.missing"},
        ])
        scope = {"type": "http", "method": "POST", "path": "/register", "headers": []}
        request = Request(scope)

        handler = app.exception_handlers[type(exc)]
        response = await handler(request, exc)
        assert response.status_code == 422

    async def test_http_exception(self, app) -> None:
        exc = HTTPException(status_code=404, detail="Not found")
        scope = {"type": "http", "method": "GET", "path": "/missing", "headers": []}
        request = Request(scope)

        handler = app.exception_handlers[type(exc)]
        response = await handler(request, exc)
        assert response.status_code == 404

    async def test_unhandled_exception(self, app) -> None:
        exc = ValueError("Unexpected error")
        scope = {"type": "http", "method": "GET", "path": "/crash", "headers": []}
        request = Request(scope)

        handler = app.exception_handlers[Exception]
        response = await handler(request, exc)
        assert response.status_code == 500
