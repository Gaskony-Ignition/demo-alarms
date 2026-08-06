-- Alarm demo journal tables.
--
-- You do NOT normally need to run this: Ignition creates both tables itself the
-- first time the alarm journal profile writes an event. It is here so the demo
-- can be stood up on a fresh database in one step, and so the schema the
-- backfill writes into is written down somewhere.
--
-- The table names are Ignition's own defaults for a datasource alarm journal.
-- Nothing in this project depends on a prefix, so a gateway that already has an
-- alarm journal can point this profile at the existing tables and the history
-- simply merges.

CREATE TABLE IF NOT EXISTS alarm_events (
    id          SERIAL,
    eventid     VARCHAR(255),
    source      VARCHAR(255),
    displaypath VARCHAR(255),
    priority    INTEGER,
    eventtype   INTEGER,   -- 0 = active, 1 = cleared, 2 = acknowledged
    eventflags  INTEGER,
    eventtime   TIMESTAMP NOT NULL,
    PRIMARY KEY (id, eventtime)
);

CREATE TABLE IF NOT EXISTS alarm_event_data (
    id         INTEGER,
    propname   VARCHAR(255),
    dtype      INTEGER,
    intvalue   BIGINT,
    floatvalue DOUBLE PRECISION,
    strvalue   TEXT
);

CREATE INDEX IF NOT EXISTS "alarm_event_dataidndx"
    ON alarm_event_data (id);

-- The analytics screens filter on eventtype and scan by time; without this the
-- 30-day Pareto does a sequential scan every refresh.
CREATE INDEX IF NOT EXISTS alarm_events_time_type_idx
    ON alarm_events (eventtime, eventtype);
