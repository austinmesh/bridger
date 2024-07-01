#!/usr/bin/env bash

set -eo pipefail

QUADLET_LOCATION="config/quadlet"
UNIT_LOCATION="$HOME/.config/containers/systemd"
SERVICES=($(ls -1 "$QUADLET_LOCATION" | grep -E '\.container$' | sed 's/\.container$//'))

export IMAGE="${IMAGE:-ghcr.io/austinmesh/bridger:lastest}"

cp -r $QUADLET_LOCATION/* "$UNIT_LOCATION"
envsubst < "$QUADLET_LOCATION/bridger.container" > "$UNIT_LOCATION/bridger.container"
systemctl --user daemon-reload
systemctl --user reload-or-restart "${SERVICES[@]}"
