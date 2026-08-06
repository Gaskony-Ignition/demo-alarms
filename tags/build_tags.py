#!/usr/bin/env python3
"""Generate the AlarmDemo tag tree.

Emits two things from one model:

  build/ondisk/<Area>/tags.json + unary-resource.json
      drop straight into  data/config/resources/core/ignition/tag-definition/AlarmDemo/
      then run a gateway config scan.

  build/AlarmDemo-tags.json
      a single Designer-importable tag export (Tag Browser -> Import), for moving
      the demo to any other 8.3 gateway.

Areas sit at the root of the provider on purpose: both the Exchange "Alarm
Intelligence Center" and this project derive an alarm's Area from the first tag
path segment.
"""

import json
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def folder(name, *children):
    return {"name": name, "tagType": "Folder", "tags": list(children)}


def mem(name, dtype, value, **kw):
    tag = {
        "name": name,
        "tagType": "AtomicTag",
        "valueSource": "memory",
        "dataType": dtype,
        "value": value,
    }
    alarms = kw.pop("alarms", None)
    tag.update(kw)
    if alarms:
        tag["alarms"] = alarms
    return tag


def analog(name, value, unit, lo, hi, fmt="#,##0.00", **kw):
    return mem(
        name,
        "Float8",
        value,
        engUnit=unit,
        engLow=lo,
        engHigh=hi,
        formatString=fmt,
        **kw
    )


def boolean(name, value=False, **kw):
    return mem(name, "Boolean", value, **kw)


def alarm(name, mode, priority, display, **kw):
    """One alarm definition. `display` becomes the Display Path, which is what
    every alarm table and the analytics group-by actually show."""
    a = {
        "name": name,
        "mode": mode,
        "priority": priority,
        "displayPath": display,
        "ackMode": "Manual",
        "notes": kw.pop("notes", ""),
    }
    a.update(kw)
    return a


# --------------------------------------------------------------------------
# plant model - a mid-size potable water treatment plant
# --------------------------------------------------------------------------

AREAS = {}


def raw_water_pump(n):
    """Raw water pump: run/fault/amps/suction, with a fault + overload alarm."""
    tag = "Raw Water Pump %d" % n
    return folder(
        "RawWaterPump%02d" % n,
        boolean("Run"),
        boolean(
            "Fault",
            alarms=[
                alarm(
                    "Motor Fault",
                    "Equality",
                    "High",
                    "Intake / %s / Motor Fault" % tag,
                    setpointA=True,
                    notes="Motor protection relay tripped. Check overload, "
                    "phase failure and thermistor before resetting.",
                )
            ],
        ),
        analog(
            "Amps",
            0.0,
            "A",
            0.0,
            60.0,
            alarms=[
                alarm(
                    "Motor Overload",
                    "AboveValue",
                    "Medium",
                    "Intake / %s / Motor Overload" % tag,
                    setpointA=48.0,
                    deadband=2.0,
                    timeOnDelaySeconds=10,
                    notes="Running above 48 A. Check for blockage or worn impeller.",
                )
            ],
        ),
        analog(
            "SuctionPressure",
            120.0,
            "kPa",
            0.0,
            300.0,
            alarms=[
                alarm(
                    "Low Suction Pressure",
                    "BelowValue",
                    "Low",
                    "Intake / %s / Low Suction Pressure" % tag,
                    setpointA=40.0,
                    deadband=5.0,
                    timeOnDelaySeconds=15,
                    notes="Possible strainer blockage or low wet well level.",
                )
            ],
        ),
        analog("RunHours", 0.0, "h", 0.0, 100000.0, fmt="#,##0"),
    )


AREAS["Intake"] = [
    raw_water_pump(1),
    raw_water_pump(2),
    folder(
        "WetWell",
        analog(
            "Level",
            65.0,
            "%",
            0.0,
            100.0,
            alarms=[
                alarm(
                    "High Level",
                    "AboveValue",
                    "Medium",
                    "Intake / Wet Well / High Level",
                    setpointA=90.0,
                    deadband=3.0,
                    notes="Inflow exceeding pumped output. Check pump availability.",
                ),
                alarm(
                    "Low Level",
                    "BelowValue",
                    "High",
                    "Intake / Wet Well / Low Level",
                    setpointA=20.0,
                    deadband=3.0,
                    notes="Risk of pump cavitation. Pumps will inhibit below 12%.",
                ),
            ],
        ),
    ),
    analog("RawWaterFlow", 180.0, "L/s", 0.0, 400.0),
    analog(
        "RawTurbidity",
        8.0,
        "NTU",
        0.0,
        200.0,
        alarms=[
            alarm(
                "High Raw Turbidity",
                "AboveValue",
                "Low",
                "Intake / Raw Water / High Turbidity",
                setpointA=50.0,
                deadband=5.0,
                timeOnDelaySeconds=30,
                notes="Catchment runoff event. Increase coagulant dose and "
                "watch filter loading.",
            )
        ],
    ),
]


def filter_bank(letter):
    tag = "Filter %s" % letter
    return folder(
        "Filter%s" % letter,
        analog(
            "DiffPressure",
            25.0,
            "kPa",
            0.0,
            100.0,
            alarms=[
                alarm(
                    "Backwash Required",
                    "AboveValue",
                    "Medium",
                    "Filtration / %s / Backwash Required" % tag,
                    setpointA=60.0,
                    deadband=8.0,
                    notes="Head loss above 60 kPa. Schedule a backwash.",
                ),
                alarm(
                    "High Head Loss",
                    "AboveValue",
                    "High",
                    "Filtration / %s / High Head Loss" % tag,
                    setpointA=80.0,
                    deadband=5.0,
                    notes="Filter is blinding. Take offline and backwash now.",
                ),
            ],
        ),
        analog(
            "Turbidity",
            0.08,
            "NTU",
            0.0,
            2.0,
            fmt="#,##0.000",
            alarms=[
                alarm(
                    "Turbidity Breakthrough",
                    "AboveValue",
                    "High",
                    "Filtration / %s / Turbidity Breakthrough" % tag,
                    setpointA=0.30,
                    deadband=0.05,
                    timeOnDelaySeconds=20,
                    notes="Individual filter effluent above 0.3 NTU. "
                    "Filter-to-waste on restart.",
                )
            ],
        ),
        boolean("BackwashActive"),
        analog("Flow", 60.0, "L/s", 0.0, 150.0),
        analog("RunHours", 0.0, "h", 0.0, 100000.0, fmt="#,##0"),
    )


AREAS["Filtration"] = [
    filter_bank("A"),
    filter_bank("B"),
    filter_bank("C"),
    analog("FilteredFlow", 175.0, "L/s", 0.0, 400.0),
    analog(
        "CombinedTurbidity",
        0.09,
        "NTU",
        0.0,
        2.0,
        fmt="#,##0.000",
        alarms=[
            alarm(
                "Regulatory Turbidity Exceedance",
                "AboveValue",
                "Critical",
                "Filtration / Combined Effluent / Regulatory Exceedance",
                setpointA=1.0,
                deadband=0.1,
                timeOnDelaySeconds=15,
                notes="ADWG limit exceeded on combined filtered water. "
                "Notify the operations manager and health regulator.",
            )
        ],
    ),
]


def dosing_skid(key, label, unit, dose, lo_crit=None):
    """Chemical dosing skid: tank level, dose rate, pump run/fault."""
    tags = [
        analog(
            "TankLevel",
            72.0,
            "%",
            0.0,
            100.0,
            alarms=[
                alarm(
                    "Tank Level Low",
                    "BelowValue",
                    "Medium",
                    "Chemical / %s / Tank Level Low" % label,
                    setpointA=25.0,
                    deadband=3.0,
                    notes="Order a refill - roughly 3 days of storage remaining.",
                ),
                alarm(
                    "Tank Level Critical",
                    "BelowValue",
                    "High",
                    "Chemical / %s / Tank Level Critical" % label,
                    setpointA=10.0,
                    deadband=2.0,
                    notes="Under 24 hours of storage. Dosing will fail.",
                ),
            ],
        ),
        analog("DoseRate", dose, unit, 0.0, dose * 3),
        boolean("PumpRun", True),
        boolean(
            "PumpFault",
            alarms=[
                alarm(
                    "Dose Pump Fault",
                    "Equality",
                    "High",
                    "Chemical / %s / Dose Pump Fault" % label,
                    setpointA=True,
                    notes="Dosing pump has faulted. Switch to the standby skid.",
                )
            ],
        ),
    ]
    return folder(key, *tags)


AREAS["Chemical"] = [
    dosing_skid("Chlorine", "Chlorine", "mg/L", 2.2),
    dosing_skid("Fluoride", "Fluoride", "mg/L", 0.9),
    dosing_skid("Coagulant", "Coagulant", "mg/L", 18.0),
    analog(
        "ChlorineResidual",
        1.05,
        "mg/L",
        0.0,
        4.0,
        alarms=[
            alarm(
                "Residual Below Compliance",
                "BelowValue",
                "Critical",
                "Chemical / Chlorine Residual / Below Compliance",
                setpointA=0.20,
                deadband=0.05,
                timeOnDelaySeconds=10,
                notes="Free chlorine residual below the 0.2 mg/L compliance "
                "floor. Disinfection is not assured - escalate immediately.",
            ),
            alarm(
                "Residual Low",
                "BelowValue",
                "High",
                "Chemical / Chlorine Residual / Low",
                setpointA=0.50,
                deadband=0.05,
                timeOnDelaySeconds=30,
                notes="Trending toward non-compliance. Check dose pump and demand.",
            ),
            alarm(
                "Residual High",
                "AboveValue",
                "Low",
                "Chemical / Chlorine Residual / High",
                setpointA=2.50,
                deadband=0.1,
                notes="Overdosing - taste and odour complaints likely.",
            ),
        ],
    ),
    analog(
        "pH",
        7.4,
        "pH",
        0.0,
        14.0,
        alarms=[
            alarm(
                "pH Out Of Range",
                "OutsideValues",
                "High",
                "Chemical / pH / Out Of Range",
                setpointA=6.5,
                setpointB=8.5,
                deadband=0.1,
                timeOnDelaySeconds=20,
                notes="Outside the 6.5-8.5 operating band. Check lime and "
                "coagulant dosing.",
            )
        ],
    ),
]


def high_lift_pump(n):
    tag = "High Lift Pump %d" % n
    return folder(
        "HighLiftPump%02d" % n,
        boolean("Run"),
        boolean(
            "Fault",
            alarms=[
                alarm(
                    "Motor Fault",
                    "Equality",
                    "High",
                    "Distribution / %s / Motor Fault" % tag,
                    setpointA=True,
                    notes="VSD or motor protection trip. Standby pump should "
                    "have auto-started - confirm network pressure held.",
                )
            ],
        ),
        analog("Amps", 0.0, "A", 0.0, 90.0),
        analog("DischargePressure", 0.0, "kPa", 0.0, 900.0),
        analog("RunHours", 0.0, "h", 0.0, 100000.0, fmt="#,##0"),
    )


AREAS["Distribution"] = [
    folder(
        "ClearwaterTank",
        analog(
            "Level",
            68.0,
            "%",
            0.0,
            100.0,
            alarms=[
                alarm(
                    "Level Critically Low",
                    "BelowValue",
                    "Critical",
                    "Distribution / Clearwater Tank / Critically Low",
                    setpointA=15.0,
                    deadband=3.0,
                    notes="Supply to the network is at risk. Escalate to the "
                    "duty manager.",
                ),
                alarm(
                    "Level Low",
                    "BelowValue",
                    "High",
                    "Distribution / Clearwater Tank / Low",
                    setpointA=30.0,
                    deadband=3.0,
                    notes="Production is not keeping up with demand.",
                ),
                alarm(
                    "Level High",
                    "AboveValue",
                    "Medium",
                    "Distribution / Clearwater Tank / High",
                    setpointA=95.0,
                    deadband=3.0,
                    notes="Overflow risk. Reduce production rate.",
                ),
            ],
        ),
        analog("Volume", 6800.0, "kL", 0.0, 10000.0, fmt="#,##0"),
    ),
    high_lift_pump(1),
    high_lift_pump(2),
    high_lift_pump(3),
    analog(
        "NetworkPressure",
        520.0,
        "kPa",
        0.0,
        900.0,
        fmt="#,##0",
        alarms=[
            alarm(
                "Low Network Pressure",
                "BelowValue",
                "Critical",
                "Distribution / Network / Low Pressure",
                setpointA=250.0,
                deadband=20.0,
                timeOnDelaySeconds=10,
                notes="Below the minimum service pressure. Possible main break "
                "or total pump failure.",
            ),
            alarm(
                "High Network Pressure",
                "AboveValue",
                "Medium",
                "Distribution / Network / High Pressure",
                setpointA=780.0,
                deadband=20.0,
                notes="Over-pressure increases main break risk.",
            ),
        ],
    ),
    analog("NetworkFlow", 168.0, "L/s", 0.0, 400.0),
]

# ---------------------------------------------------------------------------
# ACME Manufacturing - a beverage bottling line, the shape most Ignition demos
# take. Its areas sit at the provider root alongside the water plant's, because
# both this project and the Exchange dashboard derive Area from the first path
# segment. The site switcher selects which set of areas a screen shows.
# ---------------------------------------------------------------------------


def line_motor(area, key, label, amps_hi, fault_priority="High"):
    """A driven machine: run/fault/amps, plus a jam that stops the line."""
    return folder(
        key,
        boolean("Run", True),
        boolean(
            "Fault",
            alarms=[
                alarm(
                    "Motor Fault",
                    "Equality",
                    fault_priority,
                    "%s / %s / Motor Fault" % (area, label),
                    setpointA=True,
                    notes="Drive fault. Line will stop - clear and reset at the panel.",
                )
            ],
        ),
        boolean(
            "Jam",
            alarms=[
                alarm(
                    "Jam Detected",
                    "Equality",
                    "Medium",
                    "%s / %s / Jam Detected" % (area, label),
                    setpointA=True,
                    timeOnDelaySeconds=5,
                    notes="Product jam. Clear the guard and restart.",
                )
            ],
        ),
        analog(
            "Amps",
            0.0,
            "A",
            0.0,
            amps_hi,
            alarms=[
                alarm(
                    "Motor Overload",
                    "AboveValue",
                    "Medium",
                    "%s / %s / Motor Overload" % (area, label),
                    setpointA=amps_hi * 0.85,
                    deadband=amps_hi * 0.03,
                    timeOnDelaySeconds=10,
                    notes="Drawing above rated current - check for mechanical binding.",
                )
            ],
        ),
        analog("RunHours", 0.0, "h", 0.0, 100000.0, fmt="#,##0"),
    )


AREAS["Mixing"] = [
    line_motor("Mixing", "Mixer01", "Mixer 1", 55.0),
    line_motor("Mixing", "Mixer02", "Mixer 2", 55.0),
    folder(
        "SyrupTank",
        analog(
            "Level",
            70.0,
            "%",
            0.0,
            100.0,
            alarms=[
                alarm(
                    "Level Low",
                    "BelowValue",
                    "Medium",
                    "Mixing / Syrup Tank / Level Low",
                    setpointA=25.0,
                    deadband=3.0,
                    notes="Schedule a syrup transfer before the batch runs out.",
                ),
                alarm(
                    "Level Critical",
                    "BelowValue",
                    "High",
                    "Mixing / Syrup Tank / Level Critical",
                    setpointA=10.0,
                    deadband=2.0,
                    notes="Under one batch remaining. The line will starve.",
                ),
            ],
        ),
    ),
    analog(
        "BatchTemperature",
        22.5,
        "degC",
        0.0,
        90.0,
        fmt="#,##0.0",
        alarms=[
            alarm(
                "Batch Over Temperature",
                "AboveValue",
                "Critical",
                "Mixing / Batch / Over Temperature",
                setpointA=45.0,
                deadband=1.5,
                timeOnDelaySeconds=15,
                notes="Product above the food-safety limit for this recipe. "
                "The batch must be quarantined - do not release to filling.",
            ),
            alarm(
                "Batch Temperature High",
                "AboveValue",
                "High",
                "Mixing / Batch / Temperature High",
                setpointA=38.0,
                deadband=1.0,
                notes="Approaching the limit. Check chiller supply temperature.",
            ),
        ],
    ),
    analog("BatchProgress", 0.0, "%", 0.0, 100.0, fmt="#,##0"),
]

AREAS["Filling"] = [
    line_motor("Filling", "Filler", "Filler", 70.0),
    line_motor("Filling", "Capper", "Capper", 40.0),
    analog(
        "CO2Pressure",
        420.0,
        "kPa",
        0.0,
        700.0,
        fmt="#,##0",
        alarms=[
            alarm(
                "Low CO2 Pressure",
                "BelowValue",
                "High",
                "Filling / CO2 / Low Pressure",
                setpointA=280.0,
                deadband=15.0,
                timeOnDelaySeconds=10,
                notes="Carbonation will drift out of specification below 280 kPa.",
            )
        ],
    ),
    analog(
        "FillRejectRate",
        0.6,
        "%",
        0.0,
        20.0,
        fmt="#,##0.0",
        alarms=[
            alarm(
                "High Reject Rate",
                "AboveValue",
                "Medium",
                "Filling / Fill Level / High Reject Rate",
                setpointA=4.0,
                deadband=0.5,
                timeOnDelaySeconds=30,
                notes="Fill-level rejects above 4%. Check valve timing and CO2.",
            )
        ],
    ),
    analog("FillRate", 480.0, "bpm", 0.0, 700.0, fmt="#,##0"),
]

AREAS["Packaging"] = [
    line_motor("Packaging", "Labeller", "Labeller", 25.0),
    line_motor("Packaging", "CasePacker", "Case Packer", 45.0),
    line_motor("Packaging", "Palletiser", "Palletiser", 60.0),
    analog("LineSpeed", 470.0, "bpm", 0.0, 700.0, fmt="#,##0"),
    analog(
        "OEE",
        87.0,
        "%",
        0.0,
        100.0,
        fmt="#,##0.0",
        alarms=[
            alarm(
                "OEE Below Target",
                "BelowValue",
                "Low",
                "Packaging / Line / OEE Below Target",
                setpointA=75.0,
                deadband=2.0,
                timeOnDelaySeconds=60,
                notes="Overall equipment effectiveness under the 75% target "
                "for this shift.",
            )
        ],
    ),
    mem(
        "LineStopped",
        "Boolean",
        False,
        alarms=[
            alarm(
                "Line Stopped",
                "Equality",
                "Critical",
                "Packaging / Line / Stopped",
                setpointA=True,
                timeOnDelaySeconds=20,
                notes="The whole line has been down for more than 20 seconds. "
                "Every minute here is lost production.",
            )
        ],
    ),
    mem("CasesProduced", "Int4", 0),
]

AREAS["Utilities"] = [
    folder(
        "AirCompressor",
        boolean("Run", True),
        boolean(
            "Fault",
            alarms=[
                alarm(
                    "Compressor Fault",
                    "Equality",
                    "High",
                    "Utilities / Air Compressor / Fault",
                    setpointA=True,
                    notes="No instrument air means no valves - the line stops.",
                )
            ],
        ),
        analog(
            "Pressure",
            690.0,
            "kPa",
            0.0,
            1000.0,
            fmt="#,##0",
            alarms=[
                alarm(
                    "Low Air Pressure",
                    "BelowValue",
                    "High",
                    "Utilities / Air Compressor / Low Pressure",
                    setpointA=550.0,
                    deadband=20.0,
                    timeOnDelaySeconds=10,
                    notes="Pneumatics become unreliable below 550 kPa.",
                )
            ],
        ),
    ),
    folder(
        "Chiller",
        boolean("Run", True),
        boolean(
            "Fault",
            alarms=[
                alarm(
                    "Chiller Fault",
                    "Equality",
                    "High",
                    "Utilities / Chiller / Fault",
                    setpointA=True,
                    notes="Loss of cooling. Batch temperature will climb.",
                )
            ],
        ),
        analog(
            "SupplyTemp",
            6.0,
            "degC",
            -10.0,
            30.0,
            fmt="#,##0.0",
            alarms=[
                alarm(
                    "High Supply Temperature",
                    "AboveValue",
                    "High",
                    "Utilities / Chiller / High Supply Temperature",
                    setpointA=12.0,
                    deadband=0.8,
                    timeOnDelaySeconds=20,
                    notes="Chilled water above 12 degC - mixing will overheat.",
                )
            ],
        ),
    ),
    # Manufacturing's own scenario selector. One shared scenario tag meant a
    # water scenario showed in the Manufacturing header, and the two plants
    # could not be driven independently.
    boolean("DemoScenarioActive"),
    mem("DemoScenario", "String", "None"),
    boolean(
        "LineCommsFault",
        alarms=[
            alarm(
                "Line PLC Comms Fault",
                "Equality",
                "Diagnostic",
                "Utilities / Line PLC / Comms Fault",
                setpointA=True,
                notes="Loss of communications to the packaging line PLC.",
            )
        ],
    ),
]


# System / diagnostics area - gives the demo a Diagnostic-priority alarm and a
# bad-quality example, which are the two most-often-forgotten alarm modes.
AREAS["Plant"] = [
    mem(
        "PLCHeartbeat",
        "Int4",
        0,
        alarms=[
            alarm(
                "PLC Comms Loss",
                "AnyChange",
                "Diagnostic",
                "Plant / PLC / Heartbeat",
                notes="Heartbeat counter from the plant PLC.",
                enabled=False,
            )
        ],
    ),
    boolean(
        "SCADACommsFault",
        alarms=[
            alarm(
                "SCADA Comms Fault",
                "Equality",
                "Diagnostic",
                "Plant / SCADA / Comms Fault",
                setpointA=True,
                notes="Loss of communications to the plant PLC.",
            )
        ],
    ),
    mem("PlantMode", "String", "Auto"),
    boolean("DemoScenarioActive"),
    mem("DemoScenario", "String", "None"),
]


# --------------------------------------------------------------------------
# emit
# --------------------------------------------------------------------------

UNARY = {
    "scope": "G",
    "version": 1,
    "restricted": False,
    "overridable": True,
    "files": ["tags.json"],
    "attributes": {"config": {}},
}


def main():
    if os.path.isdir(BUILD):
        shutil.rmtree(BUILD)
    ondisk = os.path.join(BUILD, "ondisk")
    os.makedirs(ondisk)

    for area, tags in AREAS.items():
        d = os.path.join(ondisk, area)
        os.makedirs(d)
        with open(os.path.join(d, "tags.json"), "w") as f:
            json.dump(tags, f, indent=2)
        with open(os.path.join(d, "unary-resource.json"), "w") as f:
            json.dump(UNARY, f, indent=2)

    # Designer-importable export of the whole provider
    export = {
        "name": "",
        "tagType": "Provider",
        "tags": [folder(a, *t) for a, t in AREAS.items()],
    }
    with open(os.path.join(BUILD, "AlarmDemo-tags.json"), "w") as f:
        json.dump(export, f, indent=2)

    n_tags = n_alarms = 0

    def walk(ts):
        nonlocal n_tags, n_alarms
        for t in ts:
            if t.get("tagType") == "Folder":
                walk(t.get("tags", []))
            else:
                n_tags += 1
                n_alarms += len(t.get("alarms", []))

    for tags in AREAS.values():
        walk(tags)
    print("areas: %d  tags: %d  alarms: %d" % (len(AREAS), n_tags, n_alarms))


if __name__ == "__main__":
    main()
