"""Unit tests for Salesforce client (mocked HTTP)."""

import pytest
from unittest.mock import AsyncMock, patch

from sfir_backend.infrastructure.salesforce.client import (
    SalesforceClient,
    SalesforceClientError,
    SalesforceAuthError,
    SalesforceRateLimitError,
)


@pytest.mark.asyncio
async def test_client_initialization():
    client = SalesforceClient(
        instance_url="https://test.salesforce.com",
        api_version="62.0",
        access_token="test_token",
    )
    assert client.instance_url == "https://test.salesforce.com"
    assert client.api_version == "62.0"
    assert client.is_authenticated is True
    await client.close()


@pytest.mark.asyncio
async def test_client_not_authenticated():
    client = SalesforceClient(
        instance_url="https://test.salesforce.com",
    )
    assert client.is_authenticated is False
    await client.close()


@pytest.mark.asyncio
async def test_build_url_rest():
    client = SalesforceClient(
        instance_url="https://test.salesforce.com",
        access_token="test",
    )
    url = client._build_url(client.ApiFamily.REST, "sobjects/")
    assert "https://test.salesforce.com/services/data/v62.0/sobjects/" in url
    await client.close()


@pytest.mark.asyncio
async def test_build_url_tooling():
    client = SalesforceClient(
        instance_url="https://test.salesforce.com",
        access_token="test",
    )
    url = client._build_url(client.ApiFamily.TOOLING, "query/")
    assert "https://test.salesforce.com/services/data/v62.0/tooling/query/" in url
    await client.close()


@pytest.mark.asyncio
async def test_client_error():
    client = SalesforceClient(
        instance_url="https://test.salesforce.com",
        access_token="test",
    )
    with pytest.raises(SalesforceClientError):
        await client.rest("GET", "invalid_endpoint_that_will_fail")
    await client.close()


@pytest.mark.asyncio
async def test_auth_error():
    client = SalesforceClient(
        instance_url="https://test.salesforce.com",
    )
    with pytest.raises(SalesforceAuthError):
        await client._refresh_access_token()
    await client.close()
