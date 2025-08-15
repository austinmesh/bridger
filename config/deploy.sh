#!/usr/bin/env bash

set -eo pipefail

QUADLET_LOCATION="config/quadlet"
UNIT_LOCATION="$HOME/.config/containers/systemd"
CONFIG_LOCATION="$HOME/.config/bridger"
SERVICES=($(ls -1 "$QUADLET_LOCATION" | grep -E '\.container$' | sed 's/\.container$//'))

export IMAGE="${IMAGE:-ghcr.io/austinmesh/bridger:latest}"

mkdir -p "$UNIT_LOCATION" "$CONFIG_LOCATION"
cp -r config/loki/* "$CONFIG_LOCATION"
cp -r config/alloy/* "$CONFIG_LOCATION"
cp -r $QUADLET_LOCATION/* "$UNIT_LOCATION"

for service in bridger bot http; do
    envsubst < "$QUADLET_LOCATION/$service.container" > "$UNIT_LOCATION/$service.container"
done

systemctl --user daemon-reload
systemctl --user reload-or-restart "${SERVICES[@]}"
