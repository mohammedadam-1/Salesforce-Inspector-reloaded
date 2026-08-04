"""Prime the placeholder connection with a validly-encrypted fake token.

The stored token ('enc') fails base64 decryption, stopping the sync path
before any outbound HTTP. Encrypting a placeholder refresh token lets the
validation probe reach the real Salesforce OAuth endpoint (which should
reject the fake token with invalid_grant).

Usage: Agent.env/bin/python scripts/phase5_prime_token.py
"""

import asyncio
import uuid

CONNECTION_ID = "c29977cf-ecff-47ff-ab24-286d10c2c21c"


async def main() -> None:
    from sfir_backend.config.container import Container
    from sfir_backend.config.settings import get_settings
    from sfir_backend.domain.entities.salesforce_connection import SalesforceConnection

    container = Container(get_settings())
    await container.startup()
    try:
        repo = container.get_repository("salesforce_connection")
        conn: SalesforceConnection = await repo.get_by_id(uuid.UUID(CONNECTION_ID))
        if conn is None:
            raise SystemExit(f"connection {CONNECTION_ID} not found")
        encryption = container.get_service("encryption")
        encrypted = encryption.encrypt("placeholder-refresh-token-for-probe")
        conn.access_token_encrypted = encrypted
        conn.refresh_token_encrypted = encrypted
        await repo.update(conn)
        await repo._session.commit()
        saved = await repo.get_by_id(uuid.UUID(CONNECTION_ID))
        print(f"[prime] refresh_token_encrypted length={len(saved.refresh_token_encrypted)} "
              f"prefix={saved.refresh_token_encrypted[:16]!r}")
    finally:
        await container.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
