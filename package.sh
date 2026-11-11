#!/usr/bin/env bash
# Build the importable project zip.
#
#   ./package.sh                    -> dist/Alarm_Demo.zip
#                                      dist/Alarm_Demo_Edge.zip
#   ./package.sh --release [3.0.1]  -> dist/Alarm_Demo-v3.0.1.zip
#                                      dist/Alarm_Demo_Edge-v3.0.1.zip
#   gates: --skip-readme-check --skip-a11y-check --skip-lint-check
#
# TWO zips, every time, because the demo has two homes. Ignition Edge has no
# database connectivity at all and permits exactly ONE realtime tag provider,
# which the platform owns and calls `edge`. The Edge zip is the same project
# with that provider name substituted at build time - the scripts already
# branch at RUNTIME on whether the gateway has a database, but a tag path is a
# literal in over a hundred places and a provider-less path does not resolve.
#
# Building both unconditionally is deliberate: a flag is a thing to forget, and
# the release that ships one zip when it needed two is indistinguishable from a
# correct one until someone installs it.
#
# A PLAIN IGNITION PROJECT EXPORT, and nothing else. The tag provider, the tags,
# the alarm journal profile and the journal tables are created by the project
# itself from its Setup screen, so all that is left to ship is the project.
#
# Install on any 8.3.8+ gateway: Config -> Platform -> Projects -> Import
# Project, choose the zip, then press "Set up this gateway" on the demo's Setup
# screen. Nothing else.
#
# --release stamps the version, in the STAGED copy only, in the places a
# released project carries it:
#
#   * AlarmDemo.alarms.VERSION      shown on screen, and at ?cmd=version
#   * the views' Build label        generated from VERSION by build_views.py
#   * project.json title            "ACME Alarm Demo v2.0.0" - Config -> Projects'
#                                   Edit drawer and the Perspective launch pages
#   * project.json description      ends "... . v2.0.0" - the Projects summary
#                                   grid shows ONLY the description column
#   * the zip's filename            a bare Alarm_Demo.zip on someone's desktop
#                                   is unidentifiable
#
# The working tree stays "(dev)" / VERSION = "dev" on purpose: a gateway running
# a working copy should say so rather than claim to be a release. Version given,
# else the tag HEAD is on. The build is the workspace's modules/package-project.sh.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_NAME=Alarm_Demo
PKG_GATES="readme a11y lint"
PKG_DEV_BUILDS=1
PKG_DIR_ENTRIES=1

DEV_TITLE="ACME Alarm Demo (dev)"
DESC_TAIL="on-call rosters and shift schedules."
ALARMS=ignition/script-python/AlarmDemo/alarms/code.py

pkg_prebuild() { rm -rf dist; }

# The tags, views and resource stamps are generated into the STAGED copy, never the
# working tree: the views carry the version on screen, and every resource.json gets
# a fresh timestamp, so generating in the tree left a release's version and 44
# re-stamped files behind to be committed by mistake. The generators write beside
# themselves, so they run from a scratch folder whose project/ is the stage.
pkg_stamp() {
  local d=$1 s
  if [[ -n "$RELEASE" ]]; then
    grep -q '^VERSION = "dev"' "$d/$ALARMS" || {
      echo "package.sh: AlarmDemo.alarms.VERSION was not \"dev\" - check for drift" >&2
      exit 1; }
    sed -i "s/^VERSION = \"dev\"/VERSION = \"$VERSION\"/" "$d/$ALARMS"
    grep -q "\"title\": \"$DEV_TITLE\"" "$d/project.json" || {
      echo "package.sh: project.json title was not '$DEV_TITLE' - check for drift" >&2
      exit 1; }
    sed -i "s/\"title\": \"$DEV_TITLE\"/\"title\": \"ACME Alarm Demo v$VERSION\"/" "$d/project.json"
    grep -q "$DESC_TAIL\"" "$d/project.json" || {
      echo "package.sh: project.json description was not the expected prose - check for drift" >&2
      exit 1; }
    sed -i "s/$DESC_TAIL\"/$DESC_TAIL \xc2\xb7 v$VERSION\"/" "$d/project.json"
  fi
  echo "--> regenerating tags and views"
  s=$(mktemp -d); mkdir "$s/tags"; ln -s "$d" "$s/project"
  cp build_views.py stamp_resources.py "$s/"; cp tags/build_tags.py "$s/tags/"
  python3 "$s/tags/build_tags.py" >/dev/null
  python3 "$s/build_views.py"
  python3 "$s/stamp_resources.py" >/dev/null
  rm -rf "$s"
}

# --------------------------------------------------------------------------
# the Edge build
# --------------------------------------------------------------------------
# The same project with ONE thing changed: the tag provider name. Edge permits
# exactly one realtime provider, the platform makes it and calls it `edge`, and
# a second is refused at startup - so the Edge build adopts the name that is
# already there rather than asking a customer to rename theirs.
#
# THREE functional forms carry the provider and all three must go, because the
# ones that are missed do not fail, they come back EMPTY:
#
#   [AlarmDemo]        a tag path                  (bindings and tag writes)
#   prov:AlarmDemo:    an alarm source filter      (every journal read, and the
#                                                   stock alarm components)
#   PROVIDER = "..."   the constant everything else derives from
#
# What must NOT be substituted, and is why this is not a blanket sed: the script
# package `AlarmDemo.alarms` and its siblings, the database connection name
# `AlarmDemoDB`, and the alarm journal profile named for the demo - on Edge the
# journal is the platform's own and the screens ask
# AlarmDemo.edition.journalName() for its name at runtime.
#
# Everything else that differs between the editions is a RUNTIME branch, not a
# build-time one: AlarmDemo.edition asks the gateway what it can do, and the
# analytics, the Setup rows and the journal screen follow. A capability is a
# property of the gateway, and baking it into a zip means a zip installed on
# the wrong edition is wrong in a way nothing on screen admits.
pkg_postbuild() {
  local edge=$1 EDGE_PROVIDER="edge" form LEFT UNCLASSIFIED
  echo
  echo "--> staging the Edge build"
  pkg_stamp "$edge"
  find "$edge" -type f \( -name '*.json' -o -name '*.py' \) -print0 \
    | xargs -0 sed -i \
        -e "s/\[AlarmDemo\]/[${EDGE_PROVIDER}]/g" \
        -e "s/prov:AlarmDemo:/prov:${EDGE_PROVIDER}:/g"
  sed -i "s/^PROVIDER = \"AlarmDemo\"/PROVIDER = \"${EDGE_PROVIDER}\"/" "$edge/$ALARMS"

  # Prove it. A silent no-op here ships a zip that looks right and reads no tags -
  # or worse, reads tags and shows no alarm history.
  for form in '\[AlarmDemo\]' 'prov:AlarmDemo:'; do
    LEFT="$(grep -rl "$form" "$edge" || true)"
    if [[ -n "$LEFT" ]]; then
      echo "package.sh: these still carry $form after the Edge substitution:" >&2
      printf '%s\n' "$LEFT" | sed "s|$edge|  project|" >&2
      exit 1
    fi
  done
  grep -q "^PROVIDER = \"${EDGE_PROVIDER}\"" "$edge/$ALARMS" || {
    echo "package.sh: the Edge build did not rewrite PROVIDER" >&2; exit 1; }
  grep -rq 'AlarmDemo\.alarms' "$edge" || {
    echo "package.sh: the Edge substitution ate the AlarmDemo script package" >&2
    exit 1; }

  # Anything ELSE still saying AlarmDemo in a resource file. Expected: the script
  # package and AlarmDemoDB. Anything else is a provider reference nobody has
  # classified, which is exactly the class of miss that ships an empty screen.
  # `AlarmDemo/` is the project's own view folder and `AlarmDemo.` the script
  # package; `AlarmDemoDB` is the connection. The journal table's `props.name`
  # default is the last legitimate bare one - it is overridden at runtime by a
  # binding on AlarmDemo.edition.journalName(), because on Edge the journal is
  # the platform's own and is not called this.
  UNCLASSIFIED="$(grep -rn 'AlarmDemo' "$edge" --include='*.json' 2>/dev/null \
                  | grep -v 'AlarmDemo\.' | grep -v 'AlarmDemoDB' \
                  | grep -v 'AlarmDemo/' | grep -v '"name": "AlarmDemo"' || true)"
  if [[ -n "$UNCLASSIFIED" ]]; then
    echo "package.sh: WARNING - unclassified provider references in the Edge build:" >&2
    printf '%s\n' "$UNCLASSIFIED" | sed "s|$edge|project|" | head -20 >&2
  fi

  # The project TITLE says which build it is, so a gateway running the wrong one
  # says so on its own launch page rather than in a support call.
  python3 - "$edge/project.json" <<'PYEOF'
import json
import sys

path = sys.argv[1]
with open(path) as fh:
    p = json.load(fh)
p["title"] = p["title"].replace("ACME Alarm Demo", "ACME Alarm Demo (Edge)", 1)
p["description"] = p["description"].replace(
    "on-call rosters and shift schedules.",
    "on-call rosters and shift schedules. Built for Ignition Edge.", 1)
with open(path, "w") as fh:
    json.dump(p, fh, indent=2)
    fh.write("\n")
PYEOF

  pkg_zip "$edge" "${PKG_NAME}_Edge"
}

d=$HERE; while [ "$d" != / ] && [ ! -f "$d/modules/package-project.sh" ]; do d=$(dirname "$d"); done
[ -f "$d/modules/package-project.sh" ] || { echo "package: modules/package-project.sh not found above $HERE; build from the Ignition-Work workspace" >&2; exit 1; }
. "$d/modules/package-project.sh"
