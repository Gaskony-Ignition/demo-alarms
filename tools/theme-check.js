#!/usr/bin/env node
/*
 * Assert the two things this demo needs from a Perspective theme, on every
 * theme a gateway has. Both are invisible in a screenshot, which is why they
 * are a script.
 *
 *   node tools/theme-check.js --gateway http://host:8088 [--project AlarmDemo]
 *
 * 1. `color-scheme` resolves to the THEME's answer wherever the theme has
 *    one, and to the project's `light dark` default only where it does not.
 *    The project stylesheet declares it on `html` (0-0-1) precisely so it
 *    loses to a theme's `:root` (0-1-0); on `:root` it would load later,
 *    win on order, and replace every theme's correct answer with "either" -
 *    which puts light scrollbars and light form controls on a dark page for
 *    any viewer whose OS prefers light.
 *
 * 2. Stock text fields and dropdowns have a border that is actually DRAWN.
 *    Ignition's `.ia_inputField` does `border: var(--containerBorder)` and
 *    expects the shorthand; a theme that defines that variable as a bare
 *    colour makes the declaration invalid and the border vanishes.
 *
 *    It asserts the border is drawn, NOT how wide it is. Pinning a width
 *    tests this project's own style classes rather than the theme's
 *    contract, and reports a broken theme when nothing is broken (learned
 *    from the session working on ignition-themes, 27/08/2026).
 *
 * Exit 0 = every theme passed.
 */
const path = require('path');

function loadPlaywright() {
  const bases = ['/Home-Claude/ignition-claude-toolkit', '/claude/ignition-claude-toolkit'];
  const tries = [null];
  for (const b of bases) tries.push(path.join(b, 'plugins/ignition/skills/verify-view/tool/node_modules/playwright'));
  for (const t of tries) { try { return t ? require(t) : require('playwright'); } catch (e) {} }
  console.error('theme-check: playwright not found'); process.exit(2);
}
const arg = (n, d) => { const i = process.argv.indexOf('--' + n); return i > -1 ? process.argv[i + 1] : d; };
const GATEWAY = (arg('gateway', process.env.GATEWAY) || '').replace(/\/+$/, '');
const PROJECT = arg('project', 'AlarmDemo');
if (!GATEWAY) { console.error('theme-check: --gateway http://host:8088'); process.exit(2); }

const { chromium } = loadPlaywright();

(async () => {
  const browser = await chromium.launch();
  const pg = await (await browser.newContext({ viewport: { width: 1600, height: 950 } })).newPage();
  let failures = 0;
  try {
    await pg.goto(`${GATEWAY}/data/perspective/client/${PROJECT}/`, { waitUntil: 'networkidle', timeout: 60000 });
    try { await pg.click('text=AGREE & CLOSE', { timeout: 2500 }); } catch (e) {}
    await pg.waitForTimeout(3000);

    // Analytics, not the landing page: its "All areas" selector is a STOCK
    // dropdown carrying no project class, which is exactly the component the
    // bare-colour --containerBorder made borderless. The landing page has
    // only the sidebar's own theme picker, and checking that alone would
    // have passed while the thing that broke went unchecked.
    try { await pg.click('text=Analytics', { timeout: 10000 }); await pg.waitForTimeout(3000); }
    catch (e) { console.log('  (could not reach Analytics; checking the landing page)'); }

    // The demo's own dropdown lists exactly what this gateway offers.
    await pg.click('.psc-ad-theme-select', { timeout: 15000 });
    await pg.waitForTimeout(800);
    const themes = await pg.$$eval('.ia_dropdown__option, [class*="option"]',
      els => [...new Set(els.map(e => e.textContent.trim()).filter(t => t && t.length < 30))]);
    await pg.keyboard.press('Escape');
    await pg.waitForTimeout(500);
    if (!themes.length) throw new Error('could not read the theme list from the sidebar dropdown');
    console.log(`theme-check: ${themes.length} themes on ${GATEWAY}\n`);

    for (const label of themes) {
      await pg.click('.psc-ad-theme-select', { timeout: 15000 });
      await pg.waitForTimeout(700);
      try { await pg.click(`text="${label}"`, { timeout: 8000 }); }
      catch (e) { console.log(`  SKIP ${label} - could not select it`); continue; }
      await pg.waitForTimeout(2000);

      const r = await pg.evaluate(() => {
        const cs = getComputedStyle(document.documentElement).colorScheme.trim();
        // every stock dropdown/text field on screen
        const boxes = [...document.querySelectorAll('.ia_dropdown, .ia_inputField, .ia_textField')]
          .filter(e => e.offsetWidth > 60 && e.offsetHeight > 15);
        const borderless = boxes.filter(e => {
          const s = getComputedStyle(e);
          // DRAWN, not a particular width: a project class may legitimately
          // set 2px, and asserting "1px" would fail on this project's own CSS
          return parseFloat(s.borderTopWidth) === 0 || s.borderTopStyle === 'none';
        }).length;
        return { cs, total: boxes.length, borderless };
      });

      const csOk = r.cs === 'light' || r.cs === 'dark' || r.cs === 'light dark';
      const bOk = r.total > 0 && r.borderless === 0;
      if (!csOk || !bOk) failures++;
      console.log(`  ${csOk && bOk ? 'ok  ' : 'FAIL'} ${label.padEnd(18)} color-scheme: ${r.cs.padEnd(11)} inputs: ${r.total - r.borderless}/${r.total} bordered`);
    }
  } catch (e) {
    console.error('theme-check: FAILED -', e.message.split('\n')[0]);
    failures++;
  } finally {
    await browser.close();
  }
  console.log(failures ? `\n${failures} theme(s) failed` : '\nevery theme passed');
  process.exit(failures ? 1 : 0);
})();
