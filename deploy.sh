#!/usr/bin/env bash
# Generate, ship and scan the AlarmDemo project on the docker-server maker gateway.
#
#   ./deploy.sh
#
# There are no other options any more, because there is nothing else to ship.
# The tag provider, the tags, the alarm journal profile, the journal tables,
# the schedules, the users and the rosters used to travel as gateway CONFIG
# resources under gateway/ and tags/build/ondisk/ and needed a second,
# differently-labelled "Scan File System" button to register. They are now all
# created by the project itself, from the Setup screen (AlarmDemo.setup), which
# is what makes the demo a standalone import - so this script ships project
# resources and runs the project scan, and that is the whole deploy.
#
# The chown is load-bearing: a tar stream piped in from here lands as uid 1000,
# and the gateway later fails to rewrite root-owned paths it does not own.
#
# The project directory is PRUNED to match this repo on every deploy - see ship().
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSH_HOST=docker-server
CONTAINER=ignition-maker
GW=testbed
# The Ignition toolkit plugin. Its checkout is /Home-Claude/ignition-claude-toolkit;
# some shells see it through the /claude alias instead, so try both rather than
# hard-coding whichever one happened to work last.
PLUGIN=""
for base in /Home-Claude/ignition-claude-toolkit /claude/ignition-claude-toolkit; do
  if [[ -f "$base/plugins/ignition/skills/scan/tool/scan.js" ]]; then
    PLUGIN="$base/plugins/ignition/skills"
    break
  fi
done
[[ -n "$PLUGIN" ]] || { echo "cannot find the ignition toolkit plugin" >&2; exit 1; }

[[ $# -eq 0 ]] || { echo "usage: ./deploy.sh" >&2; exit 2; }

# ship <local dir> <container dir>
#
# Untarring over the top ADDS and OVERWRITES but never removes, so a resource
# deleted from the repo lived on inside the gateway indefinitely - which is how
# five deleted named queries stayed registered and the gateway quietly stopped
# matching this repo.
#
# The prune fixes that WITHOUT a recursive delete on a live gateway: it lists
# the files the archive actually contains, compares that against what is on
# disk, and removes only the difference. It cannot touch anything outside the
# destination, and it cannot remove a file the repo still has - the worst it can
# do is delete something that was hand-placed there and never tracked, which is
# exactly what it is for. Only ever point it at a directory this repo owns
# ENTIRELY; the project directory qualifies.
ship() {
  tar czf - -C "$1" . | ssh -o BatchMode=yes "$SSH_HOST" \
    "cat > /tmp/ad-ship.tgz \
     && sudo docker cp /tmp/ad-ship.tgz $CONTAINER:/tmp/ \
     && sudo docker exec $CONTAINER sh -lc '
          mkdir -p \"$2\"
          cd \"$2\"
          tar xzf /tmp/ad-ship.tgz
          tar tzf /tmp/ad-ship.tgz | sed \"s|^\./||\" | grep -v \"/\$\" | sort > /tmp/ad-want
          find . -type f | sed \"s|^\./||\" | sort > /tmp/ad-have
          comm -13 /tmp/ad-want /tmp/ad-have > /tmp/ad-extra
          while read -r f; do [ -n \"\$f\" ] && rm -f \"./\$f\" && echo \"    pruned: \$f\"; done < /tmp/ad-extra
          find . -type d -empty -delete 2>/dev/null || true
          rm -f /tmp/ad-want /tmp/ad-have /tmp/ad-extra
          chown -R root:root .
        '"
}

echo "--> generating"
python3 "$HERE/tags/build_tags.py" >/dev/null
python3 "$HERE/build_views.py"
python3 "$HERE/stamp_resources.py"

echo "--> shipping project"
ship "$HERE/project" "/usr/local/bin/ignition/data/projects/AlarmDemo"

echo "--> project scan"
node "$PLUGIN/scan/tool/scan.js" --gateway "$GW"
echo "done"
