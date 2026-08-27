"""
AlarmDemo.config - the one thing about this demo that belongs to the GATEWAY
rather than to the project: which database connection it uses.

Everything else the demo needs it can create for itself (see AlarmDemo.setup).
A database CONNECTION it cannot: creating one needs credentials, and a
credential has no business travelling inside a project export. So the name of
the connection is a setting, and it is stored OUTSIDE the project - beside the
gateway's data directory, not inside it - for two reasons:

  * importing a new version of the demo never overwrites the target gateway's
    setting, and
  * the setting never travels inside an export zip, so a demo exported from
    here cannot arrive somewhere else pointing at this rig's connection.

The default is "ignition", the connection name a stock Ignition install
already has. On a gateway that names it something else, the Setup page writes
the override; nothing here needs a script editor.

Same shape as Order Intake's `Orders.Config`, deliberately - two projects
solving the identical problem should not each invent their own answer.
"""

import json
import traceback

from java.lang import System as JSystem
from java.nio.file import Files, Paths

DEFAULT_DB = "ignition"
SETTINGS_FILE_NAME = "alarm-demo-settings.json"

LOG = system.util.getLogger("AlarmDemo.config")


def install_dir():
    """The gateway's installation directory.

    The gateway process runs with its install directory as the working
    directory on every platform and in the official container image (verified
    8.3.8: /usr/local/bin/ignition). No scripting function returns it, so this
    is the portable way to ask.
    """
    return JSystem.getProperty("user.dir")


def data_dir():
    return install_dir() + "/data"


def settings_path():
    return data_dir() + "/" + SETTINGS_FILE_NAME


# --------------------------------------------------------------------------
# the override file
# --------------------------------------------------------------------------
# Cached, because db() is called on the path of every query on every screen.
# The cache key is the file's last-modified time (0 for "absent"), so editing
# or deleting the file under a running gateway is picked up on the next read -
# a boolean "have I loaded it" would leave a deleted file in force forever.
_cache = {"stamp": None, "values": {}}


def _stamp():
    try:
        path = Paths.get(settings_path())
        if not Files.exists(path):
            return 0
        return Files.getLastModifiedTime(path).toMillis()
    except:
        return -1


def _read():
    path = Paths.get(settings_path())
    if not Files.exists(path):
        return {}
    try:
        from java.lang import String as JString
        from java.nio.charset import StandardCharsets
        raw = unicode(JString(Files.readAllBytes(path), StandardCharsets.UTF_8))
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except:
        LOG.warn("could not read %s, using defaults: %s"
                 % (SETTINGS_FILE_NAME, traceback.format_exc()))
        return {}


def settings():
    """The override file's contents as a dict, or {} if it is absent."""
    stamp = _stamp()
    if _cache["stamp"] != stamp:
        _cache["values"] = _read()
        _cache["stamp"] = stamp
    return _cache["values"]


def reload():
    """Force a re-read on the next call, whatever the timestamp says."""
    _cache["stamp"] = None
    return settings()


def save(dbName):
    """Write the override file. Pass "" to go back to the default.

    Staged then renamed, so a reader can never see a half-written file.
    """
    from java.lang import String as JString
    from java.nio.charset import StandardCharsets
    from java.nio.file import StandardCopyOption

    payload = {}
    if (dbName or "").strip():
        payload["db"] = dbName.strip()

    target = Paths.get(settings_path())
    staged = Paths.get(settings_path() + ".tmp")
    text = json.dumps(payload, indent=2) + "\n"
    # getBytes(), not the string: Files.write given a Jython string picks the
    # Iterable<CharSequence> overload and writes one character per line.
    Files.write(staged, JString(text).getBytes(StandardCharsets.UTF_8))
    Files.move(staged, target, [StandardCopyOption.REPLACE_EXISTING])

    reload()
    LOG.info("settings written to %s: %s" % (settings_path(), payload))
    return settings_path()


def db():
    """The name of the database connection this demo reads and writes."""
    return settings().get("db", DEFAULT_DB)


def connections():
    """Every database connection this gateway has, by name.

    Shown by the Setup page when the configured one does not answer: "which
    connections DO exist" is almost always the answer, and it is invisible
    from inside the project otherwise.

    Read from the CONFIG RESOURCES rather than system.db.getConnections(),
    which returns a ten-column dataset - iterating it yields Row objects, so
    the message read "This gateway has: <Row:10 columns>, <Row:10 columns>",
    which is worse than saying nothing.
    """
    from java.lang import Throwable as JThrowable
    try:
        return sorted([unicode(r.getName()) for r in
                       system.config.getResources(moduleId="ignition",
                                                  typeId="database-connection")])
    except (JThrowable, Exception) as e:
        LOG.warn("could not list database connections: %s" % e)
        return []


def drivers():
    """The JDBC drivers this gateway has, by name.

    A driver is a config resource registered by a JDBC driver module; the
    name is what a connection's `driver` field has to match. Listed so that
    "PostgreSQL" not being one of them is a sentence rather than a stack
    trace.
    """
    from java.lang import Throwable as JThrowable
    try:
        return sorted([unicode(r.getName()) for r in
                       system.config.getResources(moduleId="ignition",
                                                  typeId="database-driver")])
    except (JThrowable, Exception) as e:
        LOG.warn("could not list database drivers: %s" % e)
        return []


def describe():
    """What the Setup page shows: the value AND where it came from, so "why is
    it pointing there" is answerable without reading code."""
    over = settings()
    return {
        "db": db(),
        "dbSource": "settings file" if "db" in over else "default",
        "settingsPath": settings_path(),
        "settingsPresent": "db" in over,
    }
