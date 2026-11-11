"""
AlarmDemo.config - which database connection the demo uses (default "AlarmDemoDB").
The name is a gateway setting in a file beside the data directory, not in the
project, so a project import never overwrites it and an export never carries it.
"""

import json
import traceback

from java.lang import System as JSystem
from java.nio.file import Files, Paths

DEFAULT_DB = "AlarmDemoDB"
SETTINGS_FILE_NAME = "alarm-demo-settings.json"

LOG = system.util.getLogger("AlarmDemo.config")


def installDir():
	"""The gateway's installation directory."""
	# The gateway runs with its install directory as the working directory; no
	# scripting function returns it, so read user.dir.
	return JSystem.getProperty("user.dir")


def dataDir():
	"""The gateway's data directory."""
	return installDir() + "/data"


def settingsPath():
	"""Full path of the settings override file."""
	return dataDir() + "/" + SETTINGS_FILE_NAME


# Cached because db() runs on every query. Keyed on last-modified time (0 when
# absent) so editing or deleting the file is seen on the next read.
_cache = {"stamp": None, "values": {}}


def _stamp():
	try:
		path = Paths.get(settingsPath())
		if not Files.exists(path):
			return 0
		return Files.getLastModifiedTime(path).toMillis()
	except:
		return -1


def _read():
	path = Paths.get(settingsPath())
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
	"""Write the override file and return its path. Pass "" to use the default."""
	# Staged then renamed, so a reader never sees a half-written file.
	from java.lang import String as JString
	from java.nio.charset import StandardCharsets
	from java.nio.file import StandardCopyOption

	payload = {}
	if (dbName or "").strip():
		payload["db"] = dbName.strip()

	target = Paths.get(settingsPath())
	staged = Paths.get(settingsPath() + ".tmp")
	text = json.dumps(payload, indent=2) + "\n"
	# getBytes(), not the string: Files.write given a Jython string picks the
	# Iterable<CharSequence> overload and writes one character per line.
	Files.write(staged, JString(text).getBytes(StandardCharsets.UTF_8))
	Files.move(staged, target, [StandardCopyOption.REPLACE_EXISTING])

	reload()
	LOG.info("settings written to %s: %s" % (settingsPath(), payload))
	return settingsPath()


def db():
	"""The name of the database connection this demo reads and writes."""
	return settings().get("db", DEFAULT_DB)


def connections():
	"""Names of the database connections this gateway has, sorted."""
	# Read from config resources: system.db.getConnections() returns a dataset
	# whose rows print as "<Row:10 columns>".
	from java.lang import Throwable as JThrowable
	try:
		return sorted([unicode(r.getName()) for r in
					   system.config.getResources(moduleId="ignition",
												  typeId="database-connection")])
	except (JThrowable, Exception) as e:
		LOG.warn("could not list database connections: %s" % e)
		return []


def drivers():
	"""Names of the JDBC driver config resources, sorted."""
	# Not the list of drivers that work: MySQL and Oracle resources exist
	# without a jar, and driver modules (PostgreSQL, MariaDB, MSSQL) are absent.
	# Reliable only for "is SQLite registered".
	from java.lang import Throwable as JThrowable
	try:
		return sorted([unicode(r.getName()) for r in
					   system.config.getResources(moduleId="ignition",
												  typeId="database-driver")])
	except (JThrowable, Exception) as e:
		LOG.warn("could not list database drivers: %s" % e)
		return []


def describe():
	"""The db setting and where it came from, for the Setup page."""
	over = settings()
	return {
		"db": db(),
		"dbSource": "settings file" if "db" in over else "default",
		"settingsPath": settingsPath(),
		"settingsPresent": "db" in over,
	}
