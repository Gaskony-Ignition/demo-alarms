"""
AlarmDemo.ui - glue the Perspective views need that is not about alarms.

Today that is one thing: the options for the theme picker in the sidebar.

The demo is a STANDALONE project with no style-pack parent, so every colour on
every screen resolves to one of Ignition's own Perspective theme variables (see
the project stylesheet's header comment). That is what makes a theme switch
work at all: the theme supplies the values, this project only names them.
"""

LOG = system.util.getLogger("AlarmDemo.ui")

# light and dark live inside the Perspective module's own jar and never appear
# as config resources, so the stock set is a fixed base rather than something
# read from the gateway. Order is Ignition's own.
STOCK_THEMES = [u"light", u"light-warm", u"light-cool",
                u"dark", u"dark-warm", u"dark-cool"]


def themeOptions():
    """Options for the sidebar's theme dropdown: Ignition's six stock themes,
    then every custom theme installed on this gateway, alphabetical.

    Custom themes are config resources under
    `com.inductiveautomation.perspective/themes`, so a theme pack installed
    while the demo is running appears the next time a session starts - nothing
    here needs a release. If the listing fails for any reason the dropdown
    still offers the stock six, because a demo that cannot pick a theme is
    worse than one that cannot see the custom ones.
    """
    from java.lang import Throwable as JThrowable
    extra = []
    try:
        for res in system.config.getResources(
                moduleId="com.inductiveautomation.perspective", typeId="themes"):
            name = unicode(res.getName())
            if name not in STOCK_THEMES and name not in extra:
                extra.append(name)
    except (JThrowable, Exception) as e:
        LOG.warn(u"theme listing failed, offering the stock themes only: %s" % e)
    return [{u"value": n, u"label": n.replace(u"-", u" ").capitalize()}
            for n in STOCK_THEMES + sorted(extra)]
