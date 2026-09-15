#!/usr/bin/env python3
"""Stamp every Ignition resource.json in project/ .

Hand-writing these is where file-based Ignition work goes wrong. Two rules the
gateway enforces silently:

  * `lastModificationSignature` must be absent or correct. A stale one makes
    the scan skip the resource with no error anywhere.
  * `lastModification.timestamp` must move, or the scan decides nothing changed.

So this drops the signature entirely and stamps a fresh timestamp on every
run, then lists the resource's own files in `files`.
"""

import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "project")
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
ACTOR = "external"

# resource kind -> (scope, extra attributes, marker filenames)
PERSPECTIVE = "com.inductiveautomation.perspective"


def base(scope, files, attrs=None):
    r = {
        "scope": scope,
        "version": 1,
        "restricted": False,
        "overridable": True,
        "files": sorted(files),
        "attributes": {
            "lastModification": {"actor": ACTOR, "timestamp": NOW},
        },
    }
    if attrs:
        r["attributes"].update(attrs)
    return r


def write(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)
        f.write("\n")


def files_in(d, exclude=("resource.json", "unary-resource.json")):
    return [f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f)) and f not in exclude]


def main():
    n = 0

    # --- script-python: any dir containing code.py ------------------------
    sp = os.path.join(ROOT, "ignition", "script-python")
    for dirpath, _dirs, fs in os.walk(sp):
        if "code.py" in fs:
            write(
                os.path.join(dirpath, "resource.json"),
                base("A", ["code.py"], {"hintScope": 2}),
            )
            n += 1

    # --- gateway timer scripts -------------------------------------------
    tm = os.path.join(ROOT, "ignition", "timer")
    if os.path.isdir(tm):
        for name in os.listdir(tm):
            d = os.path.join(tm, name)
            if not os.path.isdir(d):
                continue
            write(
                os.path.join(d, "resource.json"),
                base(
                    "G",
                    ["handleTimerEvent.py"],
                    {
                        "enabled": True,
                        "sharedThread": True,
                        "delay": 1000,
                        "fixedDelay": True,
                    },
                ),
            )
            n += 1

    # --- named queries: any dir containing query.sql + params.json --------
    nq = os.path.join(ROOT, "ignition", "named-query")
    for dirpath, _dirs, fs in os.walk(nq):
        if "query.sql" not in fs:
            continue
        meta_path = os.path.join(dirpath, "params.json")
        meta = {}
        if os.path.isfile(meta_path):
            with open(meta_path) as f:
                meta = json.load(f)
        attrs = {
            "type": "Query",
            "enabled": True,
            "database": meta.get("database", "ignition"),
            "useMaxReturnSize": False,
            "maxReturnSize": 100,
            "autoBatchEnabled": False,
            "cacheEnabled": False,
            "cacheAmount": 1,
            "cacheUnit": "SEC",
            "fallbackEnabled": False,
            "fallbackValue": "",
            "permissions": [{"zone": "", "role": ""}],
            "parameters": meta.get("parameters", []),
        }
        r = base("DG", ["query.sql"], attrs)
        r["version"] = 2
        write(os.path.join(dirpath, "resource.json"), r)
        os.path.isfile(meta_path) and os.remove(meta_path)
        n += 1

    # --- perspective views: any dir containing view.json ------------------
    pv = os.path.join(ROOT, PERSPECTIVE, "views")
    for dirpath, _dirs, fs in os.walk(pv):
        if "view.json" in fs:
            write(os.path.join(dirpath, "resource.json"), base("G", ["view.json"]))
            n += 1

    # --- perspective style classes: any dir containing style.json ---------
    sc = os.path.join(ROOT, PERSPECTIVE, "style-classes")
    for dirpath, _dirs, fs in os.walk(sc):
        if "style.json" in fs:
            write(os.path.join(dirpath, "resource.json"), base("G", ["style.json"]))
            n += 1

    # --- singletons -------------------------------------------------------
    for sub, fname, scope in (
        (os.path.join(PERSPECTIVE, "stylesheet"), "stylesheet.css", "G"),
        (os.path.join(PERSPECTIVE, "page-config"), "config.json", "G"),
        (os.path.join(PERSPECTIVE, "session-props"), "props.json", "G"),
        (os.path.join(PERSPECTIVE, "general-properties"), "config.json", "G"),
    ):
        d = os.path.join(ROOT, sub)
        if os.path.isfile(os.path.join(d, fname)):
            write(os.path.join(d, "resource.json"), base(scope, [fname]))
            n += 1

    # --- webdev python resources -----------------------------------------
    wd = os.path.join(ROOT, "com.inductiveautomation.webdev", "resources")
    verbs = ["doGet", "doPost", "doPut", "doDelete", "doHead", "doOptions", "doTrace", "doPatch"]
    for dirpath, _dirs, fs in os.walk(wd):
        if not any(v + ".py" in fs for v in verbs):
            continue
        cfg = {"resource-type": "python-resource"}
        for v in verbs:
            present = v + ".py" in fs
            cfg[v] = {
                "enabled": present,
                "max-retry-attempts": 3,
                "require-auth": False,
                "require-https": False,
                "required-roles": "",
                "user-source": "",
            }
            if not present:
                with open(os.path.join(dirpath, v + ".py"), "w") as f:
                    f.write("def %s(request, session):\n\treturn\n" % v)
        write(os.path.join(dirpath, "config.json"), cfg)
        write(
            os.path.join(dirpath, "resource.json"),
            base("G", files_in(dirpath)),
        )
        n += 1

    print("stamped %d resource.json files at %s" % (n, NOW))


if __name__ == "__main__":
    sys.exit(main())
