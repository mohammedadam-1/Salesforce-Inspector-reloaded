SELECT id, organization_id, connection_id, sync_type, status, total_items, processed_items,
       progress, error_message, created_at, updated_at, started_at, completed_at
FROM sync_jobs
ORDER BY created_at DESC
LIMIT 8;

SELECT count(*) AS metadata_objects FROM metadata_objects;

SELECT id, sync_job_id, status, items_count, error_message
FROM sync_history
ORDER BY created_at DESC
LIMIT 5;
