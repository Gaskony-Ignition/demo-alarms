"""AlarmDemo.alarms - read-only view helpers: status roll-ups, the KPI bundle and journal analytics.

None of it raises, and every query is scoped to one site, never both plants added together.
"""

# Build number; package.sh --release stamps it and restores "dev". build_views.py reads this line.
VERSION = "dev"

PROVIDER = "AlarmDemo"
TABLE = "alarm_events"

# Journal rows from this demo start with this prefix. alarm_events is the default table
# name, so other projects may share the table and an unscoped query would count their rows.
SOURCE_PREFIX = "prov:%s:%%" % PROVIDER


def db():
	"""The database connection this demo reads and writes."""
	# A function, not a constant: the Setup page can change it while the project is loaded.
	return AlarmDemo.config.db()

PRIORITY_NAMES = ["Diagnostic", "Low", "Medium", "High", "Critical"]
PRIORITY_NUM = {n: i for i, n in enumerate(PRIORITY_NAMES)}

# Areas must be top-level folders: Area is the first tag-path segment everywhere.
SITES = {
	"Water": {
		"label": "ACME Water Treatment Plant",
		"subtitle": "Potable water production and distribution",
		"areas": ["Intake", "Filtration", "Chemical", "Distribution", "Plant"],
	},
	"Manufacturing": {
		"label": "ACME Manufacturing",
		"subtitle": "Beverage bottling and packaging line",
		"areas": ["Mixing", "Filling", "Packaging", "Utilities"],
	},
}

SITE_ORDER = ["Water", "Manufacturing"]

AREAS = [a for s in SITE_ORDER for a in SITES[s]["areas"]]

LOG = system.util.getLogger("AlarmDemo.alarms")


def _safe(fn, default):
	"""Run fn; on any failure log it and return default."""
	# traceback, not a system.util helper: a handler that raises turns every bound property into an error box.
	try:
		return fn()
	except:
		import traceback
		LOG.warn("helper failed: %s" % traceback.format_exc())
		return default


def siteAreas(site):
	"""Areas belonging to a site; every area when the site is unknown."""
	return SITES.get(site, {}).get("areas", AREAS)


def siteInfo(site):
	"""Return the header label, subtitle and areas for a site; the water plant if unknown."""
	s = SITES.get(site) or SITES["Water"]
	return {"label": s["label"], "subtitle": s["subtitle"],
			"areas": list(s["areas"])}


def _areaPattern(area):
	"""The journal source prefix (a LIKE pattern) shared by every alarm in one area."""
	return u"prov:%s:/tag:%s/%%" % (PROVIDER, area)


def _millis(when):
	"""Epoch milliseconds, the form `eventtime` is stored in."""
	# SQLite stores eventtime as TEXT digits, so queries CAST it to INTEGER and bind a number.
	return long(system.date.toMillis(when))


def _scope(hours, site, area, alias="a"):
	"""Return (whereSql, args) for the time window plus the site/area restriction."""
	# The area LIKE prefixes also scope the query to this provider's rows.
	end = system.date.now()
	start = system.date.addHours(end, -int(hours))
	args = [_millis(start), _millis(end)]
	areas = [area] if area else siteAreas(site)
	pred = "(%s)" % " OR ".join(["%s.source LIKE ?" % alias] * len(areas))
	args.extend([_areaPattern(a) for a in areas])
	where = ("CAST(%s.eventtime AS INTEGER) >= ? AND "
			 "CAST(%s.eventtime AS INTEGER) < ? AND " % (alias, alias)) + pred
	return where, args


# strftime reads 'unixepoch' as seconds, so divide the milliseconds; 'localtime' puts bucket edges on the gateway's day.
def _bucket(expr, unit):
	fmt = "%Y-%m-%d %H:00:00" if unit == "hour" else "%Y-%m-%d 00:00:00"
	return ("strftime('" + fmt + "', CAST(" + expr +
			" AS INTEGER)/1000, 'unixepoch', 'localtime')")


BUCKET_FORMAT = "yyyy-MM-dd HH:mm:ss"

# Activation-to-acknowledgement gap in milliseconds, and the test that the ack came after.
_ACK_MILLIS = "(CAST(k.eventtime AS INTEGER) - CAST(a.eventtime AS INTEGER))"
_ACK_AFTER = "CAST(k.eventtime AS INTEGER) > CAST(a.eventtime AS INTEGER)"


def _truncHour(when):
	"""The top of the hour `when` falls in."""
	return system.date.addHours(system.date.midnight(when),
								system.date.getHour24(when))


def _zeroFilled(rows, start, end, unit, columns):
	"""Turn (bucketKey, n) rows into one dataset row per bucket in the window."""
	# Empty buckets must be present: a gap in a rate trend reads as "no data", not "quiet".
	counts = {}
	for r in rows:
		counts[unicode(r["bucket"])] = int(r["n"])
	out, cursor = [], start
	while cursor.getTime() <= end.getTime():
		key = system.date.format(cursor, BUCKET_FORMAT)
		out.append([cursor, counts.get(key, 0)])
		cursor = (system.date.addHours(cursor, 1) if unit == "hour"
				  else system.date.addDays(cursor, 1))
	return system.dataset.toDataSet(columns, out)


def sourceFilter(site, area=""):
	"""Return the source filter that scopes the stock alarm tables to one site or area."""
	# Both sites share one provider; without this the tables list the other plant's alarms.
	areas = [area] if area else siteAreas(site)
	return ",".join(["prov:%s:/tag:%s/*" % (PROVIDER, a) for a in areas])


def _area(event):
	"""Area = first tag path segment, matching what the SQL analytics do."""
	src = str(event.getSource())
	if "/tag:" not in src:
		return "Ungrouped"
	segs = [s for s in src.split("/tag:")[1].split(":")[0].split("/") if s]
	return segs[0] if segs else "Ungrouped"


def _priorityName(event):
	try:
		return str(event.getPriority())
	except:
		return "Low"


# Row tints for the Alarm Status Table: translucent for dark surfaces, stronger when unacknowledged.
_TINT_UNACKED = {
	"critical": "rgba(229,34,91,0.34)",
	"high": "rgba(245,130,32,0.30)",
	"medium": "rgba(245,197,24,0.24)",
	"low": "rgba(78,168,255,0.22)",
	"diagnostic": "rgba(139,152,169,0.18)",
}
_TINT_ACKED = {
	"critical": "rgba(229,34,91,0.17)",
	"high": "rgba(245,130,32,0.15)",
	"medium": "rgba(245,197,24,0.12)",
	"low": "rgba(78,168,255,0.11)",
	"diagnostic": "rgba(139,152,169,0.09)",
}

_PRIORITY_KEYS = ["critical", "high", "medium", "low", "diagnostic"]


def rowStyles(mode="rows"):
	"""Build the Alarm Status Table's rowStyles; mode "rows" tints the row, "cells" only the priority cell."""
	# Cleared alarms are greyed in every mode.

	def styled(tints, cleared):
		pri = {}
		for k in _PRIORITY_KEYS:
			cls = {"classes": "ad-alm-%s" % k}
			if mode == "rows" and not cleared:
				cls["backgroundColor"] = tints[k]
			elif mode == "rows" and cleared:
				cls["backgroundColor"] = "rgba(110,122,136,0.10)"
			pri[k] = cls
		base = {"classes": "ad-alm-row"}
		if cleared:
			base = {"classes": "ad-alm-row ad-alm-cleared",
					"color": "#7E8A99"}
		return {"base": base, "priorities": pri}

	return {
		"activeUnacked": styled(_TINT_UNACKED, False),
		"activeAcked": styled(_TINT_ACKED, False),
		"clearUnacked": styled(_TINT_ACKED, True),
		"clearAcked": styled(_TINT_ACKED, True),
	}


def journalRowStyles(mode="cells"):
	"""Build the Alarm Journal Table's rowStyles; mode "rows" tints the row, "cells" only the priority cell."""
	# Keyed by journal event type, not alarm state, so the status table's shape breaks this component.
	# The base override is required: the component's pastel row backgrounds are unreadable on dark.

	def styled(tints, dim=False):
		pri = {}
		for k in _PRIORITY_KEYS:
			cls = {"classes": "ad-alm-%s" % k}
			if mode == "rows":
				cls["backgroundColor"] = tints[k]
			pri[k] = cls
		base = {"classes": "ad-alm-row", "backgroundColor": "transparent",
				"color": "#E6EDF3", "fontWeight": "400"}
		if dim:
			base = {"classes": "ad-alm-row ad-alm-cleared",
					"backgroundColor": "transparent", "color": "#7E8A99",
					"fontWeight": "400"}
		return {"base": base, "priorities": pri}

	return {
		"active": styled(_TINT_UNACKED),
		"acked": styled(_TINT_ACKED),
		"cleared": styled(_TINT_ACKED, dim=True),
		"enabled": styled(_TINT_ACKED),
		"disabled": styled(_TINT_ACKED, dim=True),
		"system": styled(_TINT_ACKED),
	}


def liveStatus(site="Water"):
	"""Return the live alarm roll-up for a site, from one queryStatus call.

	Keys: counts {priority: n}, total, unacked, shelved, worst ("" when clear),
	areas {area: {"total", "worst"}} for every area, other (active in the other site).
	"""

	def go():
		mine = siteAreas(site)
		counts = dict((p, 0) for p in PRIORITY_NAMES)
		areas = dict((a, {"total": 0, "worst": "OK"}) for a in mine)
		unacked = 0
		total = 0
		other = 0

		events = system.alarm.queryStatus(
			state=["ActiveUnacked", "ActiveAcked"], provider=[PROVIDER]
		)
		for e in events:
			a = _area(e)
			if a not in areas:
				other += 1
				continue
			total += 1
			p = _priorityName(e)
			counts[p] = counts.get(p, 0) + 1
			if not e.isAcked():
				unacked += 1
			rec = areas[a]
			rec["total"] += 1
			if PRIORITY_NUM.get(p, 0) >= PRIORITY_NUM.get(rec["worst"], -1):
				rec["worst"] = p

		worst = ""
		for p in reversed(PRIORITY_NAMES):
			if counts.get(p, 0) > 0:
				worst = p
				break

		try:
			shelved = len(system.alarm.getShelvedPaths())
		except:
			shelved = 0

		return {"counts": counts, "total": total, "unacked": unacked,
				"shelved": shelved, "worst": worst, "areas": areas,
				"other": other}

	return _safe(go, {
		"counts": dict((p, 0) for p in PRIORITY_NAMES),
		"total": 0, "unacked": 0, "shelved": 0, "worst": "",
		"areas": dict((a, {"total": 0, "worst": "OK"}) for a in siteAreas(site)),
		"other": 0,
	})


def areaMetrics(site="Water"):
	"""Return one metrics dict per area of the site: active, unacked, acked, per-priority counts, worst.

	Aggregated from queryStatus: the 8.3 Alarm Metrics tag properties do not resolve here.
	"""

	def go():
		areas = siteAreas(site)
		blank = lambda a: {"area": a, "active": 0, "unacked": 0, "acked": 0,
						   "worst": "OK", "worstName": "-",
						   "counts": dict((p, 0) for p in PRIORITY_NAMES)}
		out = dict((a, blank(a)) for a in areas)

		for e in system.alarm.queryStatus(
				state=["ActiveUnacked", "ActiveAcked"], provider=[PROVIDER]):
			a = _area(e)
			if a not in out:
				continue
			rec = out[a]
			pri = _priorityName(e)
			rec["active"] += 1
			rec["counts"][pri] = rec["counts"].get(pri, 0) + 1
			if e.isAcked():
				rec["acked"] += 1
			else:
				rec["unacked"] += 1
			if PRIORITY_NUM.get(pri, 0) >= PRIORITY_NUM.get(rec["worst"], -1):
				rec["worst"] = pri
				rec["worstName"] = (str(e.getDisplayPath() or "")
									or str(e.getSource()))

		return [out[a] for a in areas]

	return _safe(go, [])


def activeAlarms(site="Water", limit=200):
	"""Return the site's active alarms as a dataset, most severe first."""

	def go():
		mine = set(siteAreas(site))
		rows = []
		for e in system.alarm.queryStatus(
				state=["ActiveUnacked", "ActiveAcked"], provider=[PROVIDER]):
			if _area(e) not in mine:
				continue
			try:
				# getTimestamp() is already epoch millis; .getTime() on it throws.
				ts = system.date.format(
					system.date.fromMillis(e.getActiveData().getTimestamp()),
					"dd/MM/yyyy HH:mm:ss")
			except:
				ts = ""
			disp = str(e.getDisplayPath() or "") or str(e.getSource())
			rows.append([ts, disp, _priorityName(e),
						 "Acknowledged" if e.isAcked() else "Unacknowledged"])
		rows.sort(key=lambda r: (-PRIORITY_NUM.get(r[2], 0), r[0]))
		return system.dataset.toDataSet(
			["Active time", "Alarm", "Priority", "State"], rows[:int(limit)])

	return _safe(go, system.dataset.toDataSet(
		["Active time", "Alarm", "Priority", "State"], []))


def areaOptions(site="Water"):
	"""Dropdown options - 'All areas' plus each area of the selected site."""
	return ([{"value": "", "label": "All areas"}]
			+ [{"value": a, "label": a} for a in siteAreas(site)])


# Each analytic below calls AlarmDemo.journalq on Edge (no database); both return the same shapes.


def paretoRows(hours=24, site="Water", area="", rows=10):
	"""Worst alarm sources; reads the journal when the gateway has no database."""
	if not AlarmDemo.edition.hasDatabase():
		return AlarmDemo.journalq.paretoRows(hours, site, area, rows)

	return sqlParetoRows(hours, site, area, rows)


def sqlParetoRows(hours=24, site="Water", area="", rows=10):
	"""Return exactly `rows` dicts of the worst alarm sources, blank-padded, with bar widths as percentages."""
	# Padding matters: the view binds every row, and an index past the result set shows an error box.

	def go():
		where, args = _scope(hours, site, area)
		res = system.db.runPrepQuery(
			"SELECT COALESCE(NULLIF(a.displaypath,''), a.source) AS alarm_name, "
			"COUNT(*) AS occurrences FROM %s a WHERE a.eventtype = 0 AND %s "
			# Ties are ordered by name so the journal version, which sorts in Python, matches.
			"GROUP BY 1 ORDER BY occurrences DESC, alarm_name ASC LIMIT %d"
			% (TABLE, where, int(rows)),
			args, db(),
		)
		out = []
		top = float(res[0]["occurrences"]) if len(res) else 0.0
		for r in res:
			n = int(r["occurrences"])
			out.append({"name": r["alarm_name"], "n": n,
						"pct": "%d%%" % int(round(100.0 * n / top)) if top else "0%",
						"show": "flex"})
		while len(out) < int(rows):
			out.append({"name": "", "n": 0, "pct": "0%", "show": "none"})
		return out

	return _safe(go, [{"name": "", "n": 0, "pct": "0%", "show": "none"}
					  for _ in range(int(rows))])


def rateByHour(hours=24, site="Water", area=""):
	"""Alarms per hour; reads the journal when the gateway has no database."""
	if not AlarmDemo.edition.hasDatabase():
		return AlarmDemo.journalq.rateByHour(hours, site, area)

	return sqlRateByHour(hours, site, area)


def sqlRateByHour(hours=24, site="Water", area=""):
	"""Return alarms per hour with every hour present, empty hours as zero."""

	def go():
		where, args = _scope(hours, site, area)
		rows = system.db.runPrepQuery(
			"SELECT %s AS bucket, COUNT(*) AS n FROM %s a "
			"WHERE a.eventtype = 0 AND %s GROUP BY 1"
			% (_bucket("a.eventtime", "hour"), TABLE, where),
			args, db(),
		)
		end = system.date.now()
		first = system.date.addHours(end, -int(hours))
		return _zeroFilled(rows, _truncHour(first), _truncHour(end), "hour",
						   ["bucket", "occurrences"])

	return _safe(go, system.dataset.toDataSet(["bucket", "occurrences"], []))


def dailyLoad(days=30, site="Water", area=""):
	"""Activations per day; reads the journal when the gateway has no database."""
	if not AlarmDemo.edition.hasDatabase():
		return AlarmDemo.journalq.dailyLoad(days, site, area)

	return sqlDailyLoad(days, site, area)


def sqlDailyLoad(days=30, site="Water", area=""):
	"""Return activations per day over the last `days`, zero-filled."""

	def go():
		where, args = _scope(int(days) * 24, site, area)
		rows = system.db.runPrepQuery(
			"SELECT %s AS bucket, COUNT(*) AS n FROM %s a "
			"WHERE a.eventtype = 0 AND %s GROUP BY 1"
			% (_bucket("a.eventtime", "day"), TABLE, where),
			args, db(),
		)
		# Both bounds stop at the last COMPLETE day. Today is a few hours old
		# and would plot as a cliff at the right-hand edge that reads like the
		# plant went quiet, when all it means is that the day is not over.
		lastComplete = system.date.addDays(system.date.midnight(
			system.date.now()), -1)
		first = system.date.addDays(lastComplete, -(int(days) - 1))
		return _zeroFilled(rows, first, lastComplete, "day",
						   ["bucket", "alarms"])

	return _safe(go, system.dataset.toDataSet(["bucket", "alarms"], []))


def dailyAckTime(days=30, site="Water", area=""):
	"""Average minutes to acknowledge, per day; reads the journal when the gateway has no database."""
	if not AlarmDemo.edition.hasDatabase():
		return AlarmDemo.journalq.dailyAckTime(days, site, area)

	return sqlDailyAckTime(days, site, area)


def sqlDailyAckTime(days=30, site="Water", area=""):
	"""Return average minutes from activation to acknowledgement, per day."""
	# Not zero-filled: a day with no acknowledgements has no average, and zero would read as instant.
	# Activations never acknowledged do not join, so they are excluded.

	def go():
		where, args = _scope(int(days) * 24, site, area)
		# Same last-complete-day cut-off as sqlDailyLoad.
		rows = system.db.runPrepQuery(
			"SELECT %s AS bucket, "
			"  ROUND(AVG(%s)/60000.0, 1) AS minutes "
			"FROM %s a JOIN %s k ON k.eventid = a.eventid AND k.eventtype = 2 "
			"WHERE a.eventtype = 0 AND %s AND %s "
			"  AND CAST(a.eventtime AS INTEGER) < ? "
			"GROUP BY 1 ORDER BY 1"
			% (_bucket("a.eventtime", "day"), _ACK_MILLIS, TABLE, TABLE,
			   where, _ACK_AFTER),
			args + [_millis(system.date.midnight(system.date.now()))], db(),
		)
		# bucket is text from the GROUP BY; the chart wants a Date.
		out = []
		for r in rows:
			out.append([system.date.parse(unicode(r["bucket"]), BUCKET_FORMAT),
						r["minutes"]])
		return system.dataset.toDataSet(["bucket", "minutes"], out)

	return _safe(go, system.dataset.toDataSet(["bucket", "minutes"], []))


def topUnacked(hours=24, site="Water", area="", rows=10):
	"""Activations nobody acknowledged; reads the journal when the gateway has no database."""
	if not AlarmDemo.edition.hasDatabase():
		return AlarmDemo.journalq.topUnacked(hours, site, area, rows)

	return sqlTopUnacked(hours, site, area, rows)


def sqlTopUnacked(hours=24, site="Water", area="", rows=10):
	"""Return the top sources by activations nobody acknowledged."""

	def go():
		where, args = _scope(hours, site, area)
		return system.db.runPrepQuery(
			"SELECT COALESCE(NULLIF(a.displaypath,''), a.source) AS \"Alarm\", "
			"COUNT(*) AS \"Never acked\" FROM %s a "
			"WHERE a.eventtype = 0 AND %s AND NOT EXISTS ("
			"  SELECT 1 FROM %s k WHERE k.eventid = a.eventid AND k.eventtype = 2) "
			# Same name tiebreaker as sqlParetoRows.
			"GROUP BY 1 ORDER BY 2 DESC, 1 ASC LIMIT %d"
			% (TABLE, where, TABLE, int(rows)),
			args, db(),
		)

	return _safe(go, system.dataset.toDataSet(["Alarm", "Never acked"], []))


def priorityCounts(hours=24, site="Water", area=""):
	"""Activations per priority; reads the journal when the gateway has no database."""
	if not AlarmDemo.edition.hasDatabase():
		return AlarmDemo.journalq.priorityCounts(hours, site, area)

	return sqlPriorityCounts(hours, site, area)


def sqlPriorityCounts(hours=24, site="Water", area=""):
	"""Return activations per priority as a flat dict, with a zero for every priority."""
	# A dict so a missing priority reads as zero; a missing donut row renders as an error.

	def go():
		where, args = _scope(hours, site, area)
		rows = system.db.runPrepQuery(
			"SELECT a.priority, COUNT(*) AS n FROM %s a "
			"WHERE a.eventtype = 0 AND %s GROUP BY a.priority" % (TABLE, where),
			args, db(),
		)
		out = dict((p, 0) for p in PRIORITY_NAMES)
		for r in rows:
			idx = int(r["priority"])
			if 0 <= idx < len(PRIORITY_NAMES):
				out[PRIORITY_NAMES[idx]] = int(r["n"])
		return out

	return _safe(go, dict((p, 0) for p in PRIORITY_NAMES))


def kpis(hours=24, site="Water", area=""):
	"""The headline numbers; reads the journal when the gateway has no database."""
	if not AlarmDemo.edition.hasDatabase():
		return AlarmDemo.journalq.kpis(hours, site, area)

	return sqlKpis(hours, site, area)


def sqlKpis(hours=24, site="Water", area=""):
	"""Return the analytics headline numbers as a dict.

	Keys: rate (per hour), total, ackMedianMin, unackedPct, topShare (% from the
	worst 3 sources), floodHours (hours over 60 alarms, the EEMUA 191 flood level).
	"""

	def go():
		where, args = _scope(hours, site, area)

		total = system.db.runPrepQuery(
			"SELECT COUNT(*) AS n FROM %s a WHERE a.eventtype = 0 AND %s"
			% (TABLE, where), args, db())[0]["n"]

		top3 = system.db.runPrepQuery(
			"SELECT COUNT(*) AS n FROM %s a WHERE a.eventtype = 0 AND %s "
			"GROUP BY COALESCE(NULLIF(a.displaypath,''), a.source) "
			"ORDER BY n DESC LIMIT 3" % (TABLE, where), args, db())
		top_n = sum([r["n"] for r in top3])

		flood = system.db.runPrepQuery(
			"SELECT COUNT(*) AS n FROM (SELECT %s AS h, "
			"COUNT(*) AS c FROM %s a WHERE a.eventtype = 0 AND %s "
			"GROUP BY 1 HAVING COUNT(*) > 60) f"
			% (_bucket("a.eventtime", "hour"), TABLE, where), args, db())[0]["n"]

		# No percentile_cont in SQLite: count, then OFFSET to the middle row (the lower one when even).
		inner = ("SELECT %s AS ms "
				 "FROM %s a JOIN %s k ON k.eventid = a.eventid "
				 "  AND k.eventtype = 2 "
				 "WHERE a.eventtype = 0 AND %s AND %s"
				 % (_ACK_MILLIS, TABLE, TABLE, where, _ACK_AFTER))
		acked = int(system.db.runPrepQuery(
			"SELECT COUNT(*) AS n FROM (%s) d" % inner, args, db())[0]["n"] or 0)
		med = 0
		if acked:
			med = (system.db.runPrepQuery(
				"SELECT ms FROM (%s) d ORDER BY ms LIMIT 1 OFFSET %d"
				% (inner, (acked - 1) // 2), args, db())[0]["ms"] or 0) / 1000.0

		return {
			"total": total,
			"rate": round(float(total) / max(int(hours), 1), 1),
			"ackMedianMin": round(float(med) / 60.0, 1),
			"unackedPct": round(100.0 * (total - acked) / total, 0) if total else 0,
			"topShare": round(100.0 * top_n / total, 0) if total else 0,
			"floodHours": flood,
		}

	return _safe(go, {"total": 0, "rate": 0, "ackMedianMin": 0,
					  "unackedPct": 0, "topShare": 0, "floodHours": 0})
