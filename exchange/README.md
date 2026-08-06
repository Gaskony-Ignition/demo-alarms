# ACME Alarm Demo - Version 1.0.1

A self-contained Ignition 8.3 demonstration of **creating, visualising, routing
and analysing alarms**, across two switchable simulated sites:

- **ACME Water Treatment Plant** - potable water production and distribution
- **ACME Manufacturing** - a beverage bottling and packaging line

No PLC, no OPC server, no external device. A gateway timer script simulates both
plants, and every alarm on screen has been through the real Ignition alarm
pipeline: evaluation, deadband, time delay, priority, acknowledgement, journal,
on-call roster and shift schedule.

Both sites run continuously, so the switch in the header is instant and each
always has live alarms of its own. Everything on screen - the mimic, the header
counts, the journal, every analytic and the notification routing - is scoped to
the selected site.

## What is in it

| Piece | What it gives you |
| ----- | ----------------- |
| **120 tags / 76 alarms** across 9 process areas | all five priorities, and six alarm modes - above/below setpoint, between values, equality, and a diagnostic |
| **Two plant simulations** (1 s gateway timer) | tanks that fill and drain, filters that load until backwashed, and a packaging line where one jam stops everything downstream and drags OEE with it |
| **12 demo scenarios** | storm, chlorine failure, pump trips, filter blinding, chattering nuisance alarm, line jam, chiller failure, air loss, low CO2, batch over-temperature |
| **~10,000 rows of journal history** | 30 days for both sites: diurnal peaks, quiet weekends, a Pareto, chattering bad actors, realistic acknowledgement behaviour |
| **7 real Ignition users, 3 shift schedules, 3 on-call rosters** | genuine gateway objects, visible under Security -> Users, Alarming -> Scheduling and Alarming -> Rosters |
| **8 Perspective screens** | mimic, alarm status, journal, per-area metrics with 30-day trends, analytics, notification routing, people and shifts, demo control |

### The screens

- **Overview** - plant mimic for the selected site. Live tank levels, machine
  run/fault/jam, filter head loss, per-area alarm counts, and a site-scoped
  active alarm table.
- **Alarm Status** - the stock Perspective Alarm Status Table: filter,
  acknowledge, shelve, scoped to the selected site, with an Area selector and a
  priority-colour switch (whole row, as Ignition's own tables do it, or the
  priority column alone). The switch sits at the far right of every screen that
  has one and drives all three alarm tables from one session property.
- **Journal** - Ignition's own Alarm Journal Table against the `AlarmDemo`
  journal profile, with its own filtering, sorting and detail popup, scoped to
  the selected site and themed to the page.
- **Alarm Metrics** - a live metric card per process area, plus **Daily alarm
  load** and **Time to acknowledge** over the last 30 complete days.
- **Analytics** - Pareto of worst sources, alarm rate against the EEMUA 191
  flood threshold, priority mix, never-acknowledged table, and six KPIs.
- **Notifications** - who actually gets each alarm. Real on-call rosters, and a
  live table showing for every active alarm the roster it routes to and who on
  that roster is on shift *right now*. Roster membership is editable here and
  the routing changes immediately.
- **People & Shifts** - the seven people, their Ignition schedule, and whether
  that schedule has them on duty. One click moves someone to another shift - it
  writes a real schedule onto the real user - and the routing follows.
- **Demo Control** - scenario buttons, acknowledge-all, reset, rebuild history,
  and a one-press **Set up this gateway**.

## Installation

### Custom Instructions

Requires a **SQL database connection** - the analytics and the journal history
are SQL, not tag history. Shipped and tested against PostgreSQL; the queries use
`split_part`, `generate_series`, `percentile_cont` and `to_char`, so another
database needs those translated.

The demo creates as much of its own gateway state as a project is allowed to.
Two things it cannot create for itself, because they are not project resources:

1. **A tag provider named `AlarmDemo`.** Create a Standard provider with that
   name, or copy `Gateway/tag-provider/AlarmDemo/` into
   `data/config/resources/core/ignition/tag-provider/` and run
   **Platform -> Overview -> Scan File System**.

   The name matters. An alarm's *Area* is derived from the first tag-path
   segment throughout the project, so the areas have to sit at the root of their
   own provider.

2. **An alarm journal profile named `AlarmDemo`.** Copy
   `Gateway/alarm-journal/AlarmDemo/` into
   `data/config/resources/core/ignition/alarm-journal/` and scan, or create it
   by hand: a Datasource profile against your database, writing the standard
   `alarm_events` / `alarm_event_data` tables.

Then:

3. **Import the project** - `Projects/AlarmDemo.zip` (see Common Instructions).
4. **Import the tags** - Designer, Tag Browser -> Import,
   `Tags/AlarmDemo-tags.json`, targeting the `AlarmDemo` provider.
5. **If your database connection is not called `ignition`**, change the `DB`
   constant at the top of `AlarmDemo.alarms`. It is defined once and the other
   modules read it from there.
6. **Press Set up this gateway** on the Demo Control screen. Equivalently, from
   the Script Console:

   ```python
   AlarmDemo.setup.run()      # safe to run twice
   AlarmDemo.setup.check()    # report what is and is not in place
   ```

   That creates the journal tables, the three shift schedules, the seven users,
   the three on-call rosters, and 30 days of history.

`Gateway/schedule/` and `Gateway/roster-config/` hold the same schedules and
rosters as config resources, for a gateway you would rather set up by file and
scan than by pressing a button. `SQL/01-journal-tables.sql` is the journal
schema, if you prefer to create the tables up front.

### Verifying

`AlarmDemo.setup.check()` - or `/system/webdev/AlarmDemo/admin?cmd=check` -
separates the ways a fresh install goes wrong, which otherwise all present as
the same blank screen. It reports on the tag provider, the alarm journal
**profile**, the journal **tables**, the rosters, the schedules, the users and
who is on duty, each with its own `ok`.

The two journal checks are deliberately separate. The history is written
straight into the tables, so `journalTables` can report thousands of rows while
every journal screen is empty - which is exactly what a missing journal profile
looks like, and the profile is one of the two resources a project import cannot
bring with it. `journalProfile` reads the same rows back *through* the profile,
so only that one can tell the two apart.

### Common Instructions

**Project (.zip/.proj)**
Project backup and restoring from a project backup is referred to as Project
Export and Import. Projects are exported individually, and only include
project-specific elements visible in the Project Browser in the Ignition
Designer. They do not include Gateway resources, like database connections, Tag
Providers, Tags, and images. The exported file (.zip or .proj) is used to
restore / import a project.

.zip = Ignition 8+
.proj = Ignition 7+

There are two primary ways to export and import a project:

Gateway Webpage - exports and imports the entire project.
Designer - exports and imports only those resources that are selected.

When you restore / import a project from an exported file in the Gateway
Webpage, it will be merged into your existing Gateway. If there is a naming
collision, you have the option of renaming the project or overwriting the
project.

**Tags (.json)**
In the Designer, right-click a tag provider or folder in the Tag Browser and
choose Import. Select the JSON file and confirm the target provider.

## Running the demo

Open **Overview**, then drive it from **Demo Control**:

1. **Chlorine dose pump failure** (water) - residual decays over about a minute
   and trips a **Critical** compliance alarm. This is the one that lands: a
   public-health limit, not a nuisance.
2. **Case packer jam** (manufacturing) - switch sites and run it. The jam blocks
   everything upstream, the line stops, and OEE falls while you watch.
3. **Storm** - a cascade across three areas. Good for showing alarm *flood*
   against the EEMUA 191 line on the Analytics screen.
4. **Chattering nuisance alarm** - then open **Analytics**. The Pareto shows one
   source producing roughly a fifth of the entire alarm load. That is the
   alarm-rationalisation argument in one chart.
5. **People & Shifts → Notifications** - move someone to a different shift and
   watch the "On call now" column change. Take the last person on shift off a
   roster and the row reads NOBODY ON SHIFT.
6. **Reset plant** returns everything to normal.

Scenarios bias the *simulation*, never the alarm state directly, so what you
demonstrate is what a real plant would produce.

## Headless control

For scripted demos and for checking a fresh install without opening a Designer:

```
/system/webdev/AlarmDemo/admin?cmd=check
                            ?cmd=setup
                            ?cmd=status
                            ?cmd=rosters
                            ?cmd=scenario&name=Storm
                            ?cmd=reset
                            ?cmd=ackall
                            ?cmd=backfill&days=30
                            ?cmd=summary
                            ?cmd=journal
```

`?cmd=journal` is the profile check above on its own, which makes it the
fastest way to confirm a gateway config scan actually took.

## Things worth knowing

- **`AlarmDemo.backfill.clear()` empties the whole journal**, not just generated
  rows. Correct for a journal profile dedicated to this demo, wrong for a shared
  one - check before pointing the profile at a production journal.
- **The simulation runs at 60x.** One second of wall clock is one simulated
  minute, so tanks and filters move fast enough to demonstrate.
- **Priority colours are a status scale**, and everywhere a colour appears the
  priority word appears with it - nothing is carried by colour alone.
- **The sidebar collapses to an icon rail**, with the toggle in its brand row.
  The screens are built for a desktop or a laptop and every one of them fits
  its window without scrolling from 1280x620 up - verified at eight sizes. A
  short window sheds chrome rather than content: the header bar, the gaps
  between cards and the explanatory line under each card title. There is
  deliberately **no phone layout** - the plant mimic and the wider alarm tables
  need the width, and a breakpoint that reflows the chrome around content that
  still does not fit only makes it look as though it should work.
- **Roster membership is read from the roster config resource, not from
  `system.alarm.getRosters()`.** On 8.3.8 that call returns roster names but an
  empty user list for every roster, including rosters created through the
  gateway's own page.
- **Escalation is a design, not gateway configuration.** The rosters and
  schedules are real; the priority-to-roster escalation matrix on the
  Notifications screen is what an alarm notification pipeline would implement on
  top of them. A pipeline needs a working email or SMS profile before it can
  send anything, so it is not part of a self-contained demo.
- **Adding a third site** is a `SITES` entry in `AlarmDemo.alarms`, a set of
  top-level areas, a sim module, and one mimic view. Nothing else is
  site-specific.

## Requirements

**Ignition version**

+ 8.3.8 or later (built and verified on 8.3.8)

**Modules**

+ Perspective
+ Alarm Notification (for the on-call roster configuration)
+ Web Developer (for the headless control endpoint - optional)

**Other**

+ A SQL database connection (PostgreSQL as shipped)

## Release Notes

1.0.1 - Fixes the alarm-rate and 30-day trend charts rendering with a white
plot area on some gateways. The charts left their background colour unset, so
each gateway supplied its own default - black on 8.3.8, white on newer builds -
and the demo looked correct only on the gateway it was built on. The colour is
now stated in both the component and the stylesheet.

1.0.0 - Initial release.

## License

+ [MIT](https://choosealicense.com/licenses/mit/)
