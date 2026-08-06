def doGet(request, session):
	"""Headless control surface for the alarm demo.

	Kept deliberately small - it exists so the demo can be driven and checked
	without a Designer session:

	    ?cmd=status                 live tag + alarm snapshot
	    ?cmd=scenario&name=Storm    select a demo scenario
	    ?cmd=reset                  back to normal operation
	    ?cmd=setup                  create everything: journal tables,
	                                schedules, users, rosters, history
	    ?cmd=check                  report what is in place, change nothing
	    ?cmd=rosters                rosters, people and who is on duty
	    ?cmd=backfill&days=30       regenerate the journal history
	    ?cmd=summary                what is actually in the journal, by
	                                priority and event type
	    ?cmd=journal[&name=]        read events back THROUGH the alarm journal
	                                profile - the one check that tells a
	                                missing profile apart from an empty one
	    ?cmd=ackall                 acknowledge everything

	`status` reports the water plant's tags; the alarm counts in it cover
	whichever site is selected.

	Docstring lives inside the def on purpose: anything above `def doGet` in a
	WebDev python resource makes the endpoint return an empty 200 with no log.
	"""
	import traceback

	params = request['params']
	cmd = params.get('cmd', 'status')

	try:
		if cmd == 'status':
			live = AlarmDemo.alarms.liveStatus()
			paths = [
				'Plant/DemoScenario',
				'Intake/WetWell/Level',
				'Intake/RawTurbidity',
				'Filtration/CombinedTurbidity',
				'Chemical/ChlorineResidual',
				'Chemical/pH',
				'Distribution/ClearwaterTank/Level',
				'Distribution/NetworkPressure',
				'Distribution/NetworkFlow',
			]
			qvs = system.tag.readBlocking(['[AlarmDemo]' + p for p in paths])
			tags = {}
			for p, qv in zip(paths, qvs):
				tags[p] = {
					'value': qv.value,
					'quality': str(qv.quality),
				}
			return {'json': {'ok': True, 'alarms': live, 'tags': tags}}

		if cmd == 'scenario':
			name = AlarmDemo.demo.setScenario(params.get('name', 'None'))
			return {'json': {'ok': True, 'scenario': name}}

		if cmd == 'reset':
			AlarmDemo.demo.reset()
			return {'json': {'ok': True, 'reset': True}}

		if cmd == 'ackall':
			n = AlarmDemo.demo.ackAll()
			return {'json': {'ok': True, 'acknowledged': n}}

		if cmd == 'backfill':
			days = int(params.get('days', 30))
			perDay = int(params.get('perDay', 48))
			n = AlarmDemo.backfill.run(days=days, perDay=perDay)
			return {'json': {'ok': True, 'rowsWritten': n, 'days': days}}

		if cmd == 'journal':
			from java.util import Date
			end = Date()
			start = Date(end.getTime() - 8 * 3600000)
			name = params.get('name', 'AlarmDemo')
			evts = system.alarm.queryJournal(
				journalName=name, startDate=start, endDate=end)
			rows = []
			for e in list(evts)[:5]:
				rows.append({'source': str(e.getSource()),
				             'priority': str(e.getPriority()),
				             'state': str(e.getState())})
			return {'json': {'ok': True, 'journalName': name,
			                 'count': len(list(evts)), 'sample': rows}}

		if cmd == 'setup':
			days = int(params.get('days', 30))
			force = params.get('force', '') in ('1', 'true', 'yes')
			history = params.get('history', '1') not in ('0', 'false', 'no')
			return {'json': {'ok': True,
			                 'setup': AlarmDemo.setup.run(days=days,
			                                              force=force,
			                                              history=history)}}

		if cmd == 'check':
			return {'json': {'ok': True, 'check': AlarmDemo.setup.check()}}

		if cmd == 'rosters':
			return {'json': {'ok': True,
			                 'gatewayRosters': AlarmDemo.roster.gatewayRosterNames(),
			                 'cards': AlarmDemo.roster.rosterCards(),
			                 'people': AlarmDemo.roster.peopleRows(),
			                 'duty': AlarmDemo.roster.dutySummary()}}

		if cmd == 'summary':
			ds = AlarmDemo.backfill.summary()
			rows = []
			for r in range(ds.getRowCount()):
				rows.append({
					'priority': ds.getValueAt(r, 'priority'),
					'eventtype': ds.getValueAt(r, 'eventtype'),
					'n': ds.getValueAt(r, 'n'),
					'first': str(ds.getValueAt(r, 'first')),
					'last': str(ds.getValueAt(r, 'last')),
				})
			return {'json': {'ok': True, 'summary': rows}}

		return {'json': {'ok': False, 'error': 'unknown cmd: %s' % cmd}}

	except:
		return {'json': {'ok': False, 'error': traceback.format_exc()}}
