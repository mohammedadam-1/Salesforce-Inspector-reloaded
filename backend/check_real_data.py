"""Check if metadata in DB is from real Salesforce org."""
import asyncio
import uuid
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

ORG_ID = uuid.UUID("85962be2-e392-4a2d-b8b8-52a9338d898e")
ENGINE = create_async_engine("postgresql+asyncpg://sfir:sfir@localhost:5432/sfir")


async def main():
    async with ENGINE.connect() as conn:
        print("=== SAMPLE APEX CLASSES ===")
        r = await conn.execute(
            text("""
                SELECT component_name, component_id, version_number,
                       action, salesforce_last_modified
                FROM metadata_versions
                WHERE organization_id = :oid AND component_type = 'ApexClass'
                ORDER BY created_at DESC LIMIT 5
            """),
            {"oid": ORG_ID},
        )
        for row in r:
            print(f"  name={row[0]} sf_id={row[1]} v={row[2]} "
                  f"action={row[3]} sf_mod={row[4]}")

        print("\n=== SAMPLE CUSTOM OBJECTS ===")
        r = await conn.execute(
            text("""
                SELECT component_name, salesforce_last_modified
                FROM metadata_versions
                WHERE organization_id = :oid AND component_type = 'CustomObject'
                ORDER BY created_at DESC LIMIT 10
            """),
            {"oid": ORG_ID},
        )
        for row in r:
            print(f"  name={row[0]} sf_last_mod={row[1]}")

        print("\n=== APEX CLASS COUNT ===")
        r = await conn.execute(
            text("""
                SELECT COUNT(*) FROM metadata_versions
                WHERE organization_id = :oid AND component_type = 'ApexClass'
            """),
            {"oid": ORG_ID},
        )
        print(f"  count={r.scalar()}")

        print("\n=== CHECK FOR SF ORIGIN FIELDS IN PAYLOAD ===")
        r = await conn.execute(
            text("""
                SELECT component_name, payload->>'CreatedDate' as created,
                       payload->>'LastModifiedDate' as mod,
                       payload->>'Description' as desc_text
                FROM metadata_versions
                WHERE organization_id = :oid
                AND component_type = 'ApexClass'
                AND payload IS NOT NULL
                LIMIT 3
            """),
            {"oid": ORG_ID},
        )
        for row in r:
            print(f"  name={row[0]} created={row[1]} mod={row[2]} desc={row[3]}")

        print("\n=== DISTINCT COMPONENT TYPES WITH COUNTS ===")
        r = await conn.execute(
            text("""
                SELECT component_type, COUNT(DISTINCT component_name)
                FROM metadata_versions
                WHERE organization_id = :oid
                GROUP BY component_type
                ORDER BY component_type
            """),
            {"oid": ORG_ID},
        )
        total = 0
        for row in r:
            print(f"  {row[0]}: {row[1]}")
            total += row[1]
        print(f"  TOTAL DISTINCT COMPONENTS: {total}")

        print("\n=== CHECK CONNECTION STATUS ===")
        r = await conn.execute(
            text("""
                SELECT username, instance_url, org_id, status, api_version,
                       token_expires_at
                FROM salesforce_connections
                WHERE organization_id = :oid
            """),
            {"oid": ORG_ID},
        )
        for row in r:
            print(f"  user={row[0]} url={row[1]} sf_org={row[2]} "
                  f"status={row[3]} api={row[4]} expires={row[5]}")

        print("\n=== SYNC HISTORY ===")
        r = await conn.execute(
            text("""
                SELECT sync_type, status, total_items, processed_items,
                       started_at, completed_at, error_message
                FROM sync_history
                WHERE organization_id = :oid
                ORDER BY created_at DESC LIMIT 10
            """),
            {"oid": ORG_ID},
        )
        for row in r:
            print(f"  type={row[0]} status={row[1]} total={row[2]} "
                  f"processed={row[3]} started={row[4]} completed={row[5]} "
                  f"error={row[6]}")

    await ENGINE.dispose()


asyncio.run(main())
