# What the Setup button does

The ACME Alarm Demo installs as one project zip and then builds the rest of
itself on the gateway it landed on. This document lists everything that
happens when you press **Set up this gateway**, so the decision to press it can
be made on evidence rather than on trust.

Every claim here names the function that makes it true. The code is
`project/ignition/script-python/AlarmDemo/setup/code.py` unless another module
is named.

## In one line

It creates a SQLite database connection, a tag provider, 122 tags, an alarm
journal profile and its two tables, three shift schedules, seven contact
records, three on-call rosters, and thirty days of alarm history. It creates
nothing outside those, it sends nothing anywhere, and it refuses to overwrite
anything it did not make.

## Where it is called from

| Surface | Entry point | Who can reach it |
| ------- | ----------- | ---------------- |
| Setup screen, one row per item | `AlarmDemo.setup.check()`, `.run()`, `.fix(key)` | any Perspective session that can open the project |
| WebDev endpoint | `/system/webdev/AlarmDemo/admin?cmd=setup` | **anyone who can reach the gateway's HTTP port** |

The WebDev endpoint ships with `"require-auth": false` on every method
(`project/com.inductiveautomation.webdev/resources/admin/config.json`). It also
exposes `?cmd=createdb`, `?cmd=backfill`, `?cmd=ackall` and `?cmd=reset`. That
is deliberate for a laptop demo and wrong for anything else. To close it: open
the `admin` WebDev resource in the Designer and tick require-auth, or delete
the resource — nothing on the Setup screen needs it.

The Setup screen carries four buttons: **Set up this gateway** (`run()`),
**Re-check** (`check()`), **Rebuild 30-day history** (`fix("history")`) and
**Reset rosters and shifts** (`run(force=True)`), plus a per-row **Create** for
a single item. Only the last two change anything a person may have edited, and
both say so — see *force*, below.

## What it creates

In install order, which is dependency order. Each item is checked first and
skipped if it is already there; `run()` is safe to press twice.

### 1. Database connection — `AlarmDemoDB`

`_databaseFix` → `createDatabase`, `system.config.create`.

SQLite, in a file beside the gateway:

```text
jdbc:sqlite:${data}/alarm-demo.db?journal_mode=WAL&busy_timeout=30000
```

`${data}` is expanded by Ignition to the gateway's own data directory, so the
file lives where gateway state already lives and travels in a gateway backup.
Driver `SQLite`, translator `SQLITE`, username empty, password `None`. Pool and
timeout values are Ignition's own defaults for a new connection, with one
change: `poolMaxActive` 8 → 4, because eight pooled connections onto one SQLite
file contend for one write lock.

There is no host, no port, no user and no password, which is the whole reason
this can be automated at all. Earlier versions of the demo needed PostgreSQL
and asked for a credential on the Setup screen; that apparatus is gone.

The connection **name** is a setting, stored in
`<gateway data directory>/alarm-demo-settings.json` (`AlarmDemo.config.save`,
written to a `.tmp` file and renamed). The file holds the connection name and
nothing else.

### 2. Tag provider — `AlarmDemo`

`_tagProviderFix`, `system.config.create` / `replace`. A standard provider,
value persistence Database, no read/write/edit permissions set.

### 3. Plant tags

`_tagsFix`, `system.tag.configure("[AlarmDemo]", areas, "o")`.

122 tags and 76 alarm definitions across nine areas, from the copy the project
carries (`AlarmDemo.tagdata`). The collision policy is overwrite, scoped to the
demo's own provider — the call names `[AlarmDemo]` and can reach nothing
outside it. Tag values are simulated every second, so a rerun loses nothing.

### 4. Journal tables

`_journalTablesFix` → `AlarmDemo.backfill.ensureSchema()`.

`alarm_events` and `alarm_event_data`, created in the demo's own SQLite file.
The DDL is what Ignition's own SQLite journal writer creates, read off
`sqlite_master` on a gateway where the profile was left to make them itself.

### 5. Alarm journal profile — `AlarmDemo`

`_journalProfileFix`, `system.config.create` / `replace`. A datasource profile
pointed at the connection above and at those two table names. Store-and-forward
on, pruning off, minimum priority Diagnostic.

### 6. Shift schedules

`_peopleFix` → `AlarmDemo.roster.ensureSchedules()`. Three basic-schedule
config resources: `Day Shift` (06:00–14:00), `Afternoon Shift` (14:00–22:00),
`Night Shift` (22:00–06:00). Ignition's built-in `Always` is used but never
recreated.

### 7. People — seven users in the gateway's `default` user source

`AlarmDemo.roster.ensureUsers()` → `_addPerson`, `system.user.addUser`.

jsmith, achen, rpatel, dwilson, moconnor, shaddad, tnguyen, with
`@acme.example` addresses and `+61 400 …` mobile numbers. All fictional.

**Each is given a random UUID as its password.** The value is generated per
user, never logged, never displayed, and never stored anywhere the project can
read it back. These are contact records for alarm notification, not accounts
anyone signs in with — the password exists only because an internal user source
refuses a user without one. Contact details are added one type at a time and a
gateway that rejects a type (no SMS Notification module, for instance) simply
does not get that one.

An existing user of the same name is left alone, except that a **blank**
schedule is filled in. `run(force=True)` is the exception: it resets everyone
to the shipped shift, discarding schedule changes made on the Notifications
screen.

### 8. On-call rosters

`AlarmDemo.roster.ensureRosters()`. `Operations`, `Maintenance` and
`Management`, seeded with the people above.

These are the one thing not written through `system.config`. In 8.3 a roster is
a config resource holding a membership list and there is no scripting call for
membership, so the demo writes
`config/resources/core/ignition/roster-config/<name>/config.json` and asks the
configuration manager to rescan (`AlarmDemo.roster._writeResource`, `_rescan`).
That is the only place this project writes a file into the gateway's config
tree.

On a gateway without the Alarm Notification module this step is skipped and
says so; everything else still works.

### 9. Thirty days of history

`_historyFix` → `AlarmDemo.backfill.run(days=30, perDay=85)`. Roughly 2,550
journal rows inserted into the demo's own tables, every one with a source under
`prov:AlarmDemo:`.

## The force flag

`run(force=True)` — the **Reset rosters and shifts** button — does one extra
thing: it puts the three rosters and everyone's shift schedule back to the
shipped design, discarding changes made on the Notifications screen. It creates
nothing new and deletes nothing else. Every other step behaves exactly as
above.

## What it will not do

- **It will not overwrite a database connection.** `createDatabase` refuses
  outright if a connection of that name exists, and says so. If the configured
  connection is the wrong engine, `_databaseFix` makes a new SQLite one under a
  free name (`AlarmDemoDB_SQLite`) and repoints the demo — the other
  connection is not touched.
- **It will not count or delete another project's alarm history.**
  `alarm_events` is Ignition's default table name, so a gateway may already
  have one with someone else's events in it. Every journal read here filters on
  `source=["prov:AlarmDemo:*"]`, which is exact because the demo's tags live in
  their own provider.
- **It will not create a user outside the seven listed above**, and it will not
  set a password anyone can use.
- **It will not restart the gateway or run a project scan.** `system.config`
  applies config changes live; the one file-based item (rosters) triggers a
  configuration rescan, which is not a restart.
- **It will not reach the network.** There is no `system.net.*` call, no HTTP
  client and no outbound request anywhere in `AlarmDemo`.

## What it reads

Existing config resources of type `database-connection`, `tag-provider`,
`alarm-journal`, `roster-config`; the resource **type** list, to work out
whether the Alarm Notification module is installed; the user list and schedule
names of the `default` user source; and its own journal rows. `check()` reads
all of this and changes nothing at all.

## Removing it

1. Delete the four config resources: database connection `AlarmDemoDB`, tag
   provider `AlarmDemo`, alarm journal profile `AlarmDemo`, and the three
   `roster-config` resources.
2. Delete the seven users from the `default` user source and the three shift
   schedules.
3. Delete `<gateway data directory>/alarm-demo.db` and
   `alarm-demo-settings.json`.
4. Delete the project.

Everything the demo made is in that list. The SQLite file holds the tables, the
journal rows and nothing else, so deleting it removes the entire data footprint
in one step.

## Checking this document against the code

```bash
grep -n "system\.config\.\|system\.user\.\|system\.tag\.configure" \
    project/ignition/script-python/AlarmDemo/*/code.py
```

That is every call in the project that changes gateway state. The `ITEMS` list
at the bottom of `setup/code.py` is the same nine items in the same order, each
with the check that reports it and the fix that creates it.
