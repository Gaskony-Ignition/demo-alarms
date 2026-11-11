"""
AlarmDemo.setup - stand the demo up on a gateway from the project itself.
Creates the tag provider, tags, SQLite connection, journal profile and tables,
schedules, users, rosters and history. check() reports; run() creates.
"""

# DB and PROVIDER are defined once, in AlarmDemo.alarms.
DB = AlarmDemo.alarms.db   # a function: call DB() for the connection name
PROVIDER = AlarmDemo.alarms.PROVIDER

LOG = system.util.getLogger("AlarmDemo.setup")

# Derived from AlarmDemo.roster, which owns the names.
SCHEDULES = [s[0] for s in AlarmDemo.roster.SCHEDULES]
ROSTERS = [r[0] for r in AlarmDemo.roster.ROSTERS]

# Both ends of the plant tree and the Live folder: a gateway set up before the
# Live tags existed reads as missing here, so Setup offers to write them.
PROBE_TAGS = ["Intake/RawTurbidity", "Plant/DemoScenario", "Live/Duty"]


# The tag provider and alarm journal profile are gateway config resources, so
# they are not in the project export; system.config creates them live. The
# bodies below match the on-disk config.json and are kept only here.

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
	"""The alarm journal profile config, writing to the given datasource."""
	# Ignition's default table names: a profile pointed at other tables leaves
	# the journal screens empty with no error.
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
	"""A config resource, or None."""
	# getResource raises a Java throwable when the resource is missing; a plain
	# `except Exception` does not catch it.
	from java.lang import Throwable as JThrowable
	try:
		return system.config.getResource(moduleId="ignition", typeId=typeId,
										 name=name)
	except (JThrowable, Exception):
		return None


def _config(res):
	"""A resource's config as a plain dict."""
	# Round-tripped through JSON because getConfig() returns live wrappers.
	return system.util.jsonDecode(system.util.jsonEncode(res.getConfig()))


def _upsert(typeId, name, config, description):
	"""Create the resource, or replace it if it exists; return "created" or "updated"."""
	# replace needs the current signature (optimistic concurrency).
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


# The database is SQLite in a file in the gateway's data directory: no server
# or credential, so nothing needs to travel in a project export.

# Ignition expands ${data} to the gateway data directory on every platform.
DB_FILE = "alarm-demo.db"

# WAL lets the gateway timer write journal rows while sessions read them;
# busy_timeout makes the second writer (timer and backfill) wait, not fail.
DB_URL = ("jdbc:sqlite:${data}/%s?journal_mode=WAL&busy_timeout=30000"
		  % DB_FILE)

# `driver` names a database-driver resource; `translator` a stock translator.
DB_DRIVER = "SQLite"
DB_TRANSLATOR = "SQLITE"

# Ignition's defaults for a new connection, except poolMaxActive (8 -> 4):
# eight pooled connections contend for SQLite's single write lock.
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
	"""The connection name, driver and file the Setup screen shows before it is made."""
	return {"name": AlarmDemo.config.DEFAULT_DB,
			"driver": DB_DRIVER,
			"file": u"<gateway data directory>/%s" % DB_FILE}


def createDatabase(name=None):
	"""Create the SQLite connection and point the demo at it; return a one-line account.

	Raises if a connection of that name already exists (it is never overwritten)
	or the SQLite driver is missing.
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

	# The resource registers at once but the pool needs a moment to open the
	# file; wait so the page does not say "created" then "did not answer".
	from java.lang import Thread as JThread
	for _attempt in range(15):
		ok, _detail = _database()
		if ok:
			return u"connection '%s' created and the demo pointed at it" % name
		JThread.sleep(1000)
	return (u"connection '%s' was created and the demo is pointed at it, but "
			u"it is not answering yet - check the row below in a moment" % name)


# Each item is (key, title, check, fix, why). `check` returns (ok, detail);
# `fix` returns a one-line account of what it did, or raises.


def _driverOf(name):
	"""The JDBC driver of a connection, or None if it is missing or unreadable."""
	res = _resource("database-connection", name)
	if res is None:
		return None
	from java.lang import Throwable as JThrowable
	try:
		return _config(res).get("driver")
	except (JThrowable, Exception):
		return None


# Ignition Edge has no database connectivity, so four items cannot be answered
# there. They report what Edge does instead, not red, and are not fixable.
# AlarmDemo.edition owns the detection.

NO_DATABASE_ITEMS = ("database", "journalTables", "journalProfile", "history")


def _noDatabase():
	return not AlarmDemo.edition.hasDatabase()


def _edgeNote():
	return u"Ignition Edge" if AlarmDemo.edition.isEdge() else u"this gateway"


def _database():
	if _noDatabase():
		return True, (u"%s has no database module - the analytics read the "
					  u"alarm journal directly instead of SQL"
					  % _edgeNote())
	name = DB()
	try:
		system.db.runScalarQuery("SELECT 1", name)
	except:
		have = AlarmDemo.config.connections()
		return False, (u"connection '%s' did not answer. This gateway has: %s"
					   % (name, u", ".join(have) if have else u"(none)"))

	# SELECT 1 passes on a PostgreSQL connection left by an older install, but
	# the analytics SQL is SQLite dialect and returns empty there, so check the
	# driver. The Setup row ellipsises, so the diagnosis comes first.
	driver = _driverOf(name)
	if driver is not None and driver != DB_DRIVER:
		return False, (u"'%s' is a %s connection, not %s - this demo's queries "
					   u"return nothing against it rather than failing"
					   % (name, driver, DB_DRIVER))
	return True, u"connection '%s' answered" % name


def _databaseFix():
	"""Make the demo's SQLite connection, leaving any existing other-engine one alone."""
	name = DB()
	driver = _driverOf(name)
	if driver is None or driver == DB_DRIVER:
		# Absent: create it. Already SQLite: createDatabase refuses with a reason.
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


# Edge ships with its visualization module set to VISION; until it is
# PERSPECTIVE no Perspective session opens ("Sessions Exceeded"). It is an
# ordinary config resource, so system.config can set it.

EDGE_VISUALIZATION = "PERSPECTIVE"


def _edgeSystemProperties():
	"""Edge's settings resource, or None off Edge."""
	# A singleton with no name segment, so it is found by enumerating the type.
	from java.lang import Throwable as JThrowable
	try:
		found = list(system.config.getResources(
			moduleId="ignition", typeId="edge-system-properties"))
	except (JThrowable, Exception):
		return None
	return found[0] if found else None


def _edgeVisualizationCheck():
	res = _edgeSystemProperties()
	if res is None:
		return False, u"this gateway has no Ignition Edge settings resource"
	try:
		now = _config(res).get("visualizationName")
	except:
		now = None
	if now == EDGE_VISUALIZATION:
		return True, u"Edge's visualization module is %s" % now
	return False, (u"Edge's visualization module is %s - no Perspective "
				   u"session will open until it is %s"
				   % (now or u"unset", EDGE_VISUALIZATION))


def _edgeVisualizationFix():
	res = _edgeSystemProperties()
	if res is None:
		raise ValueError(u"this gateway has no Ignition Edge settings resource")
	config = _config(res)
	was = config.get("visualizationName")
	config["visualizationName"] = EDGE_VISUALIZATION
	# replace needs the current signature; the singleton keeps the platform's name.
	system.config.replace(moduleId="ignition", typeId="edge-system-properties",
						  name=res.getName(), config=config,
						  signature=res.getSignature(),
						  actor="AlarmDemo.setup")
	return (u"Edge's visualization module changed from %s to %s"
			% (was or u"unset", EDGE_VISUALIZATION))


def _tagProviderCheck():
	if _resource("tag-provider", PROVIDER) is None:
		if AlarmDemo.edition.isEdge():
			# Edge allows one realtime provider, owned by the platform; a second is
			# refused at startup, so the fix is a human setting.
			return False, (u"tag provider '%s' does not exist. Edge keeps one "
						   u"realtime provider and this build is built for a "
						   u"provider of that name - set Config -> Ignition "
						   u"Edge -> Tag Provider to '%s' and save"
						   % (PROVIDER, PROVIDER))
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
	n = len(AlarmDemo.alarms.AREAS)
	return True, u"%d areas readable in [%s]" % (n, PROVIDER)


def _tagsFix():
	"""Write the demo's tags into the provider, overwriting what is there."""
	from java.lang import Thread as JThread
	areas = AlarmDemo.tagdata.tags()
	# A just-created provider may not accept writes yet and fails with a bare
	# exception, so retry three times.
	last = None
	for _attempt in range(3):
		try:
			system.tag.configure(u"[%s]" % PROVIDER, areas, u"o")
			return u"wrote %d areas into [%s]" % (len(AlarmDemo.alarms.AREAS), PROVIDER)
		except:
			import traceback
			last = traceback.format_exc().strip().split("\n")[-1]
			JThread.sleep(1500)
	raise Exception(u"could not write tags into [%s]: %s" % (PROVIDER, last))


def _journalTablesCheck():
	"""The tables are readable; counts this demo's rows only."""
	if _noDatabase():
		return True, (u"%s keeps its journal internally - there are no "
					  u"alarm_events tables to create, and nothing reads them"
					  % _edgeNote())
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
	"""The journal profile exists and writes to the demo's connection."""
	if _noDatabase():
		# Edge allows one journal, owned by the platform; creating another raises.
		# So check that one exists and is the LOCAL kind, as a DATASOURCE profile
		# with no datasource keeps nothing.
		name = AlarmDemo.edition.journalName()
		res = _resource("alarm-journal", name)
		if res is None:
			return False, (u"this gateway has no alarm journal at all - "
						   u"nothing is keeping alarm history")
		try:
			kind = _config(res)["profile"]["type"]
		except:
			kind = None
		if kind != "LOCAL":
			return False, (u"journal '%s' is a %s profile on a gateway with no "
						   u"database - it keeps nothing"
						   % (name, kind or u"?"))
		return True, (u"'%s' is %s's own LOCAL journal - alarms are kept "
					  u"internally, no datasource anywhere"
					  % (name, _edgeNote()))
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
	"""True if the Alarm Notification module is installed."""
	# Tested through the roster-config resource type: system.alarm.getRosters is
	# absent without the module and the AttributeError reads like our bug.
	from java.lang import Throwable as JThrowable
	try:
		for module, typeId in system.config.getResourceTypes():
			if unicode(module) == u"ignition" and unicode(typeId) == u"roster-config":
				return True
	except (JThrowable, Exception):
		pass
	return False


def _rostersCheck():
	"""Check the roster config resources exist."""
	# Not system.alarm.getRosters(), which returns names with empty user lists.
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
	"""Create schedules, people and rosters, reporting rather than raising on partial success."""
	# Without Alarm Notification the rosters cannot be made but the rest can.
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
	"""Read this demo's last 30 days back through the journal profile."""
	# Filtered by source: alarm_events is Ignition's default table name, so
	# another project's events would otherwise count as this demo's.
	end = system.date.now()
	events = system.alarm.queryJournal(
		journalName=AlarmDemo.edition.journalName(),
		source=[u"prov:%s:*" % PROVIDER],
		startDate=system.date.addDays(end, -30), endDate=end)
	n = len(list(events))
	if _noDatabase():
		# No table to backfill and no API to seed the internal journal, so report
		# what has accumulated rather than going red for a new gateway.
		return True, (u"%d events so far - on %s the history accumulates as "
					  u"the demo runs; there is no database to backfill into"
					  % (n, _edgeNote()))
	if n < 100:
		return False, u"%d of this demo's events in the last 30 days" % n
	return True, u"%d of this demo's events in the last 30 days" % n


def _historyFix():
	n = AlarmDemo.backfill.run(days=30, perDay=85)
	return u"%d journal rows written" % n


ITEMS = [
	("edgeVisualization", "Edge visualization module", _edgeVisualizationCheck,
	 _edgeVisualizationFix,
	 "Edge ships set to Vision, and until it is Perspective no Perspective "
	 "session opens at all - which is why this one is first, and why on Edge "
	 "the install is run through the admin endpoint rather than this screen."),
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


# The three items that cannot answer anything useful until the database
# connection does; otherwise each shows a datasource NullPointerException.
NEEDS_DATABASE = ("journalTables", "journalProfile", "history")

# Items that only apply on Edge; elsewhere the row is hidden.
EDGE_ONLY = ("edgeVisualization",)

# Replacement `why` text for gateways with no database, where the normal text
# describes a button that is not there.
NO_DATABASE_WHY = {
	"database":
		u"There is no database on this edition and the demo does not want "
		u"one: the analytics read the alarm journal through the alarm system "
		u"itself, and answer the same questions.",
	"tagProvider":
		u"Edge permits exactly ONE realtime tag provider, the platform makes "
		u"it, and a second is refused at startup - so the Edge build is built "
		u"for the name Edge already uses rather than creating its own.",
	"journalTables":
		u"There are none. Edge's journal keeps its history internally, with "
		u"no datasource anywhere, so there is nothing to create and nothing "
		u"reading alarm_events.",
	"journalProfile":
		u"The journal every screen reads through. Edge keeps exactly one, the "
		u"platform owns it, and the demo adopts it - the screens ask the "
		u"gateway for its name rather than assuming one.",
	"history":
		u"Nothing can seed it: the journal is internal to the platform and no "
		u"scripting API inserts into it. So the history is whatever the demo "
		u"has raised since it started running - every analytic works from the "
		u"first alarm, over a shorter window.",
}


def check():
	"""Report every item's state in install order, changing nothing.

	Returns {"items": [{key, title, ok, detail, fixable, why}], "ok", "version",
	"db", "edition"}.
	"""
	items = []
	dbOk = None
	noDb = _noDatabase()
	isEdge = AlarmDemo.edition.isEdge()
	for key, title, checkFn, fixFn, why in ITEMS:
		if key in EDGE_ONLY and not isEdge:
			continue
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
		fixable = fixFn is not None
		if fixable and noDb and key in NO_DATABASE_ITEMS:
			fixable = False
		if fixable and key == "tagProvider" and AlarmDemo.edition.isEdge():
			# Edge refuses a second realtime provider at startup.
			fixable = False
		items.append({"key": key, "title": title, "ok": bool(ok),
					  "detail": detail, "fixable": fixable,
					  "why": NO_DATABASE_WHY.get(key, why) if noDb else why})
	return {
		"items": items,
		"ok": all(i["ok"] for i in items),
		"version": AlarmDemo.alarms.VERSION,
		"db": AlarmDemo.config.describe(),
		# The database card and history-rebuild button bind to hasDatabase and are
		# absent, not disabled, on Edge.
		"edition": {
			"isEdge": AlarmDemo.edition.isEdge(),
			"hasDatabase": not noDb,
			"describe": AlarmDemo.edition.describe(),
		},
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
	"""Create everything missing, in dependency order, and return the check() state.

	Safe to run twice. `force` also resets rosters and schedules to the shipped
	design, discarding edits made on the Notifications screen.
	"""
	done, failed = [], []
	dbOk = _database()[0]
	noDb = _noDatabase()
	isEdge = AlarmDemo.edition.isEdge()
	for key, _title, checkFn, fixFn, _why in ITEMS:
		if fixFn is None:
			continue
		if key in EDGE_ONLY and not isEdge:
			continue
		# No database module: the platform refuses these four.
		if noDb and key in NO_DATABASE_ITEMS:
			continue
		if key == "tagProvider" and AlarmDemo.edition.isEdge():
			continue
		# dbOk was read before the loop; the connection may have just been made.
		if key == "journalTables" and not dbOk:
			dbOk = _database()[0]
		if key in NEEDS_DATABASE and not dbOk:
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
			# Schedules, people and rosters share one fix; report its sentence once.
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


def fixForView(view, index):
	"""Run the fix for Setup row `index` and report the outcome in the view's busy line."""
	item = view.custom.state["items"][index]
	view.custom.busy = "creating %s..." % item["title"]
	try:
		view.custom.busy = fix(item["key"])
	except Exception as e:
		view.custom.busy = "failed: %s" % e
	view.custom.tick = view.custom.tick + 1


def runForView(view):
	"""Run the whole setup from the Setup screen and report the outcome in the view's busy line."""
	view.custom.busy = "working - this takes about a minute"
	r = run()
	done = r.get("changed", [])
	errs = r.get("errors", [])
	if errs:
		view.custom.busy = "finished with problems: " + "; ".join(errs)
	elif done:
		view.custom.busy = "; ".join(done)
	else:
		view.custom.busy = "nothing to do - this gateway was already set up"
	view.custom.tick = view.custom.tick + 1
