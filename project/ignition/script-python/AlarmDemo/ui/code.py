"""AlarmDemo.ui - view glue that is not about alarms: the sidebar theme picker's options."""

LOG = system.util.getLogger("AlarmDemo.ui")

# The stock themes live inside the Perspective jar, not as config resources,
# so they cannot be listed from the gateway.
STOCK_THEMES = [u"light", u"light-warm", u"light-cool",
				u"dark", u"dark-warm", u"dark-cool"]


def themeOptions():
	"""Theme dropdown options: the six stock themes, then installed custom themes A to Z.

	If the custom listing fails, the stock six are still returned.
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
