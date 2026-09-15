def doGet(request, session):
	"""Headless control surface for the alarm demo.

	Kept deliberately small - it exists so the demo can be driven and checked
	without a Designer session:

	    ?cmd=status                 live tag + alarm snapshot
	    ?cmd=scenario&name=Storm    select a demo scenario
	    ?cmd=reset                  back to normal operation
	    ?cmd=setup                  create everything this gateway is missing:
	                                tag provider, tags, journal profile and
	                                tables, schedules, users, rosters, history
	    ?cmd=fix&name=tags          create ONE setup item
	    ?cmd=check                  report on every item, change nothing
	    ?cmd=db[&name=<connection>] read or set the database connection
	    ?cmd=createdb[&name=]       make the demo's SQLite connection
	    ?cmd=analytics[&site=&hours=&days=]
	                                every number on the Analytics screen
	    ?cmd=rosters                rosters, people and who is on duty
	    ?cmd=backfill&days=30       regenerate the journal history
	    ?cmd=summary                what is actually in the journal, by
	                                priority and event type
	    ?cmd=journal[&name=]        read events back THROUGH the alarm journal
	                                profile - the one check that tells a
	                                missing profile apart from an empty one
	    ?cmd=ackall                 acknowledge everything
	    ?cmd=version                which build this gateway is running

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

		if cmd == 'version':
			return {'json': {'ok': True,
			                 'version': AlarmDemo.alarms.VERSION,
			                 'project': system.util.getProjectName()}}

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
			force = params.get('force', '') in ('1', 'true', 'yes')
			return {'json': {'ok': True, 'setup': AlarmDemo.setup.run(force=force)}}

		if cmd == 'fix':
			# one setup item, by key - the same thing a Create button on the
			# Setup screen presses
			name = params.get('name', '')
			return {'json': {'ok': True, 'fixed': AlarmDemo.setup.fix(name)}}

		if cmd == 'check':
			return {'json': {'ok': True, 'check': AlarmDemo.setup.check()}}

		if cmd == 'db':
			# read, or set with &name=<connection>. The one setting this demo
			# keeps outside the project.
			name = params.get('name', None)
			if name is not None:
				AlarmDemo.config.save(name)
			return {'json': {'ok': True, 'db': AlarmDemo.config.describe(),
			                 'connections': AlarmDemo.config.connections()}}

		if cmd == 'analytics':
			# What the Analytics screen shows, without a browser. Every one of
			# these goes through a different query, so it is also the fastest
			# way to tell whether the analytics survived a change to them.
			site = params.get('site', 'Water')
			hours = int(params.get('hours', 24))
			days = int(params.get('days', 30))
			rate = AlarmDemo.alarms.rateByHour(hours, site)
			load = AlarmDemo.alarms.dailyLoad(days, site)
			ack = AlarmDemo.alarms.dailyAckTime(days, site)
			return {'json': {
				'ok': True,
				'site': site,
				'kpis': AlarmDemo.alarms.kpis(hours, site),
				'priorityMix': AlarmDemo.alarms.priorityCounts(hours, site),
				'pareto': [r['name'] + ' x' + str(r['n'])
				           for r in AlarmDemo.alarms.paretoRows(hours, site, rows=5)
				           if r['n']],
				'series': {
					'rateByHour': rate.getRowCount(),
					'rateTotal': sum([rate.getValueAt(i, 1)
					                  for i in range(rate.getRowCount())]),
					'dailyLoad': load.getRowCount(),
					'dailyLoadTotal': sum([load.getValueAt(i, 1)
					                       for i in range(load.getRowCount())]),
					'dailyAckTime': ack.getRowCount(),
				},
			}}

		if cmd == 'parity':
			# Do the SQL analytics and the journal analytics agree? On a gateway
			# with a database both run against the same journal and every pair
			# must match - which is the only check that keeps the Edge build
			# honest, because a drifted analytic returns a plausible number
			# rather than an error.
			site = params.get('site', 'Water')
			hours = int(params.get('hours', 24))
			days = int(params.get('days', 30))
			return {'json': AlarmDemo.journalq.parity(hours, days, site,
			                                          params.get('area', ''))}

		if cmd == 'createdb':
			# Make the demo's SQLite connection. Takes a name and nothing
			# else - there is no host, user or password to pass, which is the
			# whole reason this command can exist at all. It used to be
			# unreachable from here: a create needed five values, one of them
			# a password, and a password in a URL is a password in the access
			# log.
			return {'json': {'ok': True, 'result': AlarmDemo.setup.createDatabase(
				params.get('name', None))}}

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
