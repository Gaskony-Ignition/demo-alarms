#!/usr/bin/env bash
# Stamp, ship and scan the AlarmDemo project on the docker-server maker gateway.
#
#   ./deploy.sh              project only
#   ./deploy.sh --tags       also re-ship the tag definitions   (config scan)
#   ./deploy.sh --gateway    also re-ship schedules + on-call rosters + the
#                            tag-provider and alarm-journal profiles (config scan)
#   ./deploy.sh --all        everything
#
# Project resources and GATEWAY CONFIG resources are registered by two different
# scans. The gateway has two identically labelled "Scan File System" buttons and
# only one of them applies each kind; running the wrong one fails silently.
#
# The chown is load-bearing: a tar stream piped in from here lands as uid 1000,
# and the gateway later fails to rewrite root-owned paths it does not own.
#
# The project directory is PRUNED to match this repo on every deploy - see ship().
# Gateway config resources are not, deliberately: they share directories with
# every other project on the gateway.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSH_HOST=docker-server
CONTAINER=ignition-maker
GW=testbed
PLUGIN=/claude/ignition-toolkit/plugins/ignition/skills
CFG=/usr/local/bin/ignition/data/config/resources/core/ignition

MODE="${1:-}"
do_tags=0; do_gateway=0
case "$MODE" in
  --tags)    do_tags=1 ;;
  --gateway) do_gateway=1 ;;
  --all)     do_tags=1; do_gateway=1 ;;
  "")        ;;
  *) echo "unknown option: $MODE" >&2; exit 2 ;;
esac

# ship <local dir> <container dir> [prune]
#
# Untarring over the top ADDS and OVERWRITES but never removes, so a resource
# deleted from the repo lived on inside the gateway indefinitely - which is how
# five deleted named queries stayed registered and the gateway quietly stopped
# matching this repo.
#
# `prune` fixes that WITHOUT a recursive delete on a live gateway: it lists the
# files the archive actually contains, compares that against what is on disk,
# and removes only the difference. It cannot touch anything outside the
# destination, and it cannot remove a file the repo still has - the worst it can
# do is delete something that was hand-placed there and never tracked, which is
# exactly what it is for.
#
# Only ever prune a directory this repo OWNS ENTIRELY. The project directory
# qualifies. Gateway config directories do NOT: $CFG/schedule holds every
# schedule on the gateway, not just this demo's three, so pruning it would
# delete other projects' resources.
ship() {
  local prune_cmd=""
  if [[ "${3:-}" == "prune" ]]; then
    prune_cmd='
          tar tzf /tmp/ad-ship.tgz | sed "s|^\./||" | grep -v "/$" | sort > /tmp/ad-want
          find . -type f | sed "s|^\./||" | sort > /tmp/ad-have
          comm -13 /tmp/ad-want /tmp/ad-have > /tmp/ad-extra
          while read -r f; do [ -n "$f" ] && rm -f "./$f" && echo "    pruned: $f"; done < /tmp/ad-extra
          find . -type d -empty -delete 2>/dev/null || true
          rm -f /tmp/ad-want /tmp/ad-have /tmp/ad-extra'
  fi
  tar czf - -C "$1" . | ssh -o BatchMode=yes "$SSH_HOST" \
    "cat > /tmp/ad-ship.tgz \
     && sudo docker cp /tmp/ad-ship.tgz $CONTAINER:/tmp/ \
     && sudo docker exec $CONTAINER sh -lc '
          mkdir -p \"$2\"
          cd \"$2\"
          tar xzf /tmp/ad-ship.tgz$prune_cmd
          chown -R root:root .
        '"
}

python3 "$HERE/stamp_resources.py"

echo "--> shipping project"
# The project tree is generated in full from this repo, so the gateway copy is
# pruned to match it exactly on every deploy. Nothing else is.
ship "$HERE/project" "/usr/local/bin/ignition/data/projects/AlarmDemo" prune

need_config_scan=0

if [[ $do_tags == 1 ]]; then
  echo "--> shipping tags"
  python3 "$HERE/tags/build_tags.py" >/dev/null
  ship "$HERE/tags/build/ondisk" "$CFG/tag-definition/AlarmDemo"
  need_config_scan=1
fi

if [[ $do_gateway == 1 ]]; then
  echo "--> shipping gateway config resources"
  python3 "$HERE/gateway/build_gateway.py" >/dev/null
  for kind in tag-provider alarm-journal schedule roster-config; do
    [[ -d "$HERE/gateway/$kind" ]] || continue
    ship "$HERE/gateway/$kind" "$CFG/$kind"
  done
  need_config_scan=1
fi

if [[ $need_config_scan == 1 ]]; then
  node "$PLUGIN/config-scan/tool/config-scan.js" --gateway "$GW"
fi

echo "--> project scan"
node "$PLUGIN/scan/tool/scan.js" --gateway "$GW"
echo "done"
