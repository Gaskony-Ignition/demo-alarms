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
./package.sh --release 2.0.0      # dist/Alarm_Demo-2.0.0.zip     (stamped)

# prove the zip on a gateway that has never seen it
node tools/import-project.js --gateway module-testing \
     --zip dist/Alarm_Demo-2.0.0.zip --name AlarmDemo [--overwrite]
```

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
name, and another project's 116,000 rows already in `alarm_events`.

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

The **one** thing it cannot create is the database CONNECTION — that needs
credentials, and a credential has no business inside a project export. Its
name lives in `AlarmDemo.config`, in a settings file beside the gateway's data
directory, written from the Setup screen. Same pattern as Order Intake's
`Orders.Config`, deliberately.

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

## Findings worth keeping

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
