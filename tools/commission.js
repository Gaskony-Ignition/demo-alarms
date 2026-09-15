// Commission a fresh Ignition 8.3 gateway, headlessly, choosing its EDITION.
//
//   node commission.js http://localhost:8588 admin password 'Edge Edition'
//   node commission.js http://localhost:8488 admin password 'Ignition'
//
// The edition is NOT an environment variable and NOT a file you can write - it
// is the first step of the commissioning wizard, and the docker image has no
// setting for it. That is the whole reason this exists: without it, "a real
// Edge gateway" is a manual browser step nobody repeats, and the Edge claim
// goes untested.
//
// With ACCEPT_IGNITION_EULA and the admin credentials passed as environment
// variables to the container, the wizard is only TWO clicks: the edition, then
// "Start Gateway". Both post to /post-step. Takes about 40 seconds.
// Playwright is not vendored here: point PLAYWRIGHT at an install, or
// run this from a directory that has one.
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright');

const URL = process.argv[2] || 'http://localhost:8588';
const USER = process.argv[3] || 'admin';
const PASS = process.argv[4] || 'password';
// Which edition button to press on the first wizard step: 'Edge Edition',
// 'Ignition' (the standard platform) or 'Maker Edition'.
const EDITION = process.argv[5] || 'Edge Edition';

(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({
    // The wizard refuses an unrecognised browser, and a headless Chromium
    // sends no userAgentData - so it says "Browser Not Supported" and hides
    // the step it was about to show.
    userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 ' +
               '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
  });
  const p = await ctx.newPage();
  const posts = [];
  p.on('request', r => { if (r.method() !== 'GET') posts.push(r.method() + ' ' + r.url()); });

  await p.goto(URL + '/welcome', { waitUntil: 'networkidle' });
  await p.waitForTimeout(1500);

  for (let step = 0; step < 14; step++) {
    const text = (await p.evaluate(() => document.body.innerText)).replace(/\n+/g, ' | ');
    const btns = await p.$$eval('button', els =>
      els.map(e => (e.innerText || '').trim()).filter(Boolean));
    console.log(`[${step}] ${text.slice(0, 220)}`);
    console.log(`     buttons: ${JSON.stringify(btns)}`);

    // password fields, if this step wants credentials
    const pw = await p.$$('input[type=password]');
    if (pw.length) {
      const user = await p.$('input[type=text]:not([disabled])');
      if (user) await user.fill(USER).catch(() => {});
      for (const f of pw) await f.fill(PASS).catch(() => {});
    }

    const order = [EDITION, 'Accept', 'I Accept', 'Next', 'Continue',
                   'Finish', 'Start Gateway', 'Submit', 'Save'];
    let clicked = null;
    for (const want of order) {
      const el = await p.$(`button:has-text("${want}")`);
      if (el && await el.isEnabled().catch(() => false)) { await el.click(); clicked = want; break; }
    }
    if (!clicked) { console.log('     (nothing to click - stopping)'); break; }
    console.log(`     -> clicked "${clicked}"`);
    await p.waitForTimeout(2500);
  }

  console.log('--- NON-GET REQUESTS ---');
  console.log(posts.join('\n'));
  await b.close();
})();
