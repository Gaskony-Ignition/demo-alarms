"""
AlarmDemo.simmfg - ACME Manufacturing simulation (beverage bottling line).

Same contract as AlarmDemo.sim: driven by the PlantSim timer, writes only
memory tags, no external dependency. The two sites run side by side so that
switching between them is instant and both have live alarms.

The line is modelled as a chain, because that is what makes a packaging demo
read as real: a fault or a jam anywhere stops everything downstream, the line
stop is what actually costs money, and OEE falls out of accumulated downtime
rather than being a number that wanders on its own.

    mixing  ->  filling  ->  capping  ->  labelling  ->  case packing  ->  palletising
"""

import math
import random

P = "[AlarmDemo]"

LOG = system.util.getLogger("AlarmDemo.simmfg")

# machines in line order: (tag folder, area, base amps)
LINE = [
    ("Mixing/Mixer01", "Mixing", 41.0),
    ("Mixing/Mixer02", "Mixing", 41.0),
    ("Filling/Filler", "Filling", 52.0),
    ("Filling/Capper", "Filling", 29.0),
    ("Packaging/Labeller", "Packaging", 18.0),
    ("Packaging/CasePacker", "Packaging", 33.0),
    ("Packaging/Palletiser", "Packaging", 44.0),
]

PATHS = [
    "Utilities/DemoScenario",
    "Mixing/SyrupTank/Level",
    "Mixing/BatchTemperature",
    "Mixing/BatchProgress",
    "Filling/CO2Pressure",
    "Filling/FillRejectRate",
    "Filling/FillRate",
    "Packaging/LineSpeed",
    "Packaging/OEE",
    "Packaging/LineStopped",
    "Packaging/CasesProduced",
    "Utilities/AirCompressor/Run",
    "Utilities/AirCompressor/Fault",
    "Utilities/AirCompressor/Pressure",
    "Utilities/Chiller/Run",
    "Utilities/Chiller/Fault",
    "Utilities/Chiller/SupplyTemp",
    "Utilities/LineCommsFault",
]
for _m, _a, _b in LINE:
    PATHS += [_m + "/Run", _m + "/Fault", _m + "/Jam", _m + "/Amps",
              _m + "/RunHours"]

DT = 60.0          # same 60x time compression as the water plant
DT_H = DT / 3600.0


def _read(paths):
    qvs = system.tag.readBlocking([P + p for p in paths])
    out = {}
    for path, qv in zip(paths, qvs):
        out[path] = qv.value if qv.quality.isGood() else None
    return out


def _write(values):
    if not values:
        return
    keys = list(values.keys())
    system.tag.writeBlocking([P + k for k in keys], [values[k] for k in keys])


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _noise(s):
    return random.gauss(0.0, s)


def tick():
    try:
        _tick()
    except:
        import traceback
        LOG.error("simmfg tick failed: %s" % traceback.format_exc())


def _tick():
    t = _read(PATHS)
    w = {}
    now = system.date.now()
    scenario = t.get("Utilities/DemoScenario") or "None"

    line_jam = scenario == "LineJam"
    chiller_fail = scenario == "ChillerFailure"
    air_loss = scenario == "AirLoss"
    comms = scenario == "CommsLoss"
    batch_hot = scenario == "BatchOverTemp"

    w["Utilities/LineCommsFault"] = bool(comms)

    # ---- utilities --------------------------------------------------------
    comp_fault = bool(t.get("Utilities/AirCompressor/Fault"))
    if air_loss:
        comp_fault = True
    elif comp_fault and random.random() < 0.03:
        comp_fault = False
    elif random.random() < 0.00008:
        comp_fault = True
    w["Utilities/AirCompressor/Fault"] = comp_fault
    w["Utilities/AirCompressor/Run"] = not comp_fault

    air = t.get("Utilities/AirCompressor/Pressure")
    air = 690.0 if air is None else air
    # receiver drains when the compressor is down, otherwise cycles on control
    air += (-38.0 if comp_fault else (700.0 - air) * 0.18) + _noise(3.0)
    air = _clamp(air, 0.0, 1000.0)
    w["Utilities/AirCompressor/Pressure"] = round(air, 0)

    ch_fault = bool(t.get("Utilities/Chiller/Fault"))
    if chiller_fail:
        ch_fault = True
    elif ch_fault and random.random() < 0.03:
        ch_fault = False
    elif random.random() < 0.00007:
        ch_fault = True
    w["Utilities/Chiller/Fault"] = ch_fault
    w["Utilities/Chiller/Run"] = not ch_fault

    chw = t.get("Utilities/Chiller/SupplyTemp")
    chw = 6.0 if chw is None else chw
    chw += ((22.0 - chw) * 0.06 if ch_fault else (5.8 - chw) * 0.15) + _noise(0.15)
    w["Utilities/Chiller/SupplyTemp"] = round(_clamp(chw, -10.0, 30.0), 1)

    # air below the pneumatic limit stops the line just as surely as a fault
    air_ok = air > 500.0

    # ---- machines ---------------------------------------------------------
    # A machine is down if it is faulted or jammed; everything downstream of a
    # down machine is starved and stops too.
    down_index = None
    states = []
    for i, (m, _area, base) in enumerate(LINE):
        fault = bool(t.get(m + "/Fault"))
        jam = bool(t.get(m + "/Jam"))

        if line_jam and m == "Packaging/CasePacker":
            jam = True
        else:
            if jam and random.random() < 0.06:
                jam = False          # operator clears it
            elif not jam and random.random() < 0.0009:
                jam = True
            if fault and random.random() < 0.025:
                fault = False
            elif not fault and random.random() < 0.00012:
                fault = True

        states.append([m, base, fault, jam])
        if (fault or jam) and down_index is None:
            down_index = i

    running_any = False
    for i, (m, base, fault, jam) in enumerate(states):
        blocked = (down_index is not None and i >= down_index) or not air_ok
        run = not fault and not jam and not blocked
        if run:
            running_any = True
            amps = base + _noise(1.1)
            w[m + "/RunHours"] = round((t.get(m + "/RunHours") or 0.0) + DT_H, 2)
        else:
            amps = 0.0
        w[m + "/Fault"] = fault
        w[m + "/Jam"] = jam
        w[m + "/Run"] = run
        w[m + "/Amps"] = round(max(amps, 0.0), 1)

    line_stopped = (down_index is not None) or not air_ok
    w["Packaging/LineStopped"] = bool(line_stopped)

    # ---- rates ------------------------------------------------------------
    target_bpm = 480.0
    speed = 0.0 if line_stopped else target_bpm + _noise(6.0)
    w["Packaging/LineSpeed"] = round(speed, 0)
    w["Filling/FillRate"] = round(speed, 0)

    cases = (t.get("Packaging/CasesProduced") or 0)
    # 24 bottles to a case, DT seconds of production per tick
    w["Packaging/CasesProduced"] = int(cases + (speed / 24.0) * (DT / 60.0))

    # ---- mixing -----------------------------------------------------------
    syrup = t.get("Mixing/SyrupTank/Level")
    syrup = 70.0 if syrup is None else syrup
    if not line_stopped:
        syrup -= 0.055 * (speed / target_bpm) * DT / 60.0
    if syrup < 8.0:
        syrup = 92.0                      # transfer from bulk storage
    w["Mixing/SyrupTank/Level"] = round(_clamp(syrup, 0.0, 100.0), 1)

    prog = (t.get("Mixing/BatchProgress") or 0.0)
    prog = 0.0 if prog >= 100.0 else prog + (0.0 if line_stopped else 1.6)
    w["Mixing/BatchProgress"] = round(_clamp(prog, 0.0, 100.0), 0)

    # batch temperature tracks chilled water, plus mixing work
    bt = t.get("Mixing/BatchTemperature")
    bt = 22.5 if bt is None else bt
    target_bt = chw + 16.0 + (3.5 if not line_stopped else 0.0)
    if batch_hot:
        target_bt = 52.0
    bt += (target_bt - bt) * 0.08 + _noise(0.15)
    w["Mixing/BatchTemperature"] = round(_clamp(bt, 0.0, 90.0), 1)

    # ---- filling ----------------------------------------------------------
    co2 = t.get("Filling/CO2Pressure")
    co2 = 420.0 if co2 is None else co2
    target_co2 = 250.0 if scenario == "CO2Loss" else 425.0
    co2 += (target_co2 - co2) * 0.09 + _noise(4.0)
    w["Filling/CO2Pressure"] = round(_clamp(co2, 0.0, 700.0), 0)

    # rejects climb when carbonation or temperature drift out of band
    rej = t.get("Filling/FillRejectRate")
    rej = 0.6 if rej is None else rej
    target_rej = 0.55
    if co2 < 300.0:
        target_rej += (300.0 - co2) / 22.0
    if bt > 34.0:
        target_rej += (bt - 34.0) / 3.5
    rej += (target_rej - rej) * 0.12 + abs(_noise(0.06))
    w["Filling/FillRejectRate"] = round(_clamp(rej, 0.0, 20.0), 2)

    # ---- OEE --------------------------------------------------------------
    # A slow exponential average of availability x quality, so a line stop
    # visibly drags it down and it recovers over a believable period rather
    # than snapping back the moment the fault clears.
    oee = t.get("Packaging/OEE")
    oee = 87.0 if oee is None else oee
    instant = 0.0 if line_stopped else (100.0 - rej * 1.8) * 0.965
    oee += (instant - oee) * 0.04
    w["Packaging/OEE"] = round(_clamp(oee, 0.0, 100.0), 1)

    _write(w)
