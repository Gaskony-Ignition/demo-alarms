# ACME Alarm Demo

A self-contained Ignition 8.3 demonstration of **creating, visualising, routing
and analysing alarms**.

## Why this exists

Two simulated plants, 76 alarms, real on-call rosters and shift schedules, and
30 days of journal history, with no PLC, no OPC server and no external device.
A gateway timer script simulates both plants. Every alarm on screen has been
through the real Ignition alarm pipeline: evaluation, deadband, time delay,
priority, acknowledgement, journal, roster and schedule.

**[Download the project →](https://github.com/Gaskony-Ignition/ignition-alarm-demo/releases/latest)**

**Nothing to install but Ignition.** Install a gateway from scratch, import one
zip, press one button. No database server, no JDBC driver to find, no
credentials to type: the demo's database is SQLite, in a file in the gateway's
own data directory, and the button makes it. That is the whole install, on a
laptop in front of a customer, on a machine that has never run Ignition
before.

**And it runs on Ignition Edge**, where there is no database at all. Every
screen is the same one; the analytics read the alarm journal directly instead
of SQL, and the Setup screen's database-shaped rows say what Edge does in their
place rather than going red. There are two zips — see
**[Running this demo on Ignition Edge](docs/EDGE.md)**.

## What it looks like

### Overview — live plant mimic, scoped to the selected site

![Plant overview during the storm scenario](docs/images/overview.png)

### Analytics — Pareto, alarm rate against EEMUA 191, priority mix

![Alarm analytics](docs/images/analytics.png)

### Notifications — who is actually being called, right now

![Alarm notifications and on-call rosters](docs/images/notifications.png)

## What it does

| | |
| --- | --- |
| **Two switchable sites** | ACME Water Treatment Plant, and ACME Manufacturing — a beverage bottling line. Both run continuously, so the switch in the header is instant. |
| **122 tags / 76 alarms** | across 9 process areas, all five priorities, six alarm modes. |
| **12 demo scenarios** | storm, chlorine dose failure, pump trips, filter blinding, a chattering nuisance alarm, line jam, chiller failure, air loss, low CO₂, batch over-temperature. |
| **~10,000 rows of journal history** | 30 days for both sites, with diurnal peaks, quiet weekends, bad actors and realistic acknowledgement behaviour. |
| **Real gateway objects** | 7 users, 3 shift schedules, 3 on-call rosters — visible under Security → Users and Alarming → Rosters, not a table pretending to be them. |
| **9 Perspective screens** | mimic, alarm status, journal, per-area metrics, analytics, notification routing, people and shifts, demo control, setup. |
| **Every Ignition theme** | the six stock variants and any custom theme installed on the gateway, picked from the sidebar. |

Alarm Status and Journal use **Ignition's own stock components**, because the
point is to demonstrate what Ignition does.

The screens meet **WCAG 2.1 AA**, except for limits in Perspective itself: no
page language setting, and the Table and chart components' own internals.

## How to use it

### Install

You need Ignition **8.3.8+** with Perspective. Nothing else — the analytics and
journal history are SQL rather than tag history, and the SQLite driver they run
on ships with Ignition. The Alarm Notification module is needed for the on-call
rosters; without it everything else still works and the Setup screen says so.

**Take the right zip.** Edge permits exactly one realtime tag provider, which
the platform names, so the Edge build is the same project with that name
substituted — a tag path is a literal and cannot be decided at runtime:

| Gateway | Zip |
| ------- | --- |
| Ignition (standard), Maker | `Alarm_Demo-<version>.zip` |
| Ignition Edge | `Alarm_Demo_Edge-<version>.zip` |

Installing on Edge differs in two ways — there is no project import UI, and one
gateway setting has to change before any Perspective session will open at all.
**[docs/EDGE.md](docs/EDGE.md)** covers both; the rest of this section is the
standard build.

1. **Import the project.** Config → Platform → Projects → Import Project,
   choose `Alarm_Demo-<version>.zip` from the
   [latest release](https://github.com/Gaskony-Ignition/ignition-alarm-demo/releases/latest),
   and give it a name.

2. **Open its Setup screen and press "Set up this gateway".**

   ![The Setup screen on a gateway that has nothing yet](docs/images/setup-fresh.png)

   That creates the database connection, the tag provider, the 122 tags and
   their alarms, the alarm journal profile, the journal tables, the three shift
   schedules, the seven users, the three on-call rosters and 30 days of
   history — all of it, on the gateway, from the project. It takes about a
   minute and it is safe to press twice: each item is only created if it is
   missing.

That is the whole install. There is no database server to stand up, no package
to unpack, no tag file to import in the Designer, and no config scan to
remember.

**The database** is a SQLite file in the gateway's own data directory, made by
the same button. A database server somebody has to install first is not a step
in "open a laptop and show a customer", it is the end of it — and neither is a
password somebody has to invent and store. SQLite needs neither.

So there is nothing to type. If the gateway already carries a connection the
demo should use instead, name it and press *Use this one*: the demo remembers
only the NAME, and keeps it outside the project, so importing a newer version
never overwrites what the gateway is pointed at.

The only things left that a button cannot do are the **modules** — Perspective,
and Alarm Notification for the rosters. A project cannot install a module, and
the Setup screen names the one that is missing rather than failing obscurely.

Every item is checked and fixed independently — see
[What the Setup button does](docs/WHAT-SETUP-DOES.md).

The same checks are available headlessly, which is the fastest way to look at a
gateway you cannot open a browser onto:

```
/system/webdev/AlarmDemo/admin?cmd=check
                            ?cmd=setup
                            ?cmd=fix&name=tags
                            ?cmd=createdb
                            ?cmd=analytics
```

The **build number** is at the bottom of the Setup and Demo Control screens, and
at `?cmd=version` — see [What the Setup button does](docs/WHAT-SETUP-DOES.md).
Hard-refresh the browser (`Ctrl+Shift+R`) after upgrading — the stylesheet is
cached.

### Themes

The demo has no colours of its own. Every surface, border, text and accent
colour resolves to one of Ignition's own Perspective theme variables, so it
follows whichever theme the session is set to — the six stock variants, and any
custom theme installed on the gateway. Pick one from the sidebar; the choice
holds for the session.

![The same page on a light theme and a custom theme](docs/images/themes.png)

The project's own default is **dark-cool**, the stock theme closest to the
palette the demo was designed in.

The one exception is the priority scale. Critical, High, Medium, Low and
Diagnostic keep their own colours on every theme, because their meanings are
fixed by convention and a customer has to read the same red as Critical
wherever they see it. What they take from the theme is contrast: each is mixed
toward the theme's own ink, so the scale darkens on a light theme and lightens
on a dark one.

### Running it

Open **Overview** and drive it from **Demo Control**:

- **Chlorine dose pump failure** — residual decays over about a minute and trips
  a Critical compliance alarm. A public-health limit, not a nuisance.
- **Case packer jam** — switch to Manufacturing. The jam blocks everything
  upstream, the line stops, and OEE falls while you watch.
- **Storm** — a cascade across three areas, then open **Analytics** and look at
  the alarm rate against the EEMUA 191 flood line.
- **Chattering nuisance alarm** — then the Pareto shows one source producing
  roughly a fifth of the whole alarm load. That is the alarm-rationalisation
  argument in one chart.
- **People & Shifts → Notifications** — move someone to a different shift and
  watch the "on call now" column follow them.

Scenarios bias the *simulation*, never the alarm state directly, so what you
demonstrate is what a real plant would produce. **Reset plant** returns
everything to normal.

The screens are built for a desktop or a laptop and each fits its window without
scrolling from 1280×620 up. There is deliberately no phone layout — the mimic
and the wider alarm tables need the width.

---

## More

- **[What the Setup button does](docs/WHAT-SETUP-DOES.md)** — every gateway
  object it creates, reads and refuses to touch, and how to remove all of it.
  Read this before pressing it on a gateway that matters.
- **[Reference](docs/REFERENCE.md)** — every screen, the headless control
  endpoint, and the things worth knowing before you point it at a shared
  journal.
- **[Developing](docs/DEVELOPING.md)** — the project is generated from Python;
  build, deploy and the findings behind the way it is put together.
- **[Running this demo on Ignition Edge](docs/EDGE.md)** — what Edge actually
  is from this project's point of view, what the two builds differ in, the one
  thing the Edge build cannot do, and how the two implementations of the
  analytics are proved to agree.

## Licence

[Apache-2.0](LICENSE).
