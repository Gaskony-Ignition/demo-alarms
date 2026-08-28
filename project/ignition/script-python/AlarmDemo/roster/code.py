"""
AlarmDemo.roster - who gets an alarm, and how that is managed.

This module deliberately holds **no** membership data of its own. Everything it
shows is read back out of Ignition:

  1. WHO      real users in a user source (`system.user.getUsers`), each with
              email and SMS contact info
  2. WHEN     each user carries a real Ignition **schedule**, so "on duty" is
              answered by `system.user.isUserScheduled` and not by arithmetic
              on the clock in this file
  3. WHO GETS IT   real Ignition **on-call rosters**
              (`system.alarm.getRosters`), the same objects an alarm
              notification pipeline selects from

That is the point of the screen: a customer can open Config -> Alarming ->
On-Call Rosters, or Security -> Schedules, and see exactly what the demo is
showing. An earlier version kept membership in a `demo_roster_member` table,
which demonstrated a table rather than Ignition.

Rosters and schedules ship with the project as gateway config resources
(`gateway/roster-config`, `gateway/schedule`). `setup()` recreates them if they
are missing, so the demo also stands itself up on a gateway that only got the
project.

WRITING a roster
----------------
`system.alarm.createRoster(name, description)` creates one, but there is no
scripting call for membership. In 8.3 a roster IS a config resource -
`config/resources/core/ignition/roster-config/<name>/config.json`, holding
`{"users": [{"profile": ..., "userId": ...}]}` - so membership edits are made by
writing that file and asking the configuration manager to rescan. The shape is
not guessed: it is `RosterConfig(List<RosterEntry(profile, userId)>)`, read off
the resource type's own default config.
"""

import os
import traceback

USER_SOURCE = "default"

LOG = system.util.getLogger("AlarmDemo.roster")

# The people. Created as real users in the user source on first run; the
# schedule is a real Ignition schedule, assigned to the user, and is what
# decides whether they are on duty.
PEOPLE = [
    ("jsmith",   "Jordan Smith",     "Shift Operator",     "jordan.smith@acme.example",    "+61 400 111 222", "Day Shift"),
    ("achen",    "Alex Chen",        "Shift Operator",     "alex.chen@acme.example",       "+61 400 111 333", "Night Shift"),
    ("rpatel",   "Riya Patel",       "Senior Operator",    "riya.patel@acme.example",      "+61 400 111 444", "Afternoon Shift"),
    ("dwilson",  "Dana Wilson",      "Maintenance Fitter", "dana.wilson@acme.example",     "+61 400 222 111", "Day Shift"),
    ("moconnor", "Michael O'Connor", "Electrician",        "michael.oconnor@acme.example", "+61 400 222 333", "Afternoon Shift"),
    ("shaddad",  "Sara Haddad",      "Operations Manager", "sara.haddad@acme.example",     "+61 400 333 111", "Always"),
    ("tnguyen",  "Tam Nguyen",       "Process Engineer",   "tam.nguyen@acme.example",      "+61 400 333 222", "Day Shift"),
]

# (name, description, seed members). The members only seed a roster that does
# not exist yet; after that the config resource is the truth.
ROSTERS = [
    ("Operations",  "First response - the control room",
     ["jsmith", "achen", "rpatel"]),
    ("Maintenance", "Called for equipment faults",
     ["dwilson", "moconnor"]),
    ("Management",  "Escalation of record",
     ["shaddad", "tnguyen"]),
]

# The shift schedules this demo creates, as basic-schedule config resources.
# "Always" is built in to Ignition and is not recreated here.
SCHEDULES = [
    ("Day Shift",       "06:00-14:00, every day", "6:00-14:00"),
    ("Afternoon Shift", "14:00-22:00, every day", "14:00-22:00"),
    ("Night Shift",     "22:00-06:00, every day", "22:00-24:00,0:00-6:00"),
]

# priority -> (roster, notify after minutes, escalate to, escalate after mins)
#
# This is the demo's escalation design, not gateway configuration. Ignition
# implements it in an alarm notification pipeline, which needs a working email
# or SMS profile before it can do anything - out of scope for a self-contained
# demo. The rosters and schedules such a pipeline consumes ARE real here, which
# is the part worth showing.
ESCALATION = [
    ("Critical",   "Operations",  0,  "Management",  5),
    ("High",       "Operations",  2,  "Maintenance", 15),
    ("Medium",     "Operations",  10, "Maintenance", 60),
    ("Low",        "Operations",  30, "",            0),
    ("Diagnostic", "Maintenance", 60, "",            0),
]


def _safe(fn, default):
    try:
        return fn()
    except:
        import traceback
        LOG.warn("roster helper failed: %s" % traceback.format_exc())
        return default


def _people_index():
    return dict((p[0], p) for p in PEOPLE)


def _person(username):
    """Contact card for a username, whether or not this demo seeded them."""
    p = _people_index().get(username)
    if p:
        return {"username": p[0], "name": p[1], "role": p[2],
                "email": p[3], "phone": p[4]}
    return {"username": username, "name": username, "role": "",
            "email": "", "phone": ""}


# ---------------------------------------------------------------------------
# gateway config resources
# ---------------------------------------------------------------------------


def _configDir():
    """The gateway's config resource root.

    Resolved from the gateway's working directory rather than a hardcoded
    install path, so this behaves the same in a container and in a normal
    install.
    """
    from java.io import File
    return File("data/config/resources/core/ignition").getAbsolutePath()


def _write(path, text):
    """Write a config-resource file so a scan can never see it half-written.

    STAGED, THEN RENAMED - and this is not tidiness. `open(path, "w")`
    truncates immediately, so between that call and the flush the file on disk
    is empty or partial. The gateway's own file-tree scanner reads these
    directories whenever it likes - after any resource write anywhere, from
    the Config scan button, from another module - and a resource.json it reads
    mid-write is not retried. It is logged once, at WARN,

        Skipping resource directory with corrupt resource.json: .../Maintenance

    and skipped for good. The file on disk is perfect afterwards and the
    gateway never looks again, so the evidence and the symptom disagree: three
    rosters written, three correct directories, two rosters live.

    That is what cost the "press one button" path a green row on one run in
    two. A rename is atomic, so the scanner sees the old file or the new one
    and never a partial one. AlarmDemo.config.save() already did this and said
    why; the roster writer did not, and it is the roster writer that a scan
    races.
    """
    from java.io import File
    staged = File(path + ".tmp")
    f = open(staged.getAbsolutePath(), "w")
    try:
        f.write(text)
    finally:
        f.close()
    target = File(path)
    if not staged.renameTo(target):
        # Same directory, so a rename should never fail; if it does, say so
        # rather than leaving a .tmp behind and reporting success.
        if target.exists() and not target.delete():
            raise IOError("could not replace %s" % path)
        if not staged.renameTo(target):
            raise IOError("could not rename %s.tmp into place" % path)


def _writeResource(kind, name, config, description):
    """Write one gateway config resource and return its directory.

    `lastModificationSignature` is deliberately omitted and the timestamp is
    fresh: a resource carrying a signature that no longer matches its files is
    skipped by the scan silently, which looks exactly like the scan not running.
    """
    from java.util import UUID
    d = os.path.join(_configDir(), kind, name)
    if not os.path.exists(d):
        os.makedirs(d)
    _write(os.path.join(d, "config.json"), system.util.jsonEncode(config))
    meta = {
        "scope": "A",
        "description": description,
        "version": 1,
        "restricted": False,
        "overridable": True,
        "files": ["config.json"],
        "attributes": {
            "uuid": str(UUID.randomUUID()),
            "enabled": True,
            "lastModification": {
                "actor": "AlarmDemo",
                "timestamp": system.date.format(
                    system.date.now(), "yyyy-MM-dd'T'HH:mm:ss'Z'"),
            },
        },
    }
    # resource.json LAST, and atomically: it is the file that names the others,
    # so a scan that sees it sees a directory that is already complete.
    _write(os.path.join(d, "resource.json"), system.util.jsonEncode(meta))
    return d


def _rescan():
    """Ask the gateway to pick up config resources written above.

    A config scan is NOT the project scan - the gateway has two identically
    labelled "Scan File System" buttons for exactly this reason - so this goes
    through the configuration manager, not `system.project.requestScan`.
    """
    from com.inductiveautomation.ignition.gateway import IgnitionGateway
    IgnitionGateway.get().getConfigurationManager().requestScan()
    return True


def _writeRoster(name, usernames, description=""):
    _writeResource("roster-config", name,
                   {"users": [{"profile": USER_SOURCE, "userId": u}
                              for u in usernames]},
                   description or "Alarm demo on-call roster")
    return _rescan()


def _readRoster(name):
    """Members of a roster, read from the resource the gateway itself holds.

    NOT `system.alarm.getRosters()`. On 8.3.8 that call returns the roster
    NAMES correctly but an empty user list for every one of them, including
    rosters created through the gateway's own Create Alarm Roster page. Verified
    against Services -> Alarming -> Rosters, which shows "# OF USERS 3" for a
    roster the scripting call reports as empty - so the data is fine and the
    scripting call is not the way to read it.

    Reading the resource keeps this symmetric with the write path above: the
    same file, in the same place, in both directions.
    """
    path = os.path.join(_configDir(), "roster-config", name, "config.json")
    if not os.path.exists(path):
        return []
    f = open(path)
    try:
        cfg = system.util.jsonDecode(f.read()) or {}
    finally:
        f.close()
    return [str(u.get("userId")) for u in (cfg.get("users") or [])
            if u.get("userId")]


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------


def ensureSchedules():
    """Create the three shift schedules if they are not already there."""

    def go():
        have = set([str(n) for n in system.user.getScheduleNames()])
        made = []
        for name, desc, times in SCHEDULES:
            if name in have:
                continue
            _writeResource("schedule", name, {
                "profile": {"type": "basic schedule"},
                "settings": {
                    "observeHolidays": False,
                    # allDays + allDayTime is the 24/7 shift pattern. The
                    # weekDay and per-day fields still have to be present, or
                    # the resource does not parse.
                    "allDays": True,
                    "allDayTime": times,
                    "weekDays": False,
                    "weekDayTime": "8:00-17:00",
                    "monday": False, "tuesday": False, "wednesday": False,
                    "thursday": False, "friday": False, "saturday": False,
                    "sunday": False,
                    "mondayTime": "0:00-24:00", "tuesdayTime": "0:00-24:00",
                    "wednesdayTime": "0:00-24:00", "thursdayTime": "0:00-24:00",
                    "fridayTime": "0:00-24:00", "saturdayTime": "0:00-24:00",
                    "sundayTime": "0:00-24:00",
                    "repeatMode": "Off", "repeatOn": 1, "repeatOff": 1,
                },
            }, desc)
            made.append(name)
        if made:
            _rescan()
        return made

    return _safe(go, [])


def _uiProblems(response):
    """The error strings out of what a system.user write returns, or [].

    `system.user.addUser`, `editUser` and `removeUser` do NOT return a list of
    validation errors. They return a `UIResponse`, which is a Java object that
    is TRUTHY whether or not anything went wrong and is not iterable - so

        errors = system.user.addUser(src, user)
        if errors:
            LOG.warn(... list(errors))

    reports every success as a failure, and then raises `TypeError:
    'UIResponse' object is not iterable` while trying to say so. On a fresh
    gateway that read as seven people "refused by the gateway" on the Setup
    screen, in the same breath as the row above it reporting seven people
    created - because they had been. The same shape cost `setSchedule` its
    return value: every shift change succeeded and every one of them reported
    that it had not.

    The errors live in `getErrors()`. Some builds hand back a plain list
    instead, so that is tried second rather than assumed away.
    """
    from java.lang import Throwable as JThrowable
    if response is None:
        return []
    try:
        return [unicode(e) for e in response.getErrors()]
    except (JThrowable, Exception):
        pass
    try:
        return [unicode(e) for e in response]
    except (JThrowable, Exception):
        return []


def _addPerson(username, fullname, email, phone, schedule):
    """Create one demo user. Returns 1 if it was created, 0 if refused.

    Contact info is added on a BEST-EFFORT basis, one type at a time. The
    contact types a gateway accepts come from the notification modules it has:
    a gateway without SMS Notification rejects an "sms" contact, and it does
    it by throwing out of addContactInfo rather than by returning a validation
    error - which took the whole loop with it.
    """
    from java.util import UUID
    user = system.user.getNewUser(USER_SOURCE, username)
    user.set("firstname", fullname.split(" ")[0])
    user.set("lastname", " ".join(fullname.split(" ")[1:]))
    # An internal user source rejects a user with no password, and addUser
    # REPORTS that rather than raising - so without this the call looked like
    # it worked and nothing was created. See _uiProblems for what it actually
    # returns and why reading it wrongly is worse than not reading it. The
    # value is random and never logged: these users carry contact details for
    # notification, they are not accounts anyone signs in with.
    user.set("password", str(UUID.randomUUID()))
    user.set("schedule", schedule)
    for kind, value in (("email", email), ("sms", phone)):
        try:
            user.addContactInfo(kind, value)
        except:
            LOG.info("%s contact info not accepted for %s on this gateway"
                     % (kind, username))
    problems = _uiProblems(system.user.addUser(USER_SOURCE, user))
    if problems:
        LOG.warn("user %s rejected: %s" % (username, ", ".join(problems)))
        return 0
    return 1


def ensureUsers():
    """Create the demo users, with contact info and their shift schedule."""

    def go():
        existing = set()
        for u in system.user.getUsers(USER_SOURCE):
            existing.add(str(u.get("username")).lower())

        made, refused = 0, []
        for username, fullname, _role, email, phone, schedule in PEOPLE:
            if username.lower() in existing:
                # Already there, but possibly from a build that predates
                # schedules. Only fill a blank one - never overwrite a shift
                # somebody has changed on the screen.
                if not userSchedule(username):
                    setSchedule(username, schedule)
                continue
            # PER USER, not around the loop. A single person the gateway will
            # not accept used to abort the whole thing and leave the rest
            # uncreated - three people in, four missing, and the reason in the
            # gateway log rather than on the screen. Now the others are still
            # created and the ones that failed are named in the return.
            try:
                made += _addPerson(username, fullname, email, phone, schedule)
            except:
                LOG.warn("user %s could not be created: %s"
                         % (username, traceback.format_exc()))
                refused.append("%s (%s)" % (
                    username, traceback.format_exc().strip().split("\n")[-1]))
        if refused:
            return {"made": made, "refused": refused}
        return made

    return _safe(go, 0)


def ensureRosters(force=False):
    """Create the on-call rosters if they are missing. Idempotent."""

    def go():
        have = set(gatewayRosterNames())
        made = []
        for name, desc, members in ROSTERS:
            if name in have and not force:
                continue
            _writeResource("roster-config", name,
                           {"users": [{"profile": USER_SOURCE, "userId": u}
                                      for u in members]}, desc)
            made.append(name)
        if made:
            _rescan()
        return made

    return _safe(go, [])


def applyDefaultSchedules():
    """Put everyone back on the shift the demo was designed around.

    Separate from `ensureUsers` because a user that already exists keeps
    whatever schedule they have - including "Always", which is what Ignition
    reports for a user who has never been given one, and is therefore
    indistinguishable from "unset". Running the demo's own setup is the one
    moment where overwriting is the intent.
    """

    def go():
        # Reports the resulting assignment rather than a list of changes: "no
        # changes" and "every change silently failed" look identical in a diff,
        # and this runs on gateways nobody is watching.
        out = {}
        for username, _f, _r, _e, _p, schedule in PEOPLE:
            if userSchedule(username) != schedule:
                setSchedule(username, schedule)
            out[username] = userSchedule(username)
        return out

    return _safe(go, {})


def setup(force=False):
    """One call for a fresh gateway: schedules, users, rosters."""
    schedules = ensureSchedules()
    users = ensureUsers()
    return {"schedules": schedules,
            "users": users,
            "shifts": applyDefaultSchedules(),
            "rosters": ensureRosters(force)}


# ---------------------------------------------------------------------------
# duty
# ---------------------------------------------------------------------------


def _user(username):
    try:
        return system.user.getUser(USER_SOURCE, username)
    except:
        return None


def userSchedule(username):
    u = _user(username)
    if u is None:
        return ""
    try:
        return str(u.get("schedule") or "")
    except:
        return ""


def onDuty(username):
    """Is this person on duty right now, per their Ignition schedule?

    `isUserScheduled` takes a User object, not a name - handed a string it
    raises a coercion TypeError rather than returning False.
    """

    def go():
        u = _user(username)
        if u is None:
            return False
        return bool(system.user.isUserScheduled(u))

    return _safe(go, False)


def dutyNow():
    """{username: bool} for everyone the demo knows about, in one pass.

    The roster cards, the people list and the routing table all want the same
    answer, and each of them would otherwise ask per row.
    """

    def go():
        return dict((p[0], onDuty(p[0])) for p in PEOPLE)

    return _safe(go, dict((p[0], False) for p in PEOPLE))


def setSchedule(username, schedule):
    """Move someone onto a different shift, for real, in the user source."""

    def go():
        u = _user(username)
        if u is None:
            return False
        u.set("schedule", schedule)
        problems = _uiProblems(system.user.editUser(USER_SOURCE, u))
        if problems:
            LOG.warn("schedule change for %s rejected: %s"
                     % (username, ", ".join(problems)))
            return False
        return True

    return _safe(go, False)


# ---------------------------------------------------------------------------
# rosters
# ---------------------------------------------------------------------------


def rosterMembers(name):
    """Usernames on a roster, straight from the gateway's own roster resource."""
    return _safe(lambda: _readRoster(name), [])


def gatewayRosterNames():
    """Roster names as the ALARM SUBSYSTEM sees them.

    Used only to prove these are genuine gateway rosters rather than a list this
    project keeps - membership comes from `rosterMembers`, for the reason in
    `_readRoster`.
    """
    return _safe(lambda: sorted([str(k) for k in
                                 (system.alarm.getRosters() or {}).keys()]), [])


def rosterCards():
    """Rosters with their members, ready for the UI.

    Each card carries both numbers that matter: how many people are ON the
    roster, and how many of them are on duty right now. A roster with five
    members and nobody on shift is the failure this screen exists to expose.
    """

    def go():
        duty = dutyNow()
        blurbs = dict((n, d) for n, d, _m in ROSTERS)
        out = []
        for name, _desc, _seed in ROSTERS:
            members = []
            for username in rosterMembers(name):
                m = _person(username)
                m["schedule"] = userSchedule(username) or "-"
                m["onDuty"] = bool(duty.get(username, onDuty(username)))
                m["duty"] = "ON DUTY" if m["onDuty"] else "off"
                members.append(m)
            members.sort(key=lambda m: (not m["onDuty"], m["name"]))
            out.append({
                "roster": name,
                "blurb": blurbs.get(name, ""),
                "count": len(members),
                "onDuty": len([m for m in members if m["onDuty"]]),
                "members": members,
            })
        return out

    return _safe(go, [])


def addMember(roster, username):
    def go():
        members = rosterMembers(roster)
        if username and username not in members:
            members.append(username)
            _writeRoster(roster, members)
        return True

    return _safe(go, False)


def removeMember(roster, username):
    def go():
        members = [m for m in rosterMembers(roster) if m != username]
        _writeRoster(roster, members)
        return True

    return _safe(go, False)


def eligible(roster):
    """People not already on this roster - the only sensible contents for an
    "add someone" picker."""

    def go():
        have = set(rosterMembers(roster))
        return [{"value": u, "label": "%s  -  %s" % (full, role)}
                for u, full, role, _e, _p, _s in PEOPLE if u not in have]

    return _safe(go, [])


def peopleRows():
    """Everyone, with their schedule, duty state and roster memberships.

    A list of dicts rather than a dataset: each row on the screen carries shift
    buttons, and those need the username behind the row, not its rendered text.
    """

    def go():
        duty = dutyNow()
        rosters = dict((n, set(rosterMembers(n))) for n, _d, _m in ROSTERS)
        known = set()
        for u in system.user.getUsers(USER_SOURCE):
            known.add(str(u.get("username")).lower())

        rows = []
        for username, full, role, email, phone, _default in PEOPLE:
            on = sorted([n for n, members in rosters.items()
                         if username in members])
            rows.append({
                "username": username,
                "name": full,
                "role": role,
                "email": email,
                "phone": phone,
                "schedule": userSchedule(username) or "-",
                "onDuty": bool(duty.get(username, False)),
                "duty": "ON DUTY" if duty.get(username, False) else "off",
                "rosters": ", ".join(on) or "not on a roster",
                "inGateway": "yes" if username.lower() in known else "no",
            })
        return rows

    return _safe(go, [])


def dutySummary():
    """"3 of 7 on duty" for the header chip."""

    def go():
        duty = dutyNow()
        return {"onDuty": len([1 for v in duty.values() if v]),
                "total": len(PEOPLE)}

    return _safe(go, {"onDuty": 0, "total": len(PEOPLE)})


# ---------------------------------------------------------------------------
# routing - who gets this alarm, right now
# ---------------------------------------------------------------------------


def _rule(priority):
    for pri, roster, delay, esc, esc_after in ESCALATION:
        if pri == priority:
            return roster, delay, esc, esc_after
    return "Operations", 15, "", 0


def escalationTable():
    rows = []
    for pri, roster, delay, esc, esc_after in ESCALATION:
        rows.append([pri, roster,
                     "immediately" if delay == 0 else "after %d min" % delay,
                     esc or "-",
                     "-" if not esc else "after %d min" % esc_after])
    return system.dataset.toDataSet(
        ["Priority", "Notifies", "When", "Escalates to", "If unacknowledged"],
        rows)


def routing(site="Water"):
    """For every active alarm on this site: who is notified right now.

    Priority picks the roster; the roster's members are then filtered by their
    Ignition schedule, which is the order a notification pipeline resolves it
    in. When nobody on a roster is on shift the row says so rather than listing
    people who are asleep.
    """

    def go():
        cards = dict((c["roster"], c) for c in rosterCards())
        mine = set(AlarmDemo.alarms.siteAreas(site))
        rows = []
        for e in system.alarm.queryStatus(
                state=["ActiveUnacked", "ActiveAcked"], provider=["AlarmDemo"]):
            if AlarmDemo.alarms._area(e) not in mine:
                continue
            pri = AlarmDemo.alarms._priorityName(e)
            roster, delay, esc, esc_after = _rule(pri)
            members = cards.get(roster, {}).get("members", [])
            on = [m["name"] for m in members if m["onDuty"]]
            who = ", ".join(on) if on else "NOBODY ON SHIFT"
            disp = str(e.getDisplayPath() or "") or str(e.getSource())
            rows.append([
                disp, pri, roster, who,
                "immediately" if delay == 0 else "after %d min" % delay,
                ("%s after %d min" % (esc, esc_after)) if esc else "-",
                "acknowledged" if e.isAcked() else "waiting",
            ])
        rows.sort(key=lambda r: -AlarmDemo.alarms.PRIORITY_NUM.get(r[1], 0))
        return system.dataset.toDataSet(
            ["Alarm", "Priority", "Roster", "On call now", "When", "Escalates",
             "Status"], rows)

    return _safe(go, system.dataset.toDataSet(
        ["Alarm", "Priority", "Roster", "On call now", "When", "Escalates",
         "Status"], []))
