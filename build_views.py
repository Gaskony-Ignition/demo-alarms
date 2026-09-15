#!/usr/bin/env python3
"""Generate the AlarmDemo Perspective views.

Perspective view JSON is verbose and highly repetitive - a mimic panel is the
same tank/pump block a dozen times over with a different tag path. Writing it by
hand invites copy-paste drift between otherwise identical widgets, so it is
generated from a handful of helpers instead. Edit this file, run it, deploy.

Views produced:

    Widgets/Tank        level vessel, fill height + colour from a tag
    Widgets/Pump        run / stop / fault indicator for one pump folder
    Widgets/Stat        a labelled analogue reading with alarm-aware colour
    Widgets/Meter       horizontal bar for filter head loss
    Nav                 docked left navigation
    Overview            plant mimic - the screen the demo opens on
    Status              live alarm status table
    Journal             alarm history
    Analytics           Pareto, rate trend, priority mix, never-acked
    DemoControl         scenario buttons
"""

import io
import json
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
VIEWS = os.path.join(HERE, "project", "com.inductiveautomation.perspective", "views")

# ONE source for the build number, and it is the script the gateway runs:
# AlarmDemo.alarms.VERSION. Reading it out of that file rather than keeping a
# second copy here is what stops the screens and the scripts disagreeing, which
# is worse than showing no version at all.
def _version():
    path = os.path.join(HERE, "project", "ignition", "script-python",
                        "AlarmDemo", "alarms", "code.py")
    with io.open(path, encoding="utf-8") as f:
        m = re.search(r'^VERSION = "([^"]+)"', f.read(), re.M)
    if not m:
        raise SystemExit("no VERSION line in AlarmDemo.alarms - check for drift")
    return m.group(1)


VERSION = _version()

# "v1.2.0" for a release, "(dev build)" for a working copy - "vdev" reads as a
# version number that is not one.
BUILD_TEXT = ("ACME Alarm Demo  (dev build)" if VERSION == "dev"
              else "ACME Alarm Demo  v%s" % VERSION)

PROV = "[AlarmDemo]"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def C(ctype, name, props=None, children=None, style=None, classes=None,
      binds=None, events=None, position=None, custom=None):
    """One component node."""
    props = dict(props or {})
    st = dict(style or {})
    if classes:
        st["classes"] = classes
    if st:
        props["style"] = st
    node = {"type": ctype, "meta": {"name": name}, "props": props}
    if children is not None:
        node["children"] = children
    if binds:
        node["propConfig"] = binds
    if events:
        node["events"] = events
    if position:
        node["position"] = position
    if custom:
        node["custom"] = custom
    return node


def flex(name, children, direction="row", gap=0, justify=None, align=None,
         wrap=None, style=None, classes=None, position=None, binds=None):
    props = {"direction": direction}
    if justify:
        props["justify"] = justify
    if align:
        props["alignItems"] = align
    if wrap:
        props["wrap"] = wrap
    st = dict(style or {})
    if gap:
        st["gap"] = "%dpx" % gap
    return C("ia.container.flex", name, props, children, st, classes,
             position=position, binds=binds)


def label(name, text="", classes=None, style=None, binds=None, position=None,
          events=None):
    return C("ia.display.label", name, {"text": text}, None, style, classes,
             binds=binds, position=position, events=events)


def grow(n=1, basis=None, shrink=1):
    p = {"grow": n, "shrink": shrink}
    if basis is not None:
        p["basis"] = basis
    return p


def fixed(basis, shrink=0):
    return {"grow": 0, "shrink": shrink, "basis": basis}


def tag_bind(path, indirect=None, transform=None):
    """Direct or indirect tag binding. `indirect` maps {"1": "{view.params.x}"}."""
    cfg = {"tagPath": path}
    if indirect:
        cfg["mode"] = "indirect"
        cfg["references"] = indirect
    b = {"type": "tag", "config": cfg}
    if transform:
        b["transforms"] = transform
    return {"binding": b}


def expr_bind(expression, transform=None):
    b = {"type": "expr", "config": {"expression": expression}}
    if transform:
        b["transforms"] = transform
    return {"binding": b}


def prop_bind(path):
    return {"binding": {"type": "property", "config": {"path": path}}}


def prop_bind_rw(path):
    """A property binding that also writes back.

    `bidirectional` goes INSIDE `config`. Beside it, the binding still reads
    and the component still renders the current value - it simply never writes
    a change back, which reads as "the control is decorative".
    """
    return {"binding": {"type": "property",
                        "config": {"path": path, "bidirectional": True}}}


def script_tf(code):
    return [{"type": "script", "code": code}]


def query_bind(qpath, params, poll=30000, transform=None):
    b = {
        "type": "query",
        "config": {
            "queryPath": qpath,
            "bindingType": "NamedQuery",
            "parameters": params,
            "returnFormat": "auto",
            "polling": {"enabled": True, "rate": poll},
        },
    }
    if transform:
        b["transforms"] = transform
    return {"binding": b}


def script_action(code, scope="G"):
    """An action script, indented.

    Perspective drops the script into a generated `def runAction(self, event):`
    body, so an unindented line is a syntax error. It does not surface as a
    broken binding or a red box - the button simply does nothing when clicked,
    which reads as "the feature is not wired up".
    """
    body = "\n".join("\t" + ln if ln.strip() else ln
                     for ln in code.strip("\n").split("\n"))
    return {"config": {"script": body}, "scope": scope, "type": "script"}


def on_nav(page):
    """Navigation is a dom event of TYPE nav, not a script that calls
    system.perspective.navigate. The script form registers the click and then
    silently does nothing."""
    return {"dom": {"onClick": {"config": {"page": page}, "scope": "C",
                                "type": "nav"}}}


def on_click(code, scope="G"):
    """A click handler for a CONTAINER.

    `component.onActionPerformed` is an input-component event: a flex container
    given one registers the click and does nothing at all, silently. Containers
    click through `dom.onClick`.
    """
    return {"dom": {"onClick": script_action(code, scope=scope)}}


def on_action(code, scope="G"):
    """Button action.

    Scope G and an indented body - both matter, and neither failure reports
    itself. An unindented script is a syntax error inside the generated
    `def runAction(self, event):`; the button then does nothing at all when
    clicked, with no console error and no broken-binding marker.
    """
    return {"component": {"onActionPerformed": script_action(code, scope=scope)}}


def view(root, params=None, custom=None, propconfig=None, size=(1600, 900)):
    v = {
        "custom": custom or {},
        "params": params or {},
        "props": {"defaultSize": {"width": size[0], "height": size[1]}},
        "root": root,
    }
    if propconfig:
        v["propConfig"] = propconfig
    return v


def write(path, v):
    d = os.path.join(VIEWS, path)
    if not os.path.isdir(d):
        os.makedirs(d)
    with open(os.path.join(d, "view.json"), "w") as f:
        json.dump(v, f, indent=2)
        f.write("\n")


def param_in(*names):
    return dict((("params." + n), {"paramDirection": "input", "persistent": True})
                for n in names)


# ---------------------------------------------------------------------------
# The chart palette - the one place a CSS variable cannot go
# ---------------------------------------------------------------------------
#
# Everything else in this file names a colour as `var(--crit)` and lets the
# stylesheet resolve it against whichever Perspective theme the session is on.
# The chart components are the exception: amCharts PARSES its colour props
# rather than handing them to CSS, so `var(--...)` reaches it as an
# unrecognised string and it falls back to black - a donut of five black
# slices and a trend line drawn in black on a dark card.
#
# So chart-internal colours are literals, and they are the same six bases the
# stylesheet publishes as --crit-base ... --ok-base. Change one, change both.
# Anything that has to MATCH a chart - the priority legend's swatches sit
# beside the donut's slices - uses these too, for the same reason.
#
# What follows the theme instead is the chart's chrome, and it does it through
# CSS: `ad-xy-chart` paints every rect the chart draws with var(--card), and
# `ad-chart` paints its SVG text with var(--ink). Both beat an SVG
# presentation attribute on every gateway version, which is why the background
# prop below can stay a literal without a light theme showing a dark slab.
CHART_CRIT = "#E5225B"
CHART_HIGH = "#F58220"
CHART_MED = "#F5C518"
CHART_LOW = "#4EA8FF"
CHART_DIAG = "#8B98A9"
CHART_OK = "#35C46A"


# ---------------------------------------------------------------------------
# Widgets/Tank
# ---------------------------------------------------------------------------


def w_tank():
    """A vessel whose fill height and colour track a level tag.

    Colour is driven by how close the level is to its alarm setpoints rather
    than by a fixed threshold, so the same widget works for a wet well (low is
    bad), a clearwater tank (both ends bad) and a chemical day tank.
    """
    shell = flex(
        "Shell",
        [
            # A grow-1 spacer pins the fill to the bottom. Perspective's
            # `justify` prop takes left/center/right rather than the CSS
            # flex-end spelling, and its meaning in a column is not obvious -
            # a spacer is unambiguous in both axes.
            flex("Spacer", [], direction="column", position=grow(1)),
            flex("Fill", [], direction="column",
                 classes="ad-tank-fill",
                 position={"grow": 0, "shrink": 0, "basis": "0px"},
                 binds={
                     "position.basis": expr_bind(
                         "toStr(max(0, min(100, {view.custom.level}))) + \"%\""
                     ),
                     "props.style.classes": expr_bind(
                         "\"ad-tank-fill\" "
                         "+ if({view.params.chem} = true, \" ad-tank-fill-chem\", \"\") "
                         "+ if({view.custom.level} <= {view.params.critLow} "
                         "     || {view.custom.level} >= {view.params.critHigh}, "
                         "     \" ad-tank-fill-crit\", "
                         "     if({view.custom.level} <= {view.params.warnLow} "
                         "        || {view.custom.level} >= {view.params.warnHigh}, "
                         "        \" ad-tank-fill-warn\", \"\"))"
                     ),
                 }),
        ],
        direction="column",
        classes="ad-tank-shell",
        position=grow(1),
        style={"minHeight": "90px"},
    )

    root = flex(
        "root",
        [
            label("Title", classes="ad-equip-name", position=fixed("15px"),
                  binds={"props.text": prop_bind("view.params.title")}),
            shell,
            flex("Readout", [
                label("Value", classes="ad-tank-value", position=grow(1),
                      binds={"props.text": expr_bind(
                          "numberFormat({view.custom.level}, \"0.0\")")}),
                label("Unit", "%", classes="ad-kpi-unit", position=fixed("22px")),
            ], gap=3, align="baseline", position=fixed("20px")),
        ],
        direction="column", gap=5,
        style={"padding": "8px"},
        classes="ad-equip",
    )

    write("AlarmDemo/Widgets/Tank", view(
        root,
        params={"title": "Tank", "path": "", "warnLow": 25, "critLow": 10,
                "warnHigh": 90, "critHigh": 96, "chem": False},
        custom={"level": 0},
        propconfig=dict(
            list(param_in("title", "path", "warnLow", "critLow",
                          "warnHigh", "critHigh", "chem").items())
            + [("custom.level", tag_bind(PROV + "{1}",
                                         indirect={"1": "{view.params.path}"}))]
        ),
        size=(150, 210),
    ))


# ---------------------------------------------------------------------------
# Widgets/Pump
# ---------------------------------------------------------------------------


def w_pump():
    """Run / stopped / faulted indicator for one pump folder.

    Reads Run and Fault from the folder given in `path`. Fault wins over Run -
    a faulted pump that the PLC still shows as commanded on must not display
    as healthy.
    """
    root = flex(
        "root",
        [
            flex("Row", [
                C("ia.container.flex", "Dot", {"direction": "row"}, [],
                  {}, "ad-dot",
                  binds={"props.style.classes": expr_bind(
                      "if({view.custom.fault} = true, \"ad-dot ad-dot-fault\", "
                      "if({view.custom.run} = true, \"ad-dot ad-dot-run\", "
                      "\"ad-dot ad-dot-stop\"))")},
                  position=fixed("10px")),
                label("Name", classes="ad-equip-name", position=grow(1),
                      binds={"props.text": prop_bind("view.params.title")}),
            ], gap=8, align="center", position=fixed("15px")),
            # State and current share a line. As two lines the widget wanted
            # 60px, and three of them stacked set the floor for the whole
            # Distribution card - which is what made the mimic unable to draw
            # in a laptop's height without every widget growing a scrollbar.
            flex("Reading", [
                label("State", classes="ad-equip-state", position=grow(1),
                      binds={
                          "props.text": expr_bind(
                              "if({view.custom.fault} = true, \"FAULT\", "
                              "if({view.custom.run} = true, \"RUNNING\", \"STOPPED\"))"),
                          "props.style.color": expr_bind(
                              "if({view.custom.fault} = true, \"var(--crit)\", "
                              "if({view.custom.run} = true, \"var(--ok)\", \"var(--ink-3)\"))"),
                      }),
                label("Amps", classes="ad-faint", position=fixed("52px"),
                      style={"fontSize": "11px", "textAlign": "right",
                             "whiteSpace": "nowrap"},
                      binds={"props.text": expr_bind(
                          "numberFormat({view.custom.amps}, \"0.0\") + \" A\"")}),
            # 16, not 14: the RUNNING line box is 15 and Chromium answers a
            # one-pixel overflow with a scrollbar down the side of the widget.
            ], gap=6, align="baseline", position=fixed("16px")),
        ],
        direction="column", gap=2,
        classes="ad-equip",
    )

    write("AlarmDemo/Widgets/Pump", view(
        root,
        params={"title": "Pump", "path": ""},
        custom={"run": False, "fault": False, "amps": 0},
        propconfig=dict(
            list(param_in("title", "path").items()) + [
                ("custom.run", tag_bind(PROV + "{1}/Run",
                                        indirect={"1": "{view.params.path}"})),
                ("custom.fault", tag_bind(PROV + "{1}/Fault",
                                          indirect={"1": "{view.params.path}"})),
                ("custom.amps", tag_bind(PROV + "{1}/Amps",
                                         indirect={"1": "{view.params.path}"})),
            ]
        ),
        size=(150, 68),
    ))


# ---------------------------------------------------------------------------
# Widgets/Stat
# ---------------------------------------------------------------------------


def w_stat():
    """A labelled analogue reading that turns amber / red as it approaches or
    passes its alarm setpoint. `invert` handles the low-is-bad case."""
    root = flex(
        "root",
        [
            label("Label", classes="ad-kpi-label", position=fixed("14px"),
                  binds={"props.text": prop_bind("view.params.title")}),
            flex("Row", [
                label("Value", position=grow(1), classes="ad-kpi-value",
                      style={"fontSize": "24px"},
                      binds={
                          "props.text": expr_bind(
                              "numberFormat({view.custom.value}, {view.params.fmt})"),
                          "props.style.color": expr_bind(
                              "if({view.params.invert} = true, "
                              "  if({view.custom.value} <= {view.params.crit}, \"var(--crit)\", "
                              "  if({view.custom.value} <= {view.params.warn}, \"var(--med)\", \"var(--ink)\")), "
                              "  if({view.custom.value} >= {view.params.crit}, \"var(--crit)\", "
                              "  if({view.custom.value} >= {view.params.warn}, \"var(--med)\", \"var(--ink)\")))"),
                      }),
                label("Unit", classes="ad-kpi-unit", position=fixed("46px"),
                      style={"paddingBottom": "3px"},
                      binds={"props.text": prop_bind("view.params.unit")}),
            ], gap=4, align="end", position=grow(1),
                style={"overflow": "hidden"}),
        ],
        direction="column", gap=2,
        classes="ad-equip",
    )

    write("AlarmDemo/Widgets/Stat", view(
        root,
        params={"title": "Value", "path": "", "unit": "", "fmt": "0.00",
                "warn": 1e9, "crit": 1e9, "invert": False},
        custom={"value": 0},
        propconfig=dict(
            list(param_in("title", "path", "unit", "fmt", "warn", "crit",
                          "invert").items())
            + [("custom.value", tag_bind(PROV + "{1}",
                                         indirect={"1": "{view.params.path}"}))]
        ),
        size=(170, 74),
    ))


# ---------------------------------------------------------------------------
# Widgets/Meter - filter head loss
# ---------------------------------------------------------------------------


def w_meter():
    root = flex(
        "root",
        [
            flex("Head", [
                label("Name", classes="ad-equip-name", position=grow(1),
                      binds={"props.text": prop_bind("view.params.title")}),
                label("Val", classes="ad-equip-state", position=fixed("70px"),
                      style={"textAlign": "right", "color": "var(--ink-2)"},
                      binds={"props.text": expr_bind(
                          "numberFormat({view.custom.value}, \"0.0\") + \" \" "
                          "+ {view.params.unit}")}),
            ], gap=6, align="baseline", position=fixed("15px")),
            flex("Bar", [
                flex("Fill", [], classes="ad-meter-fill",
                     position={"grow": 0, "shrink": 0, "basis": "0px"},
                     binds={
                         "position.basis": expr_bind(
                             "toStr(max(0, min(100, 100 * {view.custom.value} "
                             "/ {view.params.max}))) + \"%\""),
                         "props.style.classes": expr_bind(
                             "if({view.custom.value} >= {view.params.crit}, "
                             "\"ad-meter-fill-crit\", "
                             "if({view.custom.value} >= {view.params.warn}, "
                             "\"ad-meter-fill-warn\", \"ad-meter-fill\"))"),
                     }),
            ], classes="ad-meter", position=fixed("8px")),
            label("Sub", classes="ad-faint", position=fixed("13px"),
                  style={"fontSize": "10.5px"},
                  binds={"props.text": expr_bind(
                      "\"turbidity \" + numberFormat({view.custom.sub}, \"0.000\") "
                      "+ \" NTU\" + if({view.custom.bw} = true, \"  -  BACKWASHING\", \"\")"),
                      "props.style.color": expr_bind(
                          "if({view.custom.bw} = true, \"var(--low)\", "
                          "if({view.custom.sub} >= 0.30, \"var(--high)\", \"var(--ink-3)\"))")}),
        ],
        direction="column", gap=4,
        classes="ad-equip",
    )

    write("AlarmDemo/Widgets/Meter", view(
        root,
        params={"title": "Filter", "path": "", "unit": "kPa", "max": 100,
                "warn": 60, "crit": 80},
        custom={"value": 0, "sub": 0, "bw": False},
        propconfig=dict(
            list(param_in("title", "path", "unit", "max", "warn", "crit").items())
            + [
                ("custom.value", tag_bind(PROV + "{1}/DiffPressure",
                                          indirect={"1": "{view.params.path}"})),
                ("custom.sub", tag_bind(PROV + "{1}/Turbidity",
                                        indirect={"1": "{view.params.path}"})),
                ("custom.bw", tag_bind(PROV + "{1}/BackwashActive",
                                       indirect={"1": "{view.params.path}"})),
            ]
        ),
        size=(230, 70),
    ))




# ---------------------------------------------------------------------------
# Widgets/Machine - a driven line machine (manufacturing)
# ---------------------------------------------------------------------------


def w_machine():
    """Run / stopped / jammed / faulted for one packaging-line machine.

    Order matters: fault beats jam beats stopped. A machine that is jammed and
    also commanded to run must not read as healthy.
    """
    root = flex(
        "root",
        [
            flex("Row", [
                C("ia.container.flex", "Dot", {"direction": "row"}, [],
                  {}, "ad-dot",
                  binds={"props.style.classes": expr_bind(
                      "if({view.custom.fault} = true, \"ad-dot ad-dot-fault\", "
                      "if({view.custom.jam} = true, \"ad-dot ad-dot-jam\", "
                      "if({view.custom.run} = true, \"ad-dot ad-dot-run\", "
                      "\"ad-dot ad-dot-stop\")))")},
                  position=fixed("10px")),
                label("Name", classes="ad-equip-name", position=grow(1),
                      binds={"props.text": prop_bind("view.params.title")}),
            ], gap=8, align="center", position=fixed("15px")),
            # One line, as on the Pump widget - see there for why.
            flex("Reading", [
                label("State", classes="ad-equip-state", position=grow(1),
                      binds={
                          "props.text": expr_bind(
                              "if({view.custom.fault} = true, \"FAULT\", "
                              "if({view.custom.jam} = true, \"JAM\", "
                              "if({view.custom.run} = true, \"RUNNING\", \"STOPPED\")))"),
                          "props.style.color": expr_bind(
                              "if({view.custom.fault} = true, \"var(--crit)\", "
                              "if({view.custom.jam} = true, \"var(--med)\", "
                              "if({view.custom.run} = true, \"var(--ok)\", \"var(--ink-3)\")))"),
                      }),
                label("Amps", classes="ad-faint", position=fixed("52px"),
                      style={"fontSize": "11px", "textAlign": "right",
                             "whiteSpace": "nowrap"},
                      binds={"props.text": expr_bind(
                          "numberFormat({view.custom.amps}, \"0.0\") + \" A\"")}),
            ], gap=6, align="baseline", position=fixed("16px")),
        ],
        direction="column", gap=2,
        classes="ad-equip",
    )

    write("AlarmDemo/Widgets/Machine", view(
        root,
        params={"title": "Machine", "path": ""},
        custom={"run": False, "fault": False, "jam": False, "amps": 0},
        propconfig=dict(
            list(param_in("title", "path").items()) + [
                ("custom.run", tag_bind(PROV + "{1}/Run",
                                        indirect={"1": "{view.params.path}"})),
                ("custom.fault", tag_bind(PROV + "{1}/Fault",
                                          indirect={"1": "{view.params.path}"})),
                ("custom.jam", tag_bind(PROV + "{1}/Jam",
                                        indirect={"1": "{view.params.path}"})),
                ("custom.amps", tag_bind(PROV + "{1}/Amps",
                                         indirect={"1": "{view.params.path}"})),
            ]
        ),
        size=(150, 68),
    ))

def w_motor():
    """Run / fault for kit with no current measurement (compressor, chiller).

    A separate widget rather than a flag on the Pump widget: the Pump binds an
    Amps tag, and pointing that binding at a folder without one renders a red
    error box on the mimic rather than simply omitting the reading.
    """
    root = flex(
        "root",
        [
            flex("Row", [
                C("ia.container.flex", "Dot", {"direction": "row"}, [],
                  {}, "ad-dot",
                  binds={"props.style.classes": expr_bind(
                      "if({view.custom.fault} = true, \"ad-dot ad-dot-fault\", "
                      "if({view.custom.run} = true, \"ad-dot ad-dot-run\", "
                      "\"ad-dot ad-dot-stop\"))")},
                  position=fixed("10px")),
                label("Name", classes="ad-equip-name", position=grow(1),
                      binds={"props.text": prop_bind("view.params.title")}),
            ], gap=8, align="center", position=fixed("15px")),
            label("State", classes="ad-equip-state", position=fixed("14px"),
                  binds={
                      "props.text": expr_bind(
                          "if({view.custom.fault} = true, \"FAULT\", "
                          "if({view.custom.run} = true, \"RUNNING\", \"STOPPED\"))"),
                      "props.style.color": expr_bind(
                          "if({view.custom.fault} = true, \"var(--crit)\", "
                          "if({view.custom.run} = true, \"var(--ok)\", \"var(--ink-3)\"))"),
                  }),
        ],
        direction="column", gap=2,
        classes="ad-equip",
    )
    write("AlarmDemo/Widgets/Motor", view(
        root,
        params={"title": "Motor", "path": ""},
        custom={"run": False, "fault": False},
        propconfig=dict(
            list(param_in("title", "path").items()) + [
                ("custom.run", tag_bind(PROV + "{1}/Run",
                                        indirect={"1": "{view.params.path}"})),
                ("custom.fault", tag_bind(PROV + "{1}/Fault",
                                          indirect={"1": "{view.params.path}"})),
            ]
        ),
        size=(150, 64),
    ))


# ---------------------------------------------------------------------------
# Widgets/PriorityCell - a table cell that colours the alarm priority
# ---------------------------------------------------------------------------


def w_prioritycell():
    """Renders one table cell as a priority chip, or as plain text on a row
    that is already tinted.

    Perspective tables have no conditional row formatting, so per-row colour
    has to come from a cell rendered as a view (`render: "view"`). Two modes,
    matching the stock Alarm Status Table:

        cells   the row stays neutral and only this cell is coloured
        rows    the whole row is tinted and this cell is plain text, so the
                colour is not stated twice

    The `ad-p-<priority>` class is emitted in BOTH modes and is never styled
    itself. It is the hook the whole-row tint hangs off: the stylesheet selects
    a row with `:has(.psc-ad-p-critical)`, which only works if the marker
    survives the mode that removes the chip.

    The priority word is present either way, so nothing is carried by colour
    alone.
    """
    root = flex(
        "root",
        [
            label("Chip", position=fixed("auto"),
                  style={"padding": "2px 10px"},
                  binds={
                      "props.text": prop_bind("view.params.value"),
                      "props.style.classes": expr_bind(
                          "\"ad-p-\" + lower({view.params.value}) + "
                          "if({session.custom.alarmColour} = \"cells\", "
                          "\" ad-chip ad-chip-\" + lower({view.params.value}), "
                          "\" ad-plain-cell\")"),
                  }),
        ],
        align="center", justify="left",
        style={"height": "100%"},
    )
    write("AlarmDemo/Widgets/PriorityCell", view(
        root,
        params={"value": ""},
        propconfig=param_in("value"),
        size=(110, 28),
    ))




def w_statecell():
    """State rendered as a chip, so the row can be styled from its contents."""
    root = flex("root", [
        label("Chip", position=fixed("auto"),
              style={"padding": "2px 10px"},
              binds={
                  "props.text": prop_bind("view.params.value"),
                  "props.style.classes": expr_bind(
                      "if({view.params.value} = \"Cleared\", "
                      "\"ad-chip ad-state-cleared\", \"ad-chip ad-state-active\")"),
              }),
    ], align="center", justify="left", style={"height": "100%"})
    write("AlarmDemo/Widgets/StateCell", view(
        root, params={"value": ""}, propconfig=param_in("value"),
        size=(110, 28)))


# ---------------------------------------------------------------------------
# shared pieces
# ---------------------------------------------------------------------------


def col(field, title=None, width=None, justify=None, fmt=None, render=None,
        view_path=None):
    """One table column. Numeric columns get a fixed narrow width so the text
    column keeps the space and stops wrapping onto two lines."""
    c = {"field": field, "visible": True, "editable": False,
         "header": {"title": title if title is not None else field}}
    if width:
        c["width"] = width
        c["strictWidth"] = True
    if justify:
        c["justify"] = justify
        c["header"]["justify"] = justify
    if fmt:
        c["numberFormat"] = fmt
    if render:
        c["render"] = render
    if view_path:
        c["viewPath"] = view_path
    return c


def priority_col(field="Priority", width=112):
    return col(field, "Priority", width=width, render="view",
               view_path="AlarmDemo/Widgets/PriorityCell")


def colour_switch(name="ColourSwitch", label_text="PRIORITY COLOUR"):
    """Whole row vs priority column - the two ways an alarm list is coloured.

    Deliberately NOT an on/off toggle. Both settings colour by priority; the
    only question is whether the colour is on the row, as Ignition's own alarm
    tables do it, or on the priority column alone. Turning priority colour off
    entirely was never the useful third option - the priority word is in the
    row either way, so nothing is lost by always showing the colour.

    One control, one session property, every screen - the Alarm Status table,
    the Alarm Journal table and the Overview strip all follow it, so the choice
    does not have to be made again per screen. It sits LAST in its row
    everywhere for the same reason: a control that moves between screens is a
    control the audience has to hunt for.
    """
    return flex(name, [
        label("L", label_text, classes="ad-kpi-label",
              position=fixed("116px"), style={"alignSelf": "center"}),
    ] + [
        C("ia.input.button", "M_%s" % key, {
            "text": lbl, "style": {"classes": "ad-btn ad-btn-sm"},
        }, position=fixed("122px"),
            events=on_action("self.session.custom.alarmColour = '%s'" % key),
            binds={"props.style.classes": expr_bind(
                "if({session.custom.alarmColour} = \"%s\", "
                "\"ad-btn ad-btn-sm ad-btn-active\", \"ad-btn ad-btn-sm\")" % key)})
        for key, lbl in (("rows", "Whole row"), ("cells", "Priority only"))
    # 116 + 8 + 122 + 8 + 122 = 376. A basis under that overflows by a few
    # pixels and the row grows a horizontal scrollbar of its own.
    ], gap=8, align="center", position=fixed("380px"))


def embed(name, path, params, position=None):
    return C("ia.display.view", name,
             {"path": path, "params": params},
             None, None, None, position=position)


def priority_chips(name="Chips", position=None):
    """Live active-alarm counts, one chip per priority. Count and word are both
    in the chip, so the colour is reinforcement rather than the only signal."""
    chips = []
    for pri, cls in (("Critical", "critical"), ("High", "high"),
                     ("Medium", "medium"), ("Low", "low")):
        chips.append(label(
            pri, classes="ad-chip ad-chip-%s" % cls,
            style={"padding": "3px 11px"},
            position=fixed("auto"),
            binds={
                "props.text": expr_bind(
                    "toStr({session.custom.live.counts.%s}) + \"  %s\"" % (pri, pri.upper())),
                "props.style.classes": expr_bind(
                    "\"ad-chip ad-chip-%s\" + if({session.custom.live.counts.%s} > 0, "
                    "\" ad-live\", \"\")" % (cls, pri))
                if pri in ("Critical", "High") else None,
            } if pri in ("Critical", "High") else {
                "props.text": expr_bind(
                    "toStr({session.custom.live.counts.%s}) + \"  %s\"" % (pri, pri.upper())),
            },
        ))
    return flex(name, chips, gap=7, align="center", position=position)


def site_switch(name="SiteSwitch"):
    """Two-button site selector. The selected site drives the mimic, the
    header text, and the area scope of every alarm query on every screen."""
    return flex(name, [
        C("ia.input.button", "B_%s" % key, {
            "text": lbl, "style": {"classes": "ad-btn"},
        }, position=fixed("%dpx" % width),
            events=on_action("self.session.custom.site = '%s'" % key),
            binds={"props.style.classes": expr_bind(
                "if({session.custom.site} = \"%s\", \"ad-btn ad-btn-active\", "
                "\"ad-btn\")" % key)})
        for key, lbl, width in (("Water", "Water Treatment", 140),
                                ("Manufacturing", "Manufacturing", 130))
    ], gap=6, align="center", position=fixed("auto"))


def header():
    """Shared page header. Title and subtitle come from the selected site, so
    there is one header rather than one per plant."""
    return flex("Header", [
        flex("Titles", [
            # Site and page title are two labels, not one string, so the site
            # half can be dropped on a laptop. As one string it truncated
            # mid-word - "ACME Water Treatment P" - and the page you were
            # actually on was the part that fell off the end. The sidebar
            # already names the site under ACME.
            flex("TitleRow", [
                label("Site", classes="ad-title ad-title-site",
                      position=fixed("auto"),
                      style={"whiteSpace": "nowrap"},
                      # Non-breaking spaces around the dash. Ordinary spaces at
                      # the end of a text node are collapsed away, and these two
                      # labels are separate flex items - so "Plant  -  Overview"
                      # rendered as "Plant -Overview".
                      binds={"props.text": expr_bind(
                          u"{session.custom.siteInfo.label}"
                          u" + \"  -  \"")}),
                label("Title", classes="ad-title", position=grow(1),
                      style={"whiteSpace": "nowrap", "overflow": "hidden",
                             "textOverflow": "ellipsis"},
                      binds={"props.text": prop_bind("page.props.title")}),
            ], gap=0, align="center", position=fixed("26px")),
            label("Sub", classes="ad-subtitle ad-title-site",
                  position=fixed("15px"),
                  style={"whiteSpace": "nowrap", "overflow": "hidden",
                         "textOverflow": "ellipsis"},
                  binds={"props.text": prop_bind(
                      "session.custom.siteInfo.subtitle")}),
        ], direction="column", position=grow(1)),
        site_switch(),
        flex("Scenario", [
            label("ScenarioLabel", classes="ad-scenario-banner",
                  style={"padding": "5px 12px"},
                  position=fixed("auto"),
                  binds={
                      "props.text": expr_bind(
                          "\"SCENARIO:  \" + upper({session.custom.scenario})"),
                      "props.style.display": expr_bind(
                          "if({session.custom.scenario} = \"None\", \"none\", \"flex\")"),
                  }),
        ], align="center", position=fixed("auto")),
        priority_chips(position=fixed("auto")),
    ], gap=14, align="center",
        style={"padding": "0 20px", "height": "100%"},
        classes="ad-header")


# ---------------------------------------------------------------------------
# Nav
# ---------------------------------------------------------------------------

# (label, page or external project, is_external, material icon)
# Icons are all long-standing Material names, so they resolve against the icon
# set Ignition bundles rather than needing a newer one.
#
# Every entry is a page in THIS project. That is deliberate: the demo has to
# import onto a customer's gateway as one self-contained project, and a nav item
# pointing at a second project is a dependency that travels badly.
NAV_ITEMS = [
    ("Overview", "/", False, "material/dashboard"),
    ("Alarm Status", "/status", False, "material/notifications_active"),
    ("Journal", "/journal", False, "material/history"),
    ("Alarm Metrics", "/metrics", False, "material/donut_large"),
    ("Analytics", "/analytics", False, "material/assessment"),
    ("Notifications", "/notifications", False, "material/contact_phone"),
    ("People & Shifts", "/people", False, "material/people"),
    ("Demo Control", "/demo", False, "material/tune"),
    ("Setup", "/setup", False, "material/build"),
]


# Sidebar widths. The shut rail has to clear the 18px glyph plus the padding
# either side, or the icons clip.
# Worst standing alarm decides the colour of the sidebar's alarm count and its
# warning triangle. Green when there is nothing standing - the one place on the
# screen that says "all clear" without being asked.
ALARM_COLOUR = (
    "if({session.custom.live.counts.Critical} > 0, \"var(--crit)\", "
    "if({session.custom.live.counts.High} > 0, \"var(--high)\", "
    "if({session.custom.live.total} > 0, \"var(--med)\", \"var(--ok)\")))")

NAV_OPEN = 230
NAV_SHUT = 62

# Collapsing is TWO things, and doing only one is why CSS alone cannot do it:
# the dock is absolutely positioned and the page's centre column is inset
# separately, so narrowing the sidebar in CSS would leave a 168px gutter of
# empty page beside the rail. `alterDock` moves both, and addresses the dock by
# the id in page-config. The session prop is what the CONTENTS restyle from;
# alterDock is what the LAYOUT changes from, and the two must not drift, so
# they are set together in one script.
NAV_TOGGLE = (
    "is_open = not self.session.custom.navOpen\n"
    "self.session.custom.navOpen = is_open\n"
    "system.perspective.alterDock('nav', "
    "{'size': %d if is_open else %d})" % (NAV_OPEN, NAV_SHUT))


def theme_picker():
    """The theme control, in the sidebar footer rather than the header.

    The header is already at its limit - three of its four blocks are shed by
    media query on a laptop - and a dropdown there would be the fourth. The
    footer has the room, the control is a per-session preference rather than
    part of the demo, and `ad-nav-text` means the collapsed rail drops it with
    everything else that needs the width.

    No persistence and no `custom` prop: the value binds straight to
    `session.props.theme`, so the pick holds for the session (a page reload
    keeps it - it lives in the session, not the component) and a fresh session
    lands back on the project's own default, `dark-cool`.

    Options come from the gateway rather than a list here, so a theme pack
    installed on the target shows up without a new release of the demo.
    """
    return flex("Theme", [
        label("ThemeLabel", "THEME", classes="ad-kpi-label ad-nav-text",
              position=fixed("13px")),
        C("ia.input.dropdown", "Pick",
          {"options": [], "placeholder": "Theme",
           "allowClearing": False, "showSearch": False},
          classes="ad-nav-text ad-theme-select",
          style={"height": "30px"}, position=fixed("30px"),
          binds={"props.value": prop_bind_rw("session.props.theme"),
                 # a constant expression, so this is read once per session
                 # rather than polled - the theme list does not change under a
                 # running session, and a poll here would be a query a second
                 # for the life of every screen
                 "props.options": expr_bind(
                     "1", script_tf("\treturn AlarmDemo.ui.themeOptions()"))}),
    # 57, not 56, and the extra pixel is the BORDER. Perspective writes the
    # flex basis as a height and the box is border-box, so the 1px borderTop
    # comes out of the content area: 56 - 1 border - 10 padding = 45px for a
    # 13px label + 3px gap + 30px dropdown = 46px. One pixel over, and
    # Chromium answers a one-pixel overflow with a full scrollbar down the
    # side of the control - which is what it looks like, a scrollbar beside
    # the theme picker on a sidebar that has nothing to scroll.
    #
    # Third time in this file: see the brand row (24, not 22) and the alarm
    # count (36, not 30). Padding is inside the basis and margin is outside
    # it, and a border is inside it too - that last one is what this missed.
    ], direction="column", gap=3, classes="ad-nav-theme",
        style={"paddingTop": "10px", "marginTop": "4px",
               "borderTop": "1px solid var(--line)"},
        position=fixed("57px"))


def v_nav():
    items = []
    for text, target, _external, icon in NAV_ITEMS:
        events = on_nav(target)
        binds = {"props.style.classes": expr_bind(
            "if({page.props.path} = \"%s\", "
            "\"ad-nav-item ad-nav-item-active\", \"ad-nav-item\")" % target)}

        # The whole row is the click target, not just the text, so the icon and
        # the padding either side of it are live too.
        row = [
            C("ia.display.icon", "Icon",
              {"path": icon, "style": {"width": "18px", "height": "18px"}},
              position=fixed("18px")),
            # `ad-nav-text` is what the collapsed rail takes to zero width
            label("Text", text, classes="ad-nav-text", position=grow(1),
                  style={"textAlign": "left"}),
        ]
        items.append(flex("N_" + text.replace(" ", ""), row,
            gap=11, align="center",
            classes="ad-nav-item",
            position=fixed("38px"),
            binds=binds) | {"events": events})

    root = flex("root", [
        flex("Brand", [
            flex("Row", [
                label("Name", "ACME", classes="ad-title ad-nav-text",
                      style={"fontSize": "17px", "letterSpacing": "0.16em"},
                      position=grow(1)),
                # The toggle lives in the brand row rather than a row of its
                # own: a row of its own costs 40px of every screen, permanently,
                # for a control used once a session.
                label("Toggle", "\u2630", classes="ad-nav-toggle",
                      position=fixed("20px"),
                      style={"textAlign": "center", "cursor": "pointer"}),
            # 24, not 22: the 17px brand text and the 20px toggle glyph need
            # 23px of line box between them, and a ONE pixel overflow is enough
            # for Chromium to draw a scrollbar down the side of the row.
            ], gap=8, align="center", position=fixed("24px")),
            label("Sub", classes="ad-subtitle ad-nav-text",
                  style={"fontSize": "10.5px"}, position=fixed("28px"),
                  binds={"props.text": expr_bind(
                      "if({session.custom.site} = \"Manufacturing\", "
                      "\"Manufacturing\", \"Water Treatment Plant\")")}),
        ], direction="column", gap=2,
            style={"padding": "16px 14px 12px 14px"}, position=fixed("84px")),

        flex("Items", items, direction="column", gap=3,
             style={"padding": "8px 10px"}, position=grow(1)),

        flex("Footer", [
            label("TotalLabel", "ACTIVE ALARMS",
                  classes="ad-kpi-label ad-nav-text", position=fixed("14px")),
            # Expanded: a bell and the count. Collapsed: just the bell, which
            # carries the whole message on its own - it is already this
            # project's alarm glyph (the Alarm Status nav item), and its colour
            # is the worst standing priority, green when nothing is standing.
            # The number is marked `ad-nav-text`, so the rail drops it rather
            # than trying to fit a growing figure into 62px.
            flex("Count", [
                C("ia.display.icon", "Bell",
                  {"path": "material/notifications_active",
                   "style": {"width": "22px", "height": "22px"}},
                  position=fixed("22px"),
                  binds={"props.style.color": expr_bind(ALARM_COLOUR)}),
                label("Total", classes="ad-kpi-value ad-nav-text",
                      style={"fontSize": "26px"}, position=fixed("auto"),
                      binds={
                          "props.text": expr_bind(
                              "toStr({session.custom.live.total})"),
                          "props.style.color": expr_bind(ALARM_COLOUR),
                      }),
            # 36, not 30: a 26px number needs a 35px line box and Chromium
            # answers a ONE pixel shortfall with a scrollbar down the rail.
            ], gap=9, align="center", justify="center",
                classes="ad-nav-count", position=fixed("36px")),
            label("Unacked", classes="ad-faint ad-nav-text",
                  style={"fontSize": "11px", "textAlign": "center"},
                  position=fixed("15px"),
                  binds={"props.text": expr_bind(
                      "toStr({session.custom.live.unacked}) + \" unacknowledged\"")}),
            theme_picker(),
        ], direction="column", gap=3, classes="ad-nav-footer",
            style={"padding": "12px", "borderTop": "1px solid var(--line)"},
            position=fixed("162px")),
    ], direction="column",
        classes="ad-nav ad-root",
        style={"height": "100%"},
        binds={"props.style.classes": expr_bind(
            "\"ad-nav ad-root\" + if({session.custom.navOpen} = true, \"\", "
            "\" ad-nav-shut\")")})

    # The whole brand row toggles, not just the glyph: an 18px hit target is a
    # miss on a touch screen.
    root["children"][0]["children"][0]["events"] = on_click(NAV_TOGGLE)

    write("AlarmDemo/Nav", view(root, size=(NAV_OPEN, 900)))


# ---------------------------------------------------------------------------
# Overview - the plant mimic
# ---------------------------------------------------------------------------


def area_card(title, path_hint, children, basis):
    """One process area: its name, a live alarm count for that area, and its
    equipment. The per-area count is what turns a pretty mimic into something
    an operator can triage from."""
    head = flex("Head", [
        label("Title", title, classes="ad-card-head", position=grow(1)),
        label("Count", classes="ad-chip", position=fixed("auto"),
              style={"padding": "2px 9px", "fontSize": "11px"},
              binds={
                  "props.text": expr_bind(
                      "if({session.custom.live.areas.%s.total} > 0, "
                      "toStr({session.custom.live.areas.%s.total}) + \" ACTIVE\", \"OK\")"
                      % (path_hint, path_hint)),
                  "props.style.classes": expr_bind(
                      "\"ad-chip ad-chip-\" + if({session.custom.live.areas.%s.total} > 0, "
                      "lower({session.custom.live.areas.%s.worst}), \"ok\")"
                      % (path_hint, path_hint)),
              }),
    ], gap=8, align="center", position=fixed("24px"))

    return flex("Area_" + path_hint,
                [head] + children,
                direction="column", gap=9,
                classes="ad-card",
                style={"padding": "12px"},
                position={"grow": 1, "shrink": 1, "basis": basis})


def v_site_water():
    """ACME Water Treatment Plant mimic - just the area cards. The header and
    the alarm strip live in the Overview shell, shared with the other site."""
    intake = area_card("Intake", "Intake", [
        flex("Row1", [
            embed("WetWell", "AlarmDemo/Widgets/Tank",
                  {"title": "Wet Well", "path": "Intake/WetWell/Level",
                   "warnLow": 22, "critLow": 14, "warnHigh": 88, "critHigh": 95,
                   "chem": False}, position=fixed("108px")),
            flex("Pumps", [
                embed("P1", "AlarmDemo/Widgets/Pump",
                      {"title": "Raw Pump 1", "path": "Intake/RawWaterPump01"},
                      position=grow(1)),
                embed("P2", "AlarmDemo/Widgets/Pump",
                      {"title": "Raw Pump 2", "path": "Intake/RawWaterPump02"},
                      position=grow(1)),
            ], direction="column", gap=8, position=grow(1)),
        ], gap=9, position=grow(1)),
        flex("Stats", [
            embed("Turb", "AlarmDemo/Widgets/Stat",
                  {"title": "Raw Turbidity", "path": "Intake/RawTurbidity",
                   "unit": "NTU", "fmt": "0.0", "warn": 35, "crit": 50,
                   "invert": False}, position=grow(1)),
            embed("Flow", "AlarmDemo/Widgets/Stat",
                  {"title": "Raw Flow", "path": "Intake/RawWaterFlow",
                   "unit": "L/s", "fmt": "0", "warn": 1e9, "crit": 1e9,
                   "invert": False}, position=grow(1)),
        ], gap=8, classes="ad-stats", position=fixed("70px", shrink=1)),
    ], "24%")

    filtration = area_card("Filtration", "Filtration", [
        flex("Filters", [
            embed("F%s" % f, "AlarmDemo/Widgets/Meter",
                  {"title": "Filter %s" % f, "path": "Filtration/Filter%s" % f,
                   "unit": "kPa", "max": 100, "warn": 60, "crit": 80},
                  position=grow(1))
            for f in ("A", "B", "C")
        ], direction="column", gap=6, position=grow(1)),
        flex("Stats", [
            embed("Comb", "AlarmDemo/Widgets/Stat",
                  {"title": "Combined Turbidity", "path": "Filtration/CombinedTurbidity",
                   "unit": "NTU", "fmt": "0.000", "warn": 0.5, "crit": 1.0,
                   "invert": False}, position=grow(1)),
            embed("FFlow", "AlarmDemo/Widgets/Stat",
                  {"title": "Filtered Flow", "path": "Filtration/FilteredFlow",
                   "unit": "L/s", "fmt": "0", "warn": 1e9, "crit": 1e9,
                   "invert": False}, position=grow(1)),
        ], gap=8, classes="ad-stats", position=fixed("70px", shrink=1)),
    ], "26%")

    chemical = area_card("Chemical", "Chemical", [
        flex("Tanks", [
            embed(k, "AlarmDemo/Widgets/Tank",
                  {"title": t, "path": "Chemical/%s/TankLevel" % k,
                   "warnLow": 25, "critLow": 10, "warnHigh": 101,
                   "critHigh": 102, "chem": True}, position=grow(1))
            for k, t in (("Chlorine", "Chlorine"), ("Fluoride", "Fluoride"),
                         ("Coagulant", "Coagulant"))
        ], gap=8, position=grow(1)),
        flex("Stats", [
            embed("Res", "AlarmDemo/Widgets/Stat",
                  {"title": "Chlorine Residual", "path": "Chemical/ChlorineResidual",
                   "unit": "mg/L", "fmt": "0.00", "warn": 0.5, "crit": 0.2,
                   "invert": True}, position=grow(1)),
            embed("pH", "AlarmDemo/Widgets/Stat",
                  {"title": "pH", "path": "Chemical/pH", "unit": "",
                   "fmt": "0.00", "warn": 1e9, "crit": 1e9, "invert": False},
                  position=grow(1)),
        ], gap=8, classes="ad-stats", position=fixed("70px", shrink=1)),
    ], "24%")

    distribution = area_card("Distribution", "Distribution", [
        flex("Row1", [
            embed("Clearwater", "AlarmDemo/Widgets/Tank",
                  {"title": "Clearwater Tank",
                   "path": "Distribution/ClearwaterTank/Level",
                   "warnLow": 32, "critLow": 17, "warnHigh": 93, "critHigh": 97,
                   "chem": False}, position=fixed("118px")),
            flex("Pumps", [
                embed("H%d" % n, "AlarmDemo/Widgets/Pump",
                      {"title": "High Lift %d" % n,
                       "path": "Distribution/HighLiftPump%02d" % n},
                      position=grow(1))
                for n in (1, 2, 3)
            ], direction="column", gap=7, position=grow(1)),
        ], gap=9, position=grow(1)),
        flex("Stats", [
            embed("Press", "AlarmDemo/Widgets/Stat",
                  {"title": "Network Pressure", "path": "Distribution/NetworkPressure",
                   "unit": "kPa", "fmt": "0", "warn": 300, "crit": 250,
                   "invert": True}, position=grow(1)),
            embed("NFlow", "AlarmDemo/Widgets/Stat",
                  {"title": "Network Flow", "path": "Distribution/NetworkFlow",
                   "unit": "L/s", "fmt": "0", "warn": 1e9, "crit": 1e9,
                   "invert": False}, position=grow(1)),
        ], gap=8, classes="ad-stats", position=fixed("70px", shrink=1)),
    ], "26%")

    root = flex("root", [intake, filtration, chemical, distribution],
                gap=12, classes="ad-root")
    write("AlarmDemo/Sites/Water", view(root, size=(1400, 620)))


def v_site_mfg():
    """ACME Manufacturing mimic - the bottling line, laid out in flow order so
    the cascade of a stoppage reads left to right."""
    mixing = area_card("Mixing", "Mixing", [
        flex("Row1", [
            embed("Syrup", "AlarmDemo/Widgets/Tank",
                  {"title": "Syrup Tank", "path": "Mixing/SyrupTank/Level",
                   "warnLow": 25, "critLow": 10, "warnHigh": 101,
                   "critHigh": 102, "chem": True}, position=fixed("104px")),
            flex("Mixers", [
                embed("M1", "AlarmDemo/Widgets/Machine",
                      {"title": "Mixer 1", "path": "Mixing/Mixer01"},
                      position=grow(1)),
                embed("M2", "AlarmDemo/Widgets/Machine",
                      {"title": "Mixer 2", "path": "Mixing/Mixer02"},
                      position=grow(1)),
            ], direction="column", gap=8, position=grow(1)),
        ], gap=9, position=grow(1)),
        flex("Stats", [
            embed("BT", "AlarmDemo/Widgets/Stat",
                  {"title": "Batch Temperature", "path": "Mixing/BatchTemperature",
                   "unit": "degC", "fmt": "0.0", "warn": 38, "crit": 45,
                   "invert": False}, position=grow(1)),
            embed("BP", "AlarmDemo/Widgets/Stat",
                  {"title": "Batch Progress", "path": "Mixing/BatchProgress",
                   "unit": "%", "fmt": "0", "warn": 1e9, "crit": 1e9,
                   "invert": False}, position=grow(1)),
        ], gap=8, classes="ad-stats", position=fixed("70px", shrink=1)),
    ], "24%")

    filling = area_card("Filling", "Filling", [
        flex("Machines", [
            embed("Filler", "AlarmDemo/Widgets/Machine",
                  {"title": "Filler", "path": "Filling/Filler"},
                  position=grow(1)),
            embed("Capper", "AlarmDemo/Widgets/Machine",
                  {"title": "Capper", "path": "Filling/Capper"},
                  position=grow(1)),
        ], direction="column", gap=8, position=grow(1)),
        flex("Stats", [
            embed("CO2", "AlarmDemo/Widgets/Stat",
                  {"title": "CO2 Pressure", "path": "Filling/CO2Pressure",
                   "unit": "kPa", "fmt": "0", "warn": 320, "crit": 280,
                   "invert": True}, position=grow(1)),
            embed("Rej", "AlarmDemo/Widgets/Stat",
                  {"title": "Reject Rate", "path": "Filling/FillRejectRate",
                   "unit": "%", "fmt": "0.0", "warn": 3, "crit": 4,
                   "invert": False}, position=grow(1)),
        ], gap=8, classes="ad-stats", position=fixed("70px", shrink=1)),
    ], "24%")

    packaging = area_card("Packaging", "Packaging", [
        flex("Machines", [
            embed("Lab", "AlarmDemo/Widgets/Machine",
                  {"title": "Labeller", "path": "Packaging/Labeller"},
                  position=grow(1)),
            embed("CP", "AlarmDemo/Widgets/Machine",
                  {"title": "Case Packer", "path": "Packaging/CasePacker"},
                  position=grow(1)),
            embed("Pal", "AlarmDemo/Widgets/Machine",
                  {"title": "Palletiser", "path": "Packaging/Palletiser"},
                  position=grow(1)),
        ], direction="column", gap=8, position=grow(1)),
        flex("Stats", [
            embed("Speed", "AlarmDemo/Widgets/Stat",
                  {"title": "Line Speed", "path": "Packaging/LineSpeed",
                   "unit": "bpm", "fmt": "0", "warn": 1e9, "crit": 1e9,
                   "invert": False}, position=grow(1)),
            embed("OEE", "AlarmDemo/Widgets/Stat",
                  {"title": "OEE", "path": "Packaging/OEE",
                   "unit": "%", "fmt": "0.0", "warn": 80, "crit": 75,
                   "invert": True}, position=grow(1)),
        ], gap=8, classes="ad-stats", position=fixed("70px", shrink=1)),
    ], "28%")

    utilities = area_card("Utilities", "Utilities", [
        flex("Kit", [
            embed("Air", "AlarmDemo/Widgets/Motor",
                  {"title": "Air Compressor", "path": "Utilities/AirCompressor"},
                  position=grow(1)),
            embed("Chill", "AlarmDemo/Widgets/Motor",
                  {"title": "Chiller", "path": "Utilities/Chiller"},
                  position=grow(1)),
        ], direction="column", gap=8, position=grow(1)),
        flex("Stats", [
            embed("AirP", "AlarmDemo/Widgets/Stat",
                  {"title": "Air Pressure", "path": "Utilities/AirCompressor/Pressure",
                   "unit": "kPa", "fmt": "0", "warn": 600, "crit": 550,
                   "invert": True}, position=grow(1)),
            embed("ChT", "AlarmDemo/Widgets/Stat",
                  {"title": "Chilled Water", "path": "Utilities/Chiller/SupplyTemp",
                   "unit": "degC", "fmt": "0.0", "warn": 10, "crit": 12,
                   "invert": False}, position=grow(1)),
        ], gap=8, classes="ad-stats", position=fixed("70px", shrink=1)),
    ], "24%")

    root = flex("root", [mixing, filling, packaging, utilities],
                gap=12, classes="ad-root")
    write("AlarmDemo/Sites/Manufacturing", view(root, size=(1400, 620)))


def v_overview():
    """The shell: header, whichever site mimic is selected, and the live alarm
    table. Only the mimic swaps, so both plants get identical chrome."""
    mimic = C("ia.display.view", "SiteMimic", {"path": "AlarmDemo/Sites/Water"},
              position=grow(1),
              binds={"props.path": expr_bind(
                  "if({session.custom.site} = \"Manufacturing\", "
                  "\"AlarmDemo/Sites/Manufacturing\", \"AlarmDemo/Sites/Water\")")})

    alarm_strip = flex("ActiveAlarms", [
        flex("Head", [
            label("T", "ACTIVE ALARMS", classes="ad-card-head", position=grow(1)),
            # Last in the row on every screen that has one, so the control is
            # always in the same place - see colour_switch().
            colour_switch("OverviewColour"),
        ], gap=8, align="center", position=fixed("30px")),
        # Site-scoped rather than the stock component: both plants share one
        # tag provider, so the stock table would list the other site's alarms
        # under this site's header. The full component, with its own live
        # filtering, is on the Alarm Status page.
        C("ia.display.table", "Table", {
            "style": {"classes": "ad-table ad-table-plain"},
            "pager": {"bottom": False, "top": False},
            "columns": [
                col("Active time", "Active time", width=160),
                col("Alarm", "Alarm"),
                priority_col(),
                col("State", "State", width=150),
            ],
        }, position=grow(1),
            binds={
                # The mode as a class, so the stylesheet can tint whole rows.
                # Perspective's Table has no conditional row formatting, so the
                # tint is CSS selecting a row that :has() the priority marker
                # the PriorityCell view always emits.
                "props.style.classes": expr_bind(
                    "\"ad-table ad-table-plain ad-colour-\" + "
                    "{session.custom.alarmColour}"),
                "props.data": expr_bind(
                    "{session.custom.site} + toStr(now(3000))",
                    transform=script_tf(
                        "\treturn AlarmDemo.alarms.activeAlarms("
                        "self.session.custom.site)")),
                # An empty table renders as a blank bordered box with no
                # header row, which reads as "broken" rather than as "nothing
                # is wrong". `display: none` does not take on the table
                # component, so collapse it through its flex position instead.
                "position.grow": expr_bind(
                    "if({session.custom.live.total} > 0, 1, 0)"),
                "position.basis": expr_bind(
                    "if({session.custom.live.total} > 0, \"auto\", \"0px\")"),
            }),
        flex("AllClear", [
            label("Msg", "No active alarms on this site",
                  position=fixed("20px"),
                  style={"textAlign": "center", "color": "var(--ok)",
                         "fontSize": "14px", "fontWeight": "600"}),
            label("Sub", "the plant is running within limits",
                  classes="ad-faint", position=fixed("16px"),
                  style={"textAlign": "center", "fontSize": "12px"}),
        ], direction="column", gap=4, justify="center",
            position=grow(1),
            binds={"props.style.display": expr_bind(
                "if({session.custom.live.total} > 0, \"none\", \"flex\")")}),
    ], direction="column", gap=8,
        classes="ad-card",
        style={"padding": "12px", "margin": "0 12px",
               # The strip takes an equal share of the slack rather than a
               # fixed height, so a taller window buys alarm rows. Both ends
               # are pinned: below 180 a header plus three rows is the point
               # where the table stops being a table, and above 460 it is
               # just empty rows under three alarms. Past that the page keeps
               # the difference as a bottom margin, which is what it looks
               # like anyway.
               "minHeight": "180px", "maxHeight": "460px"},
        position=grow(1, "0%"))

    root = flex("root", [
        header(),
        # The mimic used to be the only thing that grew, so every pixel a
        # taller window gave the page went into stretching widgets that were
        # already drawn - which is the dead space between the tanks and the
        # stat tiles. Now the two halves share the slack:
        #   minHeight  the floor the mimic can actually draw in. Below it the
        #              widgets inside stop shrinking and grow scrollbars of
        #              their own, which is what a laptop window used to do;
        #   maxHeight  past this the mimic is just stretching. Everything
        #              beyond it goes to the alarm table instead.
        flex("Mimic", [mimic], style={"padding": "0 12px",
                                      "minHeight": "330px",
                                      "maxHeight": "460px"},
             position=grow(1, "0%")),
        alarm_strip,
    ], direction="column", gap=12,
        classes="ad-page ad-root",
        style={"padding": "0 0 12px 0", "height": "100%"})
    root["children"][0]["position"] = fixed("64px")
    write("AlarmDemo/Overview", view(root))


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def v_status():
    """Live alarm status, on the stock Perspective Alarm Status Table.

    The component is kept because its own filtering, acknowledging and
    shelving are worth demonstrating. It has no source or provider filter in
    its props - checked against the shipped component bundle - but it does
    have `filters.active.text`, and every display path begins with its area
    name ("Intake / ...", "Packaging / ..."), so an area selector driving that
    text filter gives per-area and per-site scoping using the component's own
    machinery.
    """
    controls = flex("Controls", [
        label("AL", "AREA", classes="ad-kpi-label", position=fixed("42px"),
              style={"alignSelf": "center"}),
        C("ia.input.dropdown", "Area", {
            "placeholder": "All areas", "style": {"classes": "ad-btn"},
        }, position=fixed("210px"),
            binds={
                "props.options": prop_bind("view.custom.areaOptions"),
                "props.value": {"binding": {"type": "property", "config": {
                    "path": "session.custom.statusArea",
                    "bidirectional": True}}},
            }),
        flex("Sp", [], position=grow(1)),
        colour_switch("StatusColour"),
    ], gap=8, align="center", position=fixed("40px"))

    table = C("ia.display.alarmstatustable", "Table", {
        "pager": {"enabled": False},
        "style": {"classes": "ad-table"},
    }, position=grow(1),
        binds={
            # Scope the component to the selected site. Both sites share one
            # tag provider, so without a source condition the stock table lists
            # the other plant's alarms under this plant's header. The Area
            # selector narrows it further, to one area of that site.
            "props.filters.active.conditions.source": expr_bind(
                "{session.custom.site} + \"|\" + {session.custom.statusArea}",
                transform=script_tf(
                    "\treturn AlarmDemo.alarms.sourceFilter(\n"
                    "\t    self.session.custom.site,\n"
                    "\t    self.session.custom.statusArea or '')")),
            # The component ships MM/DD/YYYY. Local convention is DD/MM, and a
            # date that is ambiguous for the first twelve days of a month is
            # worse than one that is simply unfamiliar.
            "props.dateFormat": expr_bind("\"DD/MM/YYYY HH:mm:ss\""),
            # `rowStyles` paints the whole row in "rows" mode. In "cells" mode
            # it only hands each row a per-priority CLASS, and the stylesheet
            # paints the one column - which needs the mode as a class on the
            # table itself. Without it those rules never match and "Priority
            # only" renders as no colour at all, which reads as the setting
            # doing nothing.
            "props.style.classes": expr_bind(
                "\"ad-table ad-colour-\" + {session.custom.alarmColour}"),
            "props.rowStyles": expr_bind(
                "{session.custom.alarmColour}",
                transform=script_tf(
                    "\treturn AlarmDemo.alarms.rowStyles(value)")),
        })

    root = flex("root", [
        header(),
        flex("Body", [
            controls,
            flex("Card", [table], direction="column",
                 classes="ad-card", style={"padding": "12px"},
                 position=grow(1)),
        ], direction="column", gap=12, classes="ad-body",
            style={"padding": "0 12px 12px 12px"}, position=grow(1)),
    ], direction="column", gap=12,
        classes="ad-page ad-root", style={"height": "100%"})
    root["children"][0]["position"] = fixed("64px")

    write("AlarmDemo/Status", view(
        root,
        custom={"areaOptions": []},
        propconfig={"custom.areaOptions": expr_bind(
            "{session.custom.site}",
            transform=script_tf(
                "\treturn AlarmDemo.alarms.areaOptions(self.session.custom.site)"))},
    ))


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------


def v_journal():
    controls = flex("Controls", [
        label("L", "WINDOW", classes="ad-kpi-label", position=fixed("64px"),
              style={"alignSelf": "center"}),
    ] + [
        C("ia.input.button", "J%d" % h, {
            "text": lbl, "style": {"classes": "ad-btn"},
        }, position=fixed("86px"),
            events=on_action("self.session.custom.rangeHours = %d" % h),
            binds={"props.style.classes": expr_bind(
                "if({session.custom.rangeHours} = %d, \"ad-btn ad-btn-active\", "
                "\"ad-btn\")" % h)})
        for h, lbl in ((8, "8 hours"), (24, "24 hours"), (168, "7 days"),
                       (720, "30 days"))
    ] + [
        flex("Sp", [], position=grow(1)),
        colour_switch("JournalColour"),
    ], gap=8, align="center", position=fixed("40px"))

    root = flex("root", [
        header(),
        flex("Body", [
            controls,
            flex("Card", [
                # Ignition's own Alarm Journal Table, not a SQL query dressed
                # up as one. This is a demonstration of Ignition, so the
                # journal screen should be the component a customer would
                # actually place - with its own filtering, sorting, detail
                # popup and paging behaviour.
                C("ia.display.alarmjournaltable", "Table", {
                    # The journal profile to query. The prop is `name`, and it
                    # defaults to "Journal" - a profile that does not exist
                    # here, so the component renders "No results found" with no
                    # error anywhere and the journal looks empty. It is not
                    # `journalName`, and it is not visible in the client's props
                    # either; the value came out of the component-defaults frame
                    # the gateway sends at session start.
                    "name": "AlarmDemo",
                    "refreshRate": 15000,
                    # Columns are a MAP keyed by column id, not a list - the
                    # component owns which columns exist and this only says
                    # which of them are on and in what order.
                    "columns": {
                        "eventTime":   {"enabled": True,  "order": 0,
                                        "width": 170, "strictWidth": True,
                                        "sort": "descending"},
                        "displayPath": {"enabled": True,  "order": 1,
                                        "width": 340, "sort": "none"},
                        "priority":    {"enabled": True,  "order": 2,
                                        "width": 120, "strictWidth": True,
                                        "sort": "none"},
                        "eventState":  {"enabled": True,  "order": 3,
                                        "width": 150, "strictWidth": True,
                                        "sort": "none"},
                        "name":        {"enabled": True,  "order": 4,
                                        "width": 220, "sort": "none"},
                        "eventId":     {"enabled": False, "order": 5},
                        "source":      {"enabled": False, "order": 6},
                    },
                    "pager": {"enabled": False},
                    "style": {"classes": "ad-table"},
                }, position=grow(1),
                    binds={
                        # The journal PROFILE to read, asked of the gateway
                        # rather than written here. Edge permits exactly one
                        # journal, the platform owns it and it is called
                        # EdgeJournal - so the demo's own profile does not
                        # exist there and a table naming it shows an empty
                        # history with no error. Bound to a constant
                        # expression purely so the script transform runs.
                        "props.name": expr_bind(
                            "1", transform=script_tf(
                                "\treturn AlarmDemo.edition.journalName()")),
                        "props.style.classes": expr_bind(
                            "\"ad-table ad-colour-\" + {session.custom.alarmColour}"),
                        "props.dateFormat": expr_bind(
                            "\"DD/MM/YYYY HH:mm:ss\""),
                        # site scope - the journal holds both plants
                        "props.filter.conditions.source": expr_bind(
                            "{session.custom.site} + \"|\" + {session.custom.area}",
                            transform=script_tf(
                                "\treturn AlarmDemo.alarms.sourceFilter(\n"
                                "\t    self.session.custom.site,\n"
                                "\t    self.session.custom.area or '')")),
                        # site scope - the journal holds both plants
                        # the window buttons drive the component's own realtime
                        # range rather than a hand-built start/end pair
                        "props.dateRange.realtime.interval": expr_bind(
                            "if({session.custom.rangeHours} >= 168, "
                            "{session.custom.rangeHours} / 24, "
                            "{session.custom.rangeHours})"),
                        "props.dateRange.realtime.unit": expr_bind(
                            "if({session.custom.rangeHours} >= 168, "
                            "\"days\", \"hours\")"),
                        "props.rowStyles": expr_bind(
                            "{session.custom.alarmColour}",
                            transform=script_tf(
                                "\treturn AlarmDemo.alarms.journalRowStyles(value)")),
                    }),
            ], direction="column",
                classes="ad-card", style={"padding": "12px"},
                position=grow(1)),
        ], direction="column", gap=12, classes="ad-body",
            style={"padding": "0 12px 12px 12px"}, position=grow(1)),
    ], direction="column", gap=12,
        classes="ad-page ad-root", style={"height": "100%"})
    root["children"][0]["position"] = fixed("64px")
    write("AlarmDemo/Journal", view(root))


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

QPARAMS = {
    "startDate": "{session.custom.range.start}",
    "endDate": "{session.custom.range.end}",
    "area": "{session.custom.area}",
}


def kpi_tile(name, title, expr, unit="", color_expr=None):
    binds = {"props.text": expr_bind(expr)}
    if color_expr:
        binds["props.style.color"] = expr_bind(color_expr)
    return flex(name, [
        label("L", title, classes="ad-kpi-label", position=fixed("14px")),
        flex("V", [
            label("Val", classes="ad-kpi-value", position=fixed("auto"),
                  binds=binds),
            label("U", unit, classes="ad-kpi-unit", position=fixed("auto"),
                  style={"paddingBottom": "2px"}),
        ], gap=5, align="end", position=grow(1),
            style={"overflow": "hidden"}),
    ], direction="column", gap=2, classes="ad-kpi", position=grow(1))


# Shared chart chrome. Axes are identified by `name` and typed by `render`;
# the series points at them by name. Spelling either as `type` leaves the chart
# blank and white with no error anywhere.
# The card colour, repeated from the stylesheet's --card because a chart
# background is an SVG fill and cannot read a CSS variable.
#
# Every chart states this EXPLICITLY rather than setting opacity 0 and letting
# whatever is underneath show through: an unset colour is not "transparent", it
# is "someone else's choice", and the component's default is black on 8.3.8 and
# white on a newer gateway.
#
# The prop is NOT sufficient on its own. Which SVG layer it reaches - and
# whether it is honoured at all - varies by gateway version, which is how three
# charts carrying identical JSON rendered dark on one gateway and white on
# another. `ad-xy-chart` pairs it with a CSS rule that paints every rect these
# charts draw, and CSS beats an SVG presentation attribute on any version. The
# series are lines, so every rect in them is chrome; the tooltip is an HTML div
# and is not touched.
CHART_BG = {"color": "#161B22", "opacity": 1, "render": "color"}

AXIS_LOOK = {
    "font": {"size": 11, "weight": 500},
    "grid": {"color": "#6D7486", "dashArray": "", "opacity": 0.18,
             "position": 0.5},
    "inside": False,
    "labels": {"color": CHART_DIAG, "opacity": 1, "rotation": 0},
    "opposite": False,
}


def day_trend(name, source_prop, y_field, colour, label_text, y_label=None):
    """A single-measure daily trend line over a date axis.

    One measure, one hue, one y-scale. Two measures of different units belong
    in two charts side by side, never on a second y-axis - a dual axis lets the
    author decide which line looks higher, which is exactly the decision a
    reader should be making.
    """
    return C("ia.chart.xy", name, {
        "background": CHART_BG,
        "style": {"classes": "ad-xy-chart"},
        "dataSources": {},
        "legend": {"enabled": False},
        "series": [{
            "name": name.lower(),
            "data": {"source": "d", "x": "bucket", "y": y_field},
            "label": {"text": label_text},
            "render": "line",
            "xAxis": "x",
            "yAxis": "value",
            "visible": True,
            "line": {
                "appearance": {
                    "stroke": {"color": colour, "opacity": 1, "width": 2},
                    "fill": {"color": colour, "opacity": 0.16},
                    # markers on a 30-point series are readable and make the
                    # daily granularity obvious; on the hourly rate chart they
                    # would be a solid band, which is why that one has none
                    "bullets": [{"enabled": True, "render": "circle",
                                 "radius": 3,
                                 "appearance": {
                                     "fill": {"color": colour, "opacity": 1},
                                     "stroke": {"color": colour, "opacity": 1,
                                                "width": 0}}}],
                },
            },
        }],
        "xAxes": [{
            "name": "x",
            "render": "date",
            "visible": True,
            "appearance": AXIS_LOOK,
            "date": {"format": "dd MMM", "inputFormat": "yyyy-MM-dd kk:mm:ss"},
        }],
        "yAxes": [{
            "name": "value",
            "render": "value",
            "visible": True,
            "appearance": AXIS_LOOK,
            "label": {"text": y_label or label_text},
        }],
    }, position=grow(1),
        binds={"props.dataSources.d": prop_bind(source_prop)})


def card(name, title, body, position=None, subtitle=None, binds=None):
    head = [label("T", title, classes="ad-card-head", position=fixed("16px"))]
    if subtitle:
        head.append(label("S", subtitle, classes="ad-faint ad-card-sub",
                          style={"fontSize": "11px"}, position=fixed("15px")))
    return flex(name, head + [body], direction="column", gap=8,
                classes="ad-card", style={"padding": "12px"},
                position=position, binds=binds)


def v_analytics():
    # --- Pareto -----------------------------------------------------------
    # Built from flex rows rather than a chart component. Source names are long
    # ("Distribution / High Lift Pump 3 / Motor Fault") and a category axis
    # either truncates them or turns them 90 degrees; a ranked list reads
    # straight across. Rank order carries the whole message, so every bar is
    # one hue - colour would only add a meaning that is not there.
    # 8, not 10: at 1366x768 ten 26px rows overflow the card and it grows a
    # scrollbar. The Pareto argument is carried by the top few sources either
    # way - the tail is what the chart is arguing about, not with.
    PARETO_ROWS = 8
    rows = []
    for i in range(PARETO_ROWS):
        # The helper always returns PARETO_ROWS entries with the bar width
        # already computed, so each row is three plain property bindings and
        # there is no index that can run off the end of the result set.
        rows.append(flex("P%d" % i, [
            label("Name", position=fixed("330px"),
                  style={"fontSize": "12px", "color": "var(--ink)",
                         "overflow": "hidden", "whiteSpace": "nowrap"},
                  binds={"props.text": prop_bind(
                      "view.custom.pareto[%d].name" % i)}),
            flex("Track", [
                flex("Bar", [],
                     style={"backgroundColor": "var(--low)",
                            "borderRadius": "4px", "height": "100%"},
                     position={"grow": 0, "shrink": 0, "basis": "0%"},
                     binds={"position.basis": prop_bind(
                         "view.custom.pareto[%d].pct" % i)}),
            ], classes="ad-meter",
                style={"height": "14px", "borderRadius": "4px"},
                position=grow(1)),
            label("N", position=fixed("52px"),
                  style={"fontSize": "12px", "fontWeight": "650",
                         "textAlign": "right", "color": "var(--ink-2)"},
                  binds={"props.text": prop_bind(
                      "view.custom.pareto[%d].n" % i)}),
        ], gap=10, align="center", position=fixed("23px"),
            binds={"props.style.display": prop_bind(
                "view.custom.pareto[%d].show" % i)}))

    pareto = flex("ParetoRows", rows, direction="column", gap=3,
                  position=grow(1), style={"overflowY": "auto",
                                           "minHeight": "0px"})

    # --- alarm rate: a real time series, where a chart genuinely beats a list.
    axis_look = AXIS_LOOK
    rate = C("ia.chart.xy", "Rate", {
        "background": CHART_BG,
        "style": {"classes": "ad-xy-chart"},
        "dataSources": {},
        "legend": {"enabled": False},
        "series": [{
            "name": "rate",
            "data": {"source": "rate", "x": "bucket", "y": "occurrences"},
            "label": {"text": "Alarms per hour"},
            "render": "line",
            "xAxis": "x",
            "yAxis": "value",
            "visible": True,
            "line": {
                "appearance": {
                    "stroke": {"color": CHART_HIGH, "opacity": 1, "width": 2},
                    "fill": {"color": CHART_HIGH, "opacity": 0.18},
                    "bullets": [{"enabled": False}],
                },
            },
        }],
        "xAxes": [{
            "name": "x",
            "render": "date",
            "visible": True,
            "appearance": axis_look,
            "date": {"format": "HH:mm", "inputFormat": "yyyy-MM-dd kk:mm:ss"},
        }],
        "yAxes": [{
            "name": "value",
            "render": "value",
            "visible": True,
            "appearance": axis_look,
        }],
    }, position=grow(1),
        binds={"props.dataSources.rate": prop_bind("view.custom.rate")})

    # --- priority mix: a fixed five-slice donut, one binding per slice, so a
    # priority with no alarms is an empty wedge rather than an error.
    PRI = [("Critical", CHART_CRIT), ("High", CHART_HIGH), ("Medium", CHART_MED),
           ("Low", CHART_LOW), ("Diagnostic", CHART_DIAG)]
    donut = C("ia.chart.pie", "Priority", {
        "colors": [c for _n, c in PRI],
        "cutoutRadius": 55,
        "data": [{"label": n, "count": 0} for n, _c in PRI],
        "labels": {"showName": False, "showValue": False},
        "showLabels": False,
        # The component's own legend is OFF. It renders inside the chart's box
        # and is the first thing dropped when the box is short: at 330x278 the
        # Diagnostic row was clipped away entirely, so the chart quietly showed
        # four of five priorities. The legend below is ours, and always shows
        # all five.
        "showLegend": False,
        "style": {"classes": "ad-chart"},
        # The hover tooltip draws black text on the slice colour, which is
        # unreadable on the crimson and blue slices. The legend carries every
        # label and percentage, so the tooltip adds nothing worth keeping.
        "tooltip": {"enabled": False},
    }, position=grow(1),
        binds=dict(
            ("props.data[%d].count" % i,
             prop_bind("view.custom.priorities.%s" % n))
            for i, (n, _c) in enumerate(PRI)))

    # One row per priority: swatch, name, count and share. Fixed height, so it
    # cannot be squeezed out by the donut above it however short the card gets.
    legend_rows = []
    for n, c in PRI:
        legend_rows.append(flex("L_%s" % n, [
            flex("Sw", [], position=fixed("11px"),
                 style={"backgroundColor": c, "borderRadius": "3px",
                        "height": "11px", "alignSelf": "center"}),
            label("Name", n, position=grow(1),
                  style={"fontSize": "12px", "color": "var(--ink)"}),
            label("N", position=fixed("38px"), classes="ad-muted",
                  style={"fontSize": "12px", "textAlign": "right"},
                  binds={"props.text": prop_bind(
                      "view.custom.priorities.%s" % n)}),
            label("Pct", position=fixed("52px"), classes="ad-faint",
                  style={"fontSize": "12px", "textAlign": "right"},
                  binds={"props.text": expr_bind(
                      # guard the divide: every priority is zero on a gateway
                      # with no history yet, and 0/0 renders as an error box
                      "if({view.custom.priorityTotal} > 0, "
                      "numberFormat({view.custom.priorities.%s} / "
                      "{view.custom.priorityTotal} * 100, \"0.0\") + \" %%\", "
                      "\"-\")" % n)}),
        ], gap=8, align="center", position=fixed("21px")))

    priority = flex("PriorityBody", [
        donut,
        flex("Legend", legend_rows, direction="column", gap=2,
             position=fixed("113px")),
    ], direction="column", gap=8, position=grow(1))

    unacked = C("ia.display.table", "Unacked", {
        "style": {"classes": "ad-table ad-table-plain"},
        "pager": {"bottom": False, "top": False},
        "columns": [
            col("Alarm", "Alarm"),
            col("Never acked", "Count", width=86, justify="right", fmt="0,0"),
        ],
    }, position=grow(1),
        binds={"props.data": prop_bind("view.custom.unacked")})

    kpis = flex("Kpis", [
        kpi_tile("K1", "Alarms / hour", "toStr({view.custom.kpis.rate})"),
        kpi_tile("K2", "Total activations", "toStr({view.custom.kpis.total})"),
        kpi_tile("K3", "Median ack time",
                 "toStr({view.custom.kpis.ackMedianMin})", "min"),
        kpi_tile("K4", "Never acknowledged",
                 "toStr({view.custom.kpis.unackedPct})", "%",
                 "if({view.custom.kpis.unackedPct} >= 40, \"var(--high)\", \"var(--ink)\")"),
        kpi_tile("K5", "Top 3 share of load",
                 "toStr({view.custom.kpis.topShare})", "%",
                 "if({view.custom.kpis.topShare} >= 40, \"var(--med)\", \"var(--ink)\")"),
        kpi_tile("K6", "Flood hours",
                 "toStr({view.custom.kpis.floodHours})", "",
                 "if({view.custom.kpis.floodHours} > 0, \"var(--crit)\", \"var(--ok)\")"),
    ], gap=10, position=fixed("94px"))

    controls = flex("Controls", [
        label("RangeLabel", "WINDOW", classes="ad-kpi-label",
              position=fixed("64px"),
              style={"alignSelf": "center"}),
    ] + [
        C("ia.input.button", "R%d" % h, {
            "text": lbl,
            "style": {"classes": "ad-btn"},
        }, position=fixed("86px"),
            events=on_action("self.session.custom.rangeHours = %d" % h),
            binds={"props.style.classes": expr_bind(
                "if({session.custom.rangeHours} = %d, \"ad-btn ad-btn-active\", "
                "\"ad-btn\")" % h)})
        for h, lbl in ((8, "8 hours"), (24, "24 hours"), (168, "7 days"),
                       (720, "30 days"))
    ] + [
        flex("Spacer", [], position=grow(1)),
        # options/value must be BOUND. Writing "{session.custom.x}" straight
        # into props stores the literal string, and the control renders empty.
        # `bidirectional` belongs inside config; beside it, it is ignored and
        # the selection never writes back.
        C("ia.input.dropdown", "Area", {
            "placeholder": "All areas",
            "style": {"classes": "ad-btn"},
        }, position=fixed("210px"),
            binds={
                "props.options": prop_bind("session.custom.areaOptions"),
                "props.value": {"binding": {
                    "type": "property",
                    "config": {"path": "session.custom.area",
                               "bidirectional": True}}},
            }),
    ], gap=8, align="center", position=fixed("40px"))

    root = flex("root", [
        header(),
        flex("Body", [
            controls,
            kpis,
            flex("Row1", [
                card("ParetoCard", "Alarm Pareto  -  worst sources",
                     pareto, grow(1),
                     "The top few sources usually produce most of the load. "
                     "That is where rationalisation pays."),
                card("PriorityCard", "Priority mix", priority,
                     {"grow": 0, "shrink": 0, "basis": "330px"}),
            ], gap=12, position=grow(1)),
            flex("Row2", [
                card("RateCard", "Alarm rate", rate, grow(1),
                     "EEMUA 191 considers more than 60 alarms an hour unmanageable."),
                card("UnackedCard", "Never acknowledged", unacked,
                     {"grow": 0, "shrink": 0, "basis": "430px"}),
            ], gap=12, position=grow(1)),
        ], direction="column", gap=12, classes="ad-body",
            style={"padding": "0 12px 12px 12px"}, position=grow(1)),
    ], direction="column", gap=12,
        classes="ad-page ad-root", style={"height": "100%"})
    root["children"][0]["position"] = fixed("64px")

    def helper(fn, extra=""):
        """Bind a view custom prop to a script helper, re-evaluated whenever the
        window, site or area changes, and on a slow poll.

        `site` has to be in the trigger expression as well as the call - the
        transform only re-runs when the expression's value changes, so a site
        switch with an unchanged window would otherwise leave stale numbers on
        screen."""
        return expr_bind(
            "toStr({session.custom.rangeHours}) + {session.custom.site} "
            "+ {session.custom.area} + toStr(now(30000))",
            transform=script_tf(
                "\treturn AlarmDemo.alarms.%s("
                "self.session.custom.rangeHours, "
                "self.session.custom.site, "
                "self.session.custom.area or ''%s)" % (fn, extra)))

    custom = {
        "pareto": [{"name": "", "n": 0, "pct": "0%", "show": "none"}
                   for _ in range(PARETO_ROWS)],
        "rate": None, "unacked": None, "kpis": None,
        "priorities": {"Critical": 0, "High": 0, "Medium": 0, "Low": 0,
                       "Diagnostic": 0},
        "priorityTotal": 0,
    }
    pc = {
        "custom.pareto": helper("paretoRows", ", %d" % PARETO_ROWS),
        "custom.rate": helper("rateByHour"),
        "custom.unacked": helper("topUnacked"),
        "custom.priorityTotal": expr_bind(
            "toStr({view.custom.priorities.Critical}) + "
            "toStr({view.custom.priorities.High}) + "
            "toStr({view.custom.priorities.Medium}) + "
            "toStr({view.custom.priorities.Low}) + "
            "toStr({view.custom.priorities.Diagnostic})",
            transform=script_tf(
                "\tp = self.view.custom.priorities\n"
                "\treturn sum([p[k] for k in "
                "['Critical', 'High', 'Medium', 'Low', 'Diagnostic']])")),
        "custom.priorities": expr_bind(
            "toStr({session.custom.rangeHours}) + {session.custom.site} "
            "+ {session.custom.area} + toStr(now(30000))",
            transform=script_tf(
                "\treturn AlarmDemo.alarms.priorityCounts("
                "self.session.custom.rangeHours, self.session.custom.site, "
                "self.session.custom.area or '')")),
        "custom.kpis": expr_bind(
            "toStr({session.custom.rangeHours}) + {session.custom.site} "
            "+ {session.custom.area} + toStr(now(30000))",
            transform=script_tf(
                "\treturn AlarmDemo.alarms.kpis("
                "self.session.custom.rangeHours, self.session.custom.site, "
                "self.session.custom.area or '')")),
    }
    write("AlarmDemo/Analytics", view(root, custom=custom, propconfig=pc))






# ---------------------------------------------------------------------------
# Alarm Metrics - per-area roll-up
# ---------------------------------------------------------------------------


def v_metrics():
    """A metric card per process area: how many alarms are standing, how many
    nobody has acknowledged, the split by priority, and the worst one.

    Sized for a wall display - the question it answers from across a room is
    "which area is in trouble", and only then "with what".
    """
    AREA_SLOTS = 5
    # explicit abbreviations - "Medium"[:4] gives "MEDI", and the five chips
    # then no longer fit a card's width
    # Four priorities, not five. Diagnostic is a maintenance signal rather than
    # something an operator triages from across a room, and as a fifth chip it
    # wrapped onto a line of its own and squeezed the other four. It is still
    # in the ACTIVE and UNACKED totals and still named in "Worst standing" -
    # only its chip is gone.
    PRI = [("Critical", "critical", "CRIT"), ("High", "high", "HIGH"),
           ("Medium", "medium", "MED"), ("Low", "low", "LOW")]

    cards = []
    for i in range(AREA_SLOTS):
        def chip(key, cls, abbr):
            return label("P_%s" % key, classes="ad-chip ad-chip-%s" % cls,
                         position=grow(1, "0%"),
                         style={"padding": "0 10px", "fontSize": "12.5px",
                                "textAlign": "center"},
                         binds={
                             "props.text": expr_bind(
                                 "toStr({view.custom.areas[%d].counts.%s}) + \"  %s\""
                                 % (i, key, abbr)),
                             "props.style.classes": expr_bind(
                                 "if({view.custom.areas[%d].counts.%s} > 0, "
                                 "\"ad-chip ad-chip-%s\", \"ad-chip ad-chip-zero\")"
                                 % (i, key, cls)),
                         })

        # a 2 x 2 grid rather than a wrapping row: four equal pills that always
        # sit in the same place, so the cards can be read side by side
        chips = [
            flex("R0", [chip(*PRI[0]), chip(*PRI[1])], gap=7,
                 position=fixed("27px")),
            flex("R1", [chip(*PRI[2]), chip(*PRI[3])], gap=7,
                 position=fixed("27px")),
        ]

        cards.append(flex("A%d" % i, [
            flex("Head", [
                label("Name", classes="ad-card-head", position=grow(1),
                      binds={"props.text": prop_bind(
                          "view.custom.areas[%d].area" % i)}),
                label("State", classes="ad-chip", position=fixed("auto"),
                      style={"padding": "2px 9px", "fontSize": "11px"},
                      binds={
                          "props.text": expr_bind(
                              "if({view.custom.areas[%d].active} > 0, "
                              "upper({view.custom.areas[%d].worst}), \"OK\")"
                              % (i, i)),
                          "props.style.classes": expr_bind(
                              "\"ad-chip ad-chip-\" + "
                              "if({view.custom.areas[%d].active} > 0, "
                              "lower({view.custom.areas[%d].worst}), \"ok\")"
                              % (i, i)),
                      }),
            ], gap=8, align="center", position=fixed("24px")),

            flex("Numbers", [
                flex("Act", [
                    label("V", classes="ad-kpi-value", position=fixed("auto"),
                          style={"fontSize": "34px"},
                          binds={
                              "props.text": expr_bind(
                                  "toStr({view.custom.areas[%d].active})" % i),
                              "props.style.color": expr_bind(
                                  "if({view.custom.areas[%d].active} > 0, "
                                  "\"var(--ink)\", \"var(--ok)\")" % i),
                          }),
                    label("L", "ACTIVE", classes="ad-kpi-label",
                          position=fixed("auto"),
                          style={"paddingBottom": "4px"}),
                ], gap=7, align="end", position=grow(1),
                    style={"overflow": "hidden"}),
                flex("Un", [
                    label("V", classes="ad-kpi-value", position=fixed("auto"),
                          style={"fontSize": "34px"},
                          binds={
                              "props.text": expr_bind(
                                  "toStr({view.custom.areas[%d].unacked})" % i),
                              "props.style.color": expr_bind(
                                  "if({view.custom.areas[%d].unacked} > 0, "
                                  "\"var(--high)\", \"var(--ink-3)\")" % i),
                          }),
                    label("L", "UNACKED", classes="ad-kpi-label",
                          position=fixed("auto"),
                          style={"paddingBottom": "4px"}),
                ], gap=7, align="end", position=grow(1),
                    style={"overflow": "hidden"}),
            ], gap=10, position=fixed("46px")),

            flex("Chips", chips, direction="column", gap=7,
                 position=fixed("61px")),
            flex("Gap", [], position=grow(1)),

            label("Worst", classes="ad-faint", position=fixed("32px"),
                  style={"fontSize": "11.5px"},
                  binds={"props.text": expr_bind(
                      "if({view.custom.areas[%d].active} > 0, "
                      "\"Worst standing:  \" + {view.custom.areas[%d].worstName}, "
                      "\"Nothing standing in this area\")" % (i, i))}),
        ], direction="column", gap=8,
            classes="ad-card", style={"padding": "14px"},
            # basis 0%, so every area card is exactly the same width. Left to
            # the default the longest "Worst standing" text widened its own
            # card, which then fitted five priority chips on one row where its
            # neighbours fitted four - five identical cards, one of them
            # visibly different.
            position=grow(1, "0%"),
            binds={"props.style.display": expr_bind(
                "if({view.custom.areaCount} > %d, \"flex\", \"none\")" % i)}))

    # --- the two 30-day trends -------------------------------------------
    # The cards above answer "where is it bad right now"; these answer "is it
    # getting better or worse". Separate charts rather than one with two
    # y-scales: alarms and minutes share no unit, and a dual axis would let the
    # layout decide which line looks worse.
    load = day_trend("Load", "view.custom.dailyLoad", "alarms", CHART_LOW,
                     "Alarms per day", "alarms")
    ack = day_trend("Ack", "view.custom.dailyAck", "minutes", CHART_OK,
                    "Average minutes to acknowledge", "minutes")

    root = flex("root", [
        header(),
        flex("Body", [
            label("Intro",
                  "Live alarm metrics aggregated per process area for the "
                  "selected site, and how the load and the response to it have "
                  "moved over the last 30 days. Everything here follows the "
                  "site switch.",
                  classes="ad-faint", position=fixed("18px"),
                  style={"fontSize": "12px"}),
            flex("Cards", cards, gap=12, position=fixed("268px")),
            # basis 0% on both, so the split is exactly even. Left to the
            # default the longer subtitle widens its own card, and two date
            # axes of different widths pick different label granularities -
            # one chart ends up labelled weekly and the other monthly, which
            # reads as though they cover different periods.
            flex("Trends", [
                card("LoadCard", "Daily alarm load", load, grow(1, "0%"),
                     "Last 30 complete days.  Every day is plotted, so a quiet "
                     "weekend reads as quiet rather than as missing."),
                card("AckCard", "Time to acknowledge", ack, grow(1, "0%"),
                     "Average per day, last 30 complete days.  A day when "
                     "nothing was acknowledged has no average and is left out."),
            ], gap=12, position=grow(1)),
        ], direction="column", gap=10,
            style={"padding": "0 12px 12px 12px"}, position=grow(1)),
    ], direction="column", gap=12,
        classes="ad-page ad-root", style={"height": "100%"})
    root["children"][0]["position"] = fixed("64px")

    blank = {"area": "", "active": 0, "unacked": 0, "acked": 0,
             "worst": "OK", "worstName": "-",
             "counts": {"Critical": 0, "High": 0, "Medium": 0, "Low": 0,
                        "Diagnostic": 0}}
    custom = {"areas": [dict(blank) for _ in range(AREA_SLOTS)],
              "areaCount": 0, "dailyLoad": None, "dailyAck": None}
    pc = {
        "custom.areas": expr_bind(
            "{session.custom.site} + toStr(now(3000))",
            transform=script_tf(
                "\treturn AlarmDemo.alarms.areaMetrics(self.session.custom.site)")),
        "custom.areaCount": expr_bind(
            "{session.custom.site} + toStr(now(30000))",
            transform=script_tf(
                "\treturn len(AlarmDemo.alarms.siteAreas("
                "self.session.custom.site))")),
        # 30 days of journal is a heavier query than the live roll-up, and it
        # cannot change materially inside a minute - so it polls at a different
        # rate rather than riding along with the cards.
        "custom.dailyLoad": expr_bind(
            "{session.custom.site} + toStr(now(60000))",
            transform=script_tf(
                "\treturn AlarmDemo.alarms.dailyLoad(30, "
                "self.session.custom.site)")),
        "custom.dailyAck": expr_bind(
            "{session.custom.site} + toStr(now(60000))",
            transform=script_tf(
                "\treturn AlarmDemo.alarms.dailyAckTime(30, "
                "self.session.custom.site)")),
    }
    write("AlarmDemo/Metrics", view(root, custom=custom, propconfig=pc))


# ---------------------------------------------------------------------------
# Notifications - rosters, escalation, and who is getting each live alarm
# ---------------------------------------------------------------------------




def v_escalation_popup():
    """The escalation matrix as a legend you can call up and drag aside.

    It is a fixed reference table - it never changes while the demo runs - so
    it does not earn permanent screen space next to the live routing.
    """
    esc_tbl = C("ia.display.table", "Escalation", {
        "style": {"classes": "ad-table ad-table-plain"},
        "pager": {"bottom": False, "top": False},
        "columns": [
            priority_col(width=108),
            col("Notifies", "Notifies", width=124),
            col("When", "When", width=118),
            col("Escalates to", "Escalates to", width=132),
            col("If unacknowledged", "If unacknowledged"),
        ],
    }, position=grow(1),
        binds={"props.data": expr_bind(
            "toStr(now(60000))",
            transform=script_tf("\treturn AlarmDemo.roster.escalationTable()"))})

    root = flex("root", [
        label("Sub",
              "Which roster an alarm goes to, how quickly, and who it "
              "escalates to if nobody acknowledges it.",
              classes="ad-faint", position=fixed("18px"),
              style={"fontSize": "11.5px"}),
        esc_tbl,
        label("Note",
              "The rosters and the schedules are real gateway configuration. "
              "This matrix is the design an alarm notification pipeline would "
              "implement on top of them - a pipeline needs a working email or "
              "SMS profile before it can send anything, so it is not part of "
              "this self-contained demo.",
              classes="ad-faint", position=fixed("46px"),
              style={"fontSize": "11px", "lineHeight": "15px"}),
    ], direction="column", gap=8,
        classes="ad-page ad-root",
        style={"padding": "12px", "height": "100%"})
    write("AlarmDemo/Popups/Escalation", view(root, size=(780, 400)))


# Shared by the two screens that read the roster module. Both show the same
# people and the same duty state, so the shapes have to agree: Notifications
# answers "who is being called right now", People & Shifts answers "who could
# be, and when".
ROSTER_NAMES = ["Operations", "Maintenance", "Management"]
ROSTER_SLOTS = 5
PEOPLE_SLOTS = 7
SHIFTS = [("Day", "Day Shift"), ("Arvo", "Afternoon Shift"),
          ("Night", "Night Shift"), ("Always", "Always")]

BLANK_PERSON = {"username": "", "name": "", "role": "", "email": "",
                "phone": "", "schedule": "", "onDuty": False, "duty": "",
                "rosters": "", "inGateway": "no"}


def duty_chip(name, on_path, text_path, width="76px"):
    """ON DUTY / off, green when on duty and quiet when not."""
    return label(name, position=fixed(width),
                 classes="ad-chip",
                 style={"padding": "2px 8px", "fontSize": "10px",
                        "textAlign": "center"},
                 binds={
                     "props.text": prop_bind(text_path),
                     "props.style.classes": expr_bind(
                         "if({%s} = true, \"ad-chip ad-chip-ok\", "
                         "\"ad-chip ad-chip-zero\")" % on_path),
                 })


def duty_bar(extra=None):
    """The "3 OF 7 ON DUTY NOW" strip, with a clock beside it.

    On both screens, because both are answering a question about *now* and the
    reading is worthless without knowing what time the gateway thinks it is -
    a shift screen that does not show the clock invites the audience to assume
    it is stale.
    """
    return flex("TopBar", [
        label("L", "ON CALL", classes="ad-kpi-label", position=fixed("62px"),
              style={"alignSelf": "center"}),
        label("Duty", classes="ad-chip ad-chip-ok", position=fixed("auto"),
              style={"padding": "3px 10px", "alignSelf": "center"},
              binds={"props.text": expr_bind(
                  "toStr({view.custom.duty.onDuty}) + \" OF \" + "
                  "toStr({view.custom.duty.total}) + \" ON DUTY NOW\"")}),
        label("Clock", classes="ad-faint", position=fixed("150px"),
              style={"fontSize": "11.5px", "alignSelf": "center"},
              binds={"props.text": expr_bind(
                  "dateFormat(now(10000), \"EEE dd/MM  HH:mm\")")}),
        flex("Sp", [], position=grow(1)),
    ] + (extra or []), gap=8, align="center", position=fixed("40px"))


def v_notifications():
    """Rosters and live routing - all of it real Ignition config.

    The screen is built to survive the obvious challenge from the audience,
    "yes but is any of that actually in the gateway?". Every name on it comes
    from a user source, every roster from `system.alarm.getRosters`, and every
    ON DUTY / off state from the user's Ignition schedule. Config -> Alarming ->
    On-Call Rosters and Security -> Schedules show the same thing.

    Shift is a property of a PERSON, not of a roster membership - that is
    Ignition's model, and it is why the people and their schedules get their own
    screen rather than a panel at the bottom of this one. This screen is about
    the alarms; People & Shifts is about the people.
    """
    SLOTS = ROSTER_SLOTS

    # --- top bar ----------------------------------------------------------
    top_bar = duty_bar([
        C("ia.input.button", "EscBtn", {
            "text": "Escalation rules",
            "style": {"classes": "ad-btn ad-btn-sm"},
        }, position=fixed("152px"),
            events=on_action(
                "system.perspective.openPopup(\n"
                "    'escalation',\n"
                "    'AlarmDemo/Popups/Escalation',\n"
                "    title='Escalation matrix',\n"
                "    modal=False, draggable=True, resizable=False,\n"
                "    position={'width': 780, 'height': 400})")),
    ])

    # --- roster cards -----------------------------------------------------
    roster_cards = []
    for i, rname in enumerate(ROSTER_NAMES):
        rows = []
        for m in range(SLOTS):
            base = "view.custom.rosters[%d].members[%d]" % (i, m)
            rows.append(flex("M%d" % m, [
                label("Name", position=grow(1),
                      style={"fontSize": "12.5px", "color": "var(--ink)",
                             "overflow": "hidden", "whiteSpace": "nowrap"},
                      binds={"props.text": prop_bind(base + ".name")}),
                label("Sched", position=fixed("112px"),
                      classes="ad-muted",
                      style={"fontSize": "11px", "overflow": "hidden",
                             "whiteSpace": "nowrap"},
                      binds={"props.text": prop_bind(base + ".schedule")}),
                duty_chip("Duty", base + ".onDuty", base + ".duty"),
                C("ia.input.button", "Rm", {
                    "text": "x", "style": {"classes": "ad-btn ad-btn-x"},
                }, position=fixed("26px"),
                    events=on_action(
                        "AlarmDemo.roster.removeMember(\n"
                        "    '%s', self.view.custom.rosters[%d].members[%d].username)\n"
                        "self.view.custom.tick = self.view.custom.tick + 1"
                        % (rname, i, m))),
            ], gap=8, align="center", position=fixed("26px"),
                style={"overflow": "hidden"},
                binds={"props.style.display": expr_bind(
                    "if({view.custom.rosters[%d].count} > %d, \"flex\", \"none\")"
                    % (i, m))}))

        add_row = flex("Add", [
            C("ia.input.dropdown", "Pick", {
                "placeholder": "add someone to this roster",
                "style": {"classes": "ad-btn"},
            }, position=grow(1),
                binds={
                    "props.options": prop_bind("view.custom.eligible%d" % i),
                    "props.value": {"binding": {"type": "property", "config": {
                        "path": "view.custom.pick%d" % i,
                        "bidirectional": True}}},
                }),
            C("ia.input.button", "Add", {
                "text": "+", "style": {"classes": "ad-btn ad-btn-primary ad-btn-x"},
            }, position=fixed("30px"),
                events=on_action(
                    "if self.view.custom.pick%d:\n"
                    "    AlarmDemo.roster.addMember('%s', self.view.custom.pick%d)\n"
                    "    self.view.custom.pick%d = ''\n"
                    "    self.view.custom.tick = self.view.custom.tick + 1"
                    % (i, rname, i, i))),
        ], gap=6, align="center", position=fixed("32px"))

        roster_cards.append(flex("R%d" % i, [
            flex("Head", [
                label("Name", rname, classes="ad-card-head", position=grow(1)),
                # two numbers, because they answer different questions: how
                # many people are on this roster at all, and how many of them
                # are awake right now
                label("Count", classes="ad-chip", position=fixed("auto"),
                      style={"padding": "2px 9px", "fontSize": "11px"},
                      binds={
                          "props.text": expr_bind(
                              "toStr({view.custom.rosters[%d].onDuty}) + \" ON DUTY  /  \" "
                              "+ toStr({view.custom.rosters[%d].count})" % (i, i)),
                          "props.style.classes": expr_bind(
                              "if({view.custom.rosters[%d].onDuty} > 0, "
                              "\"ad-chip ad-chip-ok\", \"ad-chip ad-chip-critical\")" % i),
                      }),
            ], gap=8, align="center", position=fixed("24px")),
            label("Blurb", classes="ad-faint", position=fixed("16px"),
                  style={"fontSize": "11.5px"},
                  binds={"props.text": prop_bind(
                      "view.custom.rosters[%d].blurb" % i)}),
            flex("Members", rows, direction="column", gap=3, position=grow(1)),
            add_row,
        ], direction="column", gap=6,
            classes="ad-card", style={"padding": "12px"}, position=grow(1, "0%")))

    # --- live routing -----------------------------------------------------
    routing_tbl = C("ia.display.table", "Routing", {
        "style": {"classes": "ad-table ad-table-plain"},
        "pager": {"bottom": False, "top": False},
        # Only the narrow columns get a width; Alarm and "On call now" share
        # what is left, so the table reflows instead of overflowing.
        "columns": [
            col("Alarm", "Alarm"),
            priority_col(width=112),
            col("Roster", "Roster", width=116),
            col("On call now", "On call now"),
            col("When", "When", width=112),
            col("Escalates", "If unacknowledged", width=200),
            col("Status", "Status", width=118),
        ],
    }, position=grow(1),
        binds={"props.data": expr_bind(
            "{session.custom.site} + toStr({view.custom.tick}) + toStr(now(4000))",
            transform=script_tf(
                "\treturn AlarmDemo.roster.routing(self.session.custom.site)"))})

    root = flex("root", [
        header(),
        flex("Body", [
            top_bar,
            flex("Rosters", roster_cards, gap=12, position=fixed("236px")),
            card("RoutingCard", "Who is getting the live alarms",
                 routing_tbl, grow(1),
                 "Priority picks the roster, the roster's Ignition schedules "
                 "pick the people. Change someone's shift on the People & "
                 "Shifts screen and this follows them."),
        ], direction="column", gap=12, classes="ad-body",
            style={"padding": "0 12px 12px 12px"}, position=grow(1)),
    ], direction="column", gap=12,
        classes="ad-page ad-root", style={"height": "100%"})
    root["children"][0]["position"] = fixed("64px")

    custom = {"rosters": [], "duty": {"onDuty": 0, "total": PEOPLE_SLOTS},
              "tick": 0}
    pc = {
        # `tick` is in every trigger so an edit refreshes the cards and the
        # routing immediately rather than on the next poll.
        "custom.rosters": expr_bind(
            "toStr({view.custom.tick}) + toStr(now(5000))",
            transform=script_tf(
                "\treturn AlarmDemo.roster.rosterCards()")),
        "custom.duty": expr_bind(
            "toStr({view.custom.tick}) + toStr(now(5000))",
            transform=script_tf(
                "\treturn AlarmDemo.roster.dutySummary()")),
    }
    for i, rname in enumerate(ROSTER_NAMES):
        custom["eligible%d" % i] = []
        custom["pick%d" % i] = ""
        pc["custom.eligible%d" % i] = expr_bind(
            "toStr({view.custom.tick}) + toStr(now(15000))",
            transform=script_tf(
                "\treturn AlarmDemo.roster.eligible('%s')" % rname))
    write("AlarmDemo/Notifications", view(root, custom=custom, propconfig=pc))


# ---------------------------------------------------------------------------
# People & Shifts - the directory, and who is awake
# ---------------------------------------------------------------------------


def v_people():
    """Everyone the alarm system can call, their Ignition schedule, and whether
    that schedule has them on duty right now.

    Split out of Notifications, which was carrying both the live routing and
    the people who serve it. They answer different questions and are read at
    different moments - routing during an incident, this one while setting the
    roster up - and sharing a screen left the routing table three rows tall.

    Rows rather than a table component: each one carries the shift buttons, and
    those need the username behind the row, not the text rendered in the cell.
    """
    def person_row(p):
        base = "view.custom.people[%d]" % p
        shift_btns = [
            C("ia.input.button", "S%s" % key, {
                "text": key, "style": {"classes": "ad-btn ad-btn-sm"},
            }, position=fixed("62px"),
                events=on_action(
                    "AlarmDemo.roster.setSchedule(\n"
                    "    self.view.custom.people[%d].username, '%s')\n"
                    "self.view.custom.tick = self.view.custom.tick + 1"
                    % (p, sched)),
                binds={"props.style.classes": expr_bind(
                    "if({%s.schedule} = \"%s\", "
                    "\"ad-btn ad-btn-sm ad-btn-active\", \"ad-btn ad-btn-sm\")"
                    % (base, sched))})
            for key, sched in SHIFTS
        ]
        return flex("P%d" % p, [
            label("Name", position=fixed("150px"),
                  style={"fontSize": "13.5px", "color": "var(--ink)",
                         "overflow": "hidden", "whiteSpace": "nowrap"},
                  binds={"props.text": prop_bind(base + ".name")}),
            label("Role", position=fixed("132px"), classes="ad-faint",
                  style={"fontSize": "12.5px", "overflow": "hidden",
                         "whiteSpace": "nowrap"},
                  binds={"props.text": prop_bind(base + ".role")}),
            flex("Shift", shift_btns, gap=5, align="center",
                 position=fixed("263px")),
            duty_chip("Duty", base + ".onDuty", base + ".duty", "80px"),
            label("Sched", position=fixed("126px"),
                  classes="ad-muted ad-col-sched",
                  style={"fontSize": "12.5px", "overflow": "hidden",
                         "whiteSpace": "nowrap"},
                  binds={"props.text": prop_bind(base + ".schedule")}),
            label("Rosters", position=fixed("156px"),
                  classes="ad-muted ad-col-rosters",
                  style={"fontSize": "12.5px", "overflow": "hidden",
                         "whiteSpace": "nowrap"},
                  binds={"props.text": prop_bind(base + ".rosters")}),
            label("Phone", position=fixed("122px"),
                  classes="ad-muted ad-col-phone",
                  style={"fontSize": "12.5px", "overflow": "hidden",
                         "whiteSpace": "nowrap"},
                  binds={"props.text": prop_bind(base + ".phone")}),
            # Email takes what is left rather than a fixed width - it is the
            # longest and least important column, so it is the right one to
            # absorb the slack at any window size.
            label("Email", position=grow(1, "0%"),
                  classes="ad-muted ad-col-email",
                  style={"fontSize": "12.5px", "overflow": "hidden",
                         "whiteSpace": "nowrap"},
                  binds={"props.text": prop_bind(base + ".email")}),
        ], gap=10, align="center", position=fixed("32px"),
            style={"overflow": "hidden",
                   "borderBottom": "1px solid rgba(39,49,64,0.7)"})

    head = flex("Head", [
        label("H1", "NAME", classes="ad-kpi-label", position=fixed("150px")),
        label("H2", "ROLE", classes="ad-kpi-label", position=fixed("132px")),
        label("H3", "SHIFT", classes="ad-kpi-label", position=fixed("263px")),
        label("H4", "NOW", classes="ad-kpi-label", position=fixed("80px")),
        label("H5", "IGNITION SCHEDULE",
              classes="ad-kpi-label ad-col-sched", position=fixed("126px")),
        label("H6", "ON CALL ROSTERS",
              classes="ad-kpi-label ad-col-rosters", position=fixed("156px")),
        label("H7", "MOBILE", classes="ad-kpi-label ad-col-phone",
              position=fixed("122px")),
        label("H8", "EMAIL", classes="ad-kpi-label ad-col-email",
              position=grow(1, "0%")),
    ], gap=10, align="center", position=fixed("16px"))

    # No `minHeight: 0` and no scrollbar of its own: with them the list was
    # the thing that gave way when the page ran short, so the seventh person
    # was simply cut off mid-row. Flex's default `min-height: auto` now keeps
    # the list at its full height and the PAGE scrolls if it has to - one
    # scrollbar, in the place a reader looks for it.
    people_body = flex("PeopleBody",
                       [head] + [person_row(p) for p in range(PEOPLE_SLOTS)],
                       direction="column", gap=2, position=grow(1),
                       style={"minHeight": "%dpx" % (
                           16 + PEOPLE_SLOTS * 32 + PEOPLE_SLOTS * 2)})

    # --- the shift schedules, drawn as a 24-hour timeline -----------------
    # A list of names and times reads as reference material; the thing an
    # audience actually asks is "so who is on right now, and who is next",
    # which is a question about where the blocks sit on a clock. So it is
    # drawn as one: four tracks against a shared 24-hour axis, with a live
    # marker, and the schedule that is currently in force lit up.
    NOW = "now(60000)"
    NOW_HOUR = "(getHour24(%s) + getMinute(%s) / 60.0)" % (NOW, NOW)

    # (name, hours label, [(startHour, endHour), ...], active-now expression)
    TRACKS = [
        ("Day Shift", "06:00 - 14:00", [(6, 14)],
         "%s >= 6 && %s < 14" % (NOW_HOUR, NOW_HOUR)),
        ("Afternoon Shift", "14:00 - 22:00", [(14, 22)],
         "%s >= 14 && %s < 22" % (NOW_HOUR, NOW_HOUR)),
        ("Night Shift", "22:00 - 06:00", [(0, 6), (22, 24)],
         "%s >= 22 || %s < 6" % (NOW_HOUR, NOW_HOUR)),
        ("Always", "all day, every day", [(0, 24)], "1 = 1"),
    ]

    def pct(hours):
        return "%.4f%%" % (hours / 24.0 * 100.0)

    def track_row(name, hours, spans, active):
        # Segments walk left to right across the 24 hours: a transparent
        # spacer, then a filled block, then the next spacer. Percentage bases
        # rather than pixels, so the axis stays true at any window width.
        segs = []
        cursor = 0.0
        for i, (start, end) in enumerate(spans):
            if start > cursor:
                segs.append(flex("G%d" % i, [], position={
                    "grow": 0, "shrink": 0, "basis": pct(start - cursor)}))
            segs.append(flex("F%d" % i, [],
                             style={"height": "100%", "borderRadius": "4px"},
                             position={"grow": 0, "shrink": 0,
                                       "basis": pct(end - start)},
                             binds={"props.style.backgroundColor": expr_bind(
                                 "if(%s, \"var(--low)\", \"color-mix(in srgb, var(--low-base) 28%%, transparent)\")"
                                 % active)}))
            cursor = end
        if cursor < 24:
            segs.append(flex("GE", [], position={
                "grow": 0, "shrink": 0, "basis": pct(24 - cursor)}))

        return flex("T_" + name.replace(" ", ""), [
            label("Name", name, position=fixed("150px"),
                  style={"fontSize": "12.5px", "whiteSpace": "nowrap"},
                  binds={"props.style.color": expr_bind(
                      "if(%s, \"var(--ink)\", \"var(--ink-3)\")" % active)}),
            label("Hours", hours, classes="ad-faint", position=fixed("128px"),
                  style={"fontSize": "11.5px", "whiteSpace": "nowrap"}),
            flex("Track", segs, classes="ad-track", position=grow(1)),
            # ON NOW / - rather than colour alone, so the live schedule is
            # readable without relying on the brightness difference
            label("Live", position=fixed("70px"), classes="ad-chip",
                  style={"padding": "1px 8px", "fontSize": "10px",
                         "textAlign": "center"},
                  binds={
                      "props.text": expr_bind(
                          "if(%s, \"ON NOW\", \"-\")" % active),
                      "props.style.classes": expr_bind(
                          "if(%s, \"ad-chip ad-chip-ok\", \"ad-chip ad-chip-zero\")"
                          % active),
                  }),
        ], gap=12, align="center", position=fixed("22px"))

    # hour ruler, aligned with the tracks
    ruler = flex("Ruler", [
        flex("Pad", [], position=fixed("290px")),
        flex("Marks", [
            label("H%d" % h, "%02d" % h, classes="ad-faint",
                  position={"grow": 1, "shrink": 1, "basis": "0%"},
                  style={"fontSize": "10px"})
            for h in range(0, 24, 3)
        ] + [
            label("H24", "24", classes="ad-faint", position=fixed("14px"),
                  style={"fontSize": "10px", "textAlign": "right"}),
        ], position=grow(1)),
        flex("PadR", [], position=fixed("82px")),
    ], gap=12, align="center", position=fixed("14px"))

    # the live marker: a spacer whose width is the time of day, then a 2px rule
    now_row = flex("NowRow", [
        flex("Pad", [], position=fixed("290px")),
        flex("Marks", [
            flex("Before", [], position={"grow": 0, "shrink": 0, "basis": "0%"},
                 binds={"position.basis": expr_bind(
                     "toStr(%s / 24.0 * 100) + \"%%\"" % NOW_HOUR)}),
            flex("Line", [], classes="ad-nowline",
                 position=fixed("2px")),
            label("Time", classes="ad-faint", position=grow(1, "0%"),
                  style={"fontSize": "10px", "paddingLeft": "5px",
                         "whiteSpace": "nowrap", "overflow": "hidden"},
                  binds={"props.text": expr_bind(
                      "dateFormat(%s, \"HH:mm\")" % NOW)}),
        ], position=grow(1), style={"height": "100%"}),
        flex("PadR", [], position=fixed("82px")),
    ], gap=12, align="center", position=fixed("16px"))

    # A floor, for the same reason the people list has one: the card around
    # it is allowed to shrink, and a flex item with `overflow` set has an
    # automatic minimum size of zero, so without this the tracks are what
    # gives way on a short window.
    shift_timeline = flex("Timeline",
                          [now_row, ruler] +
                          [track_row(n, h, s, a) for n, h, s, a in TRACKS],
                          direction="column", gap=4, position=grow(1),
                          style={"minHeight": "%dpx" % (
                              16 + 14 + 4 * 22 + 5 * 4)})

    def people_card(sub):
        # A card that will not scroll either. Giving the LIST a floor only
        # moved the scrollbar out to the card around it: both are flex items
        # with `overflow` set, which zeroes their automatic minimum size, so
        # each one has to state its own floor and let the page take the strain.
        c = card("PeopleCard", "People and shifts", people_body,
                 {"grow": 0, "shrink": 1, "basis": "auto"}, sub)
        c["props"]["style"]["minHeight"] = "300px"
        return c

    root = flex("root", [
        header(),
        flex("Body", [
            duty_bar([
                # Same popup as Notifications rather than a second inline copy:
                # it is fixed reference material, and giving it permanent space
                # here left neither table room to scale.
                C("ia.input.button", "EscBtn", {
                    "text": "Escalation rules",
                    "style": {"classes": "ad-btn ad-btn-sm"},
                }, position=fixed("152px"),
                    events=on_action(
                        "system.perspective.openPopup(\n"
                        "    'escalation',\n"
                        "    'AlarmDemo/Popups/Escalation',\n"
                        "    title='Escalation matrix',\n"
                        "    modal=False, draggable=True, resizable=False,\n"
                        "    position={'width': 780, 'height': 400})")),
            ]),
            people_card(
                 "Real users in the default user source. A shift button writes "
                 "a real Ignition schedule onto the user - the same field "
                 "Security -> Users shows - and the alarm routing follows it "
                 "immediately."),
            card("LegendCard", "The shift schedules, across a day",
                 shift_timeline, fixed("218px", shrink=1),
                 "The three shifts cover the clock between them. The marker is "
                 "now."),
            flex("Sp", [], position=grow(1)),
            # The build number, on screen. "Which build is this gateway
            # running?" was not answerable from the running demo, and a chart
            # bug that was actually a browser setting cost four rounds of
            # guessing partly because of it.
            label("Build", BUILD_TEXT,
                  classes="ad-faint", position=fixed("14px"),
                  style={"fontSize": "10.5px", "letterSpacing": "0.06em",
                         "textAlign": "right"}),
        ], direction="column", gap=12, classes="ad-body",
            style={"padding": "0 12px 12px 12px"}, position=grow(1)),
    ], direction="column", gap=12,
        classes="ad-page ad-root",
        style={"height": "100%", "overflowY": "auto"})
    root["children"][0]["position"] = fixed("64px")

    custom = {
        "people": [dict(BLANK_PERSON) for _ in range(PEOPLE_SLOTS)],
        "duty": {"onDuty": 0, "total": PEOPLE_SLOTS},
        "tick": 0,
    }
    pc = {
        # `tick` is in the trigger so a shift change refreshes the list at once
        # rather than on the next poll.
        "custom.people": expr_bind(
            "toStr({view.custom.tick}) + toStr(now(5000))",
            transform=script_tf("\treturn AlarmDemo.roster.peopleRows()")),
        "custom.duty": expr_bind(
            "toStr({view.custom.tick}) + toStr(now(5000))",
            transform=script_tf("\treturn AlarmDemo.roster.dutySummary()")),
    }
    write("AlarmDemo/People", view(root, custom=custom, propconfig=pc))


# ---------------------------------------------------------------------------
# Setup - what a fresh gateway needs, and the buttons that do it
# ---------------------------------------------------------------------------

# One row per AlarmDemo.setup.ITEMS entry. The list is generated STATICALLY at
# this length rather than repeated from data, because Perspective has no repeat
# container that can carry a per-row button: each row binds to
# view.custom.state.items[i] and shows nothing when that index is absent.
#
# The count is READ OUT OF the setup module rather than written here. It used to
# be the literal 9, with a comment saying a tenth item would appear "the moment
# this count is bumped" - and when a tenth was added the row that fell off the
# end was simply absent from the screen, with nothing anywhere saying so. A
# number that has to be kept in step by hand is a number that will not be.
def _setup_row_count():
    import ast
    src = open(os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "project/ignition/script-python/AlarmDemo/setup/code.py")).read()
    for node in ast.parse(src).body:
        if (isinstance(node, ast.Assign)
                and any(getattr(t, "id", None) == "ITEMS" for t in node.targets)
                and isinstance(node.value, ast.List)):
            return len(node.value.elts)
    raise SystemExit("build_views: cannot find AlarmDemo.setup.ITEMS")


SETUP_ROWS = _setup_row_count()


def setup_row(i):
    item = "view.custom.state.items[%d]" % i
    return flex("R%d" % i, [
        label("Status", classes="ad-chip", position=fixed("94px"),
              style={"textAlign": "center", "alignSelf": "center",
                     "lineHeight": "22px"},
              binds={
                  "props.text": expr_bind(
                      "if({%s.ok} = true, \"READY\", \"MISSING\")" % item),
                  "props.style.classes": expr_bind(
                      "if({%s.ok} = true, \"ad-chip ad-chip-ok\", "
                      "\"ad-chip ad-chip-critical\")" % item),
              }),
        flex("Text", [
            label("Title", position=fixed("17px"),
                  style={"fontSize": "13.5px", "fontWeight": "600"},
                  binds={"props.text": prop_bind("%s.title" % item)}),
            # The detail line answers "what is it now"; the why line answers
            # "what is it for". Both are always present, so a row does not
            # change height when it goes from missing to ready - a list that
            # reflows under the button you are about to press is how you press
            # the wrong one.
            label("Detail", classes="ad-muted", position=fixed("16px"),
                  style={"fontSize": "12px", "whiteSpace": "nowrap",
                         "overflow": "hidden", "textOverflow": "ellipsis"},
                  binds={"props.text": prop_bind("%s.detail" % item)}),
            label("Why", classes="ad-faint", position=fixed("15px"),
                  style={"fontSize": "11px", "whiteSpace": "nowrap",
                         "overflow": "hidden", "textOverflow": "ellipsis"},
                  binds={"props.text": prop_bind("%s.why" % item)}),
        ], direction="column", gap=1, position=grow(1)),
        C("ia.input.button", "Fix", {
            "text": "Create",
            "style": {"classes": "ad-btn ad-btn-sm"},
        }, position=fixed("94px"),
            events=on_action(
                "item = self.view.custom.state['items'][%d]\n"
                "self.view.custom.busy = 'creating %%s...' %% item['title']\n"
                "try:\n"
                "\tself.view.custom.busy = AlarmDemo.setup.fix(item['key'])\n"
                "except Exception, e:\n"
                "\tself.view.custom.busy = 'failed: %%s' %% e\n"
                "self.view.custom.tick = self.view.custom.tick + 1" % i),
            binds={"props.style.display": expr_bind(
                # A Create button on a row that is already done invites a press
                # that changes nothing. Every row can be created now - the
                # database connection was the last one that could not, and
                # SQLite is what changed that.
                #
                # `&&`, not `and`: Ignition's expression language is not
                # Python, and `and` is a parse error that shows up as a red
                # outline round the component with the binding unevaluated -
                # so the button appeared on every row, including the one that
                # has nothing to press.
                "if({%s.fixable} = true && {%s.ok} = false, "
                "\"flex\", \"none\")" % (item, item))}),
    ], gap=12, align="center", position=fixed("54px"),
        style={"padding": "0 4px"},
        binds={"props.style.display": expr_bind(
            "if(isNull({%s.key}), \"none\", \"flex\")" % item)})


def v_setup():
    name_row = flex("DbRow", [
        C("ia.input.text-field", "DbName", {
            "text": "", "placeholder": "database connection name",
            "style": {"classes": "ad-input"},
        }, position=fixed("240px"),
            binds={"props.text": prop_bind_rw("view.custom.dbName")}),
        C("ia.input.button", "SaveDb", {
            "text": "Use this one",
            "style": {"classes": "ad-btn ad-btn-primary"},
        }, position=fixed("130px"),
            events=on_action(
                "AlarmDemo.config.save(self.view.custom.dbName)\n"
                "self.view.custom.busy = 'saved - re-checking'\n"
                "self.view.custom.tick = self.view.custom.tick + 1")),
        label("Where", classes="ad-faint", position=grow(1),
              style={"fontSize": "11.5px", "alignSelf": "center",
                     "overflow": "hidden", "textOverflow": "ellipsis",
                     "whiteSpace": "nowrap"},
              binds={"props.text": expr_bind(
                  "\"from the \" + {view.custom.state.db.dbSource} + "
                  "\"   -   settings are kept at \" + "
                  "{view.custom.state.db.settingsPath}")}),
    ], gap=10, align="center", position=fixed("38px"))

    # One row. The five boxes that used to sit under it - host, port,
    # database, user, password - are gone with PostgreSQL, and the "or make
    # one" button that went with them is gone too: the connection is created
    # by the Create button on its own row in the list below, like every other
    # item. Nothing about it is special any more, which is the point.
    db_card = flex("DbCard", [name_row],
                   direction="column", gap=6, position=grow(1))

    actions = flex("SetupActions", [
        C("ia.input.button", "All", {
            "text": "Set up this gateway",
            "style": {"classes": "ad-btn ad-btn-primary"},
        }, position=fixed("200px"),
            events=on_action(
                "self.view.custom.busy = 'working - this takes about a minute'\n"
                "r = AlarmDemo.setup.run()\n"
                "done = r.get('changed', [])\n"
                "errs = r.get('errors', [])\n"
                "if errs:\n"
                "\tself.view.custom.busy = 'finished with problems: ' + '; '.join(errs)\n"
                "elif done:\n"
                "\tself.view.custom.busy = '; '.join(done)\n"
                "else:\n"
                "\tself.view.custom.busy = 'nothing to do - this gateway was already set up'\n"
                "self.view.custom.tick = self.view.custom.tick + 1")),
        C("ia.input.button", "Recheck", {
            "text": "Re-check",
            "style": {"classes": "ad-btn"},
        }, position=fixed("110px"),
            events=on_action(
                "self.view.custom.busy = ''\n"
                "self.view.custom.tick = self.view.custom.tick + 1")),
        C("ia.input.button", "ResetPeople", {
            "text": "Reset rosters and shifts",
            "style": {"classes": "ad-btn ad-btn-danger"},
        }, position=fixed("210px"),
            events=on_action(
                # through setup.fix, not straight into roster.setup: the fix
                # is the thing that knows a gateway without Alarm Notification
                # still gets its schedules and people, and says so instead of
                # throwing.
                "try:\n"
                "\tself.view.custom.busy = AlarmDemo.setup.fix('rosters', True)\n"
                "except Exception, e:\n"
                "\tself.view.custom.busy = 'failed: %s' % e\n"
                "self.view.custom.tick = self.view.custom.tick + 1")),
        # Absent, not disabled, on a gateway with no database: the backfill
        # writes rows straight into alarm_events, and Edge's journal is
        # internal to the platform with no table to write to. A disabled
        # button is a question; a missing one is an answer.
        C("ia.input.button", "Rebuild", {
            "text": "Rebuild 30-day history",
            "style": {"classes": "ad-btn ad-btn-danger"},
        }, position=fixed("220px"),
            # display, not meta.visible: an invisible flex child still holds
            # its place, so hiding the card that way left a card-shaped hole
            # in the page. `display: none` takes the space with it. Same
            # mechanism the Pareto rows use to pad to a fixed count.
            binds={"props.style.display": expr_bind(
                'if({view.custom.state.edition.hasDatabase}, "flex", "none")')},
            events=on_action(
                "self.view.custom.busy = 'rebuilding history...'\n"
                "n = AlarmDemo.backfill.run(days=30, perDay=85)\n"
                "self.view.custom.busy = "
                # ONE per cent sign. The doubled one was left over from a
                # format string this block is no longer built with, so it
                # reached the view verbatim - and `'...' %% n` is a Jython
                # syntax error, which a Perspective action reports by doing
                # nothing at all.
                "'history rebuilt: %d journal rows' % n\n"
                "self.view.custom.tick = self.view.custom.tick + 1")),
        label("Busy", classes="ad-muted", position=grow(1),
              style={"fontSize": "12px", "alignSelf": "center",
                     "overflow": "hidden", "textOverflow": "ellipsis",
                     "whiteSpace": "nowrap"},
              binds={"props.text": prop_bind("view.custom.busy")}),
    ], gap=10, align="center", position=fixed("40px"))

    rows = flex("Rows", [setup_row(i) for i in range(SETUP_ROWS)],
                direction="column", gap=2, position=grow(1))

    root = flex("root", [
        header(),
        flex("Body", [
            card("DbCard", "Database connection", db_card,
                 fixed("122px", shrink=1),
                 "SQLite, in a file in the gateway's own data directory - "
                 "press Create it and there is nothing to fill in, no server "
                 "to install and no password to type. Or name a connection "
                 "this gateway already has. Only the NAME is remembered, and "
                 "it is kept outside the project, so importing a new version "
                 "of the demo never overwrites what this gateway is pointed "
                 "at.",
                 # Absent on a gateway with no database - see the Rebuild
                 # button above for why absent rather than disabled, and for
                 # why this is `display` rather than visibility.
                 binds={"props.style.display": expr_bind(
                     'if({view.custom.state.edition.hasDatabase}, '
                     '"flex", "none")')}),
            card("ItemsCard", "This gateway",
                 flex("Wrap", [actions, rows], direction="column", gap=8,
                      position=grow(1)),
                 grow(1),
                 "Everything else the demo needs, created by the project on "
                 "the gateway it was imported onto. Safe to press twice - "
                 "each item is only created if it is missing."),
            label("Build", BUILD_TEXT,
                  classes="ad-faint", position=fixed("14px"),
                  style={"fontSize": "10.5px", "letterSpacing": "0.06em",
                         "textAlign": "right"}),
        ], direction="column", gap=12, classes="ad-body",
            style={"padding": "0 12px 12px 12px"}, position=grow(1)),
    ], direction="column", gap=12,
        classes="ad-page ad-root",
        style={"height": "100%", "overflowY": "auto"})
    root["children"][0]["position"] = fixed("64px")

    write("AlarmDemo/Setup", view(
        root,
        custom={"tick": 0, "busy": "", "dbName": "", "state": {}},
        propconfig={
            # The whole page is one call. Bound to the tick rather than polled:
            # a check that walks the config resources, the database and the
            # journal is not something to run every five seconds behind a
            # screen nobody is looking at. Every button ends by bumping the
            # tick, which is what re-runs it.
            "custom.state": expr_bind(
                "{view.custom.tick}",
                script_tf("\treturn AlarmDemo.setup.check()")),
            # Seeded from the gateway so the box shows what is actually in
            # force. The text field writes back into this prop, and Save is
            # what puts it on disk.
            "custom.dbName": expr_bind(
                "{view.custom.tick}",
                script_tf("\treturn AlarmDemo.config.db()")),

        }))


# ---------------------------------------------------------------------------
# Demo control
# ---------------------------------------------------------------------------

# (key, title, site, description) - site "" applies to both plants
SCENARIO_HELP = [
    ("None", "Normal operation", "",
     "Plant runs healthy. Alarms clear and the rate settles."),

    ("Storm", "Storm / high raw turbidity", "Water",
     "Catchment runoff. Raw turbidity spikes, filters load up, pH drops - "
     "a cascade across three areas in about a minute."),
    ("ChlorineFailure", "Chlorine dose pump failure", "Water",
     "Residual decays to a Critical compliance breach. The alarm your "
     "customer actually cares about."),
    ("PumpFailure", "Pump trips", "Water",
     "An intake pump and a high lift pump trip together. Watch the standby "
     "pick up and network pressure hold."),
    ("FilterBlinding", "Filter B blinding", "Water",
     "Head loss climbs, then turbidity breaks through - High then Critical, "
     "in the right order."),
    ("Chattering", "Chattering nuisance alarm", "Water",
     "High Lift Pump 3 flaps. Use it to demonstrate finding and shelving a "
     "bad actor."),

    ("LineJam", "Case packer jam - line stops", "Manufacturing",
     "The jam blocks everything upstream, the line stops, and OEE starts "
     "falling. Downtime you can watch accumulate."),
    ("ChillerFailure", "Chiller failure", "Manufacturing",
     "Chilled water climbs, batch temperature follows it up through High "
     "and on to a Critical food-safety limit."),
    ("AirLoss", "Instrument air loss", "Manufacturing",
     "Receiver drains, pneumatics fail, the whole line stops - one utility "
     "fault taking out four areas."),
    ("CO2Loss", "Low CO2", "Manufacturing",
     "Carbonation drifts and fill rejects climb. A quality alarm rather "
     "than a breakdown."),
    ("BatchOverTemp", "Batch over temperature", "Manufacturing",
     "Straight to the Critical quarantine alarm."),

    ("CommsLoss", "PLC comms loss", "",
     "The Diagnostic-priority case, so the priority scale is not just theory."),
]


def v_democontrol():
    buttons = []
    for key, title, site, desc in SCENARIO_HELP:
        # Rows for the other plant are hidden rather than removed, so the
        # panel is the same object on both sites and the switch is instant.
        vis = ("\"flex\"" if not site else
               "if({session.custom.site} = \"%s\", \"flex\", \"none\")" % site)
        buttons.append(flex("S_" + key, [
            flex("Row", [
                C("ia.input.button", "Btn", {
                    "text": title,
                    "style": {"classes": "ad-btn"},
                }, position=fixed("300px"),
                    events=on_action(
                        "AlarmDemo.demo.setScenario('%s')" % key),
                    binds={"props.style.classes": expr_bind(
                        "if({session.custom.scenario} = \"%s\", "
                        "\"ad-btn ad-btn-active\", \"ad-btn\")" % key)}),
                label("Desc", desc, classes="ad-muted",
                      style={"fontSize": "12.5px", "alignSelf": "center"},
                      position=grow(1)),
            ], gap=14, align="center", position=grow(1)),
            # 34, not 46: the button is 34 high and the description is one
            # line, so the other 12px was empty and seven of them added up to
            # a scrollbar on a list that fits.
        ], direction="column", position=fixed("34px"),
            binds={"props.style.display": expr_bind(vis)}))

    actions = flex("Actions", [
        C("ia.input.button", "AckAll", {
            "text": "Acknowledge all",
            "style": {"classes": "ad-btn ad-btn-primary"},
        }, position=fixed("170px"),
            events=on_action("AlarmDemo.demo.ackAll()")),
        C("ia.input.button", "Reset", {
            "text": "Reset plant",
            "style": {"classes": "ad-btn"},
        }, position=fixed("150px"),
            events=on_action("AlarmDemo.demo.reset()")),
        flex("Sp", [], position=grow(1)),
    ], gap=10, align="center", position=fixed("42px"))

    root = flex("root", [
        header(),
        flex("Body", [
            card("ScenarioCard", "Scenarios",
                 # A floor rather than a scrollbar: seven rows and six gaps
                 # always fit, so the only thing a short window can do is
                 # scroll the page - which is where a reader looks for it.
                 flex("List", buttons, direction="column", gap=3,
                      position=grow(1),
                      style={"minHeight": "%dpx" % (7 * 34 + 6 * 3)}),
                 # The card takes the page. It used to be sized to its content
                 # with a spacer underneath, which was right while a Gateway
                 # Setup card sat below it - that card is a screen of its own
                 # now, and what was left was two short cards at the top of an
                 # empty page. A card with room inside it reads as a card with
                 # room; a gap under two cards reads as something missing.
                 grow(1),
                 "Scenarios bias the simulation. Every alarm you see still "
                 "goes through the normal Ignition alarm pipeline - "
                 "evaluation, deadband, delay, priority and journal."),
            card("ActionsCard", "Actions", actions, fixed("100px", shrink=1)),
            # The build number, on screen. "Which build is this gateway
            # running?" was not answerable from the running demo, and a chart
            # bug that was actually a browser setting cost four rounds of
            # guessing partly because of it.
            label("Build", BUILD_TEXT,
                  classes="ad-faint", position=fixed("14px"),
                  style={"fontSize": "10.5px", "letterSpacing": "0.06em",
                         "textAlign": "right"}),
        ], direction="column", gap=12, classes="ad-body",
            style={"padding": "0 12px 12px 12px"}, position=grow(1)),
    ], direction="column", gap=12,
        classes="ad-page ad-root",
        style={"height": "100%", "overflowY": "auto"})
    root["children"][0]["position"] = fixed("64px")
    write("AlarmDemo/DemoControl", view(root))


# ---------------------------------------------------------------------------


def main():
    if os.path.isdir(VIEWS):
        shutil.rmtree(VIEWS)
    os.makedirs(VIEWS)
    w_tank()
    w_pump()
    w_stat()
    w_meter()
    w_machine()
    w_motor()
    w_prioritycell()
    w_statecell()
    v_nav()
    v_site_water()
    v_site_mfg()
    v_overview()
    v_status()
    v_journal()
    v_analytics()
    v_metrics()
    v_notifications()
    v_people()
    v_escalation_popup()
    v_democontrol()
    v_setup()
    n = sum(1 for _r, _d, fs in os.walk(VIEWS) if "view.json" in fs)
    print("generated %d views" % n)


if __name__ == "__main__":
    main()
