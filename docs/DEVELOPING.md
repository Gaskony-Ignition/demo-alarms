# Alarm Demo — working notes

Source for the **ACME Alarm Demo**, an Ignition 8.3 alarming demonstration
shipped as a standalone importable project. This file covers building and
working on it; nothing here is needed to *use* the demo.

There are two user-facing documents and neither is this one:

- [`README.md`](../README.md) — the repository front page. What it is, the
  screenshots, and the install.
- [`REFERENCE.md`](REFERENCE.md) — every screen, the headless endpoint, the
  requirements and the release notes.

> This folder is *not* part of the Toolbox suite that shares this repository.
> It has no `toolbox-styles` parent, no `tb_` table prefixes and no shared
> infrastructure, deliberately: it has to import onto a customer's gateway as
> one self-contained project.

---

## Build

```bash
./deploy.sh                       # generate, ship and project-scan
./package.sh                      # dist/Alarm_Demo.zip           (dev)
./package.sh --release 3.0.0      # dist/Alarm_Demo-3.0.0.zip     (stamped)

# a gateway with NOTHING on it, for proving the claim the demo makes
docker compose -f tools/fresh-gateway.yml up -d      # http://localhost:8188
node ../../launchpad/tools/preflight.js --gateway fresh   # dismiss Quick Start
./tools/deploy-fresh.sh                              # dev loop, ships project/

# prove the zip on a gateway that has never seen it
node tools/import-project.js --gateway fresh \
     --zip dist/Alarm_Demo-3.0.0.zip --name AlarmDemo [--overwrite]

docker compose -f tools/fresh-gateway.yml down -v    # and it is blank again
```

**`tools/fresh-gateway.yml` is the acceptance rig, and it matters more than it
looks.** The demo's whole claim is "install Ignition, import one zip, press one
button" — which is only true on a gateway with nothing on it. A gateway that
has been used for anything else cannot prove it, because whatever is already
there might be the reason it works. That is not hypothetical: the PostgreSQL
version of this demo was verified on a gateway that had a PostgreSQL driver,
and a blank Ignition has none, so the release could not install on the machine
its own README described. Its own volume, no database container beside it, and
`down -v` throws it away.

`deploy-fresh.sh` carries two things learned the hard way, both silent: `docker
cp` lands files owned by the host user and the gateway cannot rewrite paths it
does not own, and the `chown` that fixes it has to be `docker exec -u root`
because `exec` otherwise runs as the unprivileged `ignition` user and fails
with "Operation not permitted" — which looks like the copy worked, because it
did.

Target gateway is `ignition-maker` on the docker server, toolkit alias
`testbed`. Everything else about it lives in the toolkit's credentials file.

**`deploy.sh` ships project resources and runs one project scan, and that is
the whole deploy.** It used to have `--tags` and `--gateway` flags that pushed
tag definitions and gateway config resources as files and then ran the OTHER,
identically labelled *Scan File System* button. Those are gone: the tag
provider, the tags, the alarm journal profile, the schedules and the rosters
are all created by the project itself now (`AlarmDemo.setup`), which is what
makes the demo a standalone import — and keeping a second, file-based
definition of each of them in the repo was two sources for one thing.

**Every release must be proved by importing the zip**, not by looking at the
dev gateway. `tools/import-project.js` drives Config → Platform → Projects →
Import Project headlessly, so that is one command rather than an intention.
2.0.0 was verified that way onto `ignition-module-testing`: a gateway with no
AlarmDemo provider, no journal profile, a database connection under a different
name, and another project's 116,000 rows already in `alarm_events`. 3.0.0 was
verified onto a container built from nothing minutes earlier, which is the only
gateway that can prove what 3.0.0 changed.

## Theming

The project stylesheet defines no surface colour of its own: every page, card,
border, text and accent colour resolves to one of Ignition's own Perspective
theme variables. Read the comment block at the top of
`project/com.inductiveautomation.perspective/stylesheet/stylesheet.css` before
changing anything there — it is the whole mapping, and the reason there is no
light/dark branching anywhere in the file.

Two things that are not obvious:

- **The priority scale is deliberately NOT `--error` / `--warning` / `--info`.**
  A custom theme is free to define `--error` as a near-black danger *wash* —
  `industrial-dark` in the `ignition-themes` repo does — which would make
  Critical invisible. The scale is the demo's own six colours, mixed toward the
  theme's ink for its text form and the theme's card for its washes, so it
  adapts to a light theme without being redefined.

- **amCharts does not understand `var()`.** Chart colour props are parsed by
  amCharts rather than handed to CSS, so `var(--crit)` reaches it as an
  unrecognised string and it falls back to black — verified 8.3.8, 27/08/2026:
  a donut of five black slices and a trend line drawn in black on a dark card.
  Chart-internal colours are therefore the literals in `build_views.py`'s
  `CHART_*` constants. What follows the theme instead is the chart's CHROME,
  through CSS: `ad-xy-chart` paints every rect the chart draws with
  `var(--card)` and `ad-chart` paints its SVG text with `var(--ink)`. CSS beats
  an SVG presentation attribute on every gateway version, which is why the
  background prop can stay a literal without a light theme showing a dark slab.

**Two overrides in this stylesheet pull opposite ways, and the difference is
specificity, not taste.** `html` is 0-0-1; `:root` is 0-1-0; both match the
same element. The project stylesheet loads AFTER the theme's, so at equal
specificity it wins on order.

| declaration | selector | why |
| --- | --- | --- |
| `--containerBorder` | `:root` | must **outrank** the theme — the theme's value is the broken one |
| `color-scheme` | `html` | must **lose** to the theme — the theme's value is the right one |

Which themes have an opinion about `color-scheme` depends on the **gateway**,
not only on the theme — measured on two of them:

| | vanilla gateway | Theme Installer run |
| --- | --- | --- |
| ten custom packs | declare their own | declare their own |
| `dark-cool` / `dark-warm` / `light-cool` / `light-warm` | **declare none** | declare their own |
| base `light` / `dark` (in the jar) | declare none | declare none |

The Installer is what writes a `gaskony-additions.css` into each stock variant.
On `:root` this line replaced every theme's correct answer with "either",
which puts light scrollbars and light form controls on a dark page for any
viewer whose OS prefers light — the same class of fault as the auto-dark-mode
incident, and equally invisible in a screenshot.

On a **vanilla** gateway a residual remains: `dark-cool`, this project's own
default, declares nothing there, so `light dark` applies to it. Small here —
this project styles its own scrollbars and text inputs from theme variables,
Perspective's other controls are React rather than native, and the reason the
declaration exists at all (keeping Chrome's auto-dark-mode off) works either
way — but real, and not fixable in CSS: **Perspective puts the theme's name
nowhere in the DOM**, no class and no data attribute on `html` or `body`, so
there is nothing for a selector to match on. Running the Theme Installer
resolves it. (This whole pairing, and the correction to it, came from the
session working on `ignition-themes`, 27–28/08/2026.)

`tools/theme-check.js` asserts both, on every theme a gateway has:

```bash
node tools/theme-check.js --gateway http://host:8088
```

It makes **three independent assertions**, and the order matters:

1. `color-scheme` computes to something sane.
2. `--containerBorder` works as a `border` shorthand **on a throwaway element
   of the check's own** — asked by doing exactly what `.ia_inputField` does,
   rather than by parsing the variable's text and hoping the heuristic agrees
   with the CSS parser. This is the load-bearing one: it cannot be defeated by
   a wrong exclusion list, or by a page where every control happens to be
   project-styled, because there is no page in it. It also names the fault
   (`NOT A SHORTHAND (#d3dbd8)`) rather than its symptom.
3. Stock controls on screen actually have a drawn border — the same contract,
   observed where it matters.

(2) is belt to (3)'s braces, and the idea came from the session working on
`ignition-themes`: hardening (3)'s exclusion list fixes the symptom, whereas
asserting the variable removes the whole class of false green.

There are two ways to test your own CSS while believing you are testing the
theme's, and (3) avoids both:

* **Never pin a width.** It asserts a border is *drawn*. `1px` would fail on a
  project class that deliberately sets 2px and report a broken theme when
  nothing is broken.
* **Never assert on a control this project gives a border to.** Such a control
  cannot fail however broken the theme is, so a green run can sit over a broken
  page. `BORDERED_BY_PROJECT` in the script is that exclusion list, explicit so
  it is reviewable — a prefix match would be a rule that quietly widens. A
  screen where *everything* is project-styled reports FAIL, not pass: nothing
  was asserted.

  **That list will go stale, and it is designed not to matter.** A stale
  exclusion list is only dangerous while the exclusion is the one thing
  standing between you and a false green. Because assertion (2) is
  independent, a rotted list costs a *probe* — coverage narrows, and the check
  still fails when the fault is real. What it cannot do is go silently green,
  which is the failure that actually hurt. The mitigation is the design, not
  remembering to update the list.

Measured here rather than assumed: of the two dropdowns on Analytics, the "All
areas" selector carries `ad-btn` and sets its own border, so it stayed green
through the entire negative test and is now excluded. The control that actually
exercises the contract is the **sidebar's theme picker**, which carries only
`ad-theme-select` (font-size) — and which is on every page, so the navigation
to Analytics is for breadth rather than because it is load-bearing.

Every guard has been made to fire, because a check that has never failed is
not a check:

| test | result |
| --- | --- |
| remove the `--containerBorder` line | 10 custom themes FAIL, 6 stock pass — both (2) and (3) fire, and (2) names the bare colour |
| point the control selector at a class that exists nowhere | all 16 FAIL with `NOTHING ASSERTABLE ON SCREEN`, while `border-var: ok` — which is what proves (2) and (3) are independent rather than one implying the other |

**A stock variable this project restates, and why.** Ignition's own
`.ia_inputField` does `border: var(--containerBorder)` - it expects the
SHORTHAND, which is what the six stock themes give it
(`1px solid var(--border)`). All ten of Nigel's custom themes define it as a
bare COLOUR, so under any of them that declaration is invalid, the browser
drops it, and every stock text field and dropdown renders with no border at
all - on `finance-ledger` a white box on a white card, findable only by its
chevron. The stylesheet restates the stock shorthand on `:root`, which is a
no-op on a stock theme and repairs the custom ones; verified by computed
style (`1px solid rgb(211, 219, 216)` on finance-ledger), not by eye, because
on that theme the border colour is close enough to the card that a screenshot
cannot settle it. Found by the session working on `ignition-themes`,
27/08/2026 - the real fix is in that repo's `mapping.py`, and this is here so
the demo does not depend on which version of the pack a gateway has.

The default theme is `dark-cool` (`session-props/props.json`), the stock theme
whose neutrals are closest to the palette the demo was originally drawn in.

## The version

`AlarmDemo.alarms.VERSION` is the single source, and it says `"dev"` in the
repository. `build_views.py` reads that line out of the file rather than
keeping a copy, so the screens cannot drift from the scripts.

`./package.sh --release X.Y.Z` stamps it, plus the project title
(`ACME Alarm Demo X.Y.Z`), the end of the project description (`· vX.Y.Z` — the
Config → Projects grid shows only that column) and the zip's own filename, then
puts the working tree back to `dev` on exit. A gateway running a working copy
says `(dev build)` on screen; a gateway running a release says which one.

## Everything is generated

| Generator | Owns |
| --------- | ---- |
| `build_views.py` | all 21 Perspective views |
| `tags/build_tags.py` | the 122-tag / 76-alarm tree, the Designer tag export, and `AlarmDemo.tagdata` — the same tree embedded in the project, which is how the tags travel inside the export |
| `stamp_resources.py` | every `resource.json` under `project/` |

Edit the generator, never the JSON. `stamp_resources.py` deliberately omits
`lastModificationSignature` and stamps a fresh timestamp: a stale signature
makes the gateway skip the resource during a scan, silently, which is
indistinguishable from the scan not running.

## Gateway state, and what the project can create for itself

Anything not a project resource cannot travel in a project export, so
`AlarmDemo.setup` creates all of it from the project: the tag provider and the
alarm journal profile through `system.config.create`, the tags through
`system.tag.configure` from the copy `AlarmDemo.tagdata` carries, and then the
journal tables, shift schedules, users, on-call rosters and history. Every item
is checked and fixed independently; the Setup screen is one row per entry in
`AlarmDemo.setup.ITEMS`, and `?cmd=check` / `?cmd=fix` are the same calls.

The database CONNECTION is created here too — a SQLite connection at
`jdbc:sqlite:${data}/alarm-demo.db`, from a button with no boxes beside it.
Only the connection's NAME is remembered, in `AlarmDemo.config`'s settings file
beside the gateway's data directory — same pattern as Order Intake's
`Orders.Config`, deliberately.

It used to be PostgreSQL, and the five boxes it needed carried a password,
which is why this section used to carry the two-call `system.secrets` recipe
for writing one safely. That has gone with the form. The finding it recorded is
real and still true — `createEmbeddedSecretConfig()` alone writes the plaintext
verbatim into a file that reads as though it were encrypted, and only
`createEmbeddedSecretConfig(encrypt(x))` is correct — so it lives on in
the workspace note on 8.3 secrets scripting and in Order Intake, both of which
still need it. What is worth keeping *here* is what replaced it: the safest way
to handle a credential in a demo turned out to be to design one that has none.

**Creating the RESOURCE and having a live CONNECTION are different moments.**
The resource registers straight away; the pool then has to start and open the
file, and until it does a query against the name fails - so returning as soon
as `create()` came back had the page saying "created" on one line and "did not
answer" on the next, about the same connection, in the same second.
`createDatabase()` waits for it to answer (bounded, then says so rather than
pretending). Worth generalising: the pre-`system.config` route of writing the
resource files and calling `getConfigurationManager().requestScan()` is
asynchronous too, and anything that reads back the new resource acts on
pre-scan state unless it waits for `getScanInformation()` to change - which is
how Launchpad's setup got a bug where the second project's tags looked like
they needed a human to press Scan File System (thanks to the session working on
that repo for the trade).

Two more `system.config` traps found the same day: **`delete()` needs a
`signature`** exactly as `replace()` does (the error says "missing required
argument", which is at least honest), and `getResourceTypes()` returns
`(moduleId, typeId)` tuples — `('ignition', 'roster-config')` is registered by
the **Alarm Notification module**, so its absence is how you detect a gateway
without that module from a script.

Two things remain manual, because no API creates them: the `AlarmDemo` **tag
provider** and the `AlarmDemo` **alarm journal profile**. Both ship as config
resources under `gateway/` and are applied with a config scan.

`AlarmDemo.setup.check()` reports what is missing without changing anything.

## What the backend is, and is not

Seven Jython modules, one WebDev endpoint, one timer script. Each module has a
single job and says so in its docstring:

| Module | Job |
| ------ | --- |
| `alarms` | everything the views read - live roll-ups, KPIs, journal analytics |
| `sim` / `simmfg` | the two plant models, driven by the 1 s `PlantSim` timer |
| `demo` | scenario selection, reset, acknowledge-all |
| `roster` | people, schedules and on-call rosters, all read back out of Ignition |
| `backfill` | synthetic journal history |
| `setup` | stand the whole thing up on a fresh gateway, and `check()` it |

**`AlarmDemo.alarms` owns the constants.** `DB`, `TABLE` and `PROVIDER` are
defined there and read from there by the others. They used to be copied into
each module, which quietly turned "change the datasource" into a three-file
edit; getting one of them wrong produces a blank screen and no error.

**Every view helper returns a shape, never raises.** `_safe()` wraps each one
and hands back a zeroed default on failure, because an exception inside a
binding renders the whole screen as red error boxes - a worse outcome than a
screen of zeros, and a much harder one to diagnose.

**There are no named queries.** There were five, duplicating the analytics SQL
that `alarms` already runs; nothing called them, and they filtered by area but
not by SITE - so anything that did call them would have shown both plants at
once, which is the one bug this project keeps having to fix. The script
versions are site-scoped, zero-filled where a gap and a zero mean different
things, and shaped for the binding that consumes them.

## SQLite

The demo runs on SQLite so that a gateway needs no database server. Four things
about that are worth knowing before touching a query.

**`eventtime` is TEXT holding epoch milliseconds.** SQLite has no date type,
and this is what Ignition's own journal writer stores — read straight off a
table Ignition created and filled: `typeof(eventtime)` is `'text'` and the
value is `'1787875575442'`. So every comparison CASTs the column to INTEGER and
binds a number (`AlarmDemo.alarms._millis`), rather than binding a Date and
hoping the driver and SQLite's type affinity agree. They might: 13-digit
strings happen to sort the way the numbers do, until the year 2286. That is not
a thing to rely on without saying so.

The backfill has to write the same representation, and does — `unicode(long(
system.date.toMillis(...)))`. Backfilled rows that do not compare against
journalled ones would be worse than none: the charts would simply be missing
half their history with nothing to say why.

**The schema is read off Ignition, not invented.** See the reference doc.

**Three PostgreSQL constructs had no SQLite equivalent**, and each was replaced
by something that is arguably better rather than by a workaround:

| Was | Now |
| --- | --- |
| `split_part(split_part(source,'/tag:',2),'/',1) = ?` | `source LIKE 'prov:AlarmDemo:/tag:<area>/%'` — the prefix is what the source path is *for*, and it is a shape an index can use |
| `generate_series(...) LEFT JOIN` to zero-fill empty buckets | the buckets are built in Jython, which is less SQL for the same result, and hands the chart a real Date rather than a string |
| `percentile_cont(0.5) WITHIN GROUP` | count, then fetch the middle row by `OFFSET`. For an even count that is the lower of the two middle values where `percentile_cont` interpolated; on a figure rounded to one decimal of a minute over thousands of acknowledgements, nobody can read the difference |

**`strftime` buckets in UTC unless told otherwise.** The date-bucket helper
passes `'localtime'` as well as `'unixepoch'`, so a day starts where the
gateway's day starts — which is what `date_trunc` did, and what anyone reading
a daily chart means by a day.

## Findings worth keeping

- **`system.user.addUser`, `editUser` and `removeUser` return a `UIResponse`,
  not a list of validation errors.** It is truthy whether or not anything went
  wrong, and it is not iterable — so `if errors: LOG.warn(list(errors))`
  reports every success as a failure and then raises `TypeError: 'UIResponse'
  object is not iterable` while trying to say so. On a fresh gateway that read
  as seven people "refused by the gateway" on the Setup screen, in the same
  breath as the row above reporting seven people created, because they had
  been. The same shape had quietly cost `setSchedule` its return value: every
  shift change on the People screen succeeded and every one of them reported
  that it had not. The errors are in `getErrors()`; `AlarmDemo.roster.
  _uiProblems` is the only place that reads it. This is the same class of trap
  as a Jython `except Exception` missing a Java `Throwable` — an API that
  signals success and failure through one object that is always present.
- **On-call rosters are config resources in 8.3**, at
  `config/resources/core/ignition/roster-config/<name>/config.json`, holding
  `{"users":[{"profile": ..., "userId": ...}]}`. The field names come from
  `RosterConfig(List<RosterEntry(profile, userId)>)` read off the resource
  type's own default config — any other spelling loads as an *empty* roster with
  no error anywhere.
- **`system.alarm.getRosters()` returns roster names but no members** on 8.3.8,
  including for rosters created through the gateway's own *Create Alarm Roster*
  page — Services → Alarming → Rosters showed `# OF USERS 3` for a roster the
  call reported as empty. `AlarmDemo.roster` therefore reads membership from the
  resource and uses `getRosters()` only to prove the rosters are real.
- **Schedules are scriptable both ways**: `BasicScheduleModel()` +
  `system.user.addSchedule`, or a `schedule` config resource. `isUserScheduled`
  takes a `User` object, not a username.
- **A user with no schedule reports `"Always"`**, so "unset" and "deliberately
  always on call" are indistinguishable. `applyDefaultSchedules()` overwrites
  rather than filling blanks for that reason.
- **Alarm Metrics tag properties (`<folder>.activeCount` and friends) do not
  resolve on this gateway for any folder**, including Ignition's own
  `[default]Chat` and `[default]Roster`. The Alarm Metrics screen aggregates
  from `system.alarm.queryStatus` instead.
- **A Perspective button needs scope `G` and an indented script body.** Neither
  failure reports itself; the button simply does nothing.
- **Two side-by-side charts need `basis: 0%`.** Left to the default, the longer
  subtitle widens its own card, and two date axes of different widths pick
  different label granularities — one chart ends up labelled weekly and the
  other monthly.
- **A blanket `padding-right` on `.ia_table__cell` crushes the alarm table's
  selection column.** That cell is a fixed 30px, so 18px of padding plus the
  inner `.content`'s own 5px left the checkbox 2px to draw in — it rendered as a
  sliver clipped against the table's left edge. The body cell carries
  `select-cell`; the header's select-all does not, so it needs
  `:has(.ia_checkbox)`. Any padding rule aimed at text columns has to exclude
  both.
- **A row of fixed-width columns plus one `grow(1)` will starve the grow
  column.** The People & Shifts roster column collapsed to 26px ("Ope", "Mai")
  because the fixed widths already summed past the container. Give the slack to
  the longest, least important column — here, email.
- **The Alarm Journal Table's journal profile prop is `name`, not
  `journalName`**, and it defaults to `"Journal"` — a profile that does not
  exist here, so the component renders "No results found" with nothing in the
  logs and the journal looks broken. The prop is invisible from the browser
  (the client's props reducer never reads it); the name came out of the
  `component-defaults` websocket frame the gateway sends at session start,
  which is the fastest way to get any Perspective component's real prop list.
  Its `rowStyles` shape also differs from the Alarm Status Table's — keyed by
  event (`active`/`acked`/`cleared`), not by alarm state — and passing the
  wrong one throws inside the component and takes the whole view to an error
  boundary.
- **Both stock alarm components scope by `filters…conditions.source`**, a
  comma-separated list of alarm source paths with wildcards
  (`prov:AlarmDemo:/tag:Intake/*`). That is what keeps one plant's alarms off
  the other plant's screens; they share a tag provider, so without it both
  components list everything.
- **`dateFormat` on both components defaults to `MM/DD/YYYY`.** For the first
  twelve days of a month that is not obviously wrong, just wrong.
- **Never reach a table column by `:nth-child()`.** The hovered row inserts an
  element and shifts every index by one, so the priority tint jumped to the
  Display Path column on whichever row the mouse was over. Use
  `[data-column-id="priority"]`.
- **A generated `resource.json` must have a STABLE uuid.** `build_gateway.py`
  used `uuid4()`, so every rebuild minted fresh identities for the three
  schedules and three on-call rosters: the package was never reproducible, and a
  gateway that had already scanned an earlier build saw the next one as six
  different resources rather than the same six updated. It is now `uuid5()` over
  a fixed namespace and the resource's kind and name, so two consecutive builds
  differ only in the timestamps they are meant to differ in.
- **`deploy.sh` prunes the project directory, and only that one.** Untarring
  over the top adds and overwrites but never removes, so a resource deleted from
  this repo lived on inside the gateway - which is how five deleted named
  queries stayed registered. The prune lists what the archive contains, compares
  it with what is on disk and removes only the difference, so it cannot touch
  anything outside the project or delete a file the repo still has. Gateway
  config directories are deliberately NOT pruned: `config/.../schedule` holds
  every schedule on the gateway, not just this demo's three.
- **Chrome's "auto dark mode for web contents" repaints SVG fills on a page it
  otherwise leaves alone.** This is what the white-plot hunt was actually
  about, and it cost three releases chasing the chart. With that Chrome setting
  on, the trend charts' background rendered white while the *same resources* in
  the Designer, and in Chrome with the setting off, rendered correctly. Nothing
  in the project, the gateway, the Ignition version or the Perspective theme
  differed - it was a browser feature repainting the page after everything else
  had done its job, which is why every server-side probe came back clean.
  `:root { color-scheme: dark }` is the documented opt-out and is now in the
  stylesheet. **It cannot be reproduced headless** - Chromium ignores
  `--force-dark-mode` and `--enable-features=WebContentsForceDark` in headless
  mode, so a screenshot harness will never see it. The lesson: when the DOM,
  the props and the served CSS all say the page is correct and a human still
  sees it wrong, suspect the client, not the page.
- **A chart background of `opacity: 0` is not transparent - it is undefined,
  and the prop alone will not fix it.** The XY charts set
  `background: {"opacity": 0, "render": "color"}` and no colour, on the
  assumption that opacity zero made the colour moot. It does not: the component
  paints a background layer whose colour comes from its own default, which is
  BLACK on 8.3.8 and WHITE on a newer gateway. The demo looked right on the
  gateway it was built on and rendered its trends as white slabs on a
  colleague's.

  Setting `background` to the card colour fixed it here and **did not fix it
  there** - the three charts carried byte-identical JSON and still rendered
  differently on the two gateways, so which SVG layer that prop reaches, or
  whether it is honoured, is version-dependent. The part that holds is the
  `ad-xy-chart` CSS rule, because `fill` in a stylesheet beats the presentation
  attribute the chart writes on any version. Both are kept: the prop is correct
  and self-documenting, the CSS is what makes it true everywhere.

  Blanket `svg rect` is safe for these charts *only* because their series are
  lines - every rect they draw is chrome, bullets are circles, grid lines are
  lines, and the tooltip is an HTML div containing no rect. Adding a column
  series to one of these charts would break that. `ia.chart.pie` has no
  background prop and paints no such layer, so the donut was never affected.

  The general lesson is the one worth keeping: **a default is not a value.**
  Anything left unstated is a promise that every gateway agrees with the one on
  your desk, and this is the second time that promise has been broken here.
- **A trailing space in a label is not rendered.** The page header is two labels
  side by side - site name, then page title - and the site half appended
  `"  -  "` as its separator. HTML collapses whitespace at the end of a text
  node to nothing, and they are separate flex items, so it rendered as
  `ACME Water Treatment Plant -Plant Overview`. The separator has to be
  non-breaking spaces, or a margin.
- **Headless clicking needs the Maker licence modal dismissed *after* the
  session loads**, and its button is `AGREE & CLOSE`. Dismissing too early
  leaves it in front of everything and every click lands on the backdrop —
  which reads exactly like a broken button.

## Responsive

The sidebar collapses to a 62px icon rail. Collapsing is **two** things —
`system.perspective.alterDock` for the layout and a session prop for the
contents — because the dock is absolutely positioned and the page's centre
column is inset separately, so CSS alone leaves a gutter beside the rail.

There is deliberately **no phone breakpoint**. An auto-collapsing dock was
tried and removed (Nigel, 05/08/2026: "the mobile sized version is pretty much
useless as nothing fits"): the mimic and the wide alarm tables do not fit a
phone whatever the sidebar does, and a breakpoint that reflows the chrome
around unusable content only makes it look like it should work. `show:
"visible"` + `handle: "hide"` leaves the rail's own ☰ as the single control —
note that `autoBreakpoint` is consulted ONLY when `show` is the literal
`"auto"`, so it is inert here whatever number it carries.

**Height is the constraint, not width.** A 1366x768 laptop gives a browser about
620-640px of viewport once its own chrome is taken out, which is well short of
the 950 a desktop window has. Three things make that work:

- the Overview mimic has a `minHeight` floor and the page scrolls once below it.
  Without the floor the mimic kept shrinking, the equipment widgets inside it did
  not, and six of them grew scrollbars of their own;
- lists that genuinely cannot fit - the Pareto, the people list, the scenario
  list - scroll themselves. One scrollbar on a list is what a reader expects;
- fixed-width columns, the header's site name and its subtitle are shed by media
  query rather than allowed to overflow, and stat values step down a size so the
  unit beside them never loses a character.

Verified free of spurious scrollbars at 1920x1080, 1700x950, 1536x760, 1440x780,
1366x640 and 1280x620 — at a ONE pixel threshold, which is where they actually
live. The only scrollbars that survive are the three lists above. Desktop and
laptop; not a phone app.

## Layout

```text
build_views.py              generates project/.../views/
tags/build_tags.py          generates tags/build/ and AlarmDemo.tagdata
stamp_resources.py          restamps every project/**/resource.json
project/                    the Ignition project, as an export tree
tools/import-project.js     drives a gateway's Import Project, headlessly
docs/                       these notes, REFERENCE.md, and the screenshots
dist/                       the built project zip
```

Re-shoot the screenshots with the `verify-view` tool after a visual change, at
1600x950, with a scenario running — an idle plant photographs as an alarm demo
with no alarms in it:

```bash
curl "$GATEWAY/system/webdev/AlarmDemo/admin?cmd=scenario&name=Storm"
node .../verify-view/tool/shot.js AlarmDemo "" docs/images/overview.png \
     --w 1600 --h 950 --wait 9000            # --nav Analytics, --nav Notifications
curl "$GATEWAY/system/webdev/AlarmDemo/admin?cmd=reset"
```

Quantise them to 256 colours before committing (Pillow's `im.quantize()`); on
this palette it is visually lossless and thirds the file size.

`setup-fresh.png` is shot on a gateway that has NOT been set up - the point of
the picture is the red rows and the Create buttons, and an all-green board
shows neither. `themes.png` is two Overview shots of the same gateway in
different themes, montaged side by side (`magick montage a.png b.png -tile 2x1
-geometry +6+6`); it needs a gateway with custom themes installed, which the
dev testbed does not have and `ignition-module-testing` does.
