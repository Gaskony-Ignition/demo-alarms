// Measure the Setup screen, and screenshot it, in ONE Perspective session.
//
//   PLAYWRIGHT=<path> node tools/verify-setup.js http://host:8588 Edge out.png
//
// TWO things this exists for.
//
// One: Ignition Edge caps concurrent Perspective sessions and every page load
// takes one, so a verification that opens a page to measure and another to
// photograph it does not get two answers - it gets "Sessions Exceeded", which
// looks nothing like a session limit and tells you nothing about the screen.
//
// Two: `innerText` is NOT a visibility test. For an element that is not being
// rendered it falls back to textContent, so a `display: none` button reads as
// present and a hidden card reads as showing. Ask getComputedStyle instead.
// That mistake reported a Rebuild button on an Edge gateway that was not on
// the screen at all.
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright');

const TITLES = ["Edge visualization module", "Database connection",
                "Tag provider", "Plant tags", "Journal tables",
                "Alarm journal profile", "Shift schedules", "People",
                "On-call rosters", "30 days of history"];

(async () => {
  const [base, project, out] = process.argv.slice(2);
  const b = await chromium.launch();
  const p = await (await b.newContext({ viewport: { width: 1600, height: 900 } })).newPage();
  await p.goto(`${base}/data/perspective/client/${project}/setup`,
               { waitUntil: 'networkidle', timeout: 45000 });
  const banner = p.locator('text=No Connection to Gateway').first();
  for (let i = 0; i < 30; i++) {
    if (!(await banner.isVisible().catch(() => false))) break;
    await p.waitForTimeout(1000);
  }
  await p.waitForTimeout(Number(process.env.SETTLE_MS || 10000));

  const res = await p.evaluate((titles) => {
    const shown = (el) => {
      if (!el) return false;
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    };
    const smallestWith = (text) => {
      const hits = [...document.querySelectorAll('*')].filter(
        e => e.children.length === 0 && (e.textContent || '').trim() === text);
      return hits.length ? hits[hits.length - 1] : null;
    };
    const o = { viewport: window.innerHeight, rows: [], visible: {} };
    for (const t of titles) {
      const el = smallestWith(t);
      if (!el) { o.rows.push({ title: t, present: false }); continue; }
      let row = el;
      for (let k = 0; k < 4 && row.parentElement; k++) {
        if ((row.textContent || '').split(t)[1]) break;
        row = row.parentElement;
      }
      const r = row.getBoundingClientRect();
      o.rows.push({ title: t, present: shown(el), top: Math.round(r.top),
                    bottom: Math.round(r.bottom) });
    }
    o.visible.rebuildButton = shown(smallestWith('Rebuild 30-day history'));
    o.visible.setUpButton = shown(smallestWith('Set up this gateway'));
    // The card's own heading, which the demo renders in upper case, versus the
    // checklist row of the same name.
    const heads = [...document.querySelectorAll('*')].filter(
      e => e.children.length === 0
           && (e.textContent || '').trim().toLowerCase() === 'database connection');
    o.visible.databaseCardHeadings = heads.filter(shown).length;
    return o;
  }, TITLES);

  const seen = res.rows.filter(r => r.present);
  const clipped = seen.filter(r => r.bottom > res.viewport);
  console.log(`rows visible: ${seen.length}/${TITLES.length}` +
              `  (absent: ${res.rows.filter(r => !r.present).map(r => r.title).join(', ') || 'none'})`);
  console.log(`rows clipped by the viewport: ${clipped.length}` +
              (clipped.length ? ' -> ' + clipped.map(r => r.title).join(', ') : ''));
  console.log('visible controls:', JSON.stringify(res.visible));
  if (out) { await p.screenshot({ path: out }); console.log('shot:', out); }
  await b.close();
  process.exit(clipped.length ? 1 : 0);
})();
