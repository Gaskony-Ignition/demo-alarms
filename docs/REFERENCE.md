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
                            ?cmd=db[&name=Postgres_Test]
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
empty one.

## Sharing a gateway with other work

The demo is built to be imported onto a gateway that already has projects on
it, and two things follow from that.

**Its journal reads and writes are scoped to its own tag provider.**
`alarm_events` and `alarm_event_data` are Ignition's *default* journal table
names, so on a gateway where nobody renamed them, several projects' profiles
write to the same two tables. Every row this demo produces has a source under
`prov:AlarmDemo:`, and every query, every analytic and the history wipe filter
on that prefix. Verified on a gateway holding 116,000 rows belonging to two
other projects: the demo's Pareto shows only its own alarms, and **Rebuild
30-day history** deletes only its own rows.

**Its settings live outside the project.** The name of the database connection
is written to `<install dir>/data/alarm-demo-settings.json`, not into a project
resource — so importing a new version never overwrites what the gateway is
pointed at, and an export taken from one gateway cannot arrive on another
pointing at the first one's connection. The project deliberately has no
`ignition/global-props` resource at all, which is where a project's Default
Database and identity provider would otherwise travel.

**The Setup screen will make the connection if the gateway has not got one.**
Host, port, database, user and password, and it creates a PostgreSQL
connection through `system.config` — the password encrypted with the gateway's
own secret provider, byte-for-byte the shape Ignition's own Databases page
writes. It will **not** overwrite a connection that already exists under that
name: a gateway running this demo is usually running other things too, and
replacing someone else's connection with credentials typed into a demo's setup
page is not a thing a demo gets to do.

## What the button cannot do

Modules. Perspective, a JDBC driver, and Alarm Notification for the rosters —
a project script cannot install one, and there is no API that would let it. The
Setup screen names the missing one instead of failing obscurely: without Alarm
Notification the rosters row says so and every other row still goes green, and
without a PostgreSQL driver the create-connection button says which drivers the
gateway does have.

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

**Ignition** 8.3.8 or later (built and verified on 8.3.8).

**Modules**

- Perspective
- PostgreSQL JDBC Driver — the queries use `split_part`, `generate_series`,
  `percentile_cont` and `to_char`, so another database needs those translated
- Web Developer — for the headless control endpoint
- Alarm Notification — for the on-call rosters. Optional: without it the demo
  installs and runs, the Setup screen says the module is missing, and the
  Notifications and People screens lose their roster half.

**Other:** a PostgreSQL server the gateway can reach. The connection itself is
made by the Setup screen if the gateway has not got one.

## Release notes

**2.0.0** — A standalone project instead of an Ignition Exchange package.
Importing the project is the entire install: no package to unpack, no tag file
to import in the Designer, no config scan. Everything the demo needs that is
not a project resource — the database connection, the tag provider, the tags,
the alarm journal profile, the tables, the schedules, the people, the rosters
and the history — is created by the project itself, from a Setup screen that
reports on every item independently and has a button for each. Every colour resolves to an Ignition theme variable, so
the demo follows the six stock themes and any custom theme on the gateway;
default `dark-cool`. Journal reads and the history wipe are scoped to the
demo's own tag provider, so it is safe on a gateway whose `alarm_events` table
belongs to more than one project.

**1.0.2** — Declares `color-scheme: dark`, so Chrome's "auto dark mode for web
contents" leaves the page alone. With that setting on, Chrome repaints SVG fills
even on a page it otherwise renders correctly, which turned the trend charts'
background white in Chrome while the Designer and every other browser were fine.
Also puts the build number on screen and behind `?cmd=version`.

**1.0.1** — Fixes the alarm-rate and 30-day trend charts rendering with a white
plot area on some gateways. The charts left their background colour unset, so
each gateway supplied its own default — black on 8.3.8, white on newer builds —
and the demo looked correct only on the gateway it was built on.

**1.0.0** — Initial release.

## Licence

[MIT](../LICENSE).
