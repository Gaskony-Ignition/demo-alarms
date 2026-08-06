#!/usr/bin/env bash
# Build the Ignition Exchange resource package.
#
#   ./package.sh            -> dist/acme_alarm_demo.<version>.zip
#
# Layout follows the Exchange convention, checked against two real Exchange
# downloads (DMC Alarm Intelligence Center 1.0.0 and Perspective Dynamic Alarm
# Metric View 1.0.2). MANIFEST, README.md and Projects/ are the required trio;
# Tags/ is the standard place for a tag export.
#
#   MANIFEST                        name, version, minimum Ignition, modules
#   README.md                       Exchange README - what it is, how to install
#   LICENSE                         MIT, as the README states
#   Projects/AlarmDemo.zip          the project export
#   Tags/AlarmDemo-tags.json        the tag export
#   Gateway/                        config resources a project cannot create for
#                                   itself: the tag provider and the alarm
#                                   journal profile, plus the shift schedules
#                                   and on-call rosters for anyone who would
#                                   rather scan them in than press the button
#   SQL/01-journal-tables.sql       journal schema, for a fresh database
#
# The Gateway/ and SQL/ folders are additions to the Exchange convention, not
# part of it. Both are described in the README's Custom Instructions, which is
# where an Exchange resource is expected to put anything a plain project import
# does not cover.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST="$HERE/dist"
STAGE="$DIST/stage"
SLUG=acme_alarm_demo

VERSION="$(python3 -c '
import json, sys
print(json.load(open(sys.argv[1]))["version"])' "$HERE/exchange/MANIFEST")"

rm -rf "$DIST"
mkdir -p "$STAGE/Projects" "$STAGE/Tags" "$STAGE/Gateway" "$STAGE/SQL"

echo "--> regenerating tags, gateway resources and views"
python3 "$HERE/tags/build_tags.py" >/dev/null
python3 "$HERE/gateway/build_gateway.py" >/dev/null
python3 "$HERE/build_views.py" >/dev/null
python3 "$HERE/stamp_resources.py" >/dev/null

echo "--> project export"
( cd "$HERE/project" && zip -qr "$STAGE/Projects/AlarmDemo.zip" . )

echo "--> tag export"
cp "$HERE/tags/build/AlarmDemo-tags.json" "$STAGE/Tags/"

echo "--> gateway config resources + sql"
for kind in tag-provider alarm-journal schedule roster-config; do
  [[ -d "$HERE/gateway/$kind" ]] && cp -r "$HERE/gateway/$kind" "$STAGE/Gateway/"
done
cp "$HERE/sql/"*.sql "$STAGE/SQL/"

echo "--> manifest + readme + licence"
cp "$HERE/exchange/MANIFEST" "$STAGE/MANIFEST"
cp "$HERE/exchange/README.md" "$STAGE/README.md"
# The README states MIT; ship the text with it rather than only the claim.
cp "$HERE/LICENSE" "$STAGE/LICENSE"

OUT="$DIST/$SLUG.$VERSION.zip"
( cd "$STAGE" && zip -qr "$OUT" . )
rm -rf "$STAGE"

echo
echo "package: $OUT"
unzip -l "$OUT" | sed -n '4,40p'
