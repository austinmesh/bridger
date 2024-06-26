#!/usr/bin/env bash

set -eo pipefail

QUADLET_LOCATION="config/quadlet"
UNIT_LOCATION="$HOME/.config/containers/systemd"
SERVICES=$(ls -1 "$QUADLET_LOCATION" | grep -E '\.container$' | sed 's/\.container$//')

cp -r "$QUADLET_LOCATION/*" "$UNIT_LOCATION"
systemctl --user daemon-reload
systemctl --user reload-or-restart "${SERVICES[@]}"
