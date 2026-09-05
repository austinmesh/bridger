#!/usr/bin/env bash

set -euo pipefail

# Resolve paths from the script's own location so this works from any working directory.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

QUADLET_LOCATION="$REPO_ROOT/config/quadlet"
UNIT_LOCATION="$HOME/.config/containers/systemd"
CONFIG_LOCATION="$HOME/.config/bridger"

export IMAGE="${IMAGE:-ghcr.io/austinmesh/bridger:latest}"

# Only the services built from this repo are restarted on a deploy.
#
# Deliberately not derived from the quadlet filenames:
#   - certbot is a Type=oneshot driven by certbot.timer, and binds host :8094 while it runs.
#     Restarting it on every deploy risks a port clash and burns Let's Encrypt rate limit.
#   - restarting emqx disconnects every gateway in the mesh.
# Infra services are restarted below only when their unit file actually changed. Override
# with e.g. SERVICES="emqx" config/deploy.sh
IFS=' ' read -r -a SERVICES <<< "${SERVICES:-bridger bot http}"

mkdir -p "$UNIT_LOCATION" "$CONFIG_LOCATION/loki" "$CONFIG_LOCATION/alloy"
cp -r "$REPO_ROOT/config/loki/." "$CONFIG_LOCATION/loki/"
cp -r "$REPO_ROOT/config/alloy/." "$CONFIG_LOCATION/alloy/"

changed=()

for src in "$QUADLET_LOCATION"/*; do
    name="$(basename "$src")"
    dst="$UNIT_LOCATION/$name"

    if [[ "$name" == bridger.container || "$name" == bot.container || "$name" == http.container ]]; then
        # Restrict substitution to IMAGE. A bare envsubst would expand every $VAR in the
        # file, silently blanking anything it does not have a value for.
        # shellcheck disable=SC2016  # the literal ${IMAGE} is envsubst's SHELL-FORMAT argument
        rendered="$(envsubst '${IMAGE}' < "$src")"
        if [[ ! -f "$dst" ]] || [[ "$rendered" != "$(cat "$dst")" ]]; then
            printf '%s\n' "$rendered" > "$dst"
            changed+=("${name%.container}")
        fi
        continue
    fi

    if ! cmp -s "$src" "$dst"; then
        cp "$src" "$dst"
        [[ "$name" == *.container ]] && changed+=("${name%.container}")
    fi
done

systemctl --user daemon-reload

# Always restart the app services; restart infra only when its unit file changed, and never
# certbot, which the timer owns.
to_restart=("${SERVICES[@]}")

for service in "${changed[@]:-}"; do
    [[ -z "$service" || "$service" == "certbot" ]] && continue
    printf '%s\n' "${to_restart[@]}" | grep -qx "$service" || to_restart+=("$service")
done

echo "Restarting: ${to_restart[*]}"
systemctl --user reload-or-restart "${to_restart[@]}"
