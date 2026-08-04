SELECT c.id, c.organization_id, c.user_id, c.environment, c.instance_url, c.org_id,
       c.username, c.api_version, c.status, c.token_expires_at,
       c.last_successful_sync_at, c.last_failed_sync_at, c.error_message,
       c.is_active, c.created_at, c.updated_at,
       left(c.access_token_encrypted, 12) AS access_enc_prefix,
       left(c.refresh_token_encrypted, 12) AS refresh_enc_prefix
FROM salesforce_connections c;
SELECT id, organization_id, connection_id, sync_type, status, started_at, completed_at,
       error_message, components_synced, created_at
FROM sync_jobs ORDER BY created_at DESC LIMIT 10;
SELECT v.id, v.organization_id, v.connection_id, v.component_type, v.component_name,
       v.version, v.hash, v.created_at
FROM metadata_versions v ORDER BY v.created_at DESC LIMIT 10;
