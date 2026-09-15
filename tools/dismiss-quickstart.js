// Dismiss the "Enable Quick Start" modal a fresh standard gateway shows.
// Its scrim covers the whole page, so every headless click - including the
// scan tool's "Log In" - times out on an element that is plainly visible.
// Playwright is not vendored here: point PLAYWRIGHT at an install, or
// run this from a directory that has one.
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright');
(async () => {
  const b = await chromium.launch();
  const p = await (await b.newContext({ viewport: { width: 1500, height: 1100 } })).newPage();
  await p.goto((process.argv[2] || 'http://localhost:8688') + '/web/home',
               { waitUntil: 'networkidle', timeout: 30000 });
  await p.waitForTimeout(2000);
  const no = p.locator('button:has-text("No thanks")').first();
  if (await no.isVisible().catch(() => false)) {
    await no.click();
    console.log('quickstart: dismissed');
    await p.waitForTimeout(2500);
  } else {
    console.log('quickstart: no modal');
  }
  await b.close();
})();
