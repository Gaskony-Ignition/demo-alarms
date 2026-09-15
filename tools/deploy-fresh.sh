#!/usr/bin/env bash
# Ship this repo's project/ into the blank gateway from tools/fresh-gateway.yml
# and run the project scan.
#
#   ./tools/deploy-fresh.sh
#
# Development loop only - the release path is package.sh and an Import Project
# on the gateway's own page. This exists because iterating on a script module
# through the import dialog is thirty seconds a change.
#
# Two things here are load-bearing, both learned the hard way:
#
#   * `docker cp` lands files owned by the HOST user (uid 1000), and the
#     gateway then cannot rewrite paths it does not own. They have to be
#     chowned to the container's ignition user (2003).
#   * `docker exec` runs as that same unprivileged user, so the chown has to be
#     `docker exec -u root` or it fails with "Operation not permitted" - which
#     looks like the copy worked, because it did.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER=alarm-demo-fresh
DEST=/usr/local/bin/ignition/data/projects/AlarmDemo
GW=fresh

# The blank gateway is not in the toolkit's shared gateway list - it is a
# throwaway. Point IGNITION_SCAN_CREDS at a stanza file carrying
#   fresh.url / fresh.user / fresh.password
# (the username and password are the ones in tools/fresh-gateway.yml).
: "${IGNITION_SCAN_CREDS:?set IGNITION_SCAN_CREDS to a file with a fresh.* stanza}"
export IGNITION_SCAN_CREDS

PLUGIN=""
for base in /Home-Claude/ignition-claude-toolkit /claude/ignition-claude-toolkit; do
  if [[ -f "$base/plugins/ignition/skills/scan/tool/scan.js" ]]; then
    PLUGIN="$base/plugins/ignition/skills"; break
  fi
done
[[ -n "$PLUGIN" ]] || { echo "cannot find the ignition toolkit plugin" >&2; exit 1; }

echo "--> stamping resources"
python3 "$HERE/stamp_resources.py" >/dev/null

echo "--> shipping to $CONTAINER"
docker exec "$CONTAINER" mkdir -p "$DEST"
docker cp "$HERE/project/." "$CONTAINER:$DEST/"
docker exec -u root "$CONTAINER" chown -R 2003:2003 "$DEST"

echo "--> project scan"
( cd "$PLUGIN/scan/tool" && node scan.js --gateway "$GW" )
