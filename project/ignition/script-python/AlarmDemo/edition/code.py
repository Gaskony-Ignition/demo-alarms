"""AlarmDemo.edition - standard or Edge, and whether a database is available.

Edge has no database, so SQL analytics have a journal-reading twin (AlarmDemo.journalq).
Nothing here raises; an unanswered question counts as "no database".
"""

LOG = system.util.getLogger("AlarmDemo.edition")

# Cached: view bindings call these on a timer, and the answers cannot change
# while the gateway runs.
_CACHE = {}


def _hasResourceType(module, typeId):
	"""Is a config resource type registered on this gateway?"""
	# Throwable too: a Java error is not an Exception in Jython.
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
	"""Is this an Ignition Edge gateway?"""
	# 'edge-sync-settings' is the one type only Edge registers;
	# 'edge-system-properties' also exists on standard.
	return _hasResourceType("ignition", "edge-sync-settings")


def hasDatabase():
	"""Can this gateway hold a database connection at all (not whether one is configured)?"""
	return _hasResourceType("ignition", "database-connection")


def journalName():
	"""Return the name of the alarm journal this gateway keeps history in.

	Edge allows only one journal, which the platform creates, so that one is used.
	"""
	# A journal table bound to a missing profile shows empty history with no error.
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
