import uuid

from sfir_backend.api.schemas import (
    CursorParams,
    ErrorDetail,
    IdResponse,
    MessageResponse,
    PaginatedResponse,
    PaginationParams,
    ProblemResponse,
    SortParams,
    VersionResponse,
)


class TestPaginationParams:
    def test_defaults(self) -> None:
        p = PaginationParams()
        assert p.limit == 50
        assert p.offset == 0

    def test_validation(self) -> None:
        p = PaginationParams(limit=10, offset=100)
        assert p.limit == 10
        assert p.offset == 100


class TestCursorParams:
    def test_defaults(self) -> None:
        c = CursorParams()
        assert c.limit == 50
        assert c.cursor is None


class TestPaginatedResponse:
    def test_create(self) -> None:
        r = PaginatedResponse[int](
            items=[1, 2, 3],
            total=100,
            limit=50,
            offset=0,
            has_more=True,
        )
        assert len(r.items) == 3
        assert r.total == 100
        assert r.has_more is True


class TestSortParams:
    def test_default_order(self) -> None:
        s = SortParams()
        assert s.sort_order == "asc"

    def test_desc_order(self) -> None:
        s = SortParams(sort_order="desc")
        assert s.sort_order == "desc"


class TestErrorDetail:
    def test_create(self) -> None:
        e = ErrorDetail(field="email", code="INVALID_FORMAT", message="Invalid email")
        assert e.field == "email"
        assert e.code == "INVALID_FORMAT"


class TestProblemResponse:
    def test_default_type(self) -> None:
        r = ProblemResponse(title="Not Found", status=404, detail="Resource not found")
        assert r.type == "about:blank"
        assert r.status == 404


class TestMessageResponse:
    def test_create(self) -> None:
        r = MessageResponse(message="Success")
        assert r.message == "Success"


class TestIdResponse:
    def test_create(self) -> None:
        uid = uuid.uuid4()
        r = IdResponse(id=uid)
        assert r.id == uid


class TestVersionResponse:
    def test_create(self) -> None:
        r = VersionResponse(environment="testing")
        assert r.service == "sfir-backend"
        assert r.version == "0.1.0"
