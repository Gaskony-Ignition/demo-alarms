# Running this demo on Ignition Edge

There are **two release zips** and they are not interchangeable.

| Gateway | Zip |
| ------- | --- |
| Ignition (standard), Maker | `Alarm_Demo-<version>.zip` |
| Ignition Edge | `Alarm_Demo_Edge-<version>.zip` |

Everything below was measured on real gateways of both editions, 8.3.8, on
10/09/2026.

## What Edge actually is, from this project's point of view

An Edge gateway loads a strict subset of the modules a standard one does. The
list from a running Edge 8.3.8:

    Perspective, OPC-UA + drivers, Historian, Alarm Notification,
    WebDev, Vision, Symbol Factory, EAM

and, crucially, **not**: SQL Bridge, any JDBC driver module, the SQL historian.
There is no database connectivity of any kind — not a slower one, an absent
one. `system.db.*` has nothing to run against.

Three more limits matter here:

* **One realtime tag provider.** The platform makes it and calls it `edge`. A
  second is refused at startup.
* **One alarm journal.** The platform makes it, calls it `EdgeJournal`, and it
  is a `LOCAL` profile — history is kept internally, with no datasource
  anywhere. Creating a second is refused outright with
  `UnsupportedOperationException("Cannot create Alarm Journal on Edge")`.
* **A hard cap on concurrent Perspective sessions**, which is low. See
  *Verifying on Edge* below — it is the thing most likely to waste an hour.

## How the demo answers each of those

Everything except the provider name is a **runtime** branch, decided by
`AlarmDemo.edition` asking the gateway what it can do:

| Question | How it is asked |
| -------- | --------------- |
| Is this Edge? | `('ignition', 'edge-sync-settings')` is registered. It is the ONE resource type only Edge has. |
| Can it hold a database? | `('ignition', 'database-connection')` is registered — a question about the platform, not about whether a connection was configured. |
| Which journal holds the history? | The demo's own profile everywhere else; whatever the platform owns on Edge. |

`edge-sync-settings` is not the obvious answer and the obvious answer is wrong:
`edge-system-properties` is registered on a **standard** gateway too, so a
detector built on it fires everywhere and every Edge branch runs in the wrong
place. That mistake cost a sibling project a release.

The **analytics** are the substantial part. All seven were SQL over
`alarm_events`; `AlarmDemo.journalq` implements the same seven over
`system.alarm.queryJournal`, and `AlarmDemo.alarms` dispatches between them.
Nothing in a view knows which one ran.

The **tag provider name** is the one thing substituted at build time, by
`package.sh`. The views carry the provider in over a hundred literal tag paths
and in every alarm source filter, and a provider-less path does not resolve.
So the Edge build is the same project with `[AlarmDemo]` → `[edge]` and
`prov:AlarmDemo:` → `prov:edge:`, and the build refuses to produce a zip in
which either form survives.

## The one thing the Edge build cannot do

**It cannot pre-seed thirty days of history.** The standard build's Setup
button writes 8,900-odd rows straight into `alarm_events`; on Edge the journal
is internal to the platform and no scripting API can insert into it.

So on Edge the history *accumulates as the demo runs* — the simulator raises
alarms continuously, so a gateway left running for an afternoon has a real
day's worth. The Setup screen says exactly this rather than showing a green
row implying thirty days that are not there. Every analytic works from the
first alarm; the window is simply shorter.

**This is specific to the alarm journal, and does not generalise.** TAG history
on Edge *can* be seeded, with `system.historian.storeDataPoints` — measured at
480 backdated points across 20 days on a real Edge gateway, read back through
both the new API and `system.tag.queryTagHistory`. (The legacy
`system.tag.storeTagHistory` is a bridge that accepts the call and silently
discards it against Edge's Internal Historian, which is how this looked
impossible at first.) Alarms are the exception because `system.alarm` has no
write of any kind: query, acknowledge, shelve and rosters, and nothing that
inserts an event.

## Installing

**There is no project import UI on Edge.** Unzip the Edge build over Edge's own
project folder, chown it to the gateway user, and run a project scan:

```
unzip -q Alarm_Demo_Edge-<version>.zip -d ./edge-project
tar -C ./edge-project -cf - . | docker exec -i -u root <container> \
  tar -C /usr/local/bin/ignition/data/projects/Edge -xf -
docker exec -u root <container> \
  chown -R ignition:ignition /usr/local/bin/ignition/data/projects/Edge
```

Then press **Set up this gateway** on the Setup screen. On a fresh Edge gateway
that turns all nine rows green in one press — the four database-shaped rows
report what Edge does instead rather than going red, and none of them offers a
button, because the platform would refuse the create.

The build assumes Edge's provider is called `edge`, which is the name it ships
with. If a site renamed theirs, either rename it back or rebuild with a
different `EDGE_PROVIDER` in `package.sh`.

## Proving the two implementations agree

`?cmd=parity` runs every analytic **both ways over the same journal** and
compares the answers:

```
curl 'http://<standard-gateway>/system/webdev/Alarm_Demo/admin?cmd=parity&site=Water&hours=24&days=30'
```

It only runs where there is a database — on Edge there is no SQL side to
compare against, and it says so rather than reporting a vacuous pass. So the
gate belongs on the **standard** rig, over the backfilled 30 days, and it is
the only thing that keeps the Edge build honest: a drifted analytic returns a
plausible number, not an error.

Run it after any change to either implementation. It has already earned its
keep: it caught the SQL `ORDER BY` having no tiebreaker, so two alarm sources
on the same count could swap places between refreshes — cosmetic on one screen,
and a permanent false mismatch against an implementation that has to sort in
Python.

## The test rigs

`dockers/edge/` and `dockers/standard/` are throwaway gateways for exactly this.
Both use the same image; the **edition is chosen at commissioning** and there
is no environment variable for it, so `tools/commission.js` presses the button:

```
docker compose -f dockers/edge/docker-compose.yml up -d
node tools/commission.js http://localhost:8588 admin password 'Edge Edition'

docker compose -f dockers/standard/docker-compose.yml up -d
node tools/commission.js http://localhost:8488 admin password 'Ignition'
node tools/dismiss-quickstart.js http://localhost:8488
```

Two traps, both of which look like something else:

* A fresh **standard** gateway raises an "Enable Quick Start" modal whose scrim
  covers the whole page. Every headless click times out on an element that is
  plainly visible in the screenshot, including the scan tool's "Log In".
  `tools/dismiss-quickstart.js` clears it once, permanently.
* A **new project directory needs TWO scans**. The first registers the project;
  the second registers its resources with the modules. Between them the project
  is running and its WebDev endpoints 404 with `Project "..." not found`.

## Verifying on Edge

Edge caps concurrent Perspective sessions, and every headless page load takes
one. A verification run that opens four pages at once does not show you four
pages — it shows you **"Sessions Exceeded"** four times, which is an error page
that looks nothing like a rendering fault and tells you nothing about the demo.

So: one page per run, one browser per page (`tools/shoot-page.js` does this),
and leave a gap between runs for the previous session to time out.
