SELECT left(refresh_token_encrypted,16) AS prefix,
       length(refresh_token_encrypted) AS len,
       status, last_successful_sync_at, last_failed_sync_at, error_message
FROM salesforce_connections
WHERE id = 'c29977cf-ecff-47ff-ab24-286d10c2c21c';
