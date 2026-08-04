SELECT count(*) AS metadata_versions FROM metadata_versions;
SELECT status, error_message FROM sync_jobs
WHERE id = '5d695789-42e4-4041-ac56-622eac4070b9';
SELECT status, total_items, processed_items, error_message
FROM sync_history ORDER BY created_at DESC LIMIT 1;
