SELECT id, organization_id, connection_id, sync_type, status, progress, total_items,
       processed_items, failed_items, error_message, started_at, completed_at, created_at
FROM sync_jobs ORDER BY created_at DESC LIMIT 10;
SELECT id, organization_id, sync_job_id, component_type, component_name, component_id,
       hash, action, version_number, change_source, created_at
FROM metadata_versions ORDER BY created_at DESC LIMIT 10;
SELECT length(access_token_encrypted) AS access_len,
       length(refresh_token_encrypted) AS refresh_len,
       access_token_encrypted, refresh_token_encrypted
FROM salesforce_connections;
