def handleTimerEvent():
	# Both sites run continuously, so switching between them in the UI is
	# instant and each always has live alarms of its own.
	AlarmDemo.sim.tick()
	AlarmDemo.simmfg.tick()
