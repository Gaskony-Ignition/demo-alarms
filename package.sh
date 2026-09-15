#!/usr/bin/env bash
# Build the importable project zip.
#
#   ./package.sh                    -> dist/Alarm_Demo.zip
#                                      dist/Alarm_Demo_Edge.zip
#   ./package.sh --release 3.0.1    -> dist/Alarm_Demo-3.0.1.zip
#                                      dist/Alarm_Demo_Edge-3.0.1.zip
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
# Repo gate (REPO-STANDARD.md). Blocking; bypass deliberately with --skip-readme-check.
if [[ " $* " != *" --skip-readme-check "* ]]; then
    _repo=$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)
    _gate=""; _d="$_repo"
    while [ "$_d" != / ]; do
        [ -x "$_d/modules/readme-gate.sh" ] && { _gate="$_d/modules/readme-gate.sh"; break; }
        _d=$(dirname "$_d")
    done
    if [ -n "$_gate" ]; then
        "$_gate" "$_repo" || { echo "repo gate failed: fix the README/tree or pass --skip-readme-check" >&2; exit 1; }
    else
        echo "readme-gate.sh not found above $_repo; gate skipped" >&2
    fi
fi
# Strip --skip-readme-check (already consumed by the gate above) so this
# script's own argument parsing -- which rejects unrecognised args -- never
# sees it.
_pkgargs=(); for _a in "$@"; do [[ "$_a" == "--skip-readme-check" ]] || _pkgargs+=("$_a"); done
set -- "${_pkgargs[@]}"

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

# ONE exit handler, because `trap ... EXIT` REPLACES the previous one rather
# than adding to it. This script had two - restore-the-sources, then later
# remove-the-Edge-staging - and the second silently disabled the first, so
# every --release left the working tree stamped with the release version and
# 44 regenerated resource files staged as if they were work. That is how
# 96412b8 ("Regenerate resource stamps so the tree matches the 3.0.2 artefact")
# came to exist. Both jobs go in here, and nothing else may call `trap`.
RESTORE=0
EDGE_SRC=""
cleanup() {
  [[ -n "$EDGE_SRC" ]] && rm -rf "$EDGE_SRC"
  if (( RESTORE )); then
    # Restore the two SOURCES, then regenerate from them. Restoring alone is
    # not enough: the views are generated and carry the version on screen, so a
    # tree left un-regenerated after a release says "v2.0.0" in 21 view.json
    # files while AlarmDemo.alarms.VERSION says "dev" - which is a release
    # build sitting in the working tree waiting to be committed as if it were
    # one.
    [[ -f "$PJBACKUP" ]] && mv "$PJBACKUP" "$PROJJSON"
    [[ -f "$ALBACKUP" ]] && mv "$ALBACKUP" "$ALARMS"
    python3 "$HERE/build_views.py" >/dev/null
    python3 "$HERE/stamp_resources.py" >/dev/null
  fi
  return 0
}
trap cleanup EXIT

if [[ -n "$VERSION" ]]; then
  cp "$PROJJSON" "$PJBACKUP"
  cp "$ALARMS" "$ALBACKUP"
  # Restore the two SOURCES, then regenerate from them. Restoring alone is not
  # enough: the views are generated and carry the version on screen, so a tree
  # left un-regenerated after a release says "v2.0.0" in 21 view.json files
  # while AlarmDemo.alarms.VERSION says "dev" - which is a release build
  # sitting in the working tree waiting to be committed as if it were one.
  RESTORE=1

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

# Zip the CONTENTS of a project directory, then prove the artefact is exactly
# the tracked tree and nothing else.
#
# ...and nothing that is not a project resource. This is not hypothetical
# either: running `python3 -m py_compile` over a script module as a syntax
# check leaves __pycache__/*.pyc beside it, .gitignore hides those from `git
# status`, and `zip -r .` swept two Python 3.14 bytecode files into a Jython
# project export. A green package that shipped junk looks exactly like a green
# package.
build_zip() {
  local src="$1" out="$2"
  ( cd "$src" && zip -qr "$out" . -x '*__pycache__*' '*.pyc' )

  # Verify the ARTEFACT, not the intent. Every project resource is committed,
  # so anything in the zip that git does not track is something that should not
  # be there. A release refuses; a dev build says so and carries on.
  #
  # The comparison is against the REPOSITORY's file list even for the Edge
  # build, whose staged copy is not a git tree: the Edge substitution rewrites
  # file CONTENTS and never adds or removes a file, so the two must list
  # identically. If that ever stops being true, this catches it.
  local extra
  extra=$(comm -23 \
    <(unzip -Z1 "$out" | grep -v '/$' | LC_ALL=C sort) \
    <(cd "$HERE/project" && git ls-files . | LC_ALL=C sort))
  if [[ -n "$extra" ]]; then
    echo "package.sh: $(basename "$out") contains files git does not track:" >&2
    echo "$extra" | sed 's/^/    /' >&2
    if [[ -n "$VERSION" ]]; then
      # Delete it. A refused release that leaves a zip in dist/ has produced
      # exactly the artefact it just refused to produce, sitting under the
      # right name, ready to be uploaded by anyone who did not read the error.
      rm -f "$out"
      echo "package.sh: refusing to publish a release containing them" >&2
      echo "package.sh: $(basename "$out") deleted" >&2
      exit 1
    fi
    echo "package.sh: (dev build - continuing)" >&2
  fi

  echo
  echo "package: $out"
  unzip -l "$out" | tail -3
}

if [[ -n "$VERSION" ]]; then
  OUT="$DIST/Alarm_Demo-$VERSION.zip"
  EDGE_OUT="$DIST/Alarm_Demo_Edge-$VERSION.zip"
else
  OUT="$DIST/Alarm_Demo.zip"
  EDGE_OUT="$DIST/Alarm_Demo_Edge.zip"
fi

build_zip "$HERE/project" "$OUT"

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
echo
echo "--> staging the Edge build"
EDGE_SRC="$(mktemp -d "$DIST/.edge-stage.XXXXXX")"
cp -a "$HERE/project/." "$EDGE_SRC/"
find "$EDGE_SRC" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$EDGE_SRC" -name '*.pyc' -delete 2>/dev/null || true

EDGE_PROVIDER="edge"
find "$EDGE_SRC" -type f \( -name '*.json' -o -name '*.py' \) -print0 \
  | xargs -0 sed -i \
      -e "s/\[AlarmDemo\]/[${EDGE_PROVIDER}]/g" \
      -e "s/prov:AlarmDemo:/prov:${EDGE_PROVIDER}:/g"
sed -i "s/^PROVIDER = \"AlarmDemo\"/PROVIDER = \"${EDGE_PROVIDER}\"/" \
  "$EDGE_SRC/ignition/script-python/AlarmDemo/alarms/code.py"

# Prove it. A silent no-op here ships a zip that looks right and reads no tags -
# or worse, reads tags and shows no alarm history.
for form in '\[AlarmDemo\]' 'prov:AlarmDemo:'; do
  LEFT="$(grep -rl "$form" "$EDGE_SRC" || true)"
  if [[ -n "$LEFT" ]]; then
    echo "package.sh: these still carry $form after the Edge substitution:" >&2
    printf '%s\n' "$LEFT" | sed "s|$EDGE_SRC|  project|" >&2
    exit 1
  fi
done
grep -q "^PROVIDER = \"${EDGE_PROVIDER}\"" \
  "$EDGE_SRC/ignition/script-python/AlarmDemo/alarms/code.py" || {
  echo "package.sh: the Edge build did not rewrite PROVIDER" >&2; exit 1; }
grep -rq 'AlarmDemo\.alarms' "$EDGE_SRC" || {
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
UNCLASSIFIED="$(grep -rn 'AlarmDemo' "$EDGE_SRC" --include='*.json' 2>/dev/null \
                | grep -v 'AlarmDemo\.' | grep -v 'AlarmDemoDB' \
                | grep -v 'AlarmDemo/' | grep -v '"name": "AlarmDemo"' || true)"
if [[ -n "$UNCLASSIFIED" ]]; then
  echo "package.sh: WARNING - unclassified provider references in the Edge build:" >&2
  printf '%s\n' "$UNCLASSIFIED" | sed "s|$EDGE_SRC|project|" | head -20 >&2
fi

# The project TITLE says which build it is, so a gateway running the wrong one
# says so on its own launch page rather than in a support call.
python3 - "$EDGE_SRC/project.json" <<'PYEOF'
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

build_zip "$EDGE_SRC" "$EDGE_OUT"
rm -rf "$EDGE_SRC"
