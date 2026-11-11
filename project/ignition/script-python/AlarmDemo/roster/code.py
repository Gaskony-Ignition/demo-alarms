"""AlarmDemo.roster - who gets an alarm, and how that is managed.

Users, schedules and on-call rosters are read back from Ignition, not kept here.
setup() writes the schedules and rosters (gateway config resources) onto the gateway.
"""

import os
import traceback

USER_SOURCE = "default"

LOG = system.util.getLogger("AlarmDemo.roster")

# Created as real users in the user source on first run; the assigned
# Ignition schedule decides whether they are on duty.
PEOPLE = [
	("jsmith",   "Jordan Smith",     "Shift Operator",     "jordan.smith@acme.example",    "+61 400 111 222", "Day Shift"),
	("achen",    "Alex Chen",        "Shift Operator",     "alex.chen@acme.example",       "+61 400 111 333", "Night Shift"),
	("rpatel",   "Riya Patel",       "Senior Operator",    "riya.patel@acme.example",      "+61 400 111 444", "Afternoon Shift"),
	("dwilson",  "Dana Wilson",      "Maintenance Fitter", "dana.wilson@acme.example",     "+61 400 222 111", "Day Shift"),
	("moconnor", "Michael O'Connor", "Electrician",        "michael.oconnor@acme.example", "+61 400 222 333", "Afternoon Shift"),
	("shaddad",  "Sara Haddad",      "Operations Manager", "sara.haddad@acme.example",     "+61 400 333 111", "Always"),
	("tnguyen",  "Tam Nguyen",       "Process Engineer",   "tam.nguyen@acme.example",      "+61 400 333 222", "Day Shift"),
]

# (name, description, seed members); members only seed a roster that does not exist yet.
ROSTERS = [
	("Operations",  "First response - the control room",
	 ["jsmith", "achen", "rpatel"]),
	("Maintenance", "Called for equipment faults",
	 ["dwilson", "moconnor"]),
	("Management",  "Escalation of record",
	 ["shaddad", "tnguyen"]),
]

# "Always" is built in to Ignition, so it is not listed here.
SCHEDULES = [
	("Day Shift",       "06:00-14:00, every day", "6:00-14:00"),
	("Afternoon Shift", "14:00-22:00, every day", "14:00-22:00"),
	("Night Shift",     "22:00-06:00, every day", "22:00-24:00,0:00-6:00"),
]

# priority -> (roster, notify after minutes, escalate to, escalate after mins).
# Display only: no notification pipeline is configured, as that needs an email or SMS profile.
ESCALATION = [
	("Critical",   "Operations",  0,  "Management",  5),
	("High",       "Operations",  2,  "Maintenance", 15),
	("Medium",     "Operations",  10, "Maintenance", 60),
	("Low",        "Operations",  30, "",            0),
	("Diagnostic", "Maintenance", 60, "",            0),
]


def _safe(fn, default):
	try:
		return fn()
	except:
		import traceback
		LOG.warn("roster helper failed: %s" % traceback.format_exc())
		return default


def _peopleIndex():
	return dict((p[0], p) for p in PEOPLE)


def _person(username):
	"""Contact card for a username, whether or not this demo seeded them."""
	p = _peopleIndex().get(username)
	if p:
		return {"username": p[0], "name": p[1], "role": p[2],
				"email": p[3], "phone": p[4]}
	return {"username": username, "name": username, "role": "",
			"email": "", "phone": ""}


def _configDir():
	"""The gateway's config resource root, resolved from the working directory."""
	from java.io import File
	return File("data/config/resources/core/ignition").getAbsolutePath()


def _write(path, text):
	"""Write a config-resource file so a scan can never see it half-written."""
	from java.io import File
	# open(path, "w") truncates at once, and a scan that reads a half-written
	# resource.json skips that resource for good; a rename is atomic.
	staged = File(path + ".tmp")
	f = open(staged.getAbsolutePath(), "w")
	try:
		f.write(text)
	finally:
		f.close()
	target = File(path)
	if not staged.renameTo(target):
		if target.exists() and not target.delete():
			raise IOError("could not replace %s" % path)
		if not staged.renameTo(target):
			raise IOError("could not rename %s.tmp into place" % path)


def _writeResource(kind, name, config, description):
	"""Write one gateway config resource and return its directory."""
	# lastModificationSignature is left out on purpose: a stale one makes the
	# scan skip the resource silently.
	from java.util import UUID
	d = os.path.join(_configDir(), kind, name)
	if not os.path.exists(d):
		os.makedirs(d)
	_write(os.path.join(d, "config.json"), system.util.jsonEncode(config))
	meta = {
		"scope": "A",
		"description": description,
		"version": 1,
		"restricted": False,
		"overridable": True,
		"files": ["config.json"],
		"attributes": {
			"uuid": str(UUID.randomUUID()),
			"enabled": True,
			"lastModification": {
				"actor": "AlarmDemo",
				"timestamp": system.date.format(
					system.date.now(), "yyyy-MM-dd'T'HH:mm:ss'Z'"),
			},
		},
	}
	# resource.json goes last: a scan that sees it finds the directory complete.
	_write(os.path.join(d, "resource.json"), system.util.jsonEncode(meta))
	return d


def _rescan():
	"""Ask the gateway to pick up config resources written above."""
	# Not system.project.requestScan: that is the project scan, not the config scan.
	from com.inductiveautomation.ignition.gateway import IgnitionGateway
	IgnitionGateway.get().getConfigurationManager().requestScan()
	return True


def _writeRoster(name, usernames, description=""):
	_writeResource("roster-config", name,
				   {"users": [{"profile": USER_SOURCE, "userId": u}
							  for u in usernames]},
				   description or "Alarm demo on-call roster")
	return _rescan()


def _readRoster(name):
	"""Members of a roster, read from the resource file."""
	# system.alarm.getRosters() returns empty user lists on 8.3.8, so read the file.
	path = os.path.join(_configDir(), "roster-config", name, "config.json")
	if not os.path.exists(path):
		return []
	f = open(path)
	try:
		cfg = system.util.jsonDecode(f.read()) or {}
	finally:
		f.close()
	return [str(u.get("userId")) for u in (cfg.get("users") or [])
			if u.get("userId")]


def ensureSchedules():
	"""Create the three shift schedules if they are not already there."""

	def go():
		have = set([str(n) for n in system.user.getScheduleNames()])
		made = []
		for name, desc, times in SCHEDULES:
			if name in have:
				continue
			_writeResource("schedule", name, {
				"profile": {"type": "basic schedule"},
				"settings": {
					"observeHolidays": False,
					# allDays + allDayTime is the 24/7 shift pattern. The
					# weekDay and per-day fields still have to be present, or
					# the resource does not parse.
					"allDays": True,
					"allDayTime": times,
					"weekDays": False,
					"weekDayTime": "8:00-17:00",
					"monday": False, "tuesday": False, "wednesday": False,
					"thursday": False, "friday": False, "saturday": False,
					"sunday": False,
					"mondayTime": "0:00-24:00", "tuesdayTime": "0:00-24:00",
					"wednesdayTime": "0:00-24:00", "thursdayTime": "0:00-24:00",
					"fridayTime": "0:00-24:00", "saturdayTime": "0:00-24:00",
					"sundayTime": "0:00-24:00",
					"repeatMode": "Off", "repeatOn": 1, "repeatOff": 1,
				},
			}, desc)
			made.append(name)
		if made:
			_rescan()
		return made

	return _safe(go, [])


def _uiProblems(response):
	"""The error strings out of what a system.user write returns, or []."""
	# The write returns a UIResponse, which is truthy even on success and not
	# iterable; the errors are in getErrors().
	from java.lang import Throwable as JThrowable
	if response is None:
		return []
	try:
		return [unicode(e) for e in response.getErrors()]
	except (JThrowable, Exception):
		pass
	try:
		return [unicode(e) for e in response]
	except (JThrowable, Exception):
		return []


def _addPerson(username, fullname, email, phone, schedule):
	"""Create one demo user. Returns 1 if it was created, 0 if refused."""
	from java.util import UUID
	user = system.user.getNewUser(USER_SOURCE, username)
	user.set("firstname", fullname.split(" ")[0])
	user.set("lastname", " ".join(fullname.split(" ")[1:]))
	# An internal user source rejects a user with no password. The value is
	# random and never logged: these users are not accounts anyone signs in with.
	user.set("password", str(UUID.randomUUID()))
	user.set("schedule", schedule)
	# A gateway without SMS Notification throws on an "sms" contact, so add each type separately.
	for kind, value in (("email", email), ("sms", phone)):
		try:
			user.addContactInfo(kind, value)
		except:
			LOG.info("%s contact info not accepted for %s on this gateway"
					 % (kind, username))
	problems = _uiProblems(system.user.addUser(USER_SOURCE, user))
	if problems:
		LOG.warn("user %s rejected: %s" % (username, ", ".join(problems)))
		return 0
	return 1


def ensureUsers():
	"""Create the demo users, with contact info and their shift schedule."""

	def go():
		existing = set()
		for u in system.user.getUsers(USER_SOURCE):
			existing.add(str(u.get("username")).lower())

		made, refused = 0, []
		for username, fullname, _role, email, phone, schedule in PEOPLE:
			if username.lower() in existing:
				# Only fill a blank schedule; never overwrite a shift changed on screen.
				if not userSchedule(username):
					setSchedule(username, schedule)
				continue
			# Per user, so one rejected person does not stop the rest; failures are named in the return.
			try:
				made += _addPerson(username, fullname, email, phone, schedule)
			except:
				LOG.warn("user %s could not be created: %s"
						 % (username, traceback.format_exc()))
				refused.append("%s (%s)" % (
					username, traceback.format_exc().strip().split("\n")[-1]))
		if refused:
			return {"made": made, "refused": refused}
		return made

	return _safe(go, 0)


def ensureRosters(force=False):
	"""Create the on-call rosters if they are missing. Idempotent."""

	def go():
		have = set(gatewayRosterNames())
		made = []
		for name, desc, members in ROSTERS:
			if name in have and not force:
				continue
			_writeResource("roster-config", name,
						   {"users": [{"profile": USER_SOURCE, "userId": u}
									  for u in members]}, desc)
			made.append(name)
		if made:
			_rescan()
		return made

	return _safe(go, [])


def applyDefaultSchedules():
	"""Put everyone back on the shift the demo was designed around."""

	def go():
		# Return the resulting assignment, not a change list: "no changes" and "all failed" look the same.
		out = {}
		for username, _f, _r, _e, _p, schedule in PEOPLE:
			if userSchedule(username) != schedule:
				setSchedule(username, schedule)
			out[username] = userSchedule(username)
		return out

	return _safe(go, {})


def setup(force=False):
	"""One call for a fresh gateway: schedules, users, rosters."""
	schedules = ensureSchedules()
	users = ensureUsers()
	return {"schedules": schedules,
			"users": users,
			"shifts": applyDefaultSchedules(),
			"rosters": ensureRosters(force)}


def _user(username):
	try:
		return system.user.getUser(USER_SOURCE, username)
	except:
		return None


def userSchedule(username):
	"""Name of the schedule assigned to this user, or "" if unknown."""
	u = _user(username)
	if u is None:
		return ""
	try:
		return str(u.get("schedule") or "")
	except:
		return ""


def onDuty(username):
	"""Is this person on duty right now, per their Ignition schedule?"""

	# isUserScheduled takes a User object; a name string raises a TypeError.
	def go():
		u = _user(username)
		if u is None:
			return False
		return bool(system.user.isUserScheduled(u))

	return _safe(go, False)


def dutyNow():
	"""{username: bool} on-duty state for everyone the demo knows about."""

	def go():
		return dict((p[0], onDuty(p[0])) for p in PEOPLE)

	return _safe(go, dict((p[0], False) for p in PEOPLE))


def setSchedule(username, schedule):
	"""Move someone onto a different shift in the user source; True on success."""

	def go():
		u = _user(username)
		if u is None:
			return False
		u.set("schedule", schedule)
		problems = _uiProblems(system.user.editUser(USER_SOURCE, u))
		if problems:
			LOG.warn("schedule change for %s rejected: %s"
					 % (username, ", ".join(problems)))
			return False
		return True

	return _safe(go, False)


def rosterMembers(name):
	"""Usernames on a roster, straight from the gateway's own roster resource."""
	return _safe(lambda: _readRoster(name), [])


def gatewayRosterNames():
	"""Roster names as the alarm subsystem sees them."""
	return _safe(lambda: sorted([str(k) for k in
								 (system.alarm.getRosters() or {}).keys()]), [])


def rosterCards():
	"""Rosters with member count, on-duty count and member details, for the UI."""

	def go():
		duty = dutyNow()
		blurbs = dict((n, d) for n, d, _m in ROSTERS)
		out = []
		for name, _desc, _seed in ROSTERS:
			members = []
			for username in rosterMembers(name):
				m = _person(username)
				m["schedule"] = userSchedule(username) or "-"
				m["onDuty"] = bool(duty.get(username, onDuty(username)))
				m["duty"] = "ON DUTY" if m["onDuty"] else "off"
				members.append(m)
			members.sort(key=lambda m: (not m["onDuty"], m["name"]))
			out.append({
				"roster": name,
				"blurb": blurbs.get(name, ""),
				"count": len(members),
				"onDuty": len([m for m in members if m["onDuty"]]),
				"members": members,
			})
		return out

	return _safe(go, [])


def addMember(roster, username):
	"""Add a user to a roster; True unless the write failed."""
	def go():
		members = rosterMembers(roster)
		if username and username not in members:
			members.append(username)
			_writeRoster(roster, members)
		return True

	return _safe(go, False)


def removeMember(roster, username):
	"""Remove a user from a roster; True unless the write failed."""
	def go():
		members = [m for m in rosterMembers(roster) if m != username]
		_writeRoster(roster, members)
		return True

	return _safe(go, False)


def eligible(roster):
	"""Picker options ({value, label}) for people not already on this roster."""

	def go():
		have = set(rosterMembers(roster))
		return [{"value": u, "label": "%s  -  %s" % (full, role)}
				for u, full, role, _e, _p, _s in PEOPLE if u not in have]

	return _safe(go, [])


def peopleRows():
	"""One dict per person: schedule, duty state and roster memberships."""

	def go():
		duty = dutyNow()
		rosters = dict((n, set(rosterMembers(n))) for n, _d, _m in ROSTERS)
		known = set()
		for u in system.user.getUsers(USER_SOURCE):
			known.add(str(u.get("username")).lower())

		rows = []
		for username, full, role, email, phone, _default in PEOPLE:
			on = sorted([n for n, members in rosters.items()
						 if username in members])
			rows.append({
				"username": username,
				"name": full,
				"role": role,
				"email": email,
				"phone": phone,
				"schedule": userSchedule(username) or "-",
				"onDuty": bool(duty.get(username, False)),
				"duty": "ON DUTY" if duty.get(username, False) else "off",
				"rosters": ", ".join(on) or "not on a roster",
				"inGateway": "yes" if username.lower() in known else "no",
			})
		return rows

	return _safe(go, [])


def dutySummary():
	""""3 of 7 on duty" for the header chip."""

	def go():
		duty = dutyNow()
		return {"onDuty": len([1 for v in duty.values() if v]),
				"total": len(PEOPLE)}

	return _safe(go, {"onDuty": 0, "total": len(PEOPLE)})


def _rule(priority):
	for pri, roster, delay, esc, esc_after in ESCALATION:
		if pri == priority:
			return roster, delay, esc, esc_after
	return "Operations", 15, "", 0


def escalationTable():
	"""Dataset of the escalation design: who is notified, when, and who is next."""
	rows = []
	for pri, roster, delay, esc, esc_after in ESCALATION:
		rows.append([pri, roster,
					 "immediately" if delay == 0 else "after %d min" % delay,
					 esc or "-",
					 "-" if not esc else "after %d min" % esc_after])
	return system.dataset.toDataSet(
		["Priority", "Notifies", "When", "Escalates to", "If unacknowledged"],
		rows)


def routing(site="Water"):
	"""Dataset of active alarms on this site and who is on call for each now."""

	def go():
		cards = dict((c["roster"], c) for c in rosterCards())
		mine = set(AlarmDemo.alarms.siteAreas(site))
		rows = []
		for e in system.alarm.queryStatus(
				state=["ActiveUnacked", "ActiveAcked"], provider=["AlarmDemo"]):
			if AlarmDemo.alarms._area(e) not in mine:
				continue
			pri = AlarmDemo.alarms._priorityName(e)
			roster, delay, esc, esc_after = _rule(pri)
			members = cards.get(roster, {}).get("members", [])
			on = [m["name"] for m in members if m["onDuty"]]
			who = ", ".join(on) if on else "NOBODY ON SHIFT"
			disp = str(e.getDisplayPath() or "") or str(e.getSource())
			rows.append([
				disp, pri, roster, who,
				"immediately" if delay == 0 else "after %d min" % delay,
				("%s after %d min" % (esc, esc_after)) if esc else "-",
				"acknowledged" if e.isAcked() else "waiting",
			])
		rows.sort(key=lambda r: -AlarmDemo.alarms.PRIORITY_NUM.get(r[1], 0))
		return system.dataset.toDataSet(
			["Alarm", "Priority", "Roster", "On call now", "When", "Escalates",
			 "Status"], rows)

	return _safe(go, system.dataset.toDataSet(
		["Alarm", "Priority", "Roster", "On call now", "When", "Escalates",
		 "Status"], []))
