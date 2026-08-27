#!/usr/bin/env bash
# Build the importable project zip.
#
#   ./package.sh                    -> dist/Alarm_Demo.zip
#   ./package.sh --release 2.0.0    -> dist/Alarm_Demo-2.0.0.zip
#
# A PLAIN IGNITION PROJECT EXPORT, and nothing else. It used to be an Ignition
# Exchange resource - a MANIFEST, a README, Projects/, Tags/, Gateway/ and
# SQL/, which a human unpacked and then applied in four places. The tag
# provider, the tags, the alarm journal profile and the journal tables are now
# created by the project itself from its Setup screen, so all that is left to
# ship is the project.
#
# Install on any 8.3.8+ gateway: Config -> Platform -> Projects -> Import
# Project, choose the zip, then press "Set up this gateway" on the demo's Setup
# screen. Nothing else.
#
# --release stamps the version in the three places a released project carries
# it, and puts the working tree back afterwards:
#
#   * AlarmDemo.alarms.VERSION      shown on screen, and at ?cmd=version
#   * project.json title            "ACME Alarm Demo 2.0.0" - Config -> Projects'
#                                   Edit drawer and the Perspective launch pages
#   * project.json description      ends "... . v2.0.0" - the Projects summary
#                                   grid shows ONLY the description column
#   * the zip's filename            a bare Alarm_Demo.zip on someone's desktop
#                                   is unidentifiable
#
# The working tree stays "(dev)" / VERSION = "dev" on purpose: a gateway running
# a working copy should say so rather than claim to be a release.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST="$HERE/dist"
PROJJSON="$HERE/project/project.json"
ALARMS="$HERE/project/ignition/script-python/AlarmDemo/alarms/code.py"

DEV_TITLE="ACME Alarm Demo (dev)"
DESC_TAIL="on-call rosters and shift schedules."

VERSION=""
case "${1:-}" in
  "")         ;;
  --release)  VERSION="${2:-}"
              [[ -n "$VERSION" ]] || { echo "usage: ./package.sh --release X.Y.Z" >&2; exit 2; }
              [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
                echo "version must look like 2.0.0, got '$VERSION'" >&2; exit 2; }
              ;;
  *)          echo "unknown option: $1" >&2; exit 2 ;;
esac

# Backups live OUTSIDE project/ - the zip is built by "cd project && zip -r .",
# so a backup left inside the project tree gets zipped up too.
PJBACKUP="$HERE/.project.json.orig"
ALBACKUP="$HERE/.alarms.code.py.orig"

if [[ -n "$VERSION" ]]; then
  cp "$PROJJSON" "$PJBACKUP"
  cp "$ALARMS" "$ALBACKUP"
  # Restore the two SOURCES, then regenerate from them. Restoring alone is not
  # enough: the views are generated and carry the version on screen, so a tree
  # left un-regenerated after a release says "v2.0.0" in 21 view.json files
  # while AlarmDemo.alarms.VERSION says "dev" - which is a release build
  # sitting in the working tree waiting to be committed as if it were one.
  trap 'mv "$PJBACKUP" "$PROJJSON"; mv "$ALBACKUP" "$ALARMS"; \
        python3 "$HERE/build_views.py" >/dev/null; \
        python3 "$HERE/stamp_resources.py" >/dev/null' EXIT

  grep -q '^VERSION = "dev"' "$ALARMS" || {
    echo "package.sh: AlarmDemo.alarms.VERSION was not \"dev\" - check for drift" >&2
    exit 1; }
  sed -i "s/^VERSION = \"dev\"/VERSION = \"$VERSION\"/" "$ALARMS"

  grep -q "\"title\": \"$DEV_TITLE\"" "$PROJJSON" || {
    echo "package.sh: project.json title was not '$DEV_TITLE' - check for drift" >&2
    exit 1; }
  sed -i "s/\"title\": \"$DEV_TITLE\"/\"title\": \"ACME Alarm Demo $VERSION\"/" "$PROJJSON"

  grep -q "$DESC_TAIL\"" "$PROJJSON" || {
    echo "package.sh: project.json description was not the expected prose - check for drift" >&2
    exit 1; }
  sed -i "s/$DESC_TAIL\"/$DESC_TAIL \xc2\xb7 v$VERSION\"/" "$PROJJSON"
fi

echo "--> regenerating tags and views"
python3 "$HERE/tags/build_tags.py" >/dev/null
python3 "$HERE/build_views.py"
python3 "$HERE/stamp_resources.py" >/dev/null

# An Ignition project export is the CONTENTS of the project directory, zipped
# from inside it - a zip with a project/ folder at its root imports as nothing.
#
# What must never be in it: ignition/global-props. That resource holds the
# project's Default Database and Perspective identity provider, so shipping a
# dev rig's copy puts this rig's names onto every gateway that imports the zip.
# This project has no global-props resource at all; the check is here so that
# stays true.
if [[ -e "$HERE/project/ignition/global-props" ]]; then
  echo "package.sh: project/ignition/global-props must not be shipped - remove it" >&2
  exit 1
fi

rm -rf "$DIST"
mkdir -p "$DIST"
if [[ -n "$VERSION" ]]; then
  OUT="$DIST/Alarm_Demo-$VERSION.zip"
else
  OUT="$DIST/Alarm_Demo.zip"
fi
( cd "$HERE/project" && zip -qr "$OUT" . )

echo
echo "package: $OUT"
unzip -l "$OUT" | tail -3
