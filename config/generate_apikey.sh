#!/usr/bin/env bash

set -eo pipefail

if [ -n "$DEBUG" ]; then
  set -x
fi

BOOTSTRAP_FILE="$1"
EMQX_DIR="/opt/emqx/etc"

if [ -z "$BOOTSTRAP_FILE" ]; then
  BOOTSTRAP_FILE="$EMQX_DIR/api_key.bootstrap"
fi

mkdir -p "$(dirname "$BOOTSTRAP_FILE")"

# Generate random API key and secret
API_KEY="bridger-$(openssl rand -hex 8)"
SECRET_KEY="$(openssl rand -hex 32)"
INFLUXDB_TOKEN="$(openssl rand -base64 64 | tr -d '\n' | tr '+/' '-_')"

# Create bootstrap file
echo "${API_KEY}:${SECRET_KEY}:administrator" > "$BOOTSTRAP_FILE"

echo ""
echo "Generated API and secret keys:"
echo ""
echo "API Key: $API_KEY"
echo "Secret Key: $SECRET_KEY"
echo "InfluxDB Token: $INFLUXDB_TOKEN"
echo ""
echo "Set these in your .env file:"
echo ""
echo "EMQX_API_KEY=\"$API_KEY\""
echo "EMQX_SECRET_KEY=\"$SECRET_KEY\""
echo "INFLUXDB_V2_TOKEN=\"$INFLUXDB_TOKEN\""
echo ""
echo "Bootstrap file created at: $BOOTSTRAP_FILE"
