"""
AlarmDemo.sim - plant simulation engine.

Driven by the PlantSim gateway timer (1 s). Everything the demo shows is
produced here: there is no OPC device and no external dependency, so the whole
demo moves to another gateway with nothing but the project and the tag export.

The model is a small potable water treatment plant:

    demand curve  ->  high lift pumps  ->  clearwater tank drains
    wet well      ->  raw water pumps  ->  filters  ->  clearwater tank fills
    dosing skids  ->  chlorine residual / pH

Values are integrated rather than randomised, so trends look like a plant
rather than like noise: the tank actually empties when demand beats production,
filters actually load up until they are backwashed, and the chlorine residual
actually follows the dose pump.

Scenarios (see AlarmDemo.demo) bias the model rather than writing alarms
directly - the alarms then fire through the normal Ignition alarm pipeline,
which is the point of the demonstration.
"""

import math
import random

P = "[AlarmDemo]"

LOG = system.util.getLogger("AlarmDemo.sim")


# ---------------------------------------------------------------------------
# tag io
# ---------------------------------------------------------------------------


def _read(paths):
    """Batch read -> dict of {path: value}. Bad quality reads come back as None."""
    full = [P + p for p in paths]
    qvs = system.tag.readBlocking(full)
    out = {}
    for path, qv in zip(paths, qvs):
        out[path] = qv.value if qv.quality.isGood() else None
    return out


def _write(values):
    """Batch write from a {path: value} dict."""
    if not values:
        return
    paths = list(values.keys())
    system.tag.writeBlocking([P + p for p in paths], [values[p] for p in paths])


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ---------------------------------------------------------------------------
# demand model
# ---------------------------------------------------------------------------


def _demand_factor(now):
    """Diurnal water demand, 0.55 .. 1.35 of average.

    Two peaks - morning shower peak around 07:00 and an evening peak around
    19:00 - which is what real reticulation demand looks like and makes the
    24 h trends on the dashboard immediately readable.
    """
    hour = system.date.getHour24(now) + system.date.getMinute(now) / 60.0
    morning = math.exp(-((hour - 7.0) ** 2) / 4.0)
    evening = math.exp(-((hour - 19.0) ** 2) / 6.0)
    base = 0.62 + 0.55 * morning + 0.62 * evening
    # weekends run flatter and slightly lower
    if system.date.getDayOfWeek(now) in (1, 7):
        base = 0.60 + 0.80 * (base - 0.62)
    return _clamp(base, 0.5, 1.4)


def _noise(scale):
    return random.gauss(0.0, scale)


# ---------------------------------------------------------------------------
# main tick
# ---------------------------------------------------------------------------

PATHS = [
    # plant
    "Plant/PlantMode",
    "Plant/DemoScenario",
    "Plant/DemoScenarioActive",
    "Plant/PLCHeartbeat",
    "Plant/SCADACommsFault",
    # intake
    "Intake/WetWell/Level",
    "Intake/RawWaterFlow",
    "Intake/RawTurbidity",
    "Intake/RawWaterPump01/Run",
    "Intake/RawWaterPump01/Fault",
    "Intake/RawWaterPump01/Amps",
    "Intake/RawWaterPump01/SuctionPressure",
    "Intake/RawWaterPump01/RunHours",
    "Intake/RawWaterPump02/Run",
    "Intake/RawWaterPump02/Fault",
    "Intake/RawWaterPump02/Amps",
    "Intake/RawWaterPump02/SuctionPressure",
    "Intake/RawWaterPump02/RunHours",
    # filtration
    "Filtration/FilteredFlow",
    "Filtration/CombinedTurbidity",
    # chemical
    "Chemical/ChlorineResidual",
    "Chemical/pH",
    # distribution
    "Distribution/ClearwaterTank/Level",
    "Distribution/ClearwaterTank/Volume",
    "Distribution/NetworkPressure",
    "Distribution/NetworkFlow",
]

FILTERS = ["A", "B", "C"]
for _f in FILTERS:
    PATHS += [
        "Filtration/Filter%s/DiffPressure" % _f,
        "Filtration/Filter%s/Turbidity" % _f,
        "Filtration/Filter%s/BackwashActive" % _f,
        "Filtration/Filter%s/Flow" % _f,
        "Filtration/Filter%s/RunHours" % _f,
    ]

SKIDS = ["Chlorine", "Fluoride", "Coagulant"]
for _s in SKIDS:
    PATHS += [
        "Chemical/%s/TankLevel" % _s,
        "Chemical/%s/DoseRate" % _s,
        "Chemical/%s/PumpRun" % _s,
        "Chemical/%s/PumpFault" % _s,
    ]

HL_PUMPS = [1, 2, 3]
for _p in HL_PUMPS:
    PATHS += [
        "Distribution/HighLiftPump%02d/Run" % _p,
        "Distribution/HighLiftPump%02d/Fault" % _p,
        "Distribution/HighLiftPump%02d/Amps" % _p,
        "Distribution/HighLiftPump%02d/DischargePressure" % _p,
        "Distribution/HighLiftPump%02d/RunHours" % _p,
    ]

# seconds per tick - the timer runs at 1 s but the plant is simulated at 60x so
# tank levels, filter loading and chemical consumption move at a pace you can
# actually demonstrate inside a meeting.
DT = 60.0
DT_H = DT / 3600.0


def tick():
    """One simulation step. Never raises - a demo must not stop on a bad tick."""
    try:
        _tick()
    except:
        import traceback
        LOG.error("sim tick failed: %s" % traceback.format_exc())


def _tick():
    t = _read(PATHS)
    w = {}
    now = system.date.now()
    scenario = t.get("Plant/DemoScenario") or "None"
    demand = _demand_factor(now)

    # ---- scenario biases -------------------------------------------------
    storm = scenario == "Storm"
    dose_fail = scenario == "ChlorineFailure"
    pump_fail = scenario == "PumpFailure"
    blinding = scenario == "FilterBlinding"
    comms = scenario == "CommsLoss"
    chatter = scenario == "Chattering"

    # ---- heartbeat / comms ----------------------------------------------
    hb = (t.get("Plant/PLCHeartbeat") or 0) + 1
    w["Plant/PLCHeartbeat"] = hb % 32767
    w["Plant/SCADACommsFault"] = bool(comms)

    # ---- distribution demand --------------------------------------------
    avg_demand = 170.0
    net_flow = avg_demand * demand + _noise(3.0)
    w["Distribution/NetworkFlow"] = round(net_flow, 1)

    tank = t.get("Distribution/ClearwaterTank/Level")
    tank = 68.0 if tank is None else tank

    # ---- high lift pumps: run enough pumps to meet demand ----------------
    # each pump moves ~85 L/s; pump 3 is the standby
    needed = int(math.ceil(net_flow / 85.0))
    needed = _clamp(needed, 1, 3)
    if tank < 18.0:
        needed = 1  # protect the tank

    hl_running = 0
    hl_amps_total = 0.0
    for p in HL_PUMPS:
        base = "Distribution/HighLiftPump%02d/" % p
        fault = bool(t.get(base + "Fault"))

        if pump_fail and p == 1:
            fault = True
        elif chatter and p == 3:
            # deliberate chattering source - flips roughly every few seconds
            fault = random.random() < 0.35
        elif fault:
            # faults clear on their own after a while so the demo self-heals
            if random.random() < 0.02:
                fault = False
        elif random.random() < 0.00012:
            fault = True

        run = (not fault) and (hl_running < needed)
        if run:
            hl_running += 1
            amps = 46.0 + 14.0 * (net_flow / 200.0) + _noise(1.2)
            disch = 640.0 + 40.0 * (tank / 100.0) + _noise(8.0)
            w[base + "RunHours"] = round((t.get(base + "RunHours") or 0.0) + DT_H, 2)
        else:
            amps = 0.0
            disch = 0.0
        hl_amps_total += amps

        w[base + "Fault"] = fault
        w[base + "Run"] = run
        w[base + "Amps"] = round(_clamp(amps, 0.0, 90.0), 1)
        w[base + "DischargePressure"] = round(_clamp(disch, 0.0, 900.0), 0)

    # network pressure follows how many pumps are actually running vs demand
    if hl_running == 0:
        press = 90.0 + _noise(10.0)
    else:
        capacity = hl_running * 85.0
        press = 520.0 + 260.0 * (capacity - net_flow) / max(capacity, 1.0) + _noise(6.0)
    w["Distribution/NetworkPressure"] = round(_clamp(press, 0.0, 900.0), 0)

    # ---- intake / raw water pumps ---------------------------------------
    wet = t.get("Intake/WetWell/Level")
    wet = 65.0 if wet is None else wet

    # production target: refill the tank, more aggressively when it is low
    target_prod = _clamp(net_flow * (1.0 + (70.0 - tank) / 100.0), 60.0, 260.0)
    # hysteresis on the pump count, otherwise the duty pump bang-bangs around
    # the changeover point and manufactures a chattering alarm we did not ask for
    rw_now = sum(1 for p in (1, 2) if t.get("Intake/RawWaterPump%02d/Run" % p))
    if rw_now >= 2:
        rw_needed = 2 if target_prod > 115.0 else 1
    else:
        rw_needed = 2 if target_prod > 145.0 else 1
    if wet < 12.0:
        rw_needed = 0  # cavitation protection

    rw_running = 0
    raw_flow = 0.0
    for p in (1, 2):
        base = "Intake/RawWaterPump%02d/" % p
        fault = bool(t.get(base + "Fault"))
        if pump_fail and p == 2:
            fault = True
        elif fault:
            if random.random() < 0.02:
                fault = False
        elif random.random() < 0.0001:
            fault = True

        run = (not fault) and (rw_running < rw_needed)
        if run:
            rw_running += 1
            share = target_prod / max(rw_needed, 1)
            raw_flow += share
            amps = 32.0 + 12.0 * (share / 130.0) + _noise(1.0)
            if blinding:
                amps += 9.0  # working against a loaded filter bank
            suction = 40.0 + 1.4 * wet + _noise(3.0)
            w[base + "RunHours"] = round((t.get(base + "RunHours") or 0.0) + DT_H, 2)
        else:
            amps = 0.0
            suction = 20.0 + 1.2 * wet + _noise(2.0)

        w[base + "Fault"] = fault
        w[base + "Run"] = run
        w[base + "Amps"] = round(_clamp(amps, 0.0, 60.0), 1)
        w[base + "SuctionPressure"] = round(_clamp(suction, 0.0, 300.0), 0)

    w["Intake/RawWaterFlow"] = round(raw_flow, 1)

    # Wet well: gravity-fed from the river, so inflow falls as the well fills
    # (less head across the inlet). That negative feedback is what makes the
    # level self-regulate around whatever the raw pumps are drawing, instead of
    # pegging at 0 or 100 the moment inflow and draw differ.
    inflow = 300.0 * (1.0 - wet / 115.0) + _noise(4.0)
    if storm:
        inflow += 130.0
    inflow = max(inflow, 0.0)
    wet_next = wet + (inflow - raw_flow) * DT / 3600.0
    w["Intake/WetWell/Level"] = round(_clamp(wet_next, 0.0, 100.0), 1)

    # raw turbidity: normally single digits, spikes hard in a storm
    raw_turb = t.get("Intake/RawTurbidity") or 8.0
    target_turb = 95.0 if storm else 7.5
    raw_turb += (target_turb - raw_turb) * 0.05 + _noise(0.7)
    w["Intake/RawTurbidity"] = round(_clamp(raw_turb, 0.2, 200.0), 2)

    # ---- filtration ------------------------------------------------------
    per_filter = raw_flow / 3.0 if raw_flow > 0 else 0.0
    filtered_total = 0.0
    turb_sum = 0.0
    turb_n = 0

    for f in FILTERS:
        base = "Filtration/Filter%s/" % f
        dp = t.get(base + "DiffPressure")
        dp = 25.0 if dp is None else dp
        bw = bool(t.get(base + "BackwashActive"))

        if bw:
            # backwashing: offline, head loss recovering fast
            dp -= 9.0
            flow = 0.0
            turb = 0.02
            if dp <= 18.0:
                bw = False
        else:
            # loading rate scales with flow and raw turbidity
            load = 0.055 * (per_filter / 60.0) * (1.0 + raw_turb / 30.0)
            if blinding and f == "B":
                load *= 6.0
            dp += load * DT / 60.0 + _noise(0.05)
            flow = per_filter + _noise(1.0)
            # effluent turbidity creeps up as the filter loads, and breaks
            # through once head loss is high
            breakthrough = max(0.0, (dp - 62.0) / 55.0)
            turb = 0.055 + 0.02 * (raw_turb / 30.0) + breakthrough + abs(_noise(0.012))
            # auto backwash on high head loss
            if dp > 72.0:
                bw = True

        w[base + "DiffPressure"] = round(_clamp(dp, 0.0, 100.0), 1)
        w[base + "Turbidity"] = round(_clamp(turb, 0.0, 2.0), 3)
        w[base + "BackwashActive"] = bw
        w[base + "Flow"] = round(max(flow, 0.0), 1)
        if not bw:
            w[base + "RunHours"] = round((t.get(base + "RunHours") or 0.0) + DT_H, 2)
            filtered_total += max(flow, 0.0)
            turb_sum += turb
            turb_n += 1

    w["Filtration/FilteredFlow"] = round(filtered_total, 1)
    combined = (turb_sum / turb_n) if turb_n else 0.05
    w["Filtration/CombinedTurbidity"] = round(_clamp(combined, 0.0, 2.0), 3)

    # ---- chemical dosing -------------------------------------------------
    for s in SKIDS:
        base = "Chemical/%s/" % s
        lvl = t.get(base + "TankLevel")
        lvl = 72.0 if lvl is None else lvl
        fault = bool(t.get(base + "PumpFault"))

        if dose_fail and s == "Chlorine":
            fault = True
        elif fault:
            if random.random() < 0.03:
                fault = False
        elif random.random() < 0.00008:
            fault = True

        run = (not fault) and filtered_total > 5.0
        if run:
            # consumption scales with treated flow
            lvl -= (filtered_total / 175.0) * 0.09 * DT / 60.0
        # refill when the operator would have called for a delivery
        if lvl < 6.0:
            lvl = 95.0
        w[base + "TankLevel"] = round(_clamp(lvl, 0.0, 100.0), 1)
        w[base + "PumpFault"] = fault
        w[base + "PumpRun"] = run

    # chlorine residual: driven by whether the chlorine skid is actually dosing
    res = t.get("Chemical/ChlorineResidual")
    res = 1.05 if res is None else res
    cl_ok = bool(w.get("Chemical/Chlorine/PumpRun"))
    cl_level = w.get("Chemical/Chlorine/TankLevel", 70.0)
    if cl_ok and cl_level > 4.0:
        target_res = 1.15 - 0.25 * (raw_turb / 60.0)
    else:
        target_res = 0.05
    res += (target_res - res) * 0.06 + _noise(0.015)
    w["Chemical/ChlorineResidual"] = round(_clamp(res, 0.0, 4.0), 3)
    w["Chemical/Chlorine/DoseRate"] = round(_clamp(2.2 + (1.1 - res) * 1.5, 0.0, 6.0), 2)
    w["Chemical/Fluoride/DoseRate"] = round(_clamp(0.9 + _noise(0.03), 0.0, 2.7), 2)
    w["Chemical/Coagulant/DoseRate"] = round(
        _clamp(16.0 + raw_turb * 0.35 + _noise(0.6), 0.0, 54.0), 1
    )

    # pH drifts with coagulant dose; a storm pushes it around
    ph = t.get("Chemical/pH") or 7.4
    target_ph = 7.35 - (w["Chemical/Coagulant/DoseRate"] - 18.0) * 0.035
    if storm:
        target_ph -= 0.55
    ph += (target_ph - ph) * 0.07 + _noise(0.02)
    w["Chemical/pH"] = round(_clamp(ph, 4.0, 11.0), 2)

    # ---- clearwater tank -------------------------------------------------
    tank_next = tank + (filtered_total - net_flow) * DT / 2600.0
    tank_next = _clamp(tank_next, 0.0, 100.0)
    w["Distribution/ClearwaterTank/Level"] = round(tank_next, 1)
    w["Distribution/ClearwaterTank/Volume"] = round(tank_next * 100.0, 0)

    _write(w)
