"""
AlarmDemo.alarms - view helpers.

Everything the Perspective views need that is easier to express in script than
in a binding: live status roll-ups, the KPI bundle, and the journal-backed
analytics. All of it is read-only and none of it raises - a demo screen that
throws a red error box is worse than one showing zeros.

Every query is scoped to a *site*. Two sites share one tag provider, so
"all areas" always means "all areas of the selected site", never both plants
added together.
"""

# THE build number - this line is the single source of it. Reported by
# ?cmd=version, shown at the bottom of the Setup and Demo Control screens, and
# read straight out of this file by build_views.py so the UI cannot drift from
# the scripts.
#
# It says "dev" in the repository. `./package.sh --release X.Y.Z` stamps the
# real version here, into the project title and into the release filename, and
# puts "dev" back when it is done - so a gateway running a release says which
# one, and a gateway running a working copy says it is a working copy. It
# exists because "which build is this gateway running?" was not answerable
# from the running demo, which turned one chart bug into four rounds of
# guessing.
VERSION = "dev"

PROVIDER = "AlarmDemo"
TABLE = "alarm_events"

# Every row this demo writes - and every row its own journal profile writes -
# has a source beginning `prov:AlarmDemo:`, because the demo's tags live in
# their own provider. That prefix is what scopes every journal read and the
# history wipe to this demo's own data.
#
# It earns its keep because `alarm_events` is Ignition's DEFAULT table name:
# the table is shared far more often than the profile is, and on any gateway
# where another project journals to it, an unscoped query counts that
# project's alarms as this demo's. Seen live on a gateway holding 116,000 rows
# belonging to two other projects.
SOURCE_PREFIX = "prov:%s:%%" % PROVIDER


def DB():
    """The database connection this demo reads and writes.

    A FUNCTION rather than a constant, because the answer belongs to the
    gateway, not to the project: it comes from AlarmDemo.config, which the
    Setup page can change while the demo is running. As a module-level
    constant it was read once when the project loaded, so changing the
    connection took a project scan to have any effect - which reads as "the
    setting did not save".
    """
    return AlarmDemo.config.db()

PRIORITY_NAMES = ["Diagnostic", "Low", "Medium", "High", "Critical"]
PRIORITY_NUM = {n: i for i, n in enumerate(PRIORITY_NAMES)}

# Two sites share one tag provider, each owning a set of top-level areas.
# They have to be top-level: Area is derived from the first tag-path segment
# everywhere in this project, so a "site" folder wrapping them would collapse
# every area into one.
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
    """Run fn, and on any failure log it and hand back `default`.

    The except block uses traceback rather than a system.util helper on
    purpose: if the handler itself raises, the exception escapes the binding
    and every bound property on the screen renders as an error box - which is
    exactly the failure this wrapper exists to prevent.
    """
    try:
        return fn()
    except:
        import traceback
        LOG.warn("helper failed: %s" % traceback.format_exc())
        return default


# ---------------------------------------------------------------------------
# sites
# ---------------------------------------------------------------------------


def siteAreas(site):
    """Areas belonging to a site; every area when the site is unknown."""
    return SITES.get(site, {}).get("areas", AREAS)


def siteInfo(site):
    """Label/subtitle for the header. Falls back to the water plant."""
    s = SITES.get(site) or SITES["Water"]
    return {"label": s["label"], "subtitle": s["subtitle"],
            "areas": list(s["areas"])}


def _areaPattern(area):
    """The source prefix every alarm in one area shares.

    `prov:AlarmDemo:/tag:Intake/WetWell/Level:/alm:High Level` -> the area is
    the first path segment after `/tag:`, so every alarm in Intake starts
    `prov:AlarmDemo:/tag:Intake/`.
    """
    return u"prov:%s:/tag:%s/%%" % (PROVIDER, area)


def _millis(when):
    """Epoch milliseconds, which is what `eventtime` actually holds.

    Ignition's SQLite journal writer stores eventtime as TEXT digits - epoch
    milliseconds - not as a date type, because SQLite has none. Read straight
    back out of a table Ignition created and filled: `typeof(eventtime)` is
    'text' and the value is '1787875575442'.

    So every comparison against it CASTs the column to INTEGER and binds a
    number, rather than binding a Date and hoping the driver and SQLite's type
    affinity agree on what to do with it. They might: 13-digit strings happen
    to sort the same way the numbers do, until the year 2286. That is not a
    thing to rely on without saying so.
    """
    return long(system.date.toMillis(when))


def _scope(hours, site, area, alias="a"):
    """(whereSql, args) for the time window plus the site/area restriction.

    Area names come from the fixed SITES map, never from user input, and are
    still passed as bind parameters rather than interpolated.

    The area test is a `source LIKE` on that area's own prefix. It used to be
    `split_part(split_part(source,'/tag:',2),'/',1) = ?`, which said the same
    thing and said it in PostgreSQL - SQLite has no split_part, and the demo
    now runs on SQLite so that a gateway needs no database server at all. The
    prefix is the better test regardless: it is what the source path is FOR,
    and it is the shape an index can use.

    It also subsumes the old separate `source LIKE 'prov:AlarmDemo:%'` term -
    every area pattern already carries that prefix - so the provider scoping
    that keeps this demo out of another project's rows is still here, one
    layer more specific.
    """
    end = system.date.now()
    start = system.date.addHours(end, -int(hours))
    args = [_millis(start), _millis(end)]
    areas = [area] if area else siteAreas(site)
    pred = "(%s)" % " OR ".join(["%s.source LIKE ?" % alias] * len(areas))
    args.extend([_areaPattern(a) for a in areas])
    where = ("CAST(%s.eventtime AS INTEGER) >= ? AND "
             "CAST(%s.eventtime AS INTEGER) < ? AND " % (alias, alias)) + pred
    return where, args


# `strftime` with 'unixepoch' reads the value as seconds, so the milliseconds
# are divided out first; 'localtime' then puts the bucket boundaries where the
# gateway's own day starts, which is what `date_trunc` used to do and what
# anyone reading a daily chart means by a day.
def _bucket(expr, unit):
    fmt = "%Y-%m-%d %H:00:00" if unit == "hour" else "%Y-%m-%d 00:00:00"
    return ("strftime('" + fmt + "', CAST(" + expr +
            " AS INTEGER)/1000, 'unixepoch', 'localtime')")


BUCKET_FORMAT = "yyyy-MM-dd HH:mm:ss"

# The activation-to-acknowledgement gap, in milliseconds, and the test that
# the acknowledgement really came after the activation. Both are used by two
# queries and are written once so the two cannot drift apart.
_ACK_MILLIS = "(CAST(k.eventtime AS INTEGER) - CAST(a.eventtime AS INTEGER))"
_ACK_AFTER = "CAST(k.eventtime AS INTEGER) > CAST(a.eventtime AS INTEGER)"


def _truncHour(when):
    """The top of the hour `when` falls in."""
    return system.date.addHours(system.date.midnight(when),
                                system.date.getHour24(when))


def _zeroFilled(rows, start, end, unit, columns):
    """Turn (bucketKey, n) rows into one dataset row per bucket in the window.

    The zero-fill used to be a `generate_series` LEFT JOIN, which SQLite has
    no equivalent for. Doing it here is less SQL and the same result, and the
    bucket comes back out as a real Date rather than a string, so the charts'
    axes are unchanged.

    A gap in a rate trend reads as 'no data', not as 'quiet' - which is why
    the empty buckets have to be present at all.
    """
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
    """A source path condition scoping the stock alarm components to one site.

    The Alarm Status and Alarm Journal tables both take
    `filters.active.conditions.source` - a comma-separated list of alarm source
    paths, wildcards allowed. Both sites share one tag provider, so without this
    the stock components list the other plant's alarms under this plant's
    header, which is the one thing a two-site demo must not do.

    Returns e.g.
        prov:AlarmDemo:/tag:Intake/*,prov:AlarmDemo:/tag:Filtration/*,...
    """
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


# ---------------------------------------------------------------------------
# live status
# ---------------------------------------------------------------------------


# Row tints for the stock Alarm Status Table. Translucent so the row text
# stays legible on the dark surface, and stronger when unacknowledged - an
# unacked alarm should be the loudest thing on the screen.
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
    """`rowStyles` for the Alarm Status Table.

        rows    the whole row is tinted by priority, as Ignition's own alarm
                tables do it
        cells   the row stays neutral and only the priority column is
                coloured - the row carries a per-priority CLASS and the
                stylesheet paints just that one cell

    Those two are what the screens offer. Both colour by priority; the only
    question is where the colour sits. "Off" is still accepted for anything
    calling this directly, but it is not a choice on any screen - the priority
    word is in the row either way, so switching the colour off removes a signal
    without adding one.

    A cleared alarm is greyed and dimmed in every mode: it has stopped being
    a demand on anyone's attention, and it should stop looking like one.
    """

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
            # greyed out, and it also loses its priority tint above
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
    """`rowStyles` for the Alarm Journal Table.

    A DIFFERENT shape from the Alarm Status Table's, which is why passing that
    one to this component throws inside the component and the whole view
    renders as an error boundary. The journal keys by EVENT type - active,
    acked, cleared - where the status table keys by alarm state.

    The `base` override is not optional: the component ships light pastel row
    backgrounds (#FDAFAF for active, #F3F6C6 for acknowledged) that are
    unreadable on a dark page, and they apply whatever the colour mode is.
    """

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
    """Everything the header and the mimic need, in one queryStatus call.

    Returns a dict:
        counts      {priority: n} for active alarms in this site
        total       active alarm count
        unacked     active and unacknowledged
        shelved     shelved alarm count
        worst       highest active priority name, or "" when all clear
        areas       {area: {"total": n, "worst": name}} for EVERY area of the
                    site, zeroed - a binding that reads a missing key renders
                    a red null box instead of the zero it means
        other       active alarms belonging to the site not selected
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
    """Per-area alarm metrics, aggregated live.

    Aggregated from `system.alarm.queryStatus` rather than from 8.3 Alarm
    Metrics tag properties (`<folder>.activeCount`, `.highestActivePriority`
    and friends). Those properties do not resolve on this gateway for ANY tag
    folder - Ignition's own `[default]Chat` and `[default]Roster` folders return
    Bad_NotFound for them just as ours do - so relying on them would make the
    screen depend on something unproven. queryStatus needs no Designer step and
    works on any provider.

    Per area: total active, unacknowledged, acknowledged, a count per
    priority, and the worst alarm currently standing.
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
    """Active alarms for one site, shaped for a plain table.

    The stock Alarm Status Table shows the whole provider, and with two plants
    in one provider that means the overview of one site lists the other site's
    alarms. This is scoped, so the overview only ever shows the plant on
    screen. The full-featured component still lives on the Alarm Status page.
    """

    def go():
        mine = set(siteAreas(site))
        rows = []
        for e in system.alarm.queryStatus(
                state=["ActiveUnacked", "ActiveAcked"], provider=[PROVIDER]):
            if _area(e) not in mine:
                continue
            try:
                # getTimestamp() is already epoch millis; calling .getTime()
                # on it throws, and the resulting blank column looks like the
                # alarm simply has no time rather than like a bug.
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


# ---------------------------------------------------------------------------
# journal-backed analytics
# ---------------------------------------------------------------------------
#
# Each of the seven below opens with the same two lines:
#
#     if not AlarmDemo.edition.hasDatabase():
#         return AlarmDemo.journalq.<same name>(...)
#
# Ignition Edge has no database connectivity at all - no SQL Bridge, no JDBC
# driver modules - so on that edition these queries have nothing to run
# against. AlarmDemo.journalq answers the same questions from the alarm
# journal profile instead, and returns the same shapes. The branch is here
# rather than in the views because a binding must not have to know which
# edition it is running on.


def paretoRows(hours=24, site="Water", area="", rows=10):
    """Worst alarm sources - from SQL, or from the journal on a gateway with no
    database. AlarmDemo.journalq.paretoRows is the other half; the two are
    compared against one journal by the admin endpoint's ?cmd=parity.
    """
    if not AlarmDemo.edition.hasDatabase():
        return AlarmDemo.journalq.paretoRows(hours, site, area, rows)

    return sqlParetoRows(hours, site, area, rows)


def sqlParetoRows(hours=24, site="Water", area="", rows=10):
    """Worst alarm sources, pre-shaped for the dashboard.

    Returns EXACTLY `rows` dicts, padding with blanks, each carrying the bar
    width already worked out as a percentage string. Padding matters: the view
    binds row 8 whether or not the query returned nine, and a binding that
    indexes past the end of a result set renders as an error box.
    """

    def go():
        where, args = _scope(hours, site, area)
        res = system.db.runPrepQuery(
            "SELECT COALESCE(NULLIF(a.displaypath,''), a.source) AS alarm_name, "
            "COUNT(*) AS occurrences FROM %s a WHERE a.eventtype = 0 AND %s "
            # Ties are ordered by name, not left to the engine. Without it
            # two sources on the same count swap places between refreshes,
            # and the journal implementation - which has to sort in Python -
            # cannot be compared against this one at all.
            "GROUP BY 1 ORDER BY occurrences DESC, alarm_name ASC LIMIT %d"
            % (TABLE, where, int(rows)),
            args, DB(),
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
    """Alarms per hour - from SQL, or from the journal on a gateway with no
    database. AlarmDemo.journalq.rateByHour is the other half; the two are
    compared against one journal by the admin endpoint's ?cmd=parity.
    """
    if not AlarmDemo.edition.hasDatabase():
        return AlarmDemo.journalq.rateByHour(hours, site, area)

    return sqlRateByHour(hours, site, area)


def sqlRateByHour(hours=24, site="Water", area=""):
    """Alarms per hour, every hour present. A gap in a rate trend reads as
    'no data', not as 'quiet', so empty hours are filled with zero."""

    def go():
        where, args = _scope(hours, site, area)
        rows = system.db.runPrepQuery(
            "SELECT %s AS bucket, COUNT(*) AS n FROM %s a "
            "WHERE a.eventtype = 0 AND %s GROUP BY 1"
            % (_bucket("a.eventtime", "hour"), TABLE, where),
            args, DB(),
        )
        end = system.date.now()
        first = system.date.addHours(end, -int(hours))
        return _zeroFilled(rows, _truncHour(first), _truncHour(end), "hour",
                           ["bucket", "occurrences"])

    return _safe(go, system.dataset.toDataSet(["bucket", "occurrences"], []))


def dailyLoad(days=30, site="Water", area=""):
    """Activations per day - from SQL, or from the journal on a gateway with no
    database. AlarmDemo.journalq.dailyLoad is the other half; the two are
    compared against one journal by the admin endpoint's ?cmd=parity.
    """
    if not AlarmDemo.edition.hasDatabase():
        return AlarmDemo.journalq.dailyLoad(days, site, area)

    return sqlDailyLoad(days, site, area)


def sqlDailyLoad(days=30, site="Water", area=""):
    """Activations per day over the last `days`.

    Every day in the window is present, zero-filled: on a load chart a missing
    day and a quiet day mean opposite things, and a line that simply skips the
    gap draws a quiet weekend as a straight run between two busy weekdays.
    """

    def go():
        where, args = _scope(int(days) * 24, site, area)
        rows = system.db.runPrepQuery(
            "SELECT %s AS bucket, COUNT(*) AS n FROM %s a "
            "WHERE a.eventtype = 0 AND %s GROUP BY 1"
            % (_bucket("a.eventtime", "day"), TABLE, where),
            args, DB(),
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
    """Average minutes to acknowledge, per day - from SQL, or from the journal on a gateway with no
    database. AlarmDemo.journalq.dailyAckTime is the other half; the two are
    compared against one journal by the admin endpoint's ?cmd=parity.
    """
    if not AlarmDemo.edition.hasDatabase():
        return AlarmDemo.journalq.dailyAckTime(days, site, area)

    return sqlDailyAckTime(days, site, area)


def sqlDailyAckTime(days=30, site="Water", area=""):
    """Average minutes from activation to acknowledgement, per day.

    Deliberately NOT zero-filled. A day where nothing was acknowledged has no
    average, and plotting it as zero would claim the opposite of what happened -
    that everything was acknowledged instantly.

    The join is activation to its own acknowledgement by `eventid`, which is how
    Ignition ties the two journal rows together; an activation never
    acknowledged simply does not join and is excluded rather than counted as
    infinitely slow.
    """

    def go():
        where, args = _scope(int(days) * 24, site, area)
        # Same last-complete-day cut-off as dailyLoad, so the two charts beside
        # each other cover exactly the same period.
        rows = system.db.runPrepQuery(
            "SELECT %s AS bucket, "
            "  ROUND(AVG(%s)/60000.0, 1) AS minutes "
            "FROM %s a JOIN %s k ON k.eventid = a.eventid AND k.eventtype = 2 "
            "WHERE a.eventtype = 0 AND %s AND %s "
            "  AND CAST(a.eventtime AS INTEGER) < ? "
            "GROUP BY 1 ORDER BY 1"
            % (_bucket("a.eventtime", "day"), _ACK_MILLIS, TABLE, TABLE,
               where, _ACK_AFTER),
            args + [_millis(system.date.midnight(system.date.now()))], DB(),
        )
        # bucket comes back as the text key the GROUP BY produced; the chart
        # wants the same Date it has always had.
        out = []
        for r in rows:
            out.append([system.date.parse(unicode(r["bucket"]), BUCKET_FORMAT),
                        r["minutes"]])
        return system.dataset.toDataSet(["bucket", "minutes"], out)

    return _safe(go, system.dataset.toDataSet(["bucket", "minutes"], []))


def topUnacked(hours=24, site="Water", area="", rows=10):
    """Activations nobody acknowledged - from SQL, or from the journal on a gateway with no
    database. AlarmDemo.journalq.topUnacked is the other half; the two are
    compared against one journal by the admin endpoint's ?cmd=parity.
    """
    if not AlarmDemo.edition.hasDatabase():
        return AlarmDemo.journalq.topUnacked(hours, site, area, rows)

    return sqlTopUnacked(hours, site, area, rows)


def sqlTopUnacked(hours=24, site="Water", area="", rows=10):
    """Activations nobody ever acknowledged - the gap between what alarms and
    what an operator actually responds to."""

    def go():
        where, args = _scope(hours, site, area)
        return system.db.runPrepQuery(
            "SELECT COALESCE(NULLIF(a.displaypath,''), a.source) AS \"Alarm\", "
            "COUNT(*) AS \"Never acked\" FROM %s a "
            "WHERE a.eventtype = 0 AND %s AND NOT EXISTS ("
            "  SELECT 1 FROM %s k WHERE k.eventid = a.eventid AND k.eventtype = 2) "
            # ...and the same tiebreaker, for the same two reasons.
            "GROUP BY 1 ORDER BY 2 DESC, 1 ASC LIMIT %d"
            % (TABLE, where, TABLE, int(rows)),
            args, DB(),
        )

    return _safe(go, system.dataset.toDataSet(["Alarm", "Never acked"], []))


def priorityCounts(hours=24, site="Water", area=""):
    """Activations per priority - from SQL, or from the journal on a gateway with no
    database. AlarmDemo.journalq.priorityCounts is the other half; the two are
    compared against one journal by the admin endpoint's ?cmd=parity.
    """
    if not AlarmDemo.edition.hasDatabase():
        return AlarmDemo.journalq.priorityCounts(hours, site, area)

    return sqlPriorityCounts(hours, site, area)


def sqlPriorityCounts(hours=24, site="Water", area=""):
    """Activations per priority over the window, as a flat dict.

    The donut binds one slice to each key. A dict rather than a dataset because
    a missing priority has to read as zero - a slice bound to a row that is not
    in the result set renders as an invalid-data error instead of an empty
    wedge.
    """

    def go():
        where, args = _scope(hours, site, area)
        rows = system.db.runPrepQuery(
            "SELECT a.priority, COUNT(*) AS n FROM %s a "
            "WHERE a.eventtype = 0 AND %s GROUP BY a.priority" % (TABLE, where),
            args, DB(),
        )
        out = dict((p, 0) for p in PRIORITY_NAMES)
        for r in rows:
            idx = int(r["priority"])
            if 0 <= idx < len(PRIORITY_NAMES):
                out[PRIORITY_NAMES[idx]] = int(r["n"])
        return out

    return _safe(go, dict((p, 0) for p in PRIORITY_NAMES))


def kpis(hours=24, site="Water", area=""):
    """The headline numbers - from SQL, or from the journal on a gateway with no
    database. AlarmDemo.journalq.kpis is the other half; the two are
    compared against one journal by the admin endpoint's ?cmd=parity.
    """
    if not AlarmDemo.edition.hasDatabase():
        return AlarmDemo.journalq.kpis(hours, site, area)

    return sqlKpis(hours, site, area)


def sqlKpis(hours=24, site="Water", area=""):
    """Headline numbers for the analytics screen.

    rate            activations per hour over the window
    total           activations in the window
    ackMedianMin    median minutes to acknowledge
    unackedPct      share of activations never acknowledged
    topShare        share of the count from the worst 3 sources - the Pareto
                    number, the one that says whether rationalisation pays
    floodHours      hours busier than the EEMUA-191 flood threshold, taken
                    here as more than 60 alarms in an hour
    """

    def go():
        where, args = _scope(hours, site, area)

        total = system.db.runPrepQuery(
            "SELECT COUNT(*) AS n FROM %s a WHERE a.eventtype = 0 AND %s"
            % (TABLE, where), args, DB())[0]["n"]

        top3 = system.db.runPrepQuery(
            "SELECT COUNT(*) AS n FROM %s a WHERE a.eventtype = 0 AND %s "
            "GROUP BY COALESCE(NULLIF(a.displaypath,''), a.source) "
            "ORDER BY n DESC LIMIT 3" % (TABLE, where), args, DB())
        top_n = sum([r["n"] for r in top3])

        flood = system.db.runPrepQuery(
            "SELECT COUNT(*) AS n FROM (SELECT %s AS h, "
            "COUNT(*) AS c FROM %s a WHERE a.eventtype = 0 AND %s "
            "GROUP BY 1 HAVING COUNT(*) > 60) f"
            % (_bucket("a.eventtime", "hour"), TABLE, where), args, DB())[0]["n"]

        # SQLite has no percentile_cont, so the median is the middle row of the
        # ordered set - counted, then fetched by OFFSET. Two small queries
        # rather than one that repeats its own subquery twice.
        #
        # For an even count this is the LOWER of the two middle values, where
        # percentile_cont would have interpolated between them. On a headline
        # figure rounded to one decimal of a minute, over thousands of
        # acknowledgements, that is not a difference anyone can read.
        inner = ("SELECT %s AS ms "
                 "FROM %s a JOIN %s k ON k.eventid = a.eventid "
                 "  AND k.eventtype = 2 "
                 "WHERE a.eventtype = 0 AND %s AND %s"
                 % (_ACK_MILLIS, TABLE, TABLE, where, _ACK_AFTER))
        acked = int(system.db.runPrepQuery(
            "SELECT COUNT(*) AS n FROM (%s) d" % inner, args, DB())[0]["n"] or 0)
        med = 0
        if acked:
            med = (system.db.runPrepQuery(
                "SELECT ms FROM (%s) d ORDER BY ms LIMIT 1 OFFSET %d"
                % (inner, (acked - 1) // 2), args, DB())[0]["ms"] or 0) / 1000.0

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
