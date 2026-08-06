#!/usr/bin/env python3
"""Generate the gateway config resources this demo ships.

    python3 gateway/build_gateway.py

Writes `gateway/schedule/<name>/` and `gateway/roster-config/<name>/`, which
`deploy.sh --gateway` copies into
`data/config/resources/core/ignition/` on the target and applies with a CONFIG
scan (not a project scan - they are different buttons and only one of them
registers these).

The three schedules and three rosters here mirror `SCHEDULES` and `ROSTERS` in
`AlarmDemo.roster`. That module can recreate them at runtime on a gateway that
only received the project; these files are so a gateway that received the whole
bundle has them before the project ever runs.

`lastModificationSignature` is deliberately absent from every resource.json: a
signature that no longer matches its files makes the gateway skip the resource
during a scan, silently, which is indistinguishable from the scan not running.
"""

import json
import os
import uuid

# A fixed namespace, so a resource's UUID is derived from its kind and name and
# is the SAME on every rebuild. uuid4() here meant every run minted fresh
# identities for the three schedules and three rosters: the package was never
# reproducible, and a gateway that had already scanned an earlier build saw the
# next one as six different resources rather than the same six updated.
NS = uuid.UUID("6f9f2a54-3d1e-5c8b-9a70-2b1c4d5e6f70")
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))

USER_SOURCE = "default"

# (name, description, time ranges) - a basic schedule that repeats every day
SCHEDULES = [
    ("Day Shift", "06:00-14:00, every day", "6:00-14:00"),
    ("Afternoon Shift", "14:00-22:00, every day", "14:00-22:00"),
    ("Night Shift", "22:00-06:00, every day", "22:00-24:00,0:00-6:00"),
]

# (name, description, members)
ROSTERS = [
    ("Operations", "First response - the control room",
     ["jsmith", "achen", "rpatel"]),
    ("Maintenance", "Called for equipment faults",
     ["dwilson", "moconnor"]),
    ("Management", "Escalation of record",
     ["shaddad", "tnguyen"]),
]


def stamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write(kind, name, config, description):
    d = os.path.join(HERE, kind, name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "config.json"), "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")
    meta = {
        "scope": "A",
        "description": description,
        "version": 1,
        "restricted": False,
        "overridable": True,
        "files": ["config.json"],
        "attributes": {
            "uuid": str(uuid.uuid5(NS, "%s/%s" % (kind, name))),
            "enabled": True,
            "lastModification": {"actor": "AlarmDemo", "timestamp": stamp()},
        },
    }
    with open(os.path.join(d, "resource.json"), "w") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")
    return d


def schedule_config(times):
    """A basic schedule that is the same every day of the week.

    `allDays` + `allDayTime` carries the pattern, but the weekDay and per-day
    fields still have to be present or the resource does not parse.
    """
    cfg = {
        "profile": {"type": "basic schedule"},
        "settings": {
            "observeHolidays": False,
            "allDays": True,
            "allDayTime": times,
            "weekDays": False,
            "weekDayTime": "8:00-17:00",
            "repeatMode": "Off",
            "repeatOn": 1,
            "repeatOff": 1,
        },
    }
    for day in ("monday", "tuesday", "wednesday", "thursday", "friday",
                "saturday", "sunday"):
        cfg["settings"][day] = False
        cfg["settings"][day + "Time"] = "0:00-24:00"
    return cfg


def main():
    made = []
    for name, desc, times in SCHEDULES:
        made.append(write("schedule", name, schedule_config(times), desc))
    for name, desc, members in ROSTERS:
        # RosterConfig(List<RosterEntry(profile, userId)>) - the field names are
        # taken from the resource type's own default config, not guessed. Any
        # other spelling loads as an EMPTY roster with no error anywhere.
        made.append(write("roster-config", name,
                          {"users": [{"profile": USER_SOURCE, "userId": u}
                                     for u in members]}, desc))
    for d in made:
        print("wrote %s" % os.path.relpath(d, os.path.dirname(HERE)))


if __name__ == "__main__":
    main()
