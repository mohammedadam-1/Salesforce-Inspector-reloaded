DELETE FROM metadata_versions WHERE sync_job_id IN (
  SELECT id FROM sync_jobs WHERE created_at >= '2026-08-03 00:00:00'
);
DELETE FROM sync_retry_queue WHERE sync_job_id IN (
  SELECT id FROM sync_jobs WHERE created_at >= '2026-08-03 00:00:00'
);
DELETE FROM sync_history WHERE sync_job_id IN (
  SELECT id FROM sync_jobs WHERE created_at >= '2026-08-03 00:00:00'
);
DELETE FROM sync_jobs WHERE created_at >= '2026-08-03 00:00:00';
SELECT count(*) AS jobs_remaining FROM sync_jobs;
SELECT count(*) AS versions_remaining FROM metadata_versions;
SELECT count(*) AS history_remaining FROM sync_history;
SELECT count(*) AS retry_remaining FROM sync_retry_queue;
