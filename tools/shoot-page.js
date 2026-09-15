// ONE Perspective page per browser, because Ignition Edge caps concurrent
// sessions and every fresh navigation to a project page takes another one.
// A verification run that opens four pages at once fails with "Sessions
// Exceeded" and tells you nothing about the pages.
// Playwright is not vendored here: point PLAYWRIGHT at an install, or
// run this from a directory that has one.
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright');
(async () => {
  const [base, project, out, path] = process.argv.slice(2);
  const b = await chromium.launch();
  const p = await (await b.newContext({ viewport: { width: 1600, height: 900 } })).newPage();
  const errs = [];
  p.on('console', m => { if (m.type() === 'error') errs.push(m.text().slice(0, 160)); });
  await p.goto(`${base}/data/perspective/client/${project}${path}`,
               { waitUntil: 'networkidle', timeout: 45000 });
  // The page paints before its websocket is up and wears a "No Connection to
  // Gateway" banner until it is - so a screenshot taken on a fixed timer
  // catches a real page in a transient state that looks like a fault.
  // Match the VISIBLE banner, not the text: the element stays in the DOM after
  // the websocket connects, so innerText still carries the words on a page
  // that is rendering perfectly.
  const banner = p.locator('text=No Connection to Gateway').first();
  for (let i = 0; i < 30; i++) {
    if (!(await banner.isVisible().catch(() => false))) break;
    await p.waitForTimeout(1000);
  }
  await p.waitForTimeout(Number(process.env.SETTLE_MS || 8000));
  await p.screenshot({ path: out });
  const txt = (await p.evaluate(() => document.body.innerText)).replace(/\n+/g, ' | ');
  console.log(`${path}: ${txt.slice(0, 200)}`);
  if (errs.length) console.log('  console errors: ' + [...new Set(errs)].slice(0, 3).join(' ; '));
  await b.close();
})();
