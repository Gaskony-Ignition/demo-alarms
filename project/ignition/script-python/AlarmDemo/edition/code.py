"""
AlarmDemo.edition - what this gateway can actually do.

The demo ships in two builds, standard and Edge, and the difference between
them is not cosmetic: Ignition Edge has no database connectivity at all - no
SQL Bridge, no JDBC driver modules, no SQL historian. Measured on 8.3.8 by
listing the modules a running Edge gateway loads:

    Perspective, OPC-UA + drivers, Historian, Alarm Notification, WebDev,
    Vision, Symbol Factory, EAM

So `system.db.*` is not a slow path on Edge, it is an absent one, and every
analytic in this demo that was a SQL query has a second implementation that
reads the alarm journal through `system.alarm.queryJournal` instead. This
module is the single place that decides which one runs.

Nothing here raises. A gateway that will not answer a capability question is
treated as the smaller of the two - "no database" - because that path works
everywhere and the other one does not.
"""

LOG = system.util.getLogger("AlarmDemo.edition")

# Answers are cached for the life of the module. The edition of a gateway and
# the modules it loads cannot change while it is running, and these are read
# from view bindings that re-evaluate on a timer - an uncached answer is a
# getResourceTypes() call per chart per refresh. A project scan reloads this
# module, which is the only event that could make an answer stale.
_CACHE = {}


def _hasResourceType(module, typeId):
    """Is a config resource type registered on this gateway?

    The structural question, asked of `system.config.getResourceTypes()`.
    Catching java.lang.Throwable as well as Exception is deliberate: a Java
    error raised inside a system call is not an Exception in Jython and would
    escape an `except Exception` untouched.
    """
    from java.lang import Throwable as JThrowable
    key = (module, typeId)
    if key in _CACHE:
        return _CACHE[key]
    try:
        answer = key in system.config.getResourceTypes()
    except (JThrowable, Exception):
        LOG.warn("could not read the gateway's resource types - "
                 "assuming '%s' is absent" % typeId)
        answer = False
    _CACHE[key] = answer
    return answer


def isEdge():
    """Is this an Ignition Edge gateway?

    Asked of the ONE type only Edge registers: ('ignition',
    'edge-sync-settings').

    It is NOT 'edge-system-properties' - a standard gateway registers that too,
    so a detector built on it fires everywhere and every Edge branch runs on
    standard. That mistake cost the machine HMI demo a release on 09/09/2026.
    Measured the same day by diffing both editions on 8.3.8: 60 registered
    types on standard, 55 on Edge, and exactly one of them Edge-only.
    """
    return _hasResourceType("ignition", "edge-sync-settings")


def hasDatabase():
    """Can this gateway hold a database connection at all?

    'database-connection' is one of the six types that exist on standard and
    not on Edge. This is a question about the PLATFORM, not about whether a
    connection has been configured - AlarmDemo.config answers that one.
    """
    return _hasResourceType("ignition", "database-connection")


def journalName():
    """The alarm journal this gateway actually keeps history in.

    Everywhere but Edge it is the demo's own profile, named for the demo.
    Edge permits exactly one and the platform makes it (EdgeJournal, unless a
    site renamed it) - creating a second is refused with
    UnsupportedOperationException, so the demo adopts what is there.

    Every journal screen binds to this rather than to a constant. A journal
    table pointed at a profile that does not exist shows an empty history and
    reports no error, which is indistinguishable from a quiet plant.
    """
    from java.lang import Throwable as JThrowable
    mine = AlarmDemo.alarms.PROVIDER
    if not isEdge():
        return mine
    try:
        have = sorted([unicode(r.getName()) for r in
                       system.config.getResources(moduleId="ignition",
                                                  typeId="alarm-journal")])
    except (JThrowable, Exception):
        have = []
    if mine in have:
        return mine
    return have[0] if have else mine


def describe():
    """One line for the Setup screen's header, and for ?cmd=version."""
    if isEdge():
        return (u"Ignition Edge - no database on this edition, so the "
                u"analytics read the alarm journal directly")
    if not hasDatabase():
        return (u"this gateway has no database module - the analytics read "
                u"the alarm journal directly")
    return u"standard Ignition - the analytics are SQL over the journal tables"
