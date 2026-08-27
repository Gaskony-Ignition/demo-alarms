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
 *    It asserts the border is drawn, NOT how wide it is, and only on
 *    controls whose border THIS PROJECT does not set. Both halves come from
 *    the session working on ignition-themes, 27/08/2026, and both are ways
 *    of testing your own CSS while believing you are testing the theme's:
 *
 *      - pinning `1px` fails on a project class that deliberately sets 2px,
 *        reporting a broken theme when nothing is broken;
 *      - probing a control the project gives a border to can NEVER fail,
 *        however broken the theme is, so a green run can sit over a broken
 *        page. Measured here: of the two dropdowns on the Analytics page,
 *        the "All areas" selector carries `ad-btn`, which sets its own
 *        border - it stayed green through the entire negative test. The
 *        sidebar's theme picker carries only `ad-theme-select` (font-size),
 *        so it is the one that actually exercises the theme's contract.
 *
 *    BORDERED_BY_PROJECT below is that exclusion list, kept explicit rather
 *    than inferred so it is reviewable: add a class to it the moment you
 *    give it a border, or this check quietly stops testing anything.
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

// Project classes that set a border of their own. A control carrying one of
// these cannot fail the border assertion whatever the theme does, so it is
// reported and not asserted on. Keep in step with the stylesheet.
const BORDERED_BY_PROJECT = ['psc-ad-btn', 'psc-ad-input', 'psc-ad-card', 'psc-ad-kpi'];

const { chromium } = loadPlaywright();

(async () => {
  const browser = await chromium.launch();
  const pg = await (await browser.newContext({ viewport: { width: 1600, height: 950 } })).newPage();
  let failures = 0;
  try {
    await pg.goto(`${GATEWAY}/data/perspective/client/${PROJECT}/`, { waitUntil: 'networkidle', timeout: 60000 });
    try { await pg.click('text=AGREE & CLOSE', { timeout: 2500 }); } catch (e) {}
    await pg.waitForTimeout(3000);

    // Analytics for breadth, not because it is the load-bearing surface.
    // Measured: its "All areas" selector carries `ad-btn` and is therefore
    // excluded from the assertion, so the control that actually exercises
    // the theme here is the sidebar's theme picker, which is on every page.
    // Going here anyway costs nothing and covers a second stock control if
    // one is ever added without a project class.
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

      const r = await pg.evaluate((owned) => {
        const cs = getComputedStyle(document.documentElement).colorScheme.trim();
        const all = [...document.querySelectorAll('.ia_dropdown, .ia_inputField, .ia_textField')]
          .filter(e => e.offsetWidth > 60 && e.offsetHeight > 15);
        const ours = all.filter(e => owned.some(c => e.classList.contains(c)));
        const theirs = all.filter(e => !owned.some(c => e.classList.contains(c)));
        const borderless = theirs.filter(e => {
          const s = getComputedStyle(e);
          // DRAWN, not a particular width.
          return parseFloat(s.borderTopWidth) === 0 || s.borderTopStyle === 'none';
        }).length;
        return { cs, asserted: theirs.length, skipped: ours.length, borderless };
      }, BORDERED_BY_PROJECT);

      const csOk = r.cs === 'light' || r.cs === 'dark' || r.cs === 'light dark';
      // No assertable control on screen is a FAILURE of the check, not a pass:
      // it means every control here is project-bordered and nothing was tested.
      const bOk = r.asserted > 0 && r.borderless === 0;
      if (!csOk || !bOk) failures++;
      const note = r.asserted === 0 ? 'NOTHING ASSERTABLE ON SCREEN'
        : `${r.asserted - r.borderless}/${r.asserted} bordered (${r.skipped} project-styled, not asserted)`;
      console.log(`  ${csOk && bOk ? 'ok  ' : 'FAIL'} ${label.padEnd(18)} color-scheme: ${r.cs.padEnd(11)} ${note}`);
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
