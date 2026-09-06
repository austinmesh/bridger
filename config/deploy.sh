#!/usr/bin/env bash

set -euo pipefail

# Resolve paths from the script's own location so this works from any working directory.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

QUADLET_LOCATION="$REPO_ROOT/config/quadlet"
UNIT_LOCATION="$HOME/.config/containers/systemd"
CONFIG_LOCATION="$HOME/.config/bridger"

export IMAGE="${IMAGE:-ghcr.io/austinmesh/bridger:latest}"

mkdir -p "$UNIT_LOCATION" "$CONFIG_LOCATION/loki" "$CONFIG_LOCATION/alloy"
cp -r "$REPO_ROOT/config/loki/." "$CONFIG_LOCATION/loki/"
cp -r "$REPO_ROOT/config/alloy/." "$CONFIG_LOCATION/alloy/"

cp "$QUADLET_LOCATION"/* "$UNIT_LOCATION/"

# The services built from this repo are the only ones with an ${IMAGE} placeholder, so they
# get rewritten over the copy above. Substitution is restricted to IMAGE because a bare
# envsubst would expand every $VAR in the file, silently blanking anything it has no value for.
for name in bridger bot http; do
    # shellcheck disable=SC2016  # the literal ${IMAGE} is envsubst's SHELL-FORMAT argument
    envsubst '${IMAGE}' < "$QUADLET_LOCATION/$name.container" > "$UNIT_LOCATION/$name.container"
done

systemctl --user daemon-reload

services=()
for src in "$QUADLET_LOCATION"/*.container; do
    services+=("$(basename "$src" .container)")
done

echo "Restarting: ${services[*]}"
systemctl --user restart "${services[@]}"
