#!/usr/bin/env bash

set -eo pipefail

UNIT_LOCATION="$HOME/.config/containers/systemd"
SERVICES=(bridger.service grafana.service influxdb.service)

cp -r config/quadlet/* "$UNIT_LOCATION"
systemctl --user daemon-reload
systemctl --user reload-or-restart "${SERVICES[@]}"
