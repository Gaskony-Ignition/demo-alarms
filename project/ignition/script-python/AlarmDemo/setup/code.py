"""
AlarmDemo.setup - stand the whole demo up on a gateway, from the project.

This is what makes the demo a STANDALONE import. Everything it needs that is
not a project resource - the tag provider, the 122 tags and their 76 alarms,
the alarm journal profile, the journal tables, the shift schedules, the users,
the on-call rosters and thirty days of history - is created from here, by the
project, on the gateway it was imported onto. There is no package to unpack, no
second file to import in the Designer, and no config scan to remember: 8.3's
`system.config` lets a gateway-scope script create the config resources that
used to have to travel as files.

    AlarmDemo.setup.check()           # report on every item, change nothing
    AlarmDemo.setup.run()             # create whatever is missing
    AlarmDemo.setup.fix("tags")       # just one item
    AlarmDemo.setup.run(force=True)   # also reset rosters and shifts to the
                                      # shipped design, discarding edits made
                                      # on the Notifications screen

The Setup screen calls exactly these, one row per item. So does

    curl "http://<gateway>/system/webdev/AlarmDemo/admin?cmd=check"
    curl "http://<gateway>/system/webdev/AlarmDemo/admin?cmd=setup"

SINCE 3.0.0 THERE IS NOTHING IT CANNOT DO. The database connection was the
last exception, and it could not have been otherwise: it needed a host, a user
and a password, and a credential has no business travelling inside a project
export - so it was made by hand in Config -> Databases -> Connections and the
demo was only told its NAME. SQLite removed the question, so the button now
makes the connection too. The name is still a setting (AlarmDemo.config),
because WHICH connection a given gateway should use is not something an export
can know - and because a name a human chose may be a connection other projects
on that gateway read from, which is why nothing here ever alters one.

Every check is independent and none of them stops at the first failure:
"the connection is fine but the tables are missing" and "the connection is
wrong" need different actions and look identical if you only ever see the
first error.
"""

# The datasource, journal tables and tag provider are named ONCE, in
# AlarmDemo.alarms. Copies in this file are how "change the DB constant"
# quietly became a three-file edit that a fresh install gets wrong in one of
# them and then debugs as a blank screen.
DB = AlarmDemo.alarms.DB   # a function - see its docstring
PROVIDER = AlarmDemo.alarms.PROVIDER

LOG = system.util.getLogger("AlarmDemo.setup")

# Derived, never re-listed: AlarmDemo.roster is the design, and a second copy
# of these names here is a rename waiting to be half-done.
SCHEDULES = [s[0] for s in AlarmDemo.roster.SCHEDULES]
ROSTERS = [r[0] for r in AlarmDemo.roster.ROSTERS]

# One tag from each end of the provider. Reading both is how "the tags are
# there" is told apart from "the first area imported and then it failed".
PROBE_TAGS = ["Intake/RawTurbidity", "Plant/DemoScenario"]


# --------------------------------------------------------------------------
# gateway config resources
# --------------------------------------------------------------------------
# The tag provider and the alarm journal profile are gateway CONFIG resources,
# not project resources, so they cannot be in the export. Before 8.3 that made
# them a manual step; `system.config` creates them from here, live, with no
# scan and no restart.
#
# The two config bodies below are the same JSON the resources have on disk at
# data/config/resources/core/ignition/<type>/<name>/config.json - they are kept
# in gateway/ as files too, for anyone who would rather scan them in.

TAG_PROVIDER_CONFIG = {
    "profile": {
        "allowBackfill": False,
        "enableTagReferenceStore": True,
        "type": "STANDARD",
    },
    "settings": {
        "defaultDatasourceName": None,
        "editPermissions": {"securityLevels": [], "type": "AllOf"},
        "readOnly": False,
        "readPermissions": {"securityLevels": [], "type": "AllOf"},
        "valuePersistence": "Database",
        "writePermissions": {"securityLevels": [], "type": "AllOf"},
    },
}


def journalConfig(datasource):
    """The alarm journal profile, pointed at whichever connection is set.

    Ignition's own default table names, not DMC_*: the demo's queries and its
    backfill both write these, and a journal profile pointed somewhere else is
    a screen full of nothing with no error anywhere.
    """
    return {
        "profile": {"queryOnly": False, "type": "DATASOURCE"},
        "settings": {
            "advanced": {
                "dataTableName": AlarmDemo.backfill.DATA_TABLE,
                "tableName": AlarmDemo.alarms.TABLE,
                "useStoreAndForward": True,
            },
            "dataFilters": {"pathFilterName": "", "pathOrSourceFilterName": "",
                            "sourceFilterName": ""},
            "datasource": datasource,
            "eventData": {"dynamicAssociatedData": True, "dynamicConfig": True,
                          "staticAssociatedData": True, "staticConfig": False},
            "events": {"minPriority": "Diagnostic",
                       "storeFromEnabledChange": False,
                       "storeShelvedEvents": True},
            "pruning": {"age": 1, "ageUnits": "YEAR", "enabled": False},
        },
    }


def _resource(typeId, name):
    """A config resource, or None. `getResource` RAISES when it is missing
    rather than returning None, whatever the docs say, and it raises a Java
    throwable that a plain `except Exception` walks straight past."""
    from java.lang import Throwable as JThrowable
    try:
        return system.config.getResource(moduleId="ignition", typeId=typeId,
                                         name=name)
    except (JThrowable, Exception):
        return None


def _config(res):
    """A resource's config as a plain dict.

    getConfig() hands back live wrapper objects; round-tripping through JSON
    is what makes them ordinary Python to compare and to mutate.
    """
    return system.util.jsonDecode(system.util.jsonEncode(res.getConfig()))


def _upsert(typeId, name, config, description):
    """Create the resource, or replace it if it is already there.

    `replace` needs the CURRENT signature - it is optimistic concurrency, and
    without it the call is refused.
    """
    existing = _resource(typeId, name)
    if existing is None:
        system.config.create(moduleId="ignition", typeId=typeId, name=name,
                             config=config, description=description,
                             actor="AlarmDemo.setup")
        return "created"
    system.config.replace(moduleId="ignition", typeId=typeId, name=name,
                          config=config, signature=existing.getSignature(),
                          actor="AlarmDemo.setup")
    return "updated"


# --------------------------------------------------------------------------
# the database connection
# --------------------------------------------------------------------------
# SQLite, in a file beside the gateway, created by the button.
#
# This demo used to want PostgreSQL, and asked for a host, a database, a user
# and a password, because none of those can travel inside a project export.
# That was one honest form on a Setup screen - and a wrong answer to the
# question the demo exists to answer. What it is for is a salesperson opening
# a laptop in front of a customer: install Ignition, import one zip, press one
# button. A database server they have to install first is not a step in that
# story, it is the end of it.
#
# SQLite is what makes the story true, because it needs no server and no
# credential - not because nothing else would connect. An earlier version of
# this comment said a blank 8.3.8 has no PostgreSQL driver, and that is wrong:
# it ships PostgreSQL, MariaDB and MSSQL as JDBC driver MODULES, and a working
# PostgreSQL connection can be made on a gateway built from nothing. What is
# true is narrower and stranger. The three `database-driver` CONFIG RESOURCES a
# blank gateway carries are MySQL, Oracle Database and SQLite - and MySQL and
# Oracle are the two that do NOT work, because user-lib/jdbc is empty and their
# jars are not redistributable. The gateway's own Create Database Connection
# form disables exactly those two, under a "Drivers with Missing Files" banner,
# while offering the three modules that have no resource at all.
#
# So the resource list is a list of definitions, not of capability, and it is
# wrong in both directions. AlarmDemo.config.drivers() reads it, which is fine
# for the one question this file asks it - is SQLite there - and no basis for
# any broader claim. All verified on a container built from nothing,
# 28/08/2026.
#
# So there is no host, no port, no user and no password to ask for, and the
# whole credential apparatus this file used to carry - encrypt(), then
# createEmbeddedSecretConfig(), and a comment explaining why both - is gone
# with them. The connection is a file path, and the file is the gateway's own
# data directory, which is where a gateway's own state already lives and is
# what a gateway backup already carries.

# `${data}` is expanded by Ignition, not by us - the SQLite driver's own URL
# instructions name it, and it resolves to the gateway's data directory on
# every platform, so the same string is right on Windows, on Linux and in the
# container image.
DB_FILE = "alarm-demo.db"

# journal_mode=WAL is not a tuning knob here, it is what makes the demo work
# at all: the plant simulation writes journal rows from a gateway timer while
# a Perspective session reads them for the analytics, and rollback-journal
# SQLite blocks the readers for the length of every write. WAL lets them run
# together. busy_timeout then covers the one case WAL does not - two writers,
# the timer and the history backfill - by waiting rather than failing.
DB_URL = ("jdbc:sqlite:${data}/%s?journal_mode=WAL&busy_timeout=30000"
          % DB_FILE)

# `driver` names a database-driver resource; `translator` names a stock
# database-translator. Both ship with Ignition.
DB_DRIVER = "SQLite"
DB_TRANSLATOR = "SQLITE"

# The pool and timeout settings are Ignition's own defaults for a new
# connection, read off one the gateway made itself - not tuned here, with one
# exception. A demo has no business inventing a connection pool.
#
# The exception is poolMaxActive, 8 -> 4. Eight pooled connections onto one
# SQLite file is eight processes contending for one write lock; four is enough
# for the sim, the journal and a couple of sessions, and halves the contention
# WAL and busy_timeout then have to absorb.
DB_DEFAULTS = {
    "connectionProps": "",
    "connectionResetParams": "",
    "defaultTransactionLevel": "DEFAULT",
    "evictionRate": -1,
    "evictionTests": 3,
    "evictionTime": 1800000,
    "failoverMode": "STANDARD",
    "failoverProfile": "",
    "includeSchemaInTableName": False,
    "poolInitSize": 0,
    "poolMaxActive": 4,
    "poolMaxIdle": 8,
    "poolMaxWait": 5000,
    "poolMinIdle": 0,
    "slowQueryLogThreshold": 60000,
    "testOnBorrow": True,
    "testOnReturn": False,
    "testWhileIdle": False,
    "validationQuery": "SELECT 1",
    "validationSleepTime": 10000,
}


def databaseDefaults():
    """What the Setup screen shows about the connection it would make.

    Not a form any more - there is nothing to fill in - so this is what the
    row says before the button is pressed.
    """
    return {"name": AlarmDemo.config.DEFAULT_DB,
            "driver": DB_DRIVER,
            "file": u"<gateway data directory>/%s" % DB_FILE}


def createDatabase(name=None):
    """Create the demo's SQLite connection and point the demo at it.

    Takes a name and nothing else: there is no server to reach, no credential
    to hold, and the file is made by the driver on first use if it is not
    there. Returns a one-line account, or raises with something readable.

    It will NOT overwrite a connection that already exists under that name. A
    gateway running this demo may be running other things too, and quietly
    replacing someone else's connection is not a thing a demo gets to do.
    """
    name = (name or AlarmDemo.config.DEFAULT_DB).strip()
    if not name:
        raise ValueError("give the connection a name")
    if _resource("database-connection", name) is not None:
        raise ValueError(
            "a connection called '%s' already exists on this gateway - this "
            "will not overwrite it. Either use it as it is, or make the demo "
            "a connection under a different name." % name)

    have = AlarmDemo.config.drivers()
    if DB_DRIVER not in have:
        raise ValueError(
            "this gateway has no '%s' JDBC driver (it has: %s). SQLite ships "
            "with Ignition, so a gateway without it has had it removed."
            % (DB_DRIVER, ", ".join(have) if have else "none"))

    config = dict(DB_DEFAULTS)
    config.update({
        "connectURL": DB_URL,
        "driver": DB_DRIVER,
        "translator": DB_TRANSLATOR,
        "username": "",
        "password": None,
    })
    system.config.create(moduleId="ignition", typeId="database-connection",
                         name=name, config=config,
                         description="Created by the ACME Alarm Demo's Setup "
                                     "screen",
                         actor="AlarmDemo.setup")
    AlarmDemo.config.save(name)
    LOG.info("created SQLite connection '%s' at %s" % (name, DB_URL))

    # Creating the RESOURCE and having a live, pooled CONNECTION are not the
    # same moment. The resource registers straight away; the pool then has to
    # start and open the file, and until it does a query against the name
    # fails. Returning immediately meant the page could say "created" on one
    # line and "did not answer" on the next, about the same connection, in the
    # same second - which reads as a create that did not work.
    from java.lang import Thread as JThread
    for _attempt in range(15):
        ok, _detail = _database()
        if ok:
            return u"connection '%s' created and the demo pointed at it" % name
        JThread.sleep(1000)
    return (u"connection '%s' was created and the demo is pointed at it, but "
            u"it is not answering yet - check the row below in a moment" % name)


# --------------------------------------------------------------------------
# the items
# --------------------------------------------------------------------------
# Each item is (key, title, check, fix, why). `check` returns (ok, detail);
# `fix` returns a one-line account of what it did, or raises. A fix of None
# means the item cannot be created from a project - since 3.0.0 there are
# none: the database connection was the last one, and SQLite is what let it
# have a fix like everything else.


def _driverOf(name):
    """The JDBC driver a connection is configured with, or None if there is no
    such connection or its config cannot be read."""
    res = _resource("database-connection", name)
    if res is None:
        return None
    from java.lang import Throwable as JThrowable
    try:
        return _config(res).get("driver")
    except (JThrowable, Exception):
        return None


def _database():
    name = DB()
    try:
        system.db.runScalarQuery("SELECT 1", name)
    except:
        have = AlarmDemo.config.connections()
        return False, (u"connection '%s' did not answer. This gateway has: %s"
                       % (name, u", ".join(have) if have else u"(none)"))

    # Answering is not the same as being usable, and the gap between them is
    # invisible on every other screen. A gateway upgraded in place from 2.0.0
    # still points at the PostgreSQL connection 2.0.0 told it to make by hand.
    # `SELECT 1` succeeds against it, so this row would go green - and every
    # analytic would return nothing, because 3.0.0 changed the SQL underneath
    # to SQLite's dialect: strftime() for the date arithmetic, epoch millis
    # held as TEXT in eventtime, no split_part and no generate_series. Those
    # queries do not fail on PostgreSQL, they come back empty. Green
    # connection, empty charts, and nothing on screen joining the two.
    #
    # The Setup row shows this on one ellipsised line, so the diagnosis has to
    # be complete in the first clause - "answered, but it is a PostgreSQL
    # connection" truncates to "answered, but it is a PostgreSQL c...", which
    # reads as a complaint about nothing. What the button does about it is the
    # button's business, and _databaseFix says so when it runs.
    driver = _driverOf(name)
    if driver is not None and driver != DB_DRIVER:
        return False, (u"'%s' is a %s connection, not %s - this demo's queries "
                       u"return nothing against it rather than failing"
                       % (name, driver, DB_DRIVER))
    return True, u"connection '%s' answered" % name


def _databaseFix():
    """Make the demo's SQLite connection.

    This item had no fix at all until 3.0.0, and could not have had one: the
    connection needed a host, a user and a password, and a project cannot
    carry any of them. That is the whole reason it was the one row on the
    Setup screen with a form instead of a button, and the reason "Set up this
    gateway" did not actually set up the gateway - it created eight of the
    nine things and left the ninth to a human.

    SQLite removes the question, so the button can answer it.

    It never repairs a connection that already exists. The demo's connection
    NAME is a setting a human may have pointed at a connection other projects
    read from, so rewriting it is not this project's call - and a repair path
    has no business being more invasive than the create path it repairs, which
    refuses to overwrite at all. When the configured connection is the wrong
    engine, the fix is a new SQLite connection under a free name and a change
    to this demo's own setting; the other connection is not touched.
    """
    name = DB()
    driver = _driverOf(name)
    if driver is None or driver == DB_DRIVER:
        # Absent (make it) or already SQLite (createDatabase says so, and
        # refuses) - either way the existing path is the right one.
        return createDatabase(name)

    for candidate in [AlarmDemo.config.DEFAULT_DB,
                      AlarmDemo.config.DEFAULT_DB + u"_SQLite"]:
        if candidate == name:
            continue
        if _resource("database-connection", candidate) is not None:
            continue
        made = createDatabase(candidate)
        return (u"'%s' is a %s connection and was left untouched; %s"
                % (name, driver, made))

    raise ValueError(
        u"'%s' is a %s connection, which this demo will not alter, but the "
        u"names it would use instead are both taken on this gateway. Make a "
        u"SQLite connection under a free name and set it on this page."
        % (name, driver))


def _tagProviderCheck():
    if _resource("tag-provider", PROVIDER) is None:
        return False, u"tag provider '%s' does not exist" % PROVIDER
    return True, u"tag provider '%s' exists" % PROVIDER


def _tagProviderFix():
    what = _upsert("tag-provider", PROVIDER, TAG_PROVIDER_CONFIG,
                   "Alarm demo plant tag provider - areas live at the "
                   "provider root")
    return u"tag provider '%s' %s" % (PROVIDER, what)


def _tagsCheck():
    paths = [u"[%s]%s" % (PROVIDER, p) for p in PROBE_TAGS]
    try:
        qvs = system.tag.readBlocking(paths)
    except:
        return False, u"the tag provider did not answer"
    bad = [p for p, q in zip(PROBE_TAGS, qvs) if not q.quality.isGood()]
    if bad:
        return False, u"missing or bad: %s" % u", ".join(bad)
    n = len(AlarmDemo.tagdata.tags())
    return True, u"%d areas readable in [%s]" % (n, PROVIDER)


def _tagsFix():
    """Write the demo's tags into the provider.

    `collisionPolicy="o"` - overwrite. The tags are generated and the project
    is their only source, so a rerun should put the gateway back to the shipped
    design rather than merge with whatever is there. Tag VALUES are simulated
    every second anyway, so nothing of anyone's is lost.
    """
    from java.lang import Thread as JThread
    areas = AlarmDemo.tagdata.tags()
    # A provider created seconds ago is registered but not necessarily
    # accepting writes yet, and the failure is a bare exception rather than
    # anything that says "try again". Three goes over three seconds; the first
    # one succeeds on a provider that was already there.
    last = None
    for attempt in range(3):
        try:
            system.tag.configure(u"[%s]" % PROVIDER, areas, u"o")
            return u"wrote %d areas into [%s]" % (len(areas), PROVIDER)
        except:
            import traceback
            last = traceback.format_exc().strip().split("\n")[-1]
            JThread.sleep(1500)
    raise Exception(u"could not write tags into [%s]: %s" % (PROVIDER, last))


def _journalTablesCheck():
    """The tables exist and are readable. Counts this demo's rows, not
    everybody's - see _historyCheck for why that distinction earns its keep."""
    try:
        n = AlarmDemo.backfill.count()
        return True, u"%s is readable on '%s' - %d rows are this demo's" % (
            AlarmDemo.alarms.TABLE, DB(), n)
    except:
        return False, u"%s is not readable on '%s'" % (AlarmDemo.alarms.TABLE,
                                                       DB())


def _journalTablesFix():
    AlarmDemo.backfill.ensureSchema()
    return u"%s and %s created on '%s'" % (AlarmDemo.alarms.TABLE,
                                           AlarmDemo.backfill.DATA_TABLE, DB())


def _journalProfileCheck():
    """Prove the PROFILE exists and points at this demo's tables.

    This is the check that separates the two ways a journal looks empty. The
    backfill writes straight into the tables, so the item above can report
    thousands of rows while every journal screen is blank - which is what a
    missing or misdirected profile looks like, and it reports no error
    anywhere.
    """
    res = _resource("alarm-journal", PROVIDER)
    if res is None:
        return False, u"alarm journal profile '%s' does not exist" % PROVIDER
    try:
        ds = _config(res)["settings"]["datasource"]
    except:
        ds = None
    if ds != DB():
        return False, (u"profile '%s' writes to '%s', not '%s'"
                       % (PROVIDER, ds, DB()))
    return True, u"profile '%s' writes to '%s'" % (PROVIDER, DB())


def _journalProfileFix():
    what = _upsert("alarm-journal", PROVIDER, journalConfig(DB()),
                   "Alarm demo journal - datasource profile writing the "
                   "standard alarm_events / alarm_event_data tables")
    return u"alarm journal profile '%s' %s, pointed at '%s'" % (PROVIDER, what,
                                                                DB())


def _schedulesCheck():
    have = [unicode(n) for n in system.user.getScheduleNames()]
    missing = [w for w in SCHEDULES if w not in have]
    if missing:
        return False, u"missing: %s" % u", ".join(missing)
    return True, u", ".join(SCHEDULES)


ALARM_NOTIFICATION_MISSING = (
    u"the Alarm Notification module is not installed on this gateway - "
    u"on-call rosters are part of it, and so are the Notifications screen's "
    u"routing and the People screen's on-call column. Everything else in this "
    u"demo works without it.")


def _hasAlarmNotification():
    """Is the Alarm Notification module on this gateway?

    Asked of the CONFIG RESOURCE TYPE rather than of system.alarm, for two
    reasons. `roster-config` is registered by that module, so its presence is
    the same question; and `system.alarm.getRosters` is missing rather than
    failing on a gateway without it, so calling it produces an AttributeError
    that reads like a bug in this project.

    It is worth naming: on a gateway with the module absent, every other row
    on the Setup screen goes green and this one reported
    "ValueError: Resource type not found: ignition/roster-config", which says
    nothing about what to do.
    """
    from java.lang import Throwable as JThrowable
    try:
        for module, typeId in system.config.getResourceTypes():
            if unicode(module) == u"ignition" and unicode(typeId) == u"roster-config":
                return True
    except (JThrowable, Exception):
        pass
    return False


def _rostersCheck():
    """Read the roster CONFIG RESOURCES, not system.alarm.getRosters().

    getRosters() belongs to the Alarm Notification module, and on a gateway
    that has the module it returns roster NAMES with an empty user list for
    every roster - so it cannot answer this question either way. The config
    resources are what AlarmDemo.roster creates and edits, so they are what
    this row asks about.
    """
    if not _hasAlarmNotification():
        return False, ALARM_NOTIFICATION_MISSING
    have = [unicode(r.getName()) for r in
            system.config.getResources(moduleId="ignition",
                                       typeId="roster-config")]
    missing = [w for w in ROSTERS if w not in have]
    if missing:
        return False, u"missing: %s" % u", ".join(missing)
    return True, u", ".join(ROSTERS)


def _usersCheck():
    known = set()
    for u in system.user.getUsers(AlarmDemo.roster.USER_SOURCE):
        known.add(unicode(u.get("username")).lower())
    want = [p[0] for p in AlarmDemo.roster.PEOPLE]
    missing = [w for w in want if w.lower() not in known]
    if missing:
        return False, u"missing: %s" % u", ".join(missing)
    return True, u"%d people in the '%s' user source" % (
        len(want), AlarmDemo.roster.USER_SOURCE)


def _peopleFix(force=False):
    """Schedules, people and rosters - one call, because they are one design.

    Reports what it could not do rather than throwing: on a gateway without
    Alarm Notification the schedules and the people are still created and only
    the rosters cannot be, and a run that creates six of seven things should
    say so rather than look like a failure.
    """
    if not _hasAlarmNotification():
        AlarmDemo.roster.ensureSchedules()
        AlarmDemo.roster.ensureUsers()
        AlarmDemo.roster.applyDefaultSchedules()
        return (u"shift schedules and people created; rosters skipped - %s"
                % ALARM_NOTIFICATION_MISSING)
    result = AlarmDemo.roster.setup(force)
    users = result.get("users")
    if isinstance(users, dict) and users.get("refused"):
        return (u"shift schedules and on-call rosters created; these people "
                u"were refused by the gateway: %s"
                % u"; ".join(users["refused"]))
    return u"shift schedules, people and on-call rosters created"


def _historyCheck():
    """Read THIS DEMO'S history back THROUGH the profile.

    Two things have to be true and they are different questions. Rows in the
    table prove the backfill ran; rows read back through the profile prove the
    journal SCREENS will have something to show. Only the second is worth a
    row on this page.

    `source` is not optional. Without it the query counts every event in the
    journal, and `alarm_events` is Ignition's default table name - so on a
    gateway where another project already journals to it, this reported
    "86,687 events in the last 30 days" and went green on a gateway where this
    demo's backfill had never run at all. Every event this demo produces has a
    source under its own provider, which is what makes the filter exact.
    """
    end = system.date.now()
    events = system.alarm.queryJournal(
        journalName=PROVIDER,
        source=[u"prov:%s:*" % PROVIDER],
        startDate=system.date.addDays(end, -30), endDate=end)
    n = len(list(events))
    if n < 100:
        return False, u"%d of this demo's events in the last 30 days" % n
    return True, u"%d of this demo's events in the last 30 days" % n


def _historyFix():
    n = AlarmDemo.backfill.run(days=30, perDay=85)
    return u"%d journal rows written" % n


ITEMS = [
    ("database", "Database connection", _database, _databaseFix,
     "The analytics and the journal history are SQL. SQLite, in a file beside "
     "the gateway - press Create it and there is nothing to fill in, or name "
     "a connection this gateway already has."),
    ("tagProvider", "Tag provider", _tagProviderCheck, _tagProviderFix,
     "A standard provider named AlarmDemo, created live through "
     "system.config."),
    ("tags", "Plant tags", _tagsCheck, _tagsFix,
     "122 tags and 76 alarm definitions across nine areas, written into the "
     "provider from the copy the project carries."),
    ("journalTables", "Journal tables", _journalTablesCheck,
     _journalTablesFix,
     "alarm_events and alarm_event_data. Ignition creates them on the first "
     "journalled event; the history backfill inserts straight into them, so "
     "on a fresh gateway they have to exist first."),
    ("journalProfile", "Alarm journal profile", _journalProfileCheck,
     _journalProfileFix,
     "The profile every journal screen reads through. Without it the tables "
     "fill up and the screens stay empty."),
    ("schedules", "Shift schedules", _schedulesCheck, _peopleFix,
     "Day, Afternoon and Night - real Ignition schedules, not a table of "
     "shift names."),
    ("users", "People", _usersCheck, _peopleFix,
     "Seven users in the gateway's own user source, with email and mobile."),
    ("rosters", "On-call rosters", _rostersCheck, _peopleFix,
     "Operations, Maintenance and Management - real Ignition on-call "
     "rosters, which is what the Notifications screen edits."),
    ("history", "30 days of history", _historyCheck, _historyFix,
     "So every analytic has something to say from the first minute rather "
     "than after a week of running."),
]

FIXABLE = [k for k, _t, _c, f, _w in ITEMS if f is not None]


# --------------------------------------------------------------------------
# the API the screen and the HTTP endpoint use
# --------------------------------------------------------------------------

# The three items that cannot answer anything useful until the database
# connection does. Their real failures - "no such table", "profile points
# somewhere else" - are worth reading; what a missing CONNECTION gets out of
# them is a Java NullPointerException about a datasource, three times over,
# which buries the one row that actually needs attention.
NEEDS_DATABASE = ("journalTables", "journalProfile", "history")


def check():
    """Every item's state, in install order. Changes nothing.

    Returns {"items": [...], "ok": bool, "version": str, "db": {...}} where
    each item is {key, title, ok, detail, fixable, why}. One row of the Setup
    screen per item.
    """
    items = []
    dbOk = None
    for key, title, checkFn, fixFn, why in ITEMS:
        if key in NEEDS_DATABASE and dbOk is False:
            ok, detail = False, u"waiting for the database connection above"
        else:
            try:
                ok, detail = checkFn()
            except:
                import traceback
                ok, detail = False, traceback.format_exc().strip().split("\n")[-1]
                LOG.warn("check %s failed: %s" % (key, traceback.format_exc()))
        if key == "database":
            dbOk = bool(ok)
        items.append({"key": key, "title": title, "ok": bool(ok),
                      "detail": detail, "fixable": fixFn is not None,
                      "why": why})
    return {
        "items": items,
        "ok": all(i["ok"] for i in items),
        "version": AlarmDemo.alarms.VERSION,
        "db": AlarmDemo.config.describe(),
    }


def fix(key, force=False):
    """Create one item. Returns a one-line account, or raises."""
    for k, _title, _checkFn, fixFn, _why in ITEMS:
        if k != key:
            continue
        if fixFn is None:
            raise ValueError("%s cannot be created from the project" % key)
        if fixFn is _peopleFix:
            return fixFn(force)
        return fixFn()
    raise ValueError("no such setup item: %s" % key)


def run(force=False, history=True):
    """Create everything that is missing, in order, and report.

    Safe to run twice: every fix is an upsert. `force` also resets the rosters
    and shift schedules to the shipped design, discarding edits made on the
    Notifications screen.

    Ordered as the dependencies run, not as the list reads: the provider
    before the tags that go in it, the connection's tables before the profile
    that writes them, and the history last because it needs all three.
    """
    done, failed = [], []
    dbOk = _database()[0]
    for key, _title, checkFn, fixFn, _why in ITEMS:
        if fixFn is None:
            continue
        # Re-ask after the database item has had its turn. `dbOk` is read once
        # before the loop so that three dependent items can fail with one
        # sentence between them rather than three NullPointerExceptions - but
        # since 3.0.0 the connection is itself something this loop creates, so
        # the answer it was read from is out of date by the time those three
        # are reached.
        if key == "journalTables" and not dbOk:
            dbOk = _database()[0]
        if key in NEEDS_DATABASE and not dbOk:
            # Three failures that all say the same thing, and none of them the
            # thing to do about it. Say it once.
            failed.append(u"%s: needs a working database connection first"
                          % key)
            continue
        try:
            ok, _detail = checkFn()
        except:
            ok = False
        if ok and not (force and fixFn is _peopleFix):
            continue
        try:
            # Three items - schedules, people, rosters - share one fix, so a
            # run that creates all three used to report the same sentence
            # three times in a row on the Setup screen.
            said = fix(key, force)
            if said not in done:
                done.append(said)
        except:
            import traceback
            failed.append("%s: %s"
                          % (key, traceback.format_exc().strip().split("\n")[-1]))
            LOG.warn("setup step %s failed: %s" % (key, traceback.format_exc()))

    state = check()
    state["changed"] = done
    if failed:
        state["errors"] = failed
    LOG.info("setup run: %d changed, %d failed, ok=%s"
             % (len(done), len(failed), state["ok"]))
    return state
