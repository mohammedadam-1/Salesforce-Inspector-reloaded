"""Salesforce connection management endpoints."""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.api.deps import get_current_user, get_db
from sfir_backend.config.settings import get_settings
from sfir_backend.infrastructure.database.models.salesforce import SalesforceConnection
from sfir_backend.infrastructure.salesforce.auth import SalesforceOAuthFlow
from sfir_backend.infrastructure.salesforce.client import SalesforceClient
from sfir_backend.infrastructure.security.encryption import decrypt, encrypt
from sfir_backend.repositories.base import BaseRepository

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/connections", tags=["Salesforce Connections"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_connection(
    organization_id: uuid.UUID,
    instance_url: str,
    api_version: str = "62.0",
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Initiate OAuth connection to a Salesforce org.

    Returns the authorization URL that the user must visit.
    """
    flow = SalesforceOAuthFlow()
    auth_url = flow.get_authorization_url(
        is_sandbox="sandbox" in instance_url or "test" in instance_url,
        state=str(uuid.uuid4()),
    )
    return {
        "authorization_url": auth_url,
        "state": auth_url.split("state=")[-1] if "state=" in auth_url else None,
        "message": "Redirect the user to the authorization URL to complete setup.",
    }


@router.get("/callback")
async def oauth_callback(
    code: str = Query(...),
    state: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Handle OAuth 2.0 callback from Salesforce."""
    is_sandbox = state and "sandbox" in state
    flow = SalesforceOAuthFlow()
    token_response = await flow.exchange_code(code, is_sandbox=is_sandbox)

    org_id = token_response.salesforce_org_id or "unknown"
    instance_url = token_response.instance_url or ""

    existing = await db.execute(
        select(SalesforceConnection).where(
            SalesforceConnection.salesforce_org_id == org_id
        )
    )
    conn = existing.scalar_one_or_none()

    if conn:
        conn.access_token_encrypted = encrypt(token_response.access_token)
        if token_response.refresh_token:
            conn.refresh_token_encrypted = encrypt(token_response.refresh_token)
        conn.status = "active"
    else:
        conn = SalesforceConnection(
            id=uuid.uuid4(),
            organization_id=uuid.UUID(int=0),
            connected_by_user_id=user.id,
            connection_type="oauth",
            salesforce_org_id=org_id,
            instance_url=instance_url,
            login_url=flow.SF_AUTH_URL,
            api_version="62.0",
            status="active",
            access_token_encrypted=encrypt(token_response.access_token),
            refresh_token_encrypted=encrypt(token_response.refresh_token)
            if token_response.refresh_token
            else None,
        )
        db.add(conn)

    await db.flush()
    logger.info("salesforce_connected", org_id=org_id, connection_id=str(conn.id))
    return {
        "status": "connected",
        "connection_id": str(conn.id),
        "organization_id": org_id,
        "instance_url": instance_url,
    }


@router.get("", response_model=list[dict])
async def list_connections(
    organization_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """List all Salesforce connections."""
    query = select(SalesforceConnection)
    if organization_id:
        query = query.where(
            SalesforceConnection.organization_id == organization_id
        )
    result = await db.execute(query)
    connections = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "organization_id": str(c.organization_id),
            "connection_type": c.connection_type,
            "salesforce_org_id": c.salesforce_org_id,
            "instance_url": c.instance_url,
            "api_version": c.api_version,
            "status": c.status,
            "token_expires_at": c.token_expires_at,
            "last_refreshed_at": c.last_refreshed_at,
            "created_at": c.created_at,
        }
        for c in connections
    ]


@router.get("/{connection_id}")
async def get_connection(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get connection details."""
    repo = BaseRepository(db, SalesforceConnection)
    conn = await repo.get_by_id(connection_id)
    if not conn:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )
    return {
        "id": str(conn.id),
        "organization_id": str(conn.organization_id),
        "connection_type": conn.connection_type,
        "salesforce_org_id": conn.salesforce_org_id,
        "instance_url": conn.instance_url,
        "api_version": conn.api_version,
        "status": conn.status,
        "scopes": conn.scopes,
        "token_expires_at": conn.token_expires_at,
        "last_refreshed_at": conn.last_refreshed_at,
        "created_at": conn.created_at,
    }


@router.post("/{connection_id}/test")
async def test_connection(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Test a Salesforce connection by making a simple API call."""
    repo = BaseRepository(db, SalesforceConnection)
    conn = await repo.get_by_id(connection_id)
    if not conn:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )

    try:
        access_token = decrypt(conn.access_token_encrypted) if conn.access_token_encrypted else None
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No access token available. Reconnect the org.",
            )

        client = SalesforceClient(
            instance_url=conn.instance_url,
            api_version=conn.api_version,
            access_token=access_token,
            refresh_token=decrypt(conn.refresh_token_encrypted)
            if conn.refresh_token_encrypted
            else None,
            client_id=get_settings().salesforce_client_id,
        )

        limits = await client.get_limits()
        await client.close()

        return {
            "status": "ok",
            "instance_url": conn.instance_url,
            "api_version": conn.api_version,
            "api_limits": limits.data if limits.data else {},
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Connection test failed: {str(e)}",
        )


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Revoke and remove a Salesforce connection."""
    repo = BaseRepository(db, SalesforceConnection)
    conn = await repo.get_by_id(connection_id)
    if not conn:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found",
        )
    await repo.delete(conn)
