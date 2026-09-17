// Fail on containers that scroll by a hair.
//
//   node tools/layout-check.js --gateway fresh [--project AlarmDemo]
//
// WHY THIS EXISTS. Perspective writes a flex position as a fixed pixel height
// and the box is border-box, so padding AND borders come out of the content
// area. Get the arithmetic one pixel wrong and Chromium answers with a full
// scrollbar down the side of the element - a decorative container that has
// nothing to scroll to, wearing a scroll rail. It looks like a styling bug and
// it is an arithmetic bug, and nothing on the server can see it: the JSON is
// right, the props are right, and only the rendered box model disagrees.
//
// It has now happened three times in this project - the brand row (24, not 22),
// the alarm count (36, not 30) and the theme picker (57, not 56, where the
// pixel went to a border-top). Each was found by a human noticing a scrollbar
// in a screenshot. This finds them by measuring.
//
// THE THRESHOLD IS THE WHOLE IDEA. Real scrollers overflow by a lot - a table
// of 30 rows, a page of content. Layout bugs overflow by one to a few pixels.
// So anything overflowing by MORE than the threshold is left alone (this
// project deliberately lets tables scroll rather than paginate), and anything
// overflowing by 1..threshold is a defect.

const fs = require('fs');
const path = require('path');

function loadPlaywright() {
  const roots = [
    '/home/nigel/Ignition-Work/water-suite/node_modules',
    '/Home-Claude/ignition-claude-toolkit/plugins/ignition/skills/verify-view/tool/node_modules',
    path.join(__dirname, '..', 'node_modules'),
  ];
  for (const r of roots) { try { return require(path.join(r, 'playwright')); } catch (e) {} }
  return require('playwright');
}
const { chromium } = loadPlaywright();

const arg = (n, d) => {
  const i = process.argv.indexOf('--' + n);
  return i > -1 ? process.argv[i + 1] : d;
};

const CREDS = arg('creds') || process.env.IGNITION_SCAN_CREDS
  || '/Home-Claude/secrets/ignition-gateways.env';
const NAME = arg('gateway', 'fresh');
const PROJECT = arg('project', 'AlarmDemo');
const THRESHOLD = parseInt(arg('threshold', '4'), 10);

let url = arg('url');
if (!url) {
  const kv = {};
  for (const line of fs.readFileSync(CREDS, 'utf8').split('\n')) {
    const m = line.match(/^([^=]+)=(.*)$/);
    if (m) kv[m[1].trim()] = m[2].trim();
  }
  url = kv[`${NAME}.url`];
}
if (!url) { console.error(`layout-check: no url for "${NAME}"`); process.exit(2); }
url = url.replace(/\/+$/, '');

const PAGES = ['/', '/status', '/journal', '/metrics', '/analytics',
               '/notifications', '/people', '/demo', '/setup'];

// Two sidebar states: the rail hides the theme picker and gives its height
// back to the footer, which is its own piece of arithmetic to get wrong.
const NAV_STATES = [
  { label: 'sidebar open', collapse: false },
  { label: 'sidebar collapsed', collapse: true },
];

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
  const findings = [];

  for (const state of NAV_STATES) {
    for (const p of PAGES) {
      const pg = await ctx.newPage();
      try {
        await pg.goto(`${url}/data/perspective/client/${PROJECT}${p}`,
                      { waitUntil: 'networkidle', timeout: 60000 });
        await pg.waitForTimeout(4500);
        if (state.collapse) {
          const toggle = pg.locator('.psc-ad-nav-toggle').first();
          if (await toggle.count()) { await toggle.click(); await pg.waitForTimeout(1200); }
        }
        const hits = await pg.evaluate((limit) => {
          const out = [];
          document.querySelectorAll('*').forEach(e => {
            if (!e.clientHeight && !e.clientWidth) return;
            const cs = getComputedStyle(e);
            const scrolls = (a) => a === 'auto' || a === 'scroll';
            const dy = e.scrollHeight - e.clientHeight;
            const dx = e.scrollWidth - e.clientWidth;
            if (dy > 0 && dy <= limit && scrolls(cs.overflowY)) {
              out.push({ axis: 'y', by: dy, cls: (e.className || '').toString().slice(0, 80) });
            }
            if (dx > 0 && dx <= limit && scrolls(cs.overflowX)) {
              out.push({ axis: 'x', by: dx, cls: (e.className || '').toString().slice(0, 80) });
            }
          });
          return out;
        }, THRESHOLD);
        for (const h of hits) findings.push({ page: p, state: state.label, ...h });
        console.log(`${hits.length ? 'FAIL' : 'ok  '}  ${state.label.padEnd(17)} ${p}`);
      } catch (e) {
        console.log(`ERR   ${state.label.padEnd(17)} ${p}  ${e.message.split('\n')[0]}`);
        findings.push({ page: p, state: state.label, axis: '-', by: 0, cls: 'page failed to load' });
      }
      await pg.close();
    }
  }

  await browser.close();

  if (!findings.length) {
    console.log(`\nno element overflows by 1..${THRESHOLD}px - nothing wears a scrollbar it cannot use`);
    process.exit(0);
  }
  console.log(`\n${findings.length} hairline overflow(s) - each one draws a scrollbar:\n`);
  for (const f of findings) {
    console.log(`  ${f.page} (${f.state})  ${f.axis} by ${f.by}px  .${f.cls.split(' ').join(' .')}`);
  }
  console.log(`\nThe basis is a BORDER-BOX height: padding and border come out of it.`);
  process.exit(1);
})();
