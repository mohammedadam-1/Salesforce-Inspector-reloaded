SELECT id, sync_type, status, total_items, processed_items, progress, error_message
FROM sync_jobs
ORDER BY created_at DESC
LIMIT 5;

SELECT count(*) FROM metadata_objects;
SELECT count(*) FROM metadata_versions;
