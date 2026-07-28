"""Check if encrypted tokens exist in the existing connection."""
import asyncio
import uuid
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

ORG_ID = uuid.UUID("85962be2-e392-4a2d-b8b8-52a9338d898e")
ENGINE = create_async_engine("postgresql+asyncpg://sfir:sfir@localhost:5432/sfir")


async def main():
    async with ENGINE.connect() as conn:
        r = await conn.execute(
            text("""
                SELECT access_token_encrypted, refresh_token_encrypted
                FROM salesforce_connections
                WHERE organization_id = :oid
            """),
            {"oid": ORG_ID},
        )
        for row in r:
            tok = row[0]
            ref = row[1]
            print(f"access_token_encrypted: length={len(tok)} non-empty={bool(tok)}")
            print(f"refresh_token_encrypted: length={len(ref)} non-empty={bool(ref)}")
            print(f"access_token_encrypted first 20 chars: {tok[:20]!r}")
    await ENGINE.dispose()


asyncio.run(main())
