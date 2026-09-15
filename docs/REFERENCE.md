# ACME Alarm Demo — reference

Everything the [front page](../README.md) does not need to say: what each
screen is, the headless control endpoint, and the things worth knowing before
you point this at a gateway that is doing other work.

Two switchable simulated sites:

- **ACME Water Treatment Plant** — potable water production and distribution
- **ACME Manufacturing** — a beverage bottling and packaging line

No PLC, no OPC server, no external device. A gateway timer script simulates
both plants, and every alarm on screen has been through the real Ignition alarm
pipeline: evaluation, deadband, time delay, priority, acknowledgement, journal,
on-call roster and shift schedule.

Both sites run continuously, so the switch in the header is instant and each
always has live alarms of its own. Everything on screen — the mimic, the header
counts, the journal, every analytic and the notification routing — is scoped to
the selected site.

## What is in it

| Piece | What it gives you |
| ----- | ----------------- |
| **122 tags / 76 alarms** across 9 process areas | all five priorities, and six alarm modes — above/below setpoint, between values, equality, and a diagnostic |
| **Two plant simulations** (1 s gateway timer) | tanks that fill and drain, filters that load until backwashed, and a packaging line where one jam stops everything downstream and drags OEE with it |
| **12 demo scenarios** | storm, chlorine failure, pump trips, filter blinding, chattering nuisance alarm, line jam, chiller failure, air loss, low CO₂, batch over-temperature |
| **~9,000 rows of journal history** | 30 days for both sites: diurnal peaks, quiet weekends, a Pareto, chattering bad actors, realistic acknowledgement behaviour |
| **7 real Ignition users, 3 shift schedules, 3 on-call rosters** | genuine gateway objects, visible under Security → Users, Alarming → Scheduling and Alarming → Rosters |
| **9 Perspective screens** | mimic, alarm status, journal, per-area metrics with 30-day trends, analytics, notification routing, people and shifts, demo control, setup |

## The screens

- **Overview** — plant mimic for the selected site. Live tank levels, machine
  run/fault/jam, filter head loss, per-area alarm counts, and a site-scoped
  active alarm table.
- **Alarm Status** — the stock Perspective Alarm Status Table: filter,
  acknowledge, shelve, scoped to the selected site, with an Area selector and a
  priority-colour switch (whole row, as Ignition's own tables do it, or the
  priority column alone). The switch sits at the far right of every screen that
  has one and drives all three alarm tables from one session property.
- **Journal** — Ignition's own Alarm Journal Table against the `AlarmDemo`
  journal profile, with its own filtering, sorting and detail popup, scoped to
  the selected site and themed to the page.
- **Alarm Metrics** — a live metric card per process area, plus **Daily alarm
  load** and **Time to acknowledge** over the last 30 complete days.
- **Analytics** — Pareto of worst sources, alarm rate against the EEMUA 191
  flood threshold, priority mix, never-acknowledged table, and six KPIs.
- **Notifications** — who actually gets each alarm. Real on-call rosters, and a
  live table showing for every active alarm the roster it routes to and who on
  that roster is on shift *right now*. Roster membership is editable here and
  the routing changes immediately.
- **People & Shifts** — the seven people, their Ignition schedule, and whether
  that schedule has them on duty. One click moves someone to another shift — it
  writes a real schedule onto the real user — and the routing follows.
- **Demo Control** — the scenario buttons, acknowledge-all and reset.
- **Setup** — what this gateway has and what it is missing, one row per item,
  with the button that creates each. See the front page.

## Headless control

For scripted demos, and for checking a gateway you cannot open a browser onto:

```text
/system/webdev/AlarmDemo/admin?cmd=check
                            ?cmd=setup
                            ?cmd=fix&name=tags
                            ?cmd=db[&name=<connection>]
                            ?cmd=createdb[&name=]
                            ?cmd=analytics[&site=&hours=&days=]
                            ?cmd=status
                            ?cmd=rosters
                            ?cmd=scenario&name=Storm
                            ?cmd=reset
                            ?cmd=ackall
                            ?cmd=backfill&days=30
                            ?cmd=summary
                            ?cmd=journal
                            ?cmd=version
```

`?cmd=check` is the same list the Setup screen shows, and `?cmd=fix` presses
one of its Create buttons. `?cmd=journal` reads the journal back *through the
profile*, which makes it the fastest way to tell a missing profile from an
empty one. `?cmd=analytics` returns every number the Analytics screen shows —
each one through a different query, so it is also the fastest way to tell
whether the analytics survived a change.

`?cmd=createdb` can exist at all only because the connection is SQLite. It
takes a name and nothing else; the PostgreSQL version needed five values, one
of them a password, and a password in a URL is a password in the access log.

## The database

**SQLite, in the gateway's own data directory.** The Setup screen creates a
connection named `AlarmDemoDB` pointing at `${data}/alarm-demo.db`, and the
driver makes the file on first use. There is no server, no host, no port, no
user and no password — which is the point: the demo has to install on a machine
where nothing but Ignition has ever been installed.

It is also the only engine that needs nothing beside it. Other drivers do work
on a stock gateway — 8.3.8 ships PostgreSQL, MariaDB and MSSQL as JDBC driver
modules — but every one of them still wants a *server* somebody installed and a
credential somebody typed. SQLite wants a file path.

The connect URL carries two parameters, and both earn their place:

- **`journal_mode=WAL`** is what makes the demo work at all. The plant
  simulation writes journal rows from a gateway timer while a Perspective
  session reads them for the analytics, and rollback-journal SQLite blocks the
  readers for the length of every write.
- **`busy_timeout=30000`** covers the case WAL does not — two writers, the
  timer and the history backfill — by waiting rather than failing.

The pool is Ignition's own default with one change: `poolMaxActive` 8 → 4.
Eight pooled connections onto one SQLite file is eight threads contending for
one write lock.

**The schema is Ignition's, not ours.** `AlarmDemo.backfill.ensureSchema()`
creates `alarm_events` and `alarm_event_data` because the history backfill
inserts into them directly and a brand new gateway has neither — but the DDL
was read off `sqlite_master` on a gateway where the journal profile was made
first and left to create them itself. That matters more than it looks:
`eventtime` is a TEXT column holding epoch **milliseconds** (SQLite has no date
type), and every query in `AlarmDemo.alarms` is written against that
representation. A schema of our own that Ignition merely tolerated would work
until the first event Ignition wrote.

## Sharing a gateway with other work

The demo is built to be imported onto a gateway that already has projects on
it, and two things follow from that.

**Its journal reads and writes are scoped to its own tag provider.** On SQLite
the demo has its own file and nothing else is in it, so this is now
belt-and-braces rather than load-bearing — but it is still true, and it is what
makes naming an *existing* connection safe. `alarm_events` and
`alarm_event_data` are Ignition's *default* journal table names, so on a
gateway where nobody renamed them several projects' profiles write to the same
two tables. Every row this demo produces has a source under `prov:AlarmDemo:`,
and every query, every analytic and the history wipe filter on that prefix.
Verified on a gateway holding 116,000 rows belonging to two other projects: the
demo's Pareto showed only its own alarms, and **Rebuild 30-day history** deleted
only its own rows.

**Its settings live outside the project.** The name of the database connection
is written to `<install dir>/data/alarm-demo-settings.json`, not into a project
resource — so importing a new version never overwrites what the gateway is
pointed at, and an export taken from one gateway cannot arrive on another
pointing at the first one's connection. The project deliberately has no
`ignition/global-props` resource at all, which is where a project's Default
Database and identity provider would otherwise travel.

**It will not overwrite a connection that already exists** under the name it is
about to use. A gateway running this demo may be running other things too.

## What the button cannot do

Modules. Perspective, and Alarm Notification for the rosters — a project script
cannot install one, and there is no API that would let it. The Setup screen
names the missing one instead of failing obscurely: without Alarm Notification
the rosters row says so and every other row still goes green.

Everything else the demo needs, it makes.

## Things worth knowing

- **The simulation runs at 60×.** One second of wall clock is one simulated
  minute, so tanks and filters move fast enough to demonstrate.
- **Priority colours are a status scale**, and everywhere a colour appears the
  priority word appears with it — nothing is carried by colour alone. They are
  the one part of the palette that does not come from the Perspective theme;
  see the front page.
- **The sidebar collapses to an icon rail**, with the toggle in its brand row.
  The screens are built for a desktop or a laptop and every one of them fits
  its window without scrolling from 1280×620 up — verified at eight sizes. A
  short window sheds chrome rather than content: the header bar, the gaps
  between cards and the explanatory line under each card title. There is
  deliberately **no phone layout** — the plant mimic and the wider alarm tables
  need the width, and a breakpoint that reflows the chrome around content that
  still does not fit only makes it look as though it should work.
- **Roster membership is read from the roster config resource, not from
  `system.alarm.getRosters()`.** On 8.3.8 that call returns roster names but an
  empty user list for every roster, including rosters created through the
  gateway's own page. It also belongs to the Alarm Notification module, so on a
  gateway without that module it is missing rather than empty — which is why
  the Setup screen asks the platform for the roster resource type instead, and
  says plainly when the module is absent.
- **Escalation is a design, not gateway configuration.** The rosters and
  schedules are real; the priority-to-roster escalation matrix on the
  Notifications screen is what an alarm notification pipeline would implement on
  top of them. A pipeline needs a working email or SMS profile before it can
  send anything, so it is not part of a self-contained demo.
- **Adding a third site** is a `SITES` entry in `AlarmDemo.alarms`, a set of
  top-level areas, a sim module, and one mimic view. Nothing else is
  site-specific.

## Requirements

**Ignition** 8.3.8 or later (built and verified on 8.3.8), with nothing added
to it.

**Modules**

- Perspective
- Web Developer — for the headless control endpoint
- Alarm Notification — for the on-call rosters. Optional: without it the demo
  installs and runs, the Setup screen says the module is missing, and the
  Notifications and People screens lose their roster half.

**Other:** nothing. The SQLite driver ships with Ignition and the Setup screen
makes the connection.

The queries are SQLite's dialect — `strftime(... 'unixepoch', 'localtime')` for
the date buckets, an OFFSET row for the median, and the zero-filling of empty
buckets done in Jython rather than by `generate_series`. Pointing the demo at
another engine means translating those; pointing it at another *SQLite* file
does not.

## Licence

[Apache-2.0](../LICENSE).
