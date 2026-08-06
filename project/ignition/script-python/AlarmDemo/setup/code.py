"""
AlarmDemo.setup - stand the whole demo up on a gateway, from the project.

Everything this demo needs that lives OUTSIDE the project - the journal tables,
the shift schedules, the users, the on-call rosters, and thirty days of history
- is created from here. That is deliberate: a project export is the only thing
that reliably travels between gateways, so anything the demo needs which is not
a project resource has to be something the project can create for itself.

    AlarmDemo.setup.run()             # everything, safe to run twice
    AlarmDemo.setup.run(days=60)      # deeper history
    AlarmDemo.setup.run(force=True)   # also reset rosters and shifts to the
                                      # shipped design, discarding edits made
                                      # on the Notifications screen
    AlarmDemo.setup.check()           # report state, change nothing

Run it from the Script Console, from the Set up demo button on the Demo Control
screen, or over HTTP:

    curl "http://<gateway>/system/webdev/AlarmDemo/admin?cmd=setup"

What it does NOT do, because a project cannot: create the `AlarmDemo` tag
provider, the alarm journal profile, or the database connection they depend on.
Those ship in the bundle as gateway config resources and are applied with a
config scan - see the README. `check()` tells you which of them are missing.
"""

# The datasource, journal tables and tag provider are defined ONCE, in
# AlarmDemo.alarms. Copies in this file are how "change the DB constant"
# quietly became a three-file edit that a fresh install gets wrong in one of
# them and then debugs as a blank screen.
DB = AlarmDemo.alarms.DB
PROVIDER = AlarmDemo.alarms.PROVIDER

LOG = system.util.getLogger("AlarmDemo.setup")


def _step(name, fn, report):
    try:
        report[name] = fn()
    except:
        import traceback
        report[name] = "FAILED"
        report.setdefault("errors", []).append(
            "%s: %s" % (name, traceback.format_exc().strip().split("\n")[-1]))
        LOG.warn("setup step %s failed: %s" % (name, traceback.format_exc()))
    return report


def run(days=30, perDay=85, force=False, history=True):
    """Create everything and return a report of what changed.

    Idempotent: rosters, schedules and users that already exist are left alone
    unless `force` is set. History is always regenerated, because a half-built
    30 days is worse than none.
    """
    report = {}

    # 1. journal tables. Ignition creates these on the first journalled event,
    #    but the backfill inserts straight into them, so on a fresh gateway
    #    they have to exist first.
    _step("journalTables", AlarmDemo.backfill.ensureSchema, report)

    # 2. shift schedules, users, on-call rosters - all real gateway objects
    _step("rosters", lambda: AlarmDemo.roster.setup(force), report)

    # 3. history, so every analytic has something to say from the first minute
    if history:
        _step("history", lambda: AlarmDemo.backfill.run(days=days,
                                                        perDay=perDay), report)
    else:
        report["history"] = "skipped"

    report["ok"] = "errors" not in report
    LOG.info("setup complete: %s" % report)
    return report


def check():
    """Report what is and is not in place. Changes nothing.

    Written to be the first thing to run when the demo looks wrong on a new
    gateway: it separates "the project did not import" from "the gateway
    resources were never scanned" from "there is simply no history yet", which
    otherwise all present as blank screens.
    """
    report = {}

    def tagProvider():
        # a read against any known tag proves the provider exists AND is running
        q = system.tag.readBlocking(["[%s]Intake/RawTurbidity" % PROVIDER])[0]
        return {"quality": str(q.quality), "ok": bool(q.quality.isGood())}

    def journalTables():
        n = system.db.runScalarQuery(
            "SELECT COUNT(*) FROM %s" % AlarmDemo.alarms.TABLE, DB)
        return {"datasource": DB, "rows": int(n or 0), "ok": True}

    def journalProfile():
        """Prove the alarm journal PROFILE exists, not just its tables.

        This is the check that separates the two ways a journal looks empty.
        The backfill writes straight into the tables, so `journalTables` above
        can report thousands of rows while every journal screen is blank -
        which is what a missing profile looks like, and it is one of the two
        resources a project import cannot bring with it.

        Reading the same rows back THROUGH the profile is the only thing that
        proves the profile exists and is pointed at these tables.
        """
        end = system.date.now()
        events = system.alarm.queryJournal(
            journalName=PROVIDER,
            startDate=system.date.addDays(end, -30), endDate=end)
        n = len(list(events))
        return {"profile": PROVIDER, "readable": n, "ok": n > 0}

    def rosters():
        names = [str(p) for p in system.alarm.getRosters().keys()]
        want = ("Operations", "Maintenance", "Management")
        return {"have": names,
                "missing": [w for w in want if w not in names],
                "ok": len([n for n in names if n in want]) == len(want)}

    def schedules():
        have = [str(n) for n in system.user.getScheduleNames()]
        want = ["Day Shift", "Afternoon Shift", "Night Shift"]
        return {"have": sorted(have),
                "missing": [w for w in want if w not in have],
                "ok": not [w for w in want if w not in have]}

    def users():
        known = set()
        for u in system.user.getUsers(AlarmDemo.roster.USER_SOURCE):
            known.add(str(u.get("username")).lower())
        want = [p[0] for p in AlarmDemo.roster.PEOPLE]
        missing = [w for w in want if w.lower() not in known]
        return {"missing": missing, "ok": not missing}

    def duty():
        return AlarmDemo.roster.dutySummary()

    # Ordered the way a broken install is diagnosed: the two things a project
    # import cannot bring with it first, then what the project creates itself.
    for name, fn in (("tagProvider", tagProvider),
                     ("journalProfile", journalProfile),
                     ("journalTables", journalTables),
                     ("rosters", rosters), ("schedules", schedules),
                     ("users", users), ("onDuty", duty)):
        _step(name, fn, report)

    report["ok"] = all(
        isinstance(v, dict) and v.get("ok", True)
        for k, v in report.items() if k not in ("errors", "ok"))
    return report
