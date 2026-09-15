"""
AlarmDemo.journalq - the analytics, without a database.

Every function here answers the same question as the identically named one in
AlarmDemo.alarms and returns the same shape, so a view binding does not know
or care which ran. The difference is where the events come from: the SQL
versions read the journal TABLES, these read the journal PROFILE through
`system.alarm.queryJournal`.

That matters because Ignition Edge has no database connectivity at all - not a
slower one, an absent one - and the demo's whole analytics screen was SQL.
AlarmDemo.edition decides which implementation runs; nothing else does.

## How a journal event is shaped

`queryJournal` returns one PyAlarmEvent per TRANSITION, not per alarm, which
is the same grain the `alarm_events` table has. Which transition it is, is
told by which data bundle is populated - the other two are None:

    getActiveData()   the activation      (eventtype 0 in SQL)
    getClearedData()  the clear           (eventtype 1)
    getAckData()      the acknowledgement (eventtype 2)

`getId()` is the same UUID across all three, which is what `eventid` is for in
the SQL, so activation-to-acknowledgement is a lookup rather than a join.
`getTimestamp()` on a bundle is epoch MILLISECONDS as a Java long.

Measured against a real Edge gateway on 10/09/2026. `getEventTime()`,
`getTimestamp()` and `getEventType()` on the event itself are all None on Edge
- the timestamp lives on the bundle, not on the event.
"""

# Everything shared with the SQL implementation - site membership, priority
# names, the bucket format, the zero-fill - is imported rather than repeated.
# Two implementations of the same chart that disagree about where a day starts
# is exactly the drift this module has to avoid.

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
    """Every one of this demo's journal transitions in the window.

    Returns a list of dicts: {kind, ts, id, key, priority, area}.

    The journal is queried with the PROVIDER-wide source filter, which is the
    one shape this demo has already proved works for queryJournal, and the
    area restriction is applied here in Python. Doing it that way means the
    area test is literally the same code as _areaOf rather than a second
    expression of it in a wildcard, and it costs one pass over a few thousand
    events.
    """
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
    """Milliseconds from activation to acknowledgement, per acknowledged alarm.

    An activation nobody ever acknowledged does not appear - it is excluded
    rather than counted as infinitely slow, which is what the SQL join does.
    An acknowledgement that predates its own activation is dropped for the
    same reason the SQL carries `k.eventtime > a.eventtime`: on a journal that
    has been backfilled, out-of-order pairs exist and a negative delay plotted
    as an average drags the whole day below zero.
    """
    activeAt = {}
    for e in _activations(events):
        # Several activations can share an id only if the journal is odd;
        # keeping the earliest matches the SQL, which joins to all of them.
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
    """The bucket an event falls in, as the same string the SQL GROUP BY made.

    `strftime(..., 'localtime')` on the SQL side puts the boundary where the
    gateway's own day starts; system.date does the same here, so the two
    implementations cannot disagree about which day an evening alarm belongs
    to.
    """
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


# ---------------------------------------------------------------------------
# the eight the views bind to
# ---------------------------------------------------------------------------


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
    """Average minutes from activation to acknowledgement, per day.

    Deliberately NOT zero-filled, and cut at the same last-complete-day bound
    as dailyLoad so the two charts beside each other cover one period. A day
    where nothing was acknowledged has no average; plotting it as zero would
    claim everything was acknowledged instantly.
    """

    def go():
        events = _events(int(days) * 24, site, area)
        cutoff = long(system.date.toMillis(
            system.date.midnight(system.date.now())))
        activeAt = {}
        for e in _activations(events):
            prev = activeAt.get(e["id"])
            if prev is None or e["ts"] < prev:
                activeAt[e["id"]] = e["ts"]
        # Bucketed by the day the ACTIVATION happened, which is what the SQL
        # groups by - an alarm raised before midnight and acknowledged after it
        # belongs to the day it interrupted someone.
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
        # The LOWER of the two middle values for an even count, which is what
        # the SQL's LIMIT 1 OFFSET (n-1)/2 returns - SQLite has no
        # percentile_cont. On a figure rounded to a tenth of a minute the
        # difference from interpolating is not readable.
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


# ---------------------------------------------------------------------------
# proving the two implementations agree
# ---------------------------------------------------------------------------


def _comparable(value):
    """Whatever an analytic returned, as something two answers can be ==.

    Datasets do not compare, and the two implementations build theirs from
    different primitives - a Date out of system.date.parse on one side and out
    of system.date.fromMillis on the other. Reducing both to lists of plain
    values is what makes the comparison about the ANSWER rather than about the
    types it arrived in.
    """
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
    """Run every analytic BOTH ways over one journal and compare the answers.

    The point of the demo running on Edge is that the screens say the same
    thing there as anywhere else. Two implementations of seven analytics is
    two chances for that to stop being true, and neither one fails loudly when
    it drifts - a wrong Pareto is a plausible Pareto.

    So this is the gate: on a gateway that HAS a database, both paths are
    available, they are pointed at the same journal, and every pair must
    match. On a gateway without one there is nothing to compare against and it
    says so rather than reporting a vacuous pass.

    Returns {ok, comparable, results: [{name, match, sql, journal}]}, with the
    two answers included only where they differ - a matching pair is a line
    saying so, not a wall of numbers.
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
