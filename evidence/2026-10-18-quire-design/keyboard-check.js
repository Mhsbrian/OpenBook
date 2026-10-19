// Keyboard consent / cancel / hide evidence for docs/quire-design (ANAL-215, ANAL-217 review item 2).
// usage: node keyboard-check.js <repo> <outdir>
const { chromium } = require('playwright'); const fs = require('fs'); const path = require('path');
const [repo, out] = process.argv.slice(2); fs.mkdirSync(out, { recursive: true });
const URL = 'file://' + path.join(repo, 'docs/quire-design/index.html');
const log = []; const say = (s) => { log.push(s); console.log(s); };
(async () => {
  const browser = await chromium.launch(process.env.CHROME ? { executablePath: process.env.CHROME, args: ['--no-sandbox'] } : {}); const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }});
  const page = await ctx.newPage(); const errors = []; page.on('pageerror', e => errors.push(String(e)));
  const focused = () => page.evaluate(() => { const a = document.activeElement; if (!a || a === document.body) return 'body'; return (a.tagName.toLowerCase() + (a.className ? '.' + String(a.className).trim().split(/\s+/).join('.') : '')) + ' "' + (a.getAttribute('aria-label') || a.textContent.trim().slice(0, 40)) + '"'; });
  const state = () => page.evaluate(() => { const P = window.QUIRE_PLAY; const tb = document.querySelector('.taskbar .tb-quire'); return { state: P.state, running: P.running, hidden: P.hidden, pending: !!P.pending, note: !!P.note, tbRunning: tb.classList.contains('running'), badge: tb.querySelector('.badge') ? tb.querySelector('.badge').textContent : null, ring: !!tb.querySelector('.ring'), tbLabel: tb.getAttribute('aria-label'), foot: P.note ? P.note.querySelector('.n-foot') && P.note.querySelector('.n-foot').textContent.trim() : null, result: P.note && P.note.querySelector('.result .msg') ? P.note.querySelector('.result .msg').textContent.trim() : null, lastTrace: P.trace.slice(-2) }; });
  const shot = (n) => page.screenshot({ path: path.join(out, n + '.png') });
  const show = async (label) => { const s = await state(); say(`${label}: focus=${await focused()} state=${JSON.stringify(s)}`); return s; };
  const open = async (text) => { await page.goto(URL + '?play=1'); await page.waitForTimeout(100); await page.keyboard.press('Alt+Space'); await page.waitForTimeout(400); await page.keyboard.type(text); await page.keyboard.press('Enter'); };
  const toConsent = async () => { await open('Turn on battery saver'); await page.waitForFunction(() => window.QUIRE_PLAY.state === 'consent'); await page.waitForTimeout(150); };

  say('== A. keyboard deny: Alt+Space, type, Enter → consent; Tab through the card; Enter on Don’t allow');
  await toConsent(); await show('consent arrived'); await shot('a1-consent-focus-card');
  for (let i = 1; i <= 5; i++) { await page.keyboard.press('Tab'); say(`Tab ${i}: ${await focused()}`); if (i === 1) await shot('a2-tab1-dont-allow'); }
  for (let i = 0; i < 5; i++) await page.keyboard.press('Shift+Tab');
  await page.keyboard.press('Tab'); say(`back at: ${await focused()}`); await page.keyboard.press('Enter'); await page.waitForTimeout(150);
  await show('after Enter on Don’t allow'); await shot('a3-denied');
  await page.keyboard.press('Escape'); await page.waitForTimeout(150); await show('Esc on the stopped note');

  say('== B. Esc at consent = cancel: answers the request cancelled, task not running, no badge');
  await toConsent(); await page.keyboard.press('Escape'); await page.waitForTimeout(150); await show('after Esc at consent'); await shot('b1-esc-at-consent');
  await page.keyboard.press('Escape'); await page.waitForTimeout(150); await show('second Esc closes');

  say('== C. keyboard allow (Tab ×2 → Allow for this session, Enter), then Esc mid-run: partial-effect copy');
  await toConsent(); await page.keyboard.press('Tab'); await page.keyboard.press('Tab'); say(`focus: ${await focused()}`); await page.keyboard.press('Enter');
  await page.waitForTimeout(1100); await show('mid-run after step 3'); await page.keyboard.press('Escape'); await page.waitForTimeout(150); await show('after Esc mid-run'); await shot('c1-stopped-mid-run');
  say(`result sub: ${await page.evaluate(() => window.QUIRE_PLAY.note.querySelector('.result small').textContent)}`);

  say('== D. hiding is separate: Alt+Space at consent hides; task keeps running; badge; Alt+Space reopens with focus on the card');
  await toConsent(); await page.keyboard.press('Alt+Space'); await page.waitForTimeout(300); await show('after Alt+Space (hidden)'); await shot('d1-hidden-badge');
  await page.keyboard.press('Escape'); await page.waitForTimeout(100); await show('Esc while hidden (no effect)');
  await page.keyboard.press('Alt+Space'); await page.waitForTimeout(300); await show('after Alt+Space (reopened)'); await shot('d2-reopened');
  await page.keyboard.press('Tab'); await page.keyboard.press('Tab'); await page.keyboard.press('Tab'); say(`Tab ×3: ${await focused()}`); await page.keyboard.press('Enter'); await page.waitForTimeout(2200); await show('allowed (Allow) → done');
  say('-- hide mid-run, let it finish hidden, reopen shows Done');
  await open('Turn on battery saver'); await page.waitForTimeout(600); await page.keyboard.press('Alt+Space'); await page.waitForTimeout(300); await show('hidden while working');
  await page.waitForFunction(() => window.QUIRE_PLAY.state === 'consent'); await page.waitForTimeout(100); await show('reached consent while hidden'); await shot('d3-hidden-needs-answer');

  say('== E. platform consent + mirror: Enter on Don’t allow stops; Allow → mirror; Tab to Stop; Enter');
  await open('In Settings, find Bluetooth and turn it off'); await page.waitForFunction(() => window.QUIRE_PLAY.state === 'sysconsent'); await page.waitForTimeout(150); await show('platform dialog'); await shot('e1-sysdialog-focus');
  await page.keyboard.press('Tab'); say(`Tab: ${await focused()}`); await page.keyboard.press('Enter'); await page.waitForTimeout(300); await show('mirror open');
  const names = []; for (let i = 0; i < 6; i++) { await page.keyboard.press('Tab'); names.push(await focused()); } say('Tab order in the mirror note: ' + names.join(' → '));
  await page.evaluate(() => document.querySelector('[data-act="pause"]').focus()); await page.keyboard.press('Enter'); await page.waitForTimeout(150); await show('paused (focus stays on Resume)'); await shot('e2-paused');
  await page.keyboard.press('Shift+Tab'); say(`Shift+Tab from Resume: ${await focused()}`); await page.keyboard.press('Enter'); await page.waitForTimeout(150); await show('after Enter on Stop'); await shot('e3-mirror-stopped');
  say('-- Esc in the mirror');
  await open('In Settings, find Bluetooth and turn it off'); await page.waitForFunction(() => window.QUIRE_PLAY.state === 'sysconsent'); await page.keyboard.press('Tab'); await page.keyboard.press('Enter'); await page.waitForTimeout(2800); await page.keyboard.press('Escape'); await page.waitForTimeout(150); await show('Esc during step 3 of the mirror'); say(`result sub: ${await page.evaluate(() => window.QUIRE_PLAY.note.querySelector('.result small').textContent)}`); await shot('e4-mirror-esc');
  say('-- Esc at the platform dialog');
  await open('In Settings, find Bluetooth and turn it off'); await page.waitForFunction(() => window.QUIRE_PLAY.state === 'sysconsent'); await page.keyboard.press('Escape'); await page.waitForTimeout(150); await show('Esc at platform dialog');

  say('== F. Esc on an idle note closes it; Esc while streaming stops');
  await page.goto(URL + '?play=1'); await page.keyboard.press('Alt+Space'); await page.waitForTimeout(300); await page.keyboard.press('Escape'); await page.waitForTimeout(150); await show('Esc on compose');
  await open('What can you do here?'); await page.waitForTimeout(1200); await page.keyboard.press('Escape'); await page.waitForTimeout(150); await show('Esc while streaming');

  say('== G. geometry: consent button row and mirror note height');
  for (const size of ['fhd', 'g14']) {
    const vp = size === 'g14' ? { width: 1920, height: 1200 } : { width: 1920, height: 1080 }; await page.setViewportSize(vp);
    await page.goto(URL + `?screen=consent&size=${size}`); await page.waitForTimeout(200);
    say(`${size} consent .btns rows: ` + await page.evaluate(() => { const bs = [...document.querySelectorAll('.card.consent .btns .btn')]; const tops = new Set(bs.map(b => Math.round(b.getBoundingClientRect().top))); return `${tops.size} row(s); widths ${bs.map(b => Math.round(b.getBoundingClientRect().width)).join('+')} in ${Math.round(document.querySelector('.card.consent .btns').getBoundingClientRect().width)}`; }));
    await page.goto(URL + `?screen=mirror&size=${size}`); await page.waitForTimeout(200);
    say(`${size} mirror note: ` + await page.evaluate(() => { const n = document.querySelector('.note.mirror'), v = document.querySelector('.mirror-view'); const H = document.querySelector('.artboard').clientHeight; return `note ${Math.round(n.offsetWidth)}×${Math.round(n.offsetHeight)} dp of ${H} (${(100 * n.offsetHeight / H).toFixed(0)} %); mirror view ${Math.round(v.clientWidth)}×${Math.round(v.clientHeight)} dp`; }));
  }
  say(`page errors: ${errors.length ? errors.join(' | ') : 'none'}`);
  fs.writeFileSync(path.join(out, 'keyboard-check.log'), log.join('\n') + '\n');
  await browser.close();
})();
