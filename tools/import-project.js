#!/usr/bin/env node
/*
 * Import the packaged project zip onto a gateway through its own web UI,
 * headlessly - the same Config -> Platform -> Projects -> Import Project a
 * person would use, driven rather than described.
 *
 * It exists so that "importing this zip onto a gateway that has never seen it
 * works" is something the repo can PROVE on demand, not something a README
 * asserts. That is the whole claim of a standalone project.
 *
 *   node tools/import-project.js --gateway module-testing \
 *        --zip dist/Alarm_Demo-2.0.0.zip --name AlarmDemo [--overwrite]
 *
 * Credentials come from the same 0600 stanza file the toolkit's scan tool
 * uses (<gateway>.url / .user / .password), never from argv - argv is readable
 * by every process on the host.
 *
 * Import dialog specifics, all learned the hard way and none of them guessable:
 *   * there is no [role=dialog] - the modal is .MuiModal-root, and a loosely
 *     scoped `input` selector matches the page BEHIND the backdrop, so the
 *     click times out instead of failing usefully;
 *   * the project-name box is a React controlled input, so fill() sets the DOM
 *     value without firing the events React listens for: the field looks
 *     filled, the component's state stays empty, and Import stays disabled.
 *     pressSequentially() types it properly;
 *   * Allow Overwrite is a full resource-level REPLACE - any resource type the
 *     zip does not carry is deleted from the target. Left off, an import onto
 *     an existing name is refused outright, which is the safe default.
 */
const fs = require('fs');
const path = require('path');

function loadPlaywright() {
  const bases = ['/Home-Claude/ignition-claude-toolkit', '/claude/ignition-claude-toolkit'];
  const candidates = [null];
  for (const b of bases) {
    candidates.push(path.join(b, 'plugins/ignition/skills/verify-view/tool/node_modules/playwright'));
    candidates.push(path.join(b, 'plugins/ignition/skills/scan/tool/node_modules/playwright'));
  }
  for (const c of candidates) {
    try { return c ? require(c) : require('playwright'); } catch (e) { /* next */ }
  }
  console.error('import: playwright not found');
  process.exit(2);
}

const arg = (n) => { const i = process.argv.indexOf('--' + n); return i > -1 ? process.argv[i + 1] : undefined; };
const has = (n) => process.argv.indexOf('--' + n) > -1;

const CREDS = arg('creds') || process.env.IGNITION_SCAN_CREDS
  || '/Home-Claude/secrets/ignition-gateways.env';
const NAME = arg('gateway');
const ZIP = path.resolve(arg('zip') || '');
const PROJECT = arg('name') || 'AlarmDemo';
const OVERWRITE = has('overwrite');
const STEP = parseInt(process.env.TIMEOUT_MS || '20000', 10);

let url = arg('url'), user, pass;
if (fs.existsSync(CREDS) && NAME) {
  const kv = {};
  for (const line of fs.readFileSync(CREDS, 'utf8').split('\n')) {
    const i = line.indexOf('=');
    if (i > 0 && !line.trim().startsWith('#')) kv[line.slice(0, i).trim()] = line.slice(i + 1).trim();
  }
  url = url || kv[`${NAME}.url`];
  user = kv[`${NAME}.user`];
  pass = kv[`${NAME}.password`];
}
if (!url || !user || !pass) { console.error(`import: no url/credentials for "${NAME}" in ${CREDS}`); process.exit(2); }
if (!fs.existsSync(ZIP)) { console.error(`import: no such zip: ${ZIP}`); process.exit(2); }
url = url.replace(/\/+$/, '');

const { chromium } = loadPlaywright();

(async () => {
  const browser = await chromium.launch({ headless: !process.env.HEADFUL });
  const pg = await (await browser.newContext({ viewport: { width: 1500, height: 1100 } })).newPage();
  let code = 1;
  try {
    await pg.goto(`${url}/web/home`, { waitUntil: 'networkidle', timeout: 30000 });

    // Login is TWO pages: username, Enter, then the password field appears.
    await pg.click('text=Log In', { timeout: STEP });
    const u = pg.locator('input').first();
    await u.waitFor({ state: 'visible', timeout: STEP });
    await u.fill(user); await u.press('Enter');
    const p = pg.locator('input[type="password"]').first();
    await p.waitFor({ state: 'visible', timeout: STEP });
    await p.fill(pass); await p.press('Enter');
    await pg.waitForLoadState('networkidle', { timeout: STEP }).catch(() => {});

    await pg.click('text=Platform', { timeout: STEP });
    await pg.click('text=Projects', { timeout: STEP });
    await pg.waitForLoadState('networkidle', { timeout: STEP }).catch(() => {});

    await pg.click('button:has-text("Import Project")', { timeout: STEP });
    const modal = pg.locator('.MuiModal-root').last();
    await modal.waitFor({ state: 'visible', timeout: STEP });

    await modal.locator('#project-file-id-input').setInputFiles(ZIP);
    const nameBox = modal.locator('#project-name-id-input');
    await nameBox.click();
    await nameBox.fill('');
    await nameBox.pressSequentially(PROJECT, { delay: 25 });
    if (OVERWRITE) await modal.locator('#allow-overwrite-id').click();

    await pg.waitForTimeout(500);
    const btn = modal.locator('button:has-text("Import")').last();
    if (await btn.isDisabled()) throw new Error('the Import button stayed disabled - the name or the file did not register');
    await btn.click({ timeout: STEP });

    for (let i = 0; i < 60; i++) {
      if (!(await modal.isVisible().catch(() => false))) { code = 0; break; }
      await pg.waitForTimeout(1000);
    }
    if (code === 0) {
      await pg.waitForTimeout(2000);
      const listed = await pg.locator(`text=${PROJECT}`).count();
      console.log(`import: ${path.basename(ZIP)} -> ${PROJECT} on ${NAME} (${url}); listed=${listed > 0}`);
    } else {
      const shot = `/tmp/import-stuck-${PROJECT}.png`;
      await pg.screenshot({ path: shot });
      console.error(`import: the dialog never closed - screenshot at ${shot}`);
    }
  } catch (e) {
    const shot = `/tmp/import-error-${PROJECT}.png`;
    try { await pg.screenshot({ path: shot }); } catch (_) {}
    console.error('import: FAILED -', e.message.split('\n')[0], `(screenshot at ${shot})`);
  } finally {
    await browser.close();
  }
  process.exit(code);
})();
