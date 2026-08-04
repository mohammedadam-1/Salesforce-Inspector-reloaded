#!/bin/bash
awk -F= '/^SFIR_SALESFORCE_CLIENT_ID=/{print $2}' .env | tr -d '\r\n' | sha256sum | cut -d' ' -f1
printf '3MVG9dAEux2v1sLuPk.mnMkJRMWDfsK3i0ClQquiU2gKMLjziwzK8N579lmpxZtdptyFEXEi_ryaWqMy5UJg0' | sha256sum | cut -d' ' -f1
