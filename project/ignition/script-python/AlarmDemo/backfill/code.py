"""
AlarmDemo.backfill - synthetic alarm journal history.

A brand new gateway has an empty journal, so every analytics screen is blank
until the plant has been running for weeks. This writes a realistic history
straight into the journal tables so the Pareto, heatmap and trend screens have
something to say from the first minute.

What makes it look real rather than random:

  * diurnal shape      - alarms cluster around the 07:00 and 19:00 demand peaks
  * weekly shape       - weekends are quieter, Monday is the worst day
  * Pareto             - a handful of bad actors produce most of the count,
                         which is the entire point of the analysis
  * chattering         - two sources fire in tight bursts
  * event days         - three storm days with a cross-area cascade
  * ack behaviour      - Critical is acked in a couple of minutes, Low is often
                         never acked at all
  * durations          - each activation gets a matching clear, with a duration
                         that depends on what the alarm is

Every row is written against the same sources and display paths as the live
tags, so history and live alarms line up in the tables and the analytics.

Usage (Script Console, or the Demo Control view):

    AlarmDemo.backfill.run()          # 30 days for BOTH sites, wipes first
    AlarmDemo.backfill.run(days=60)
    AlarmDemo.backfill.clear()        # empty the demo journal
"""

import random

from java.util import UUID

# The datasource, journal tables and tag provider are defined ONCE, in
# AlarmDemo.alarms. Copies in this file are how "change the DB constant"
# quietly became a three-file edit that a fresh install gets wrong in one of
# them and then debugs as a blank screen.
DB = AlarmDemo.alarms.DB
TABLE = AlarmDemo.alarms.TABLE
DATA_TABLE = "alarm_event_data"   # written only from here
PROVIDER = AlarmDemo.alarms.PROVIDER

PRIORITY_NUM = {"Diagnostic": 0, "Low": 1, "Medium": 2, "High": 3, "Critical": 4}

EVT_ACTIVE, EVT_CLEAR, EVT_ACK = 0, 1, 2

# Event flags as the gateway itself writes them - sampled from real journalled
# events rather than guessed. The built-in Alarm Journal Table reads these; get
# them wrong and rows are silently dropped from the component while still being
# perfectly visible to plain SQL.
FLAGS = {EVT_ACTIVE: 0, EVT_CLEAR: 16, EVT_ACK: 0}

LOG = system.util.getLogger("AlarmDemo.backfill")


# ---------------------------------------------------------------------------
# the alarm catalogue - mirrors the tag definitions
#
# (tagPath, alarmName, displayPath, priority, weight, minDurSec, maxDurSec)
#
# weight drives the Pareto: the top few entries deliberately dominate.
# ---------------------------------------------------------------------------

CATALOGUE = [
    # --- bad actors: these three produce most of the count ----------------
    # Weight 55 rather than something larger because this one chatters: each
    # pick emits a burst of 4-11 occurrences, so its effective share is roughly
    # 7x its weight. It lands near 20% of all activations - a clear number one
    # bad actor without swamping every other pattern in the data.
    ("Distribution/HighLiftPump03/Fault", "Motor Fault",
     "Distribution / High Lift Pump 3 / Motor Fault", "High", 55, 20, 400),
    ("Filtration/FilterB/DiffPressure", "Backwash Required",
     "Filtration / Filter B / Backwash Required", "Medium", 150, 300, 2400),
    ("Intake/WetWell/Level", "High Level",
     "Intake / Wet Well / High Level", "Medium", 120, 180, 1800),

    # --- routine operational -------------------------------------------
    ("Filtration/FilterA/DiffPressure", "Backwash Required",
     "Filtration / Filter A / Backwash Required", "Medium", 70, 300, 2400),
    ("Filtration/FilterC/DiffPressure", "Backwash Required",
     "Filtration / Filter C / Backwash Required", "Medium", 66, 300, 2400),
    ("Intake/RawWaterPump01/Amps", "Motor Overload",
     "Intake / Raw Water Pump 1 / Motor Overload", "Medium", 44, 60, 900),
    ("Intake/RawWaterPump02/Amps", "Motor Overload",
     "Intake / Raw Water Pump 2 / Motor Overload", "Medium", 38, 60, 900),
    ("Distribution/ClearwaterTank/Level", "Level High",
     "Distribution / Clearwater Tank / High", "Medium", 34, 240, 1500),
    ("Distribution/NetworkPressure", "High Network Pressure",
     "Distribution / Network / High Pressure", "Medium", 30, 120, 900),

    # --- higher consequence --------------------------------------------
    ("Intake/RawWaterPump01/Fault", "Motor Fault",
     "Intake / Raw Water Pump 1 / Motor Fault", "High", 40, 300, 5400),
    ("Intake/RawWaterPump02/Fault", "Motor Fault",
     "Intake / Raw Water Pump 2 / Motor Fault", "High", 33, 300, 5400),
    ("Distribution/HighLiftPump01/Fault", "Motor Fault",
     "Distribution / High Lift Pump 1 / Motor Fault", "High", 26, 300, 5400),
    ("Distribution/HighLiftPump02/Fault", "Motor Fault",
     "Distribution / High Lift Pump 2 / Motor Fault", "High", 22, 300, 5400),
    ("Distribution/ClearwaterTank/Level", "Level Low",
     "Distribution / Clearwater Tank / Low", "High", 28, 600, 7200),
    ("Chemical/Chlorine/TankLevel", "Tank Level Critical",
     "Chemical / Chlorine / Tank Level Critical", "High", 14, 1800, 14400),
    ("Chemical/Coagulant/TankLevel", "Tank Level Critical",
     "Chemical / Coagulant / Tank Level Critical", "High", 12, 1800, 14400),
    ("Chemical/ChlorineResidual", "Residual Low",
     "Chemical / Chlorine Residual / Low", "High", 24, 300, 3600),
    ("Chemical/pH", "pH Out Of Range",
     "Chemical / pH / Out Of Range", "High", 20, 240, 2700),
    ("Filtration/FilterB/Turbidity", "Turbidity Breakthrough",
     "Filtration / Filter B / Turbidity Breakthrough", "High", 18, 300, 2400),
    ("Filtration/FilterA/DiffPressure", "High Head Loss",
     "Filtration / Filter A / High Head Loss", "High", 10, 300, 1800),

    # --- medium / low background ---------------------------------------
    ("Chemical/Chlorine/TankLevel", "Tank Level Low",
     "Chemical / Chlorine / Tank Level Low", "Medium", 30, 3600, 28800),
    ("Chemical/Fluoride/TankLevel", "Tank Level Low",
     "Chemical / Fluoride / Tank Level Low", "Medium", 26, 3600, 28800),
    ("Chemical/Coagulant/TankLevel", "Tank Level Low",
     "Chemical / Coagulant / Tank Level Low", "Medium", 28, 3600, 28800),
    ("Intake/RawTurbidity", "High Raw Turbidity",
     "Intake / Raw Water / High Turbidity", "Low", 190, 600, 10800),
    ("Intake/RawWaterPump01/SuctionPressure", "Low Suction Pressure",
     "Intake / Raw Water Pump 1 / Low Suction Pressure", "Low", 120, 120, 900),
    ("Intake/RawWaterPump02/SuctionPressure", "Low Suction Pressure",
     "Intake / Raw Water Pump 2 / Low Suction Pressure", "Low", 100, 120, 900),
    ("Chemical/ChlorineResidual", "Residual High",
     "Chemical / Chlorine Residual / High", "Low", 90, 300, 2400),
    ("Intake/WetWell/Level", "Low Level",
     "Intake / Wet Well / Low Level", "High", 16, 180, 1200),

    # --- rare, high consequence - the ones the customer cares about ------
    ("Chemical/ChlorineResidual", "Residual Below Compliance",
     "Chemical / Chlorine Residual / Below Compliance", "Critical", 7, 180, 1800),
    ("Filtration/CombinedTurbidity", "Regulatory Turbidity Exceedance",
     "Filtration / Combined Effluent / Regulatory Exceedance", "Critical", 5, 240, 2400),
    ("Distribution/ClearwaterTank/Level", "Level Critically Low",
     "Distribution / Clearwater Tank / Critically Low", "Critical", 4, 600, 5400),
    ("Distribution/NetworkPressure", "Low Pressure",
     "Distribution / Network / Low Pressure", "Critical", 4, 180, 1800),

    # --- diagnostics ----------------------------------------------------
    ("Plant/SCADACommsFault", "SCADA Comms Fault",
     "Plant / SCADA / Comms Fault", "Diagnostic", 60, 60, 600),

    # =====================================================================
    # ACME Manufacturing. Weighted to about the same total as the water
    # plant, so each site has a comparable history density and neither
    # dominates the other's analytics.
    # =====================================================================

    # --- bad actor: jams are the classic packaging nuisance alarm --------
    ("Packaging/CasePacker/Jam", "Jam Detected",
     "Packaging / Case Packer / Jam Detected", "Medium", 60, 30, 420),
    ("Packaging/Labeller/Jam", "Jam Detected",
     "Packaging / Labeller / Jam Detected", "Medium", 140, 30, 360),
    ("Filling/Filler/Jam", "Jam Detected",
     "Filling / Filler / Jam Detected", "Medium", 95, 30, 400),

    # --- routine --------------------------------------------------------
    ("Filling/FillRejectRate", "High Reject Rate",
     "Filling / Fill Level / High Reject Rate", "Medium", 85, 300, 3600),
    ("Mixing/SyrupTank/Level", "Level Low",
     "Mixing / Syrup Tank / Level Low", "Medium", 70, 1800, 14400),
    ("Packaging/Palletiser/Amps", "Motor Overload",
     "Packaging / Palletiser / Motor Overload", "Medium", 40, 60, 900),
    ("Filling/Filler/Amps", "Motor Overload",
     "Filling / Filler / Motor Overload", "Medium", 34, 60, 900),

    # --- higher consequence ---------------------------------------------
    ("Packaging/CasePacker/Fault", "Motor Fault",
     "Packaging / Case Packer / Motor Fault", "High", 44, 300, 4200),
    ("Filling/Filler/Fault", "Motor Fault",
     "Filling / Filler / Motor Fault", "High", 36, 300, 5400),
    ("Packaging/Palletiser/Fault", "Motor Fault",
     "Packaging / Palletiser / Motor Fault", "High", 30, 300, 4800),
    ("Mixing/Mixer01/Fault", "Motor Fault",
     "Mixing / Mixer 1 / Motor Fault", "High", 24, 300, 5400),
    ("Utilities/Chiller/SupplyTemp", "High Supply Temperature",
     "Utilities / Chiller / High Supply Temperature", "High", 30, 600, 7200),
    ("Utilities/AirCompressor/Pressure", "Low Air Pressure",
     "Utilities / Air Compressor / Low Pressure", "High", 26, 180, 2400),
    ("Filling/CO2Pressure", "Low CO2 Pressure",
     "Filling / CO2 / Low Pressure", "High", 28, 300, 3600),
    ("Mixing/BatchTemperature", "Batch Temperature High",
     "Mixing / Batch / Temperature High", "High", 22, 300, 2700),
    ("Mixing/SyrupTank/Level", "Level Critical",
     "Mixing / Syrup Tank / Level Critical", "High", 14, 900, 5400),

    # --- low background --------------------------------------------------
    ("Packaging/OEE", "OEE Below Target",
     "Packaging / Line / OEE Below Target", "Low", 180, 1800, 21600),

    # --- rare, expensive -------------------------------------------------
    ("Packaging/LineStopped", "Line Stopped",
     "Packaging / Line / Stopped", "Critical", 16, 300, 3600),
    ("Mixing/BatchTemperature", "Batch Over Temperature",
     "Mixing / Batch / Over Temperature", "Critical", 5, 240, 2400),

    # --- diagnostics -----------------------------------------------------
    ("Utilities/LineCommsFault", "Line PLC Comms Fault",
     "Utilities / Line PLC / Comms Fault", "Diagnostic", 55, 60, 600),
]

# Sources that chatter - they fire in tight bursts rather than singly.
CHATTERERS = {
    "Distribution / High Lift Pump 3 / Motor Fault": (4, 11),
    "Distribution / Network / High Pressure": (3, 7),
    # the manufacturing site gets its own bad actor, so the Pareto tells the
    # same story whichever plant the demo is showing
    "Packaging / Case Packer / Jam Detected": (4, 12),
}

# Typical minutes to acknowledge, and the chance the alarm is never acked at
# all. Operators chase Critical and ignore Low - that gap is worth showing.
ACK_BEHAVIOUR = {
    "Critical": (0.5, 4.0, 0.00),
    "High": (2.0, 25.0, 0.05),
    "Medium": (5.0, 90.0, 0.30),
    "Low": (15.0, 240.0, 0.65),
    "Diagnostic": (30.0, 480.0, 0.80),
}


def _source(tag_path, alarm_name):
    return "prov:%s:/tag:%s:/alm:%s" % (PROVIDER, tag_path, alarm_name)


def _hour_weight(hour):
    """Relative alarm likelihood by hour - tracks the demand peaks."""
    import math

    morning = math.exp(-((hour - 7.0) ** 2) / 5.0)
    evening = math.exp(-((hour - 19.0) ** 2) / 7.0)
    night = 0.25 if 0 <= hour < 5 else 0.0
    return 0.35 + 1.5 * morning + 1.7 * evening + night


def _pick(cum, total):
    r = random.random() * total
    for weight, item in cum:
        if r <= weight:
            return item
    return cum[-1][1]


# ---------------------------------------------------------------------------
# generation
# ---------------------------------------------------------------------------


def _generate(days, per_day):
    """Build the full list of (eventtime, eventtype, source, displaypath,
    priority, eventid) rows, plus the ack-notes rows for the data table."""
    now = system.date.now()
    start = system.date.addDays(system.date.midnight(now), -days)

    # weighted picker over the catalogue
    cum, total = [], 0
    for entry in CATALOGUE:
        total += entry[4]
        cum.append((total, entry))

    rows = []          # tuples for alarm_events
    seq = [0]

    def emit(ts, etype, src, disp, prio, eid):
        rows.append((ts, etype, src, disp, PRIORITY_NUM[prio], eid))

    def occurrence(active_ts, entry, dur_scale=1.0):
        tag_path, alarm_name, disp, prio, _w, dmin, dmax = entry
        seq[0] += 1
        # A real UUID, because the Alarm Journal Table parses eventid as one.
        # A readable marker like "bf-12-3456" reads fine in SQL and makes every
        # backfilled row invisible to the built-in journal component.
        eid = str(UUID.randomUUID())
        src = _source(tag_path, alarm_name)

        emit(active_ts, EVT_ACTIVE, src, disp, prio, eid)

        # acknowledge
        lo, hi, never = ACK_BEHAVIOUR[prio]
        acked = random.random() > never
        ack_ts = None
        if acked:
            mins = random.uniform(lo, hi)
            # a long tail: sometimes an operator is busy
            if random.random() < 0.12:
                mins *= random.uniform(3.0, 8.0)
            ack_ts = system.date.addSeconds(active_ts, int(mins * 60))

        # clear
        dur = random.uniform(dmin, dmax) * dur_scale
        clear_ts = system.date.addSeconds(active_ts, int(dur))

        events = []
        if ack_ts is not None:
            events.append((ack_ts, EVT_ACK))
        events.append((clear_ts, EVT_CLEAR))
        events.sort(key=lambda e: system.date.toMillis(e[0]))
        for ts, etype in events:
            if system.date.isBefore(ts, now):
                emit(ts, etype, src, disp, prio, eid)
        return eid

    # storm days - a cross-area cascade, three of them spread through the window
    storm_days = set(
        random.sample(range(2, days - 1), 3) if days > 6 else []
    )

    for d in range(days):
        day_start = system.date.addDays(start, d)
        dow = system.date.getDayOfWeek(day_start)  # 1=Sun .. 7=Sat

        day_factor = 1.0
        if dow in (1, 7):
            day_factor = 0.55           # quiet weekend
        elif dow == 2:
            day_factor = 1.35           # Monday catch-up
        # a slow improvement trend across the window, so the daily trend chart
        # tells a story rather than sitting flat
        day_factor *= 1.25 - 0.4 * (float(d) / max(days - 1, 1))

        count = int(random.gauss(per_day * day_factor, per_day * 0.18))
        count = max(count, 4)

        for _ in range(count):
            # pick an hour from the diurnal shape
            hours = range(24)
            weights = [_hour_weight(h) for h in hours]
            tw = sum(weights)
            r, acc, hour = random.random() * tw, 0.0, 23
            for h, wt in zip(hours, weights):
                acc += wt
                if r <= acc:
                    hour = h
                    break
            ts = system.date.addSeconds(
                day_start, hour * 3600 + random.randint(0, 3599)
            )
            if not system.date.isBefore(ts, now):
                continue

            entry = _pick(cum, total)
            disp = entry[2]
            if disp in CHATTERERS:
                lo, hi = CHATTERERS[disp]
                burst_ts = ts
                for _b in range(random.randint(lo, hi)):
                    if not system.date.isBefore(burst_ts, now):
                        break
                    occurrence(burst_ts, entry, dur_scale=0.05)
                    burst_ts = system.date.addSeconds(
                        burst_ts, random.randint(20, 150)
                    )
            else:
                occurrence(ts, entry)

        # storm cascade
        if d in storm_days:
            storm_start = system.date.addSeconds(
                day_start, random.randint(4, 16) * 3600
            )
            cascade = [
                "Intake / Raw Water / High Turbidity",
                "Filtration / Filter A / Backwash Required",
                "Filtration / Filter B / Backwash Required",
                "Filtration / Filter C / Backwash Required",
                "Filtration / Filter B / Turbidity Breakthrough",
                "Chemical / pH / Out Of Range",
                "Filtration / Combined Effluent / Regulatory Exceedance",
                "Intake / Wet Well / High Level",
                "Distribution / Clearwater Tank / Low",
            ]
            by_disp = {}
            for e in CATALOGUE:
                by_disp.setdefault(e[2], e)
            offset = 0
            for disp in cascade:
                entry = by_disp.get(disp)
                if entry is None:
                    continue
                ts = system.date.addSeconds(storm_start, offset)
                if system.date.isBefore(ts, now):
                    occurrence(ts, entry, dur_scale=1.6)
                offset += random.randint(120, 900)

    rows.sort(key=lambda r: system.date.toMillis(r[0]))
    return rows


# ---------------------------------------------------------------------------
# database
# ---------------------------------------------------------------------------


def ensureSchema():
    """Create the journal tables if the profile has not written an event yet.

    Ignition creates them itself on the first journalled event, but the backfill
    inserts straight into them - so on a brand new gateway it would otherwise
    fail on a table that is about to exist. Same DDL as sql/01-journal-tables.sql;
    the two are kept in step deliberately so a hand-built database and a
    scripted one end up identical.
    """
    system.db.runUpdateQuery(
        "CREATE TABLE IF NOT EXISTS %s ("
        "  id SERIAL, eventid VARCHAR(255), source VARCHAR(255),"
        "  displaypath VARCHAR(255), priority INTEGER, eventtype INTEGER,"
        "  eventflags INTEGER, eventtime TIMESTAMP NOT NULL,"
        "  PRIMARY KEY (id, eventtime))" % TABLE, DB)
    system.db.runUpdateQuery(
        "CREATE TABLE IF NOT EXISTS %s ("
        "  id INTEGER, propname VARCHAR(255), dtype INTEGER, intvalue BIGINT,"
        "  floatvalue DOUBLE PRECISION, strvalue TEXT)" % DATA_TABLE, DB)
    system.db.runUpdateQuery(
        "CREATE INDEX IF NOT EXISTS alarm_event_dataidndx ON %s (id)"
        % DATA_TABLE, DB)
    system.db.runUpdateQuery(
        "CREATE INDEX IF NOT EXISTS alarm_events_time_type_idx ON %s "
        "(eventtime, eventtype)" % TABLE, DB)
    return True


def clear():
    """Empty the journal.

    Everything, not just the generated rows: this journal profile exists only
    for the demo, and now that backfilled rows carry real UUIDs there is no
    marker left to tell them apart. On a shared journal this would be the wrong
    thing to do - see the README before pointing the profile at one.
    """
    n = system.db.runUpdateQuery("DELETE FROM %s" % TABLE, DB)
    system.db.runUpdateQuery("DELETE FROM %s" % DATA_TABLE, DB)
    LOG.info("cleared %d journal rows" % n)
    return n


def run(days=30, perDay=85, wipe=True):
    """Generate and insert the history. Returns the number of rows written."""
    ensureSchema()
    if wipe:
        clear()

    rows = _generate(days, perDay)
    LOG.info("generating %d journal rows over %d days" % (len(rows), days))

    # batch in chunks - one runPrepUpdate per row is far too slow for 10k rows
    CHUNK = 200
    written = 0
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i : i + CHUNK]
        values = (
            "INSERT INTO %s (eventtime, eventtype, source, displaypath, "
            "priority, eventflags, eventid) VALUES " % TABLE
            + ", ".join(["(?, ?, ?, ?, ?, ?, ?)"] * len(chunk))
        )
        args = []
        for r in chunk:
            args.extend([r[0], r[1], r[2], r[3], r[4],
                         FLAGS.get(r[1], 0), r[5]])
        system.db.runPrepUpdate(values, args, DB)
        written += len(chunk)

    LOG.info("backfill complete: %d rows" % written)
    return written


def summary():
    """Quick sanity check - what is actually in the journal."""
    return system.db.runQuery(
        "SELECT priority, eventtype, COUNT(*) AS n, MIN(eventtime) AS first, "
        "MAX(eventtime) AS last FROM %s GROUP BY priority, eventtype "
        "ORDER BY priority DESC, eventtype" % TABLE,
        DB,
    )
