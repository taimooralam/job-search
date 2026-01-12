#!/bin/bash
# Add MONGODB_VPS_URI to Vercel production environment

set -e

# Load the password
source "$(dirname "$0")/.env"

# URL encode the password
ENCODED_PWD=$(python3 -c "from urllib.parse import quote_plus; print(quote_plus('${MONGO_APP_PASSWORD}'))")

# Build the connection string
MONGODB_VPS_URI="mongodb://jobsearch_app:${ENCODED_PWD}@72.61.92.76:27018/jobs?authSource=jobs&directConnection=true"

echo "Adding MONGODB_VPS_URI to Vercel production..."
echo "$MONGODB_VPS_URI" | vercel env add MONGODB_VPS_URI production

echo "Done! You may need to redeploy for the change to take effect."
