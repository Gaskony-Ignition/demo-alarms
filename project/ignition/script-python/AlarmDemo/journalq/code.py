"""AlarmDemo.journalq - the analytics without a database, for Edge.

Same names and shapes as AlarmDemo.alarms, but read from the journal profile
through system.alarm.queryJournal. AlarmDemo.edition decides which runs.
"""

LOG = system.util.getLogger("AlarmDemo.journalq")

ACTIVE, CLEARED, ACKED = "active", "cleared", "acked"


def _safe(fn, default):
	"""Same contract as AlarmDemo.alarms._safe - never raise into a binding."""
	return AlarmDemo.alarms._safe(fn, default)


def _areaOf(source):
	"""Area = first tag path segment, exactly what the SQL LIKE prefix means."""
	src = unicode(source)
	if u"/tag:" not in src:
		return u"Ungrouped"
	rest = src.split(u"/tag:", 1)[1]
	return rest.split(u"/", 1)[0] if u"/" in rest else u"Ungrouped"


def _events(hours, site, area):
	"""Return the demo's journal transitions in the window as dicts {kind, ts, id, key, priority, area}."""
	# One event per transition; which bundle (active, cleared, ack) is set says which.
	# On Edge the event's own timestamp is None, so ts comes from the bundle (epoch ms).
	# Area is filtered here with _areaOf, so it matches the SQL prefix test.
	end = system.date.now()
	start = system.date.addHours(end, -int(hours))
	wanted = set([area] if area else AlarmDemo.alarms.siteAreas(site))
	provider = AlarmDemo.alarms.PROVIDER

	out = []
	for e in system.alarm.queryJournal(
			journalName=AlarmDemo.edition.journalName(),
			source=[u"prov:%s:*" % provider],
			startDate=start, endDate=end):
		src = unicode(e.getSource())
		a = _areaOf(src)
		if a not in wanted:
			continue
		for kind, bundle in ((ACTIVE, e.getActiveData()),
							 (CLEARED, e.getClearedData()),
							 (ACKED, e.getAckData())):
			if bundle is None:
				continue
			label = unicode(e.getDisplayPathOrSource())
			out.append({"kind": kind,
						"ts": long(bundle.getTimestamp()),
						"id": unicode(e.getId()),
						"key": label,
						"priority": unicode(e.getPriority()),
						"area": a})
	return out


def _activations(events):
	return [e for e in events if e["kind"] == ACTIVE]


def _ackDelays(events):
	"""Milliseconds from activation to acknowledgement, per acknowledged alarm."""
	# Unacknowledged activations are excluded, as in the SQL join. Acks before their
	# activation (backfilled journals) are dropped: a negative delay drags the average down.
	activeAt = {}
	for e in _activations(events):
		# Keep the earliest activation for an id, as the SQL join does.
		prev = activeAt.get(e["id"])
		if prev is None or e["ts"] < prev:
			activeAt[e["id"]] = e["ts"]
	out = []
	for e in events:
		if e["kind"] != ACKED:
			continue
		t0 = activeAt.get(e["id"])
		if t0 is not None and e["ts"] > t0:
			out.append(e["ts"] - t0)
	return out


def _bucketKey(ts, unit):
	"""The bucket an event falls in, as the same string the SQL GROUP BY makes."""
	# system.date uses the gateway's local day, like strftime 'localtime' in the SQL.
	when = system.date.fromMillis(ts)
	if unit == "hour":
		top = AlarmDemo.alarms._truncHour(when)
	else:
		top = system.date.midnight(when)
	return system.date.format(top, AlarmDemo.alarms.BUCKET_FORMAT)


def _counted(events, unit):
	"""[{bucket, n}] in the shape AlarmDemo.alarms._zeroFilled consumes."""
	counts = {}
	for e in events:
		k = _bucketKey(e["ts"], unit)
		counts[k] = counts.get(k, 0) + 1
	return [{"bucket": k, "n": n} for k, n in counts.items()]


def paretoRows(hours=24, site="Water", area="", rows=10):
	"""Worst alarm sources. Padded to EXACTLY `rows` - see the SQL twin."""

	def go():
		counts = {}
		for e in _activations(_events(hours, site, area)):
			counts[e["key"]] = counts.get(e["key"], 0) + 1
		ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
		ranked = ranked[:int(rows)]
		out = []
		top = float(ranked[0][1]) if ranked else 0.0
		for name, n in ranked:
			out.append({"name": name, "n": n,
						"pct": "%d%%" % int(round(100.0 * n / top)) if top else "0%",
						"show": "flex"})
		while len(out) < int(rows):
			out.append({"name": "", "n": 0, "pct": "0%", "show": "none"})
		return out

	return _safe(go, [{"name": "", "n": 0, "pct": "0%", "show": "none"}
					  for _ in range(int(rows))])


def rateByHour(hours=24, site="Water", area=""):
	"""Alarms per hour, every hour present, empty hours zero-filled."""

	def go():
		acts = _activations(_events(hours, site, area))
		end = system.date.now()
		first = system.date.addHours(end, -int(hours))
		return AlarmDemo.alarms._zeroFilled(
			_counted(acts, "hour"),
			AlarmDemo.alarms._truncHour(first),
			AlarmDemo.alarms._truncHour(end),
			"hour", ["bucket", "occurrences"])

	return _safe(go, system.dataset.toDataSet(["bucket", "occurrences"], []))


def dailyLoad(days=30, site="Water", area=""):
	"""Activations per day, zero-filled, stopping at the last COMPLETE day."""

	def go():
		acts = _activations(_events(int(days) * 24, site, area))
		lastComplete = system.date.addDays(
			system.date.midnight(system.date.now()), -1)
		first = system.date.addDays(lastComplete, -(int(days) - 1))
		return AlarmDemo.alarms._zeroFilled(_counted(acts, "day"), first,
											lastComplete, "day",
											["bucket", "alarms"])

	return _safe(go, system.dataset.toDataSet(["bucket", "alarms"], []))


def dailyAckTime(days=30, site="Water", area=""):
	"""Return average minutes from activation to acknowledgement per day, without zero-fill."""
	# Cut at the last complete day, like dailyLoad; a day with no acks has no average.

	def go():
		events = _events(int(days) * 24, site, area)
		cutoff = long(system.date.toMillis(
			system.date.midnight(system.date.now())))
		activeAt = {}
		for e in _activations(events):
			prev = activeAt.get(e["id"])
			if prev is None or e["ts"] < prev:
				activeAt[e["id"]] = e["ts"]
		# Bucketed by activation day, as the SQL does.
		sums, counts = {}, {}
		for e in events:
			if e["kind"] != ACKED:
				continue
			t0 = activeAt.get(e["id"])
			if t0 is None or e["ts"] <= t0 or t0 >= cutoff:
				continue
			k = _bucketKey(t0, "day")
			sums[k] = sums.get(k, 0) + (e["ts"] - t0)
			counts[k] = counts.get(k, 0) + 1
		out = []
		for k in sorted(sums.keys()):
			minutes = round((sums[k] / float(counts[k])) / 60000.0, 1)
			out.append([system.date.parse(k, AlarmDemo.alarms.BUCKET_FORMAT),
						minutes])
		return system.dataset.toDataSet(["bucket", "minutes"], out)

	return _safe(go, system.dataset.toDataSet(["bucket", "minutes"], []))


def topUnacked(hours=24, site="Water", area="", rows=10):
	"""Activations nobody ever acknowledged."""

	def go():
		events = _events(hours, site, area)
		ackedIds = set([e["id"] for e in events if e["kind"] == ACKED])
		counts = {}
		for e in _activations(events):
			if e["id"] in ackedIds:
				continue
			counts[e["key"]] = counts.get(e["key"], 0) + 1
		ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
		return system.dataset.toDataSet(
			["Alarm", "Never acked"],
			[[name, n] for name, n in ranked[:int(rows)]])

	return _safe(go, system.dataset.toDataSet(["Alarm", "Never acked"], []))


def priorityCounts(hours=24, site="Water", area=""):
	"""Activations per priority, as a flat dict with every priority present."""

	def go():
		out = dict((p, 0) for p in AlarmDemo.alarms.PRIORITY_NAMES)
		for e in _activations(_events(hours, site, area)):
			if e["priority"] in out:
				out[e["priority"]] += 1
		return out

	return _safe(go, dict((p, 0) for p in AlarmDemo.alarms.PRIORITY_NAMES))


def kpis(hours=24, site="Water", area=""):
	"""The headline numbers. Same six keys, same rounding, as the SQL twin."""

	def go():
		events = _events(hours, site, area)
		acts = _activations(events)
		total = len(acts)

		counts = {}
		for e in acts:
			counts[e["key"]] = counts.get(e["key"], 0) + 1
		top_n = sum(sorted(counts.values(), reverse=True)[:3])

		perHour = {}
		for e in acts:
			k = _bucketKey(e["ts"], "hour")
			perHour[k] = perHour.get(k, 0) + 1
		flood = len([n for n in perHour.values() if n > 60])

		delays = sorted(_ackDelays(events))
		acked = len(delays)
		# The lower middle value for an even count, matching the SQL OFFSET.
		med = (delays[(acked - 1) // 2] / 1000.0) if acked else 0

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


def _comparable(value):
	"""Reduce an analytic's result to plain lists and dicts so two answers can be compared."""
	from java.util import Date as JDate
	if hasattr(value, "getRowCount") and hasattr(value, "getColumnCount"):
		rows = []
		for r in range(value.getRowCount()):
			row = []
			for c in range(value.getColumnCount()):
				v = value.getValueAt(r, c)
				if isinstance(v, JDate):
					v = long(system.date.toMillis(v))
				elif isinstance(v, float):
					v = round(v, 3)
				row.append(v)
			rows.append(row)
		return rows
	if isinstance(value, dict):
		return dict((k, round(v, 3) if isinstance(v, float) else v)
					for k, v in value.items())
	if isinstance(value, list):
		return [_comparable(v) for v in value]
	return value


def parity(hours=24, days=30, site="Water", area=""):
	"""Run every analytic through SQL and the journal and compare the answers.

	Returns {ok, comparable, results}; the two answers are included only where they differ.
	Without a database there is nothing to compare, so comparable is False.
	"""
	if not AlarmDemo.edition.hasDatabase():
		return {"ok": True, "comparable": False,
				"note": (u"this gateway has no database, so there is no SQL "
						 u"implementation to compare against - the journal "
						 u"path is the only one that runs here")}

	a = AlarmDemo.alarms
	cases = [
		("paretoRows", lambda: a.sqlParetoRows(hours, site, area, 10),
		 lambda: paretoRows(hours, site, area, 10)),
		("rateByHour", lambda: a.sqlRateByHour(hours, site, area),
		 lambda: rateByHour(hours, site, area)),
		("dailyLoad", lambda: a.sqlDailyLoad(days, site, area),
		 lambda: dailyLoad(days, site, area)),
		("dailyAckTime", lambda: a.sqlDailyAckTime(days, site, area),
		 lambda: dailyAckTime(days, site, area)),
		("topUnacked", lambda: a.sqlTopUnacked(hours, site, area, 10),
		 lambda: topUnacked(hours, site, area, 10)),
		("priorityCounts", lambda: a.sqlPriorityCounts(hours, site, area),
		 lambda: priorityCounts(hours, site, area)),
		("kpis", lambda: a.sqlKpis(hours, site, area),
		 lambda: kpis(hours, site, area)),
	]

	results, allOk = [], True
	for name, sqlFn, jFn in cases:
		left = _comparable(sqlFn())
		right = _comparable(jFn())
		match = left == right
		allOk = allOk and match
		row = {"name": name, "match": match}
		if not match:
			row["sql"] = unicode(left)[:800]
			row["journal"] = unicode(right)[:800]
		results.append(row)

	return {"ok": allOk, "comparable": True, "window":
			{"hours": hours, "days": days, "site": site, "area": area},
			"results": results}
