#!/bin/bash
set -euo pipefail

# Approve a Web UI pairing code on the Torrent Search REST API server.
# Usage: approve.sh <token>
#
# Configuration is read from the local .env file in the same directory:
#   TEST_URL                 Base URL of the API server
#   TORRENT_SEARCH_API_KEY   Secret used for the Authorization bearer header
#   TEST_CHAT_ID             Telegram chat id to bind (default: 12345)
#
# Example:
#   ./approve.sh ABC123

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "Error: $ENV_FILE not found." >&2
  exit 1
fi

# shellcheck source=/dev/null
source "$ENV_FILE"

if [ -z "${TEST_URL:-}" ]; then
  echo "Error: TEST_URL is not set in $ENV_FILE." >&2
  exit 1
fi

if [ -z "${TORRENT_SEARCH_API_KEY:-}" ]; then
  echo "Error: TORRENT_SEARCH_API_KEY is not set in $ENV_FILE." >&2
  exit 1
fi

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <token>" >&2
  echo "" >&2
  echo "Approves a Web UI pairing code on $TEST_URL." >&2
  echo "Requires TEST_URL and TORRENT_SEARCH_API_KEY in $ENV_FILE." >&2
  exit 1
fi

CODE=$1
URL=${TEST_URL%/}
CHAT_ID=${TEST_CHAT_ID:-12345}

curl -s -X POST \
  "$URL/telegram/auth/register" \
  --url-query "code=$CODE" \
  --url-query "chat_id=$CHAT_ID" \
  -H "Authorization: Bearer $TORRENT_SEARCH_API_KEY" \
  -H "Accept: application/json"
echo
