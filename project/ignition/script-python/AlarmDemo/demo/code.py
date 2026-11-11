"""AlarmDemo.demo - scenario control for the live demonstration.

Scenarios bias the simulation (AlarmDemo.sim), so every alarm still goes
through the real alarm pipeline. The list is SCENARIOS below.
"""

P = "[AlarmDemo]"

# One scenario tag per site: a shared tag would light the other site's banner.
SCENARIO_TAG = {
	"Water": "Plant/DemoScenario",
	"Manufacturing": "Utilities/DemoScenario",
}
ACTIVE_TAG = {
	"Water": "Plant/DemoScenarioActive",
	"Manufacturing": "Utilities/DemoScenarioActive",
}

# (key, label, site) - site "" means it applies to both plants.
SCENARIOS = [
	("None", "Normal operation", ""),
	("Storm", "Storm / high raw turbidity", "Water"),
	("ChlorineFailure", "Chlorine dose pump failure", "Water"),
	("PumpFailure", "Pump trips (intake + high lift)", "Water"),
	("FilterBlinding", "Filter B blinding", "Water"),
	("Chattering", "Chattering nuisance alarm", "Water"),
	("LineJam", "Case packer jam - line stops", "Manufacturing"),
	("ChillerFailure", "Chiller failure - batch overheats", "Manufacturing"),
	("AirLoss", "Instrument air loss", "Manufacturing"),
	("CO2Loss", "Low CO2 - fill rejects climb", "Manufacturing"),
	("BatchOverTemp", "Batch over temperature", "Manufacturing"),
	("CommsLoss", "PLC comms loss", ""),
]


def _siteOf(name):
	for key, _label, site in SCENARIOS:
		if key == name:
			return site
	return ""


def setScenario(name):
	"""Select a scenario on the site that owns it; a siteless one is written to both sites."""
	valid = [s[0] for s in SCENARIOS]
	if name not in valid:
		name = "None"
	site = _siteOf(name)
	targets = [site] if site else list(SCENARIO_TAG.keys())
	paths, values = [], []
	for t in targets:
		paths += [P + SCENARIO_TAG[t], P + ACTIVE_TAG[t]]
		values += [name, name != "None"]
	system.tag.writeBlocking(paths, values)
	return name


def getScenario(site="Water"):
	"""Return the site's current scenario name, or "None" if the tag is not good."""
	path = SCENARIO_TAG.get(site, SCENARIO_TAG["Water"])
	qv = system.tag.readBlocking([P + path])[0]
	return qv.value if qv.quality.isGood() else "None"


def reset():
	"""Back to normal, clear the injected faults and re-seed a healthy plant."""
	setScenario("None")
	writes = {
		"Mixing/Mixer01/Fault": False,
		"Mixing/Mixer02/Fault": False,
		"Mixing/Mixer01/Jam": False,
		"Mixing/Mixer02/Jam": False,
		"Filling/Filler/Fault": False,
		"Filling/Filler/Jam": False,
		"Filling/Capper/Fault": False,
		"Filling/Capper/Jam": False,
		"Packaging/Labeller/Fault": False,
		"Packaging/Labeller/Jam": False,
		"Packaging/CasePacker/Fault": False,
		"Packaging/CasePacker/Jam": False,
		"Packaging/Palletiser/Fault": False,
		"Packaging/Palletiser/Jam": False,
		"Utilities/AirCompressor/Fault": False,
		"Utilities/Chiller/Fault": False,
		"Utilities/LineCommsFault": False,
		"Utilities/DemoScenario": "None",
		"Utilities/DemoScenarioActive": False,
		"Mixing/SyrupTank/Level": 70.0,
		"Mixing/BatchTemperature": 22.5,
		"Filling/CO2Pressure": 425.0,
		"Filling/FillRejectRate": 0.6,
		"Packaging/OEE": 87.0,
		"Packaging/LineStopped": False,
		"Utilities/AirCompressor/Pressure": 690.0,
		"Utilities/Chiller/SupplyTemp": 6.0,
		"Intake/RawWaterPump01/Fault": False,
		"Intake/RawWaterPump02/Fault": False,
		"Distribution/HighLiftPump01/Fault": False,
		"Distribution/HighLiftPump02/Fault": False,
		"Distribution/HighLiftPump03/Fault": False,
		"Chemical/Chlorine/PumpFault": False,
		"Chemical/Fluoride/PumpFault": False,
		"Chemical/Coagulant/PumpFault": False,
		"Plant/SCADACommsFault": False,
		"Intake/WetWell/Level": 65.0,
		"Intake/RawTurbidity": 8.0,
		"Chemical/ChlorineResidual": 1.05,
		"Chemical/pH": 7.4,
		"Distribution/ClearwaterTank/Level": 68.0,
		"Chemical/Chlorine/TankLevel": 72.0,
		"Chemical/Fluoride/TankLevel": 68.0,
		"Chemical/Coagulant/TankLevel": 75.0,
	}
	for f in ("A", "B", "C"):
		writes["Filtration/Filter%s/DiffPressure" % f] = 25.0
		writes["Filtration/Filter%s/BackwashActive" % f] = False
	system.tag.writeBlocking(
		[P + k for k in writes.keys()], list(writes.values())
	)
	return "reset"


def ackAll(notes="Acknowledged from the demo control panel"):
	"""Acknowledge every unacknowledged alarm in the demo provider."""
	# getId() returns a Java UUID; acknowledge() needs strings.
	events = [
		str(e.getId())
		for e in system.alarm.queryStatus(
			state=["ActiveUnacked", "ClearUnacked"], provider=["AlarmDemo"]
		)
	]
	if events:
		# 8.3 requires the username argument.
		system.alarm.acknowledge(events, notes, "demo")
	return len(events)
