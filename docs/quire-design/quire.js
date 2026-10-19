/* Quire design prototype (ANAL-215, revised by ANAL-227: glass and ink). Renders every state of the note as static
   screens (gallery, single screen) and runs the clickable prototype (?play=1). Motion tokens here are the ones in
   docs/quire-design.md §5. */
'use strict';

/* ------------------------------------------------------------------------------------------ tokens (motion) */
const MOTION = {
  // springs: stiffness (N/m) and damping ratio, as Compose spring() / SpringForce take them
  spring: {
    unfold:  { stiffness: 380,  damping: 0.80 },  // note out of the pointer; one gentle overshoot
    settle:  { stiffness: 700,  damping: 0.90 },  // reflow when content grows, agent picker, tray
    expand:  { stiffness: 300,  damping: 0.85 },  // note → mirror and back
    fold:    { stiffness: 900,  damping: 1.00 },  // note → pointer or taskbar; no overshoot
    tick:    { stiffness: 1400, damping: 0.70 },  // halo bloom, taskbar press
  },
  // fixed durations (ms) for fades and non-spatial changes; easing from Material 3
  halo: 90, tick: 160, fade: 120, fadeSlow: 200,
  // the pen (§5.1): the sheet unrolls from the pen tip, the rim lights up, a word arrives, the rule is drawn, a tick is drawn
  unroll: 220, rim: 200, ink: 160, inkStagger: 24, rule: 240, draw: 180, unwrite: 160,
  easing: { standard: 'cubic-bezier(.2,0,0,1)', decel: 'cubic-bezier(.05,.7,.1,1)', accel: 'cubic-bezier(.3,0,.8,.15)' },
};

/* ------------------------------------------------------------------------------------------ helpers */
const qs = new URLSearchParams(location.search);
const h = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
const ms = (name, cls = '') => `<span class="ms ${cls}" aria-hidden="true">${name}</span>`;
const LEAF = `<svg class="leaf" viewBox="0 0 24 24" aria-hidden="true"><path d="M7.5 3H14l6 6v8.5A3.5 3.5 0 0 1 16.5 21h-9A3.5 3.5 0 0 1 4 17.5v-11A3.5 3.5 0 0 1 7.5 3Z" fill="url(#leafA)"/><path d="M14 3v4.5A1.5 1.5 0 0 0 15.5 9H20Z" fill="url(#leafB)"/></svg>`;
const leaf = (cls = '') => `<span class="leaf-wrap ${cls}">${LEAF}</span>`;
const POINTER = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4.33 4.07 Q4.33 3.07 5.02 3.79 L14.27 13.47 Q15.03 14.27 13.93 14.3 L12.77 14.32 Q10.93 14.37 9.62 14.64 L8.91 14.79 Q8.03 14.97 7.36 15.57 L5.15 17.54 Q4.33 18.27 4.33 17.17 L4.33 4.07 Z" fill="#fff" stroke="#fff" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/><path d="M4.33 4.07 Q4.33 3.07 5.02 3.79 L14.27 13.47 Q15.03 14.27 13.93 14.3 L12.77 14.32 Q10.93 14.37 9.62 14.64 L8.91 14.79 Q8.03 14.97 7.36 15.57 L5.15 17.54 Q4.33 18.27 4.33 17.17 L4.33 4.07 Z" fill="#000"/></svg>`;
// the pen's marks: a tick and a cross drawn as strokes (--len is the path length, for the draw animation)
const TICK = `<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4.5 10.5l3.6 3.6 7.4-7.6" style="--len:17"/></svg>`;
const CROSS = `<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M6 6l8 8M14 6l-8 8" style="--len:23"/></svg>`;

const AGENTS = {
  claude:   { name: 'Claude Code', ini: 'CC', col: '#5B5D72', where: 'on this laptop' },
  opencode: { name: 'opencode',    ini: 'oc', col: '#72557B', where: 'in the Linux environment' },
  copilot:  { name: 'Copilot',     ini: 'Cp', col: '#4F5065', where: 'on this laptop' },
  cursor:   { name: 'Cursor',      ini: 'Cu', col: '#5E5E68', where: 'on this laptop' },
  gemini:   { name: 'Gemini CLI',  ini: 'G',  col: '#565B8C', where: 'on this laptop' },
  codex:    { name: 'Codex',       ini: 'Cx', col: '#7A7A84', where: 'on Brian’s desk' },
};
const KIND_ICON = { read: 'visibility', edit: 'edit', delete: 'delete', move: 'drive_file_move', search: 'search', execute: 'terminal', think: 'psychology', fetch: 'language', other: 'more_horiz', setting: 'tune', app: 'apps', window: 'select_window', web: 'language', file: 'folder' };

/* ink: words as spans, so each can arrive on its own (§5.2). `from` marks the first new word in a re-render. */
function inkWords(text, from = 0, cls = '') {
  const words = String(text).split(/(\s+)/);
  let i = 0, out = '';
  for (const w of words) {
    if (!w) continue;
    if (/^\s+$/.test(w)) { out += w; continue; }
    const fresh = i >= from;
    out += `<span class="w${fresh ? ' new' : ''} ${cls}" style="--i:${fresh ? i - from : 0}">${w}</span>`; i++;
  }
  return out;
}
const wordCount = t => String(t).split(/\s+/).filter(Boolean).length;

/* ------------------------------------------------------------------------------------------ desktop */
function desktop(board, o) {
  const size = board.dataset.size;
  const H = size === 'g14' ? 1200 : 1080;
  board.innerHTML = '';
  board.insertAdjacentHTML('beforeend', `<div class="statusbar"><span>12:22</span><span>Sun, Oct 19</span>
    <div class="right">${ms('notifications')}${ms('wifi')}<span class="batt">35</span></div></div>`);
  if (o.mic) board.insertAdjacentHTML('beforeend', `<div class="priv-dot"></div><div class="mic-indicator">${ms('mic', 'fill')}Quire</div>`);

  // windows
  const wins = qs.get('bare') === '1' ? [] : (o.windows || ['doc', 'settings']);
  for (const w of wins) {
    if (w === 'settings') board.appendChild(settingsWindow(o, H));
    if (w === 'doc') board.appendChild(docWindow(o, H));
    if (w === 'browser') board.appendChild(browserWindow(o, H));
  }
  if (o.secure) { const w = h('div', 'window'); Object.assign(w.style, { left: '760px', top: '200px', width: '720px', height: '520px' });
    w.innerHTML = `<div class="caption"><span class="appicon" style="background:#2F6B45">${ms('account_balance', 'fill')}</span>Bank ${ms('expand_more')}<div class="ctl"><span>${ms('minimize')}</span><span>${ms('crop_square')}</span><span>${ms('close')}</span></div></div>
      <div class="win-body" style="flex-direction:column;padding:32px 40px;gap:16px;background:var(--surface-low)"><div style="font-size:22px">Current account</div><div style="height:12px;width:40%;border-radius:6px;background:var(--outline-variant)"></div><div style="height:12px;width:60%;border-radius:6px;background:var(--outline-variant)"></div><div style="height:12px;width:50%;border-radius:6px;background:var(--outline-variant)"></div><div style="margin-top:auto;display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--on-surface-variant)">${ms('lock')}This app protects its screen (FLAG_SECURE)</div></div>`;
    board.appendChild(w); }
  // taskbar
  const tb = h('div', 'taskbar');
  tb.innerHTML = `<div class="tb-btn">${ms('apps')}</div>
    <button type="button" class="tb-btn tb-quire ${o.tbRunning ? 'running' : ''}" data-role="quire" title="Quire" aria-label="Quire">${leaf()}${o.tbRing != null ? ring(o.tbRing) : ''}${o.tbBadge ? `<span class="badge">${o.tbBadge}</span>` : ''}</button>
    <div class="tb-divider"></div>
    <div class="tb-btn app ${wins.includes('doc') ? 'active' : ''}" style="background:#FBF8FE;color:#565B8C">${ms('description', 'fill')}</div>
    <div class="tb-btn app" style="background:#FBF8FE;color:#2F6B45">${ms('folder', 'fill')}</div>
    <div class="tb-btn app ${wins.includes('settings') ? 'active' : ''}" style="background:#FBF8FE;color:#565B8C">${ms('settings', 'fill')}</div>
    <div class="tb-btn app ${wins.includes('browser') ? 'active' : ''}" style="background:#FBF8FE;color:#1A696D">${ms('public', 'fill')}</div>`;
  board.appendChild(tb);
  return tb;
}
function ring(pct) {
  const r = 22, c = 2 * Math.PI * r;
  return `<span class="ring"><svg viewBox="0 0 48 48"><circle class="track" cx="24" cy="24" r="${r}"/><circle class="bar" cx="24" cy="24" r="${r}" stroke-dasharray="${c}" stroke-dashoffset="${c * (1 - pct)}"/></svg></span>`;
}
function settingsWindow(o, H) {
  const w = h('div', 'window settings' + (o.activeWin === 'doc' ? ' inactive' : ''));
  const geo = o.settingsGeo || { left: 560, top: 96, width: 1180, height: H - 96 - 120 };
  Object.assign(w.style, { left: geo.left + 'px', top: geo.top + 'px', width: geo.width + 'px', height: geo.height + 'px' });
  const s = o.settings || {};
  const dark = s.dark ?? (document.body.dataset.theme === 'dark' || o.theme === 'dark');
  w.innerHTML = `<div class="caption"><span class="appicon" style="background:#565B8C">${ms('settings', 'fill')}</span>Settings ${ms('expand_more')}
      <div class="ctl"><span>${ms('minimize')}</span><span>${ms('crop_square')}</span><span>${ms('close')}</span></div></div>
    <div class="win-body">
      <div class="nav">
        <div class="search">${ms('search')}Search Settings</div>
        ${navRow('wifi', '#2F6B45', 'Network & internet', 'Wi-Fi, hotspot')}
        ${navRow('devices', '#565B8C', 'Connected devices', 'Bluetooth, pairing', s.page === 'devices')}
        ${navRow('apps', '#72557B', 'Apps', 'Recent apps, default apps')}
        ${navRow('notifications', '#A8364B', 'Notifications', 'Notification history')}
        ${navRow('volume_up', '#5C5E72', 'Sound', 'Volume and vibration')}
        ${navRow('battery_charging_full', '#2F6B45', 'Battery', 'Battery saver, usage', s.page === 'battery')}
        ${navRow('display_settings', '#565B8C', 'Display', 'Dark theme, font size, brightness', !s.page || s.page === 'display')}
        ${navRow('palette', '#7A4CE0', 'Wallpaper', 'Home, lock screen')}
      </div>
      <div class="page">
        ${s.page === 'battery' ? `<h2>${ms('arrow_back')}Battery</h2>
          ${pref('Battery saver', 'Turns off or restricts background activity', sw(s.saver))}
          ${pref('Adaptive battery', 'Extends battery life by limiting rarely used apps', sw(true))}
          ${pref('Battery percentage', 'Show percentage in the status bar', sw(true))}`
        : s.page === 'devices' ? `<h2>${ms('arrow_back')}Connected devices</h2>
          ${pref('Bluetooth', s.bt === false ? 'Off' : 'On', sw(s.bt !== false), s.changed === 'bt')}
          ${pref('Pair new device', 'Make this laptop visible to nearby devices', ms('chevron_right'))}
          ${pref('Saved devices', 'Headphones, OpenBook Mouse', ms('chevron_right'))}`
        : `<h2>${ms('arrow_back')}Display</h2>
          ${pref('Dark theme', dark ? 'On · Will never turn off automatically' : 'Off · Will never turn on automatically', sw(dark), s.changed === 'dark')}
          ${pref('Brightness level', (s.brightness ?? 80) + '%', slider(s.brightness ?? 80), s.changed === 'brightness')}
          ${pref('Adaptive brightness', 'Adjusts brightness for your surroundings', sw(true))}
          ${pref('Night Light', s.night ? 'On · Schedule: sunset to sunrise' : 'Off', sw(!!s.night), s.changed === 'night')}
          ${pref('Display size and text', (s.font ? 'Text: large' : 'Text: default') + ' · Display: default', ms('chevron_right'), s.changed === 'font')}
          ${pref('Screen timeout', 'After 5 minutes of inactivity', ms('chevron_right'))}`}
      </div>
    </div>`;
  return w;
}
const navRow = (ic, col, t, sub, sel) => `<div class="row ${sel ? 'sel' : ''}"><span class="ic" style="background:${col}">${ms(ic, 'fill')}</span><div><b>${t}</b><span>${sub}</span></div></div>`;
const pref = (t, sub, ctl, changed) => `<div class="pref ${changed ? 'changed' : ''}"><div><b>${t}</b><span>${sub}</span></div>${ctl}</div>`;
const sw = on => `<span class="sw ${on ? 'on' : ''}"></span>`;
const slider = v => `<span class="slider"><i style="width:${v}%"></i><b style="left:calc(${v}% - 2px)"></b></span>`;

function docWindow(o, H) {
  const w = h('div', 'window doc' + (o.activeWin === 'settings' ? ' inactive' : ''));
  const geo = o.docGeo || { left: 120, top: 140, width: 1000, height: H - 140 - 160 };
  Object.assign(w.style, { left: geo.left + 'px', top: geo.top + 'px', width: geo.width + 'px', height: geo.height + 'px' });
  const sel = o.selection;
  w.innerHTML = `<div class="caption"><span class="appicon" style="background:#4355B9">${ms('description', 'fill')}</span>Notes · Trip planning ${ms('expand_more')}
      <div class="ctl"><span>${ms('minimize')}</span><span>${ms('crop_square')}</span><span>${ms('close')}</span></div></div>
    <div class="doc-body">
      <h1>Lisbon, 14–18 November</h1>
      <p>Flights are booked for the 14th, leaving at 07:40. The apartment is in Alfama, a ten-minute walk from the Santa Apolónia station, and check-in opens at 15:00.</p>
      <p>${sel ? '<mark>' : ''}The conference runs Tuesday to Thursday at the Centro de Congressos. Registration opens at 08:30 on Tuesday, and the keynote is at 09:15. Badges can be collected on Monday afternoon as well.${sel ? '</mark>' : ''} Dinner with the Porto team is still unconfirmed.</p>
      <p>Things to pack: the HDMI adapter, the second laptop charger, walking shoes, and a light jacket for the evenings. The forecast says 18 °C and mostly dry.</p>
      <p>Open questions: whether the Thursday workshop needs a separate ticket, and how long the tram from Belém takes in the afternoon.</p>
    </div>`;
  return w;
}
function browserWindow(o, H) { // Chrome, opened by a Q6 tool step ("open chrome and go to fox news")
  const w = h('div', 'window browser' + (o.activeWin && o.activeWin !== 'browser' ? ' inactive' : ''));
  const geo = o.browserGeo || { left: 200, top: 96, width: 1300, height: H - 96 - 140 };
  Object.assign(w.style, { left: geo.left + 'px', top: geo.top + 'px', width: geo.width + 'px', height: geo.height + 'px' });
  w.innerHTML = `<div class="caption"><span class="appicon" style="background:#1A696D">${ms('public', 'fill')}</span>Chrome ${ms('expand_more')}
      <div class="ctl"><span>${ms('minimize')}</span><span>${ms('crop_square')}</span><span>${ms('close')}</span></div></div>
    <div class="win-body" style="flex-direction:column">
      <div class="bar">${ms('arrow_back')}${ms('arrow_forward')}${ms('refresh')}<div class="url">${ms('lock')}<b>foxnews.com</b></div>${ms('more_vert')}</div>
      <div class="page"><div class="mast"></div><div class="hero"></div><div class="ln" style="width:70%"></div><div class="ln" style="width:92%"></div><div class="ln" style="width:84%"></div><div class="ln" style="width:60%"></div></div>
    </div>`;
  return w;
}

/* ------------------------------------------------------------------------------------------ note blocks */
// The quiet line (§6): who answers, what was taken in, the state, and how to leave. It is the note's last line in
// every state; there is no header. The agent's name opens the picker; the intake's name offers to drop it.
// The agent's name only; where it runs is in the picker, the tooltip and the TalkBack label (§6). An exception
// (`n.where`, e.g. "not connected") shows beside the name.
function who(n) {
  if (n.noAgent) return `<span class="who" data-role="agent" role="button" tabindex="0" aria-label="No agent connected. Choose one." title="No agent"><span class="av" style="background:var(--outline)">?</span><span class="nm">No agent</span></span>`;
  const a = AGENTS[n.agent || 'claude'];
  return `<span class="who ${n.picker ? 'open' : ''}" data-role="agent" role="button" tabindex="0" aria-label="Agent: ${a.name} ${n.where || a.where}. Change." title="${a.name} · ${n.where || a.where}"><span class="av" style="background:${a.col}">${a.ini}</span><span class="nm">${a.name}</span>${n.where ? `<span class="where">${n.where}</span>` : ''}</span>`;
}
function took(i, hasState) {
  if (!i) return '';
  if (hasState && i.kind === 'none') return '';
  if (hasState && (i.kind === 'window' || i.kind === 'region')) i = { kind: i.kind, text: i.text.split(' · ')[0] };
  if (i.kind === 'selection') return `<span class="dot"></span><span class="took" title="Remove">${ms('format_quote')}<q class="tx">${i.text}</q></span>`;
  if (i.kind === 'window' || i.kind === 'region') return `<span class="dot"></span><span class="took" title="Remove"><span class="thumb"><i></i><i></i></span><span class="tx">${i.text}</span></span>`;
  if (i.kind === 'secure') return `<span class="dot"></span><span class="took">${ms('lock')}<span class="tx">Secure window · nothing taken in</span></span>`;
  if (i.kind === 'none') return `<span class="dot"></span><span class="took" data-role="add-screen">${ms('add_a_photo')}<span class="tx">Add what’s on screen</span></span>`;
  return '';
}
function foot(n) {
  const closing = n.running
    ? `<button type="button" class="ibtn sm" data-role="background" title="Hide · keeps running (Meta+Space)" aria-label="Hide the note; the task keeps running">${ms('close')}</button>`
    : `<button type="button" class="ibtn sm ${n.focusClose ? 'focus' : ''}" data-role="close" title="Close (Esc)" aria-label="Close">${ms('close')}</button>`;
  return `<div class="n-foot ${n.foot ? 'has-state' : ''}">${who(n)}${took(n.intake, !!n.foot)}<span class="spacer"></span>${n.foot ? `<span class="state">${n.foot}</span>` : ''}${n.footRight != null ? n.footRight : `<kbd>Esc</kbd> ${n.running ? 'stop' : 'close'}`}${n.noClose ? '' : closing}</div>`;
}
function prompt(n) {
  if (!n.you) return '';
  return `<div class="you ink ${n.spoken ? 'spoken' : ''} ${n.fresh ? 'fresh' : ''}">${inkWords(n.you, n.fresh ? 0 : 1e9)}<span class="rule"></span></div>`;
}
function stepRow(s) {
  const mark = s.st === 'done' ? TICK : s.st === 'failed' ? CROSS : '';
  const undo = s.undo ? `<span class="undo-pill ${s.undone ? 'done' : ''}" data-act="undo-step" role="button" tabindex="0" aria-label="Undo: ${s.t}">${ms(s.undone ? 'check' : 'undo')}${s.undone ? 'Undone' : 'Undo'}</span>` : '';
  return `<div class="step ${s.st} ${s.undone ? 'undone' : ''} ${s.fresh ? 'fresh' : ''}"><span class="st">${mark}</span>${ms(KIND_ICON[s.kind] || 'more_horiz', 'kind')}<span class="t">${s.t}${s.val ? ` <span class="val">${s.val}</span>` : ''}</span>${undo}</div>`;
}
function steps(list, folded) {
  if (folded) return `<span class="steps-folded">${ms('check_circle', 'fill')}${list.length} steps ${ms('expand_more', 'chev')}</span>`;
  return `<div class="steps">${list.map(stepRow).join('')}</div>`;
}
function plan(entries) {
  return `<div class="card"><div class="ct">${ms('checklist')}Plan<span class="meta">${entries.filter(e => e.st === 'done').length} of ${entries.length}</span></div>
    <ol class="plan">${entries.map((e, i) => `<li class="${e.st}"><span class="n">${e.st === 'done' ? '✓' : i + 1}</span><span class="t">${e.t}</span>${e.pri ? `<span class="pri ${e.pri}">${e.pri}</span>` : ''}</li>`).join('')}</ol></div>`;
}
function change(c, mode) {
  return `<div class="change"><span class="k">${c.k}</span><span class="w">${c.w}</span>
    <span class="v"><span class="old">${c.old}</span>${ms('arrow_forward')}<span class="new">${c.nu}</span>${mode === 'undo' ? `<span class="undo" title="Undo">${ms('undo')}</span>` : ''}</span></div>`;
}
// ACP `session/request_permission`: the agent supplies `options[]` with its own `optionId`, `name` and `kind`.
// The card shows the agent's names, orders reject kinds first, styles by kind, and returns the chosen optionId.
// ACP gives `allow_always` no defined lifetime, so the label is the agent's own wording, never Quire's "for this task".
// The default sample is what quired's Claude Code adapter sends today (harness/claude.go).
const OPTIONS_CLAUDE = [
  { optionId: 'deny',   name: 'Don’t allow',            kind: 'reject_once' },
  { optionId: 'always', name: 'Allow for this session', kind: 'allow_always' },
  { optionId: 'allow',  name: 'Allow',                  kind: 'allow_once' },
];
const KIND_ORDER = { reject_always: 0, reject_once: 1, allow_always: 2, allow_once: 3 };
const KIND_STYLE = { reject_always: 'text', reject_once: 'text', allow_always: 'tonal', allow_once: 'filled' };
function optionButtons(c) {
  const opts = (c.options || OPTIONS_CLAUDE).slice().sort((a, b) => (KIND_ORDER[a.kind] ?? 9) - (KIND_ORDER[b.kind] ?? 9));
  return opts.map(o => `<button type="button" class="btn ${KIND_STYLE[o.kind] || 'text'} ${c.focus === o.optionId ? 'focus' : ''}" data-option="${o.optionId}" data-kind="${o.kind}">${o.name}</button>`).join('');
}
function consent(c) {
  return `<div class="card consent ${c.focusCard ? 'focus' : ''}" role="group" aria-label="Permission" tabindex="-1">
    <div class="ct">${ms('shield', 'fill')}${c.title}<span class="meta">${c.meta || ''}</span></div>
    ${c.changes ? c.changes.map(x => change(x)).join('') : ''}
    ${c.cmd ? `<div class="cmd">${c.cmd}</div>` : ''}
    ${c.diff ? `<div class="diff">${c.diff.map(l => `<div class="${l[0]}">${l[1]}</div>`).join('')}</div>` : ''}
    ${c.why ? `<div class="consent-why">${c.why}</div>` : ''}
    <div class="btns end">${optionButtons(c)}</div>
  </div>`;
}
// Q6's one question: a destructive action. Quire's own card (the broker's), with Quire's two options. The safe
// option is filled and focused; the destructive one sits on error-container. Nothing happens on Enter by accident:
// focus is on the card, Tab reaches Keep first.
function destructive(c) {
  return `<div class="card destructive ${c.focusCard ? 'focus' : ''}" role="group" aria-label="${c.title}" tabindex="-1">
    <div class="ct">${ms(c.icon || 'delete', 'fill')}${c.title}</div>
    ${c.file ? `<div class="file-row">${ms(c.file.ic || 'description')}${c.file.name}<small>${c.file.sub || ''}</small></div>` : ''}
    <div class="consent-why">${c.why}</div>
    <div class="btns end"><button type="button" class="btn danger" data-act="destroy">${c.go}</button><button type="button" class="btn filled ${c.focus === 'keep' ? 'focus' : ''}" data-act="keep">${c.keep}</button></div>
  </div>`;
}
function composer(c = {}) {
  return `<div class="composer"><div class="field ${c.focus ? 'focus' : ''}">${LEAF}<span class="text ${c.text ? '' : 'ph'}">${c.text || c.placeholder || 'Ask Quire'}${c.focus ? '<span class="caret"></span>' : ''}</span>
    <div class="mic ${c.mic ? 'on' : ''}" title="Hold to talk" role="button" aria-label="Hold to talk">${ms('mic')}</div><div class="send ${c.text ? '' : 'disabled'}" title="Send (Enter)" role="button" aria-label="Send">${ms('arrow_upward')}</div></div></div>`;
}

/* ------------------------------------------------------------------------------------------ the note */
function note(n) {
  const el = h('div', 'note ' + (n.cls || '') + (n.mirror ? ' mirror' : '') + (n.listening ? ' listening' : '') + (n.thinking || n.running ? ' working' : ''));
  el.setAttribute('role', 'dialog'); el.setAttribute('aria-label', 'Quire');
  const scroll = n.scroll ? 'scroll' : '';
  let body = '';
  if (n.listening) {
    body = `<div class="listen"><div class="levels"><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div><div class="tx">${n.listening.final || ''}<span class="partial">${n.listening.partial || ''}</span></div></div>`;
    el.innerHTML = body + foot(Object.assign({}, n, { foot: 'Listening · release to send', footRight: '<kbd>Esc</kbd> cancel', noClose: true }));
    return el;
  }
  if (n.mirror) {
    const m = n.mirror;
    el.innerHTML = `<div class="mirror-bar"><span class="auto ${m.paused ? 'paused' : ''}"><span class="dot"></span>${m.paused ? 'Paused' : 'Using ' + (m.app || 'Settings')}</span><span>${m.title}</span><span class="spacer"></span></div>
      ${prompt(n)}
      <div class="mirror-view">
        <div class="stage"><div class="desk"></div>${settingsWindow({ settings: m.settings, settingsGeo: { left: 0, top: 0, width: SESSION[0], height: SESSION[1] } }, 0).outerHTML}</div>
        <div class="overlay"></div>
        ${m.paused ? `<div class="paused-scrim"><span>${ms('pause')}Paused · click in the mirror to act, or Take over</span></div>` : ''}
      </div>
      <div class="mirror-step">${steps(m.steps)}</div>
      <div class="mirror-foot"><span class="status">${m.status}</span>
        <button type="button" class="btn stop" data-act="stop">${ms('stop')}Stop</button><button type="button" class="btn paper" data-act="pause" aria-label="${m.paused ? 'Resume' : 'Pause'}">${ms(m.paused ? 'play_arrow' : 'pause')}${m.paused ? 'Resume' : 'Pause'}</button><button type="button" class="btn filled ${m.focusTake ? 'focus' : ''}" data-act="takeover" aria-label="Take over">${ms('open_in_full')}Take over</button></div>
      ${foot(Object.assign({}, n, { running: true, foot: '', footRight: '<kbd>Esc</kbd> stop' }))}`;
    el._mirror = m;
    return el;
  }
  body = (n.blocks || []).map(b => {
    switch (b.type) {
      case 'thought': return `<div class="thought">${leaf('thinking')}${b.t}<span class="ellipsis">…</span></div>`;
      case 'answer': return `<div class="answer ink">${b.html}${b.caret ? '<span class="caret"></span>' : ''}</div>`;
      case 'steps': return steps(b.list, b.folded);
      case 'plan': return plan(b.entries);
      case 'consent': return consent(b);
      case 'destructive': return destructive(b);
      case 'changes': return `<div class="card"><div class="ct">${ms(b.icon || 'tune')}${b.title}<span class="meta">${b.meta || ''}</span></div>${b.list.map(c => change(c, b.mode)).join('')}${b.foot || ''}</div>`;
      case 'result': return `<div class="result">${ms(b.icon || 'check_circle', (b.cls || '') + ' fill')}<div class="msg">${b.msg}${b.sub ? `<small>${b.sub}</small>` : ''}</div></div>`;
      case 'error': return `<div class="card error"><div class="ct">${ms('error', 'fill')}${b.title}<span class="meta">${b.meta || ''}</span></div><div class="consent-why">${b.msg}</div>${b.details ? `<div class="details">${b.details}</div>` : ''}<div class="btns end">${b.btns}</div></div>`;
      case 'auth': return `<div class="card"><div class="ct">${ms('key', 'fill')}${b.title}</div><div class="consent-why">${b.msg}</div><div class="auth-list">${b.methods.map(m => `<div class="row">${ms(m.ic)}${m.t}<small>${m.sub || ''}</small></div>`).join('')}</div></div>`;
      case 'agents': return `<div class="card"><div class="ct">${ms('hub')}${b.title}</div><div class="consent-why">${b.msg}</div><div class="auth-list">${b.list.map(m => `<div class="row"><span class="av" style="width:22px;height:22px;border-radius:50%;display:grid;place-items:center;font-size:10px;font-weight:700;color:#fff;background:${m.col}">${m.ini}</span>${m.t}<small>${m.sub || ''}</small></div>`).join('')}</div>${b.foot || ''}</div>`;
      case 'btns': return `<div class="btns ${b.end ? 'end' : ''}">${b.html}</div>`;
      case 'code': return `<div class="codeblock"><div class="bar">${b.lang}<button type="button" class="ibtn" title="Copy" aria-label="Copy code">${ms('content_copy')}</button></div><pre>${b.src}</pre></div>`;
      case 'image': return `<div class="img" style="height:${b.h || 180}px">${b.html || ''}<span class="expand">${ms('open_in_full')}</span><span class="cap">${ms('image')}${b.cap}</span></div>`;
      case 'jump': return `<div class="jump"><span>${ms('arrow_downward')}Jump to latest</span></div>`;
      case 'html': return b.html;
    }
    return '';
  }).join('');
  el.innerHTML = prompt(n) + (body ? `<div class="${scroll}"><div class="n-body">${body}</div></div>` : '') + (n.composer === false ? '' : composer(n.composer)) + foot(n);
  if (n.picker) el.appendChild(picker(n.picker));
  return el;
}
function picker(p) {
  const el = h('div', 'picker');
  el.innerHTML = `<div class="hd">In the Linux environment</div>
    ${pItem('claude', 'Claude Code', 'Signed in · last used today', 'check', 'ok', p.sel === 'claude')}
    ${pItem('opencode', 'opencode', 'Signed in', 'check', 'ok')}
    ${pItem('cursor', 'Cursor', 'Needs sign-in', 'key', 'warn', false, true)}
    <div class="hd">Paired computers</div>
    ${pItem('codex', 'Codex', 'Brian’s desk · connected', 'check', 'ok')}
    <div class="foot"><div class="it">${ms('add_circle')}<div class="w">Connect an agent<small>or pair a computer</small></div></div></div>`;
  return el;
}
const pItem = (id, t, sub, ic, cls, sel, dim) => { const a = AGENTS[id]; return `<div class="it ${sel ? 'sel' : ''} ${dim ? 'dim' : ''}"><span class="av" style="background:${a.col}">${a.ini}</span><div class="w">${t}<small>${sub}</small></div>${ms(ic, cls)}</div>`; };

/* ------------------------------------------------------------------------------------------ mirror geometry */
// The session display has the reference display's size and density (C): 1920x1200 dp on the G14. The 736 dp view
// shows all of it at 0.383; while the agent acts on a control, the view zooms 2x (0.767) on a 960x600 dp region
// around it (spring.expand in the build; a cut in this prototype). Paused shows the full view.
const SESSION = [1920, 1200], VIEW_W = 736, FULL = VIEW_W / SESSION[0], ZOOM = 2;
function relTo(el, stage) { let x = 0, y = 0; for (let e = el; e && e !== stage; e = e.offsetParent) { x += e.offsetLeft; y += e.offsetTop; } return { x, y, w: el.offsetWidth, h: el.offsetHeight }; }
function mirrorLayout(n) {
  const m = n && n._mirror, view = n && n.querySelector('.mirror-view'); if (!m || !view) return;
  const stage = view.querySelector('.stage'), ov = view.querySelector('.overlay');
  const te = m.target ? stage.querySelector(m.target) : null, t = te ? relTo(te, stage) : null;
  let sc = FULL, ox = 0, oy = 0;
  if (t && !m.paused) { sc = FULL * ZOOM; const rw = VIEW_W / sc, rh = (VIEW_W * 10 / 16) / sc; ox = Math.max(0, Math.min(SESSION[0] - rw, t.x + t.w / 2 - rw / 2)); oy = Math.max(0, Math.min(SESSION[1] - rh, t.y + t.h / 2 - rh / 2)); }
  stage.style.transform = `scale(${sc}) translate(${-ox}px, ${-oy}px)`;
  const mv = (x, y) => [((x - ox) * sc).toFixed(1), ((y - oy) * sc).toFixed(1)];
  let html = '';
  const g = m.ghost || (t ? [t.x + t.w * 0.62, t.y + t.h * 0.56] : null);
  if (g && !m.paused) { const [x, y] = mv(g[0], g[1]); html += `<span class="ghost" style="left:${x}px;top:${y}px">${POINTER}</span>`; if (m.tap) html += `<span class="tap" style="left:${x}px;top:${y}px"></span>`; }
  if (t && !m.paused) { const [x, y] = mv(t.x, t.y); html += `<span class="focus-ring" style="left:${x}px;top:${y}px;width:${(t.w * sc).toFixed(1)}px;height:${(t.h * sc).toFixed(1)}px"></span>`; }
  ov.innerHTML = html;
}

/* ------------------------------------------------------------------------------------------ placement */
function place(board, el, anchor, opt = {}) {
  board.appendChild(el); mirrorLayout(el);
  const W = board.clientWidth || 1920, H = board.clientHeight || 1080;
  const w = el.offsetWidth, hh = el.offsetHeight;
  let x, y;
  if (anchor.from === 'taskbar') {
    x = Math.round(W / 2 - w / 2 + (opt.dx || 0)); y = H - 64 - 12 - hh;
    el.style.setProperty('--ox', '50%'); el.style.setProperty('--oy', '100%');
  } else {
    const [px, py] = anchor.at;
    x = px + 18; y = py + 18;
    el.style.setProperty('--ox', '0px'); el.style.setProperty('--oy', '0px');
    if (x + w > W - 24) { x = px - 18 - w; el.style.setProperty('--ox', '100%'); }
    if (y + hh > H - 64 - 16) { y = Math.max(40, H - 64 - 16 - hh); el.style.setProperty('--oy', (py - y) + 'px'); }
  }
  el.style.left = x + 'px'; el.style.top = y + 'px';
  return { x, y, w, h: hh };
}
function pointer(board, [x, y], o = {}) {
  if (o.halo) { const ha = h('div', 'halo ' + (o.halo === 'listening' ? 'listening' : '') + (o.breathe ? ' breathe' : '')); ha.style.left = (x + 4) + 'px'; ha.style.top = (y + 3) + 'px'; if (o.haloScale) ha.style.transform = `scale(${o.haloScale})`; board.appendChild(ha); }
  if (o.label) { const l = h('div', 'halo-label', o.label); l.style.left = (x + 28) + 'px'; l.style.top = (y - 6) + 'px'; board.appendChild(l); }
  const p = h('div', 'pointer', POINTER); p.style.left = x + 'px'; p.style.top = y + 'px'; board.appendChild(p);
  return p;
}
function intake(board, geo, region) { const i = h('div', 'intake' + (region ? ' region' : '')); Object.assign(i.style, { left: geo.left + 'px', top: geo.top + 'px', width: geo.width + 'px', height: geo.height + 'px' }); board.appendChild(i); return i; }
function selToolbar(board, x, y, hover) { // the text toolbar with its overflow open: Ask Quire is a label there, not an iconed item
  const tb = h('div', 'sel-toolbar', `<span>Copy</span><span>Share</span><span>Select all</span><span class="sep"></span><span class="more">${ms('more_vert')}</span>`);
  tb.style.left = x + 'px'; tb.style.top = y + 'px'; board.appendChild(tb);
  const menu = h('div', 'sel-menu', `<span class="q ${hover ? 'hover' : ''}" data-act="ask-selection">Ask Quire</span>`);
  board.appendChild(menu); menu.style.left = (x + tb.offsetWidth - menu.offsetWidth) + 'px'; menu.style.top = (y + 50) + 'px';   // under the ⋮
  return [tb, menu];
}
function anno(board, x, y, text, cls = '') { const a = h('div', 'anno ' + cls, `<i></i>${text}`); a.style.left = x + 'px'; a.style.top = y + 'px'; board.appendChild(a); }

/* ------------------------------------------------------------------------------------------ sample content */
// Q6's tool steps: the agent acts through Quire's tools without asking; each change carries its own undo.
const STEPS_CHROME = [
  { st: 'done', kind: 'app', t: 'Opening Chrome' },
  { st: 'running', kind: 'web', t: 'Going to', val: 'foxnews.com' },
];
const STEPS_DARK = [
  { st: 'done', kind: 'read', t: 'Reading Display settings' },
  { st: 'done', kind: 'setting', t: 'Settings: Dark theme', val: 'on', undo: true, effect: 'Dark theme was turned on', where: 'Settings · Display' },
];
const STEPS_BATTERY = [
  { st: 'done', kind: 'read', t: 'Reading Display settings' },
  { st: 'done', kind: 'read', t: 'Reading Battery settings' },
  { st: 'running', kind: 'setting', t: 'Settings: Battery saver', val: 'on', effect: 'Battery saver was turned on', where: 'Settings · Battery' },
  { st: 'pending', kind: 'setting', t: 'Settings: Brightness', val: '40%', effect: 'Brightness was lowered to 40%', where: 'Settings · Display' },
];
const ANSWER_ADAPTIVE = `<p><b>Adaptive brightness</b> uses the light sensor to set the screen's brightness for the room you are in, and learns from the adjustments you make.</p><p>On this laptop it is on. It will not change the brightness while Battery saver is active, which is why the slider`;
const ANSWER_ADAPTIVE_INK = `<p><b>Adaptive brightness</b> uses the light sensor to set the screen's brightness for the room you are in, and learns from the adjustments you make.</p><p>On this laptop it is on. It will not change the brightness while Battery saver is active, which is why <span class="w a2">the</span> <span class="w a1">slider</span>`;
const CODE_RENAME = `<span class="c"># Rename photos in ~/Pictures/Lisbon by the date they were taken</span>
<span class="k">for</span> f <span class="k">in</span> ~/Pictures/Lisbon/*.jpg; <span class="k">do</span>
  d=$(exiftool -s3 -DateTimeOriginal <span class="s">"$f"</span> | tr <span class="s">': '</span> <span class="s">'--'</span>)
  mv -n <span class="s">"$f"</span> <span class="s">"$(dirname "$f")/$d.jpg"</span>
<span class="k">done</span>`;

/* ------------------------------------------------------------------------------------------ screens */
const PTR = [1010, 470];           // pointer over the Settings window's Display page
const SETTINGS_GEO = H => ({ left: 560, top: 96, width: 1180, height: H - 96 - 120 });
const WIN = { kind: 'window', text: 'Settings · Display' };
const S = {}; // id -> { caption, build(board, H, theme) }

S['idle'] = { caption: '<b>Idle.</b> Quire’s button sits in the taskbar’s system group, after All apps. Nothing else is on screen until the person calls it.',
  build(b) { desktop(b, {}); pointer(b, PTR); } };

S['invoke-shake'] = { caption: '<b>Shake, first 100 ms.</b> The halo blooms around the hotspot (90 ms), and the window under the pointer gets the intake outline. The note has not appeared yet.',
  build(b, H) { desktop(b, { activeWin: 'settings' }); intake(b, SETTINGS_GEO(H)); pointer(b, PTR, { halo: true, label: `${LEAF}Ask Quire` }); anno(b, PTR[0] - 40, PTR[1] - 60, 'halo: 0 → 32 dp in 90 ms, then the sheet unrolls from the pen tip'); anno(b, 600, 60, 'intake outline: the window under the pointer, 2 dp primary at 55 %', 't'); } };

S['invoke-key'] = { caption: '<b>Meta+Space or the assist key, first 100 ms.</b> The pointer was used in the last 10 s, so the halo appears there with the shortcut label; otherwise the note rises from the taskbar button. Intake is the focused window.',
  build(b, H) { desktop(b, { activeWin: 'settings' }); intake(b, SETTINGS_GEO(H)); pointer(b, PTR, { halo: true, label: `${LEAF}Quire <kbd>Meta</kbd><kbd>Space</kbd>` }); } };

S['open'] = { caption: '<b>The first moment.</b> The sheet has unrolled beside the pointer: one field with focus, and the quiet line under it naming the agent and what was taken in. Nothing else. Two things on screen, one place to type.',
  build(b, H) { desktop(b, { activeWin: 'settings' }); intake(b, SETTINGS_GEO(H)); pointer(b, PTR, { halo: true, haloScale: 1 }); place(b, note({ agent: 'claude', intake: WIN, composer: { focus: true } }), { at: PTR }); anno(b, PTR[0] + 20, PTR[1] + 128, 'the quiet line: who answers · what was taken in · how to leave', 't'); anno(b, PTR[0] + 20, PTR[1] - 40, 'glass: the system blur at 34 dp under the note’s own colour at 80 %; the rim is the halo’s light'); } };

S['invoke-taskbar'] = { caption: '<b>Taskbar button.</b> The note rises from the button and settles 12 dp above the taskbar. Nothing is taken in; the quiet line offers to add what is on screen.',
  build(b, H) { desktop(b, { activeWin: 'doc' }); pointer(b, [960, H - 36]); place(b, note({ agent: 'claude', intake: { kind: 'none' }, composer: { focus: true } }), { from: 'taskbar' }); } };

S['invoke-secure'] = { caption: '<b>Secure window.</b> The pointer is over a window with FLAG_SECURE. The halo still answers, but nothing is taken in: no screenshot, no selection. The quiet line says so.',
  build(b, H) { desktop(b, { activeWin: 'settings', secure: true }); pointer(b, PTR, { halo: true }); place(b, note({ agent: 'claude', intake: { kind: 'secure' }, composer: { focus: true } }), { at: PTR }); } };

S['invoke-voice'] = { caption: '<b>Hold to talk.</b> The halo becomes a mic ring; the mic indicator and privacy dot appear in the status bar. Words arrive as they are recognised, in ink; release sends.',
  build(b, H) { desktop(b, { activeWin: 'settings', mic: true }); intake(b, SETTINGS_GEO(H)); pointer(b, PTR, { halo: 'listening', breathe: true }); place(b, note({ agent: 'claude', intake: WIN, listening: { final: 'Make my screen easier to read ', partial: 'at night' } }), { at: PTR }); } };

S['invoke-selection'] = { caption: '<b>Ask Quire on a selection.</b> Android lists an <code>ACTION_PROCESS_TEXT</code> handler in the text toolbar’s overflow menu as a plain label, no icon (C). The selection stays highlighted and is quoted in the quiet line; the note opens at the pointer, which just chose the item.',
  build(b, H) { desktop(b, { activeWin: 'doc', selection: true, windows: ['settings', 'doc'] }); selToolbar(b, 184, 306, true); pointer(b, [470, 388], { halo: true }); place(b, note({ agent: 'claude', intake: { kind: 'selection', text: 'The conference runs Tuesday to Thursday…' }, composer: { focus: true, placeholder: 'Ask about the selection' } }), { at: [470, 388] }); } };

S['compose'] = { caption: '<b>Composing.</b> Typing is the person’s own act, so letters appear at once; the ink comes when they send. The field grows to four lines, then scrolls. Enter sends, Shift+Enter breaks the line.',
  build(b, H) { desktop(b, { activeWin: 'settings' }); intake(b, SETTINGS_GEO(H)); pointer(b, PTR); place(b, note({ agent: 'claude', intake: WIN, composer: { focus: true, text: 'Make my screen easier to read at ni' }, foot: '', footRight: '<kbd>Enter</kbd> send' }), { at: PTR }); } };

S['agent-picker'] = { caption: '<b>Choosing the agent.</b> The agent’s name in the quiet line opens a list grouped by where agents run. Sign-in state shows per agent (ACP <code>authMethods</code>). The last used agent is preselected.',
  build(b, H) { desktop(b, { activeWin: 'settings' }); intake(b, SETTINGS_GEO(H)); pointer(b, PTR); place(b, note({ agent: 'claude', picker: { sel: 'claude' }, intake: WIN, composer: { text: 'Make my screen easier to read at night' }, foot: '' }), { at: PTR }); } };

S['streaming'] = { caption: '<b>Streaming.</b> The prompt is written in ink under the pen’s rule. The answer arrives word by word, each word rising 2 dp into place over 160 ms; the rim’s light turns slowly while the agent works.',
  build(b, H) { desktop(b, { activeWin: 'settings' }); pointer(b, PTR); place(b, note({ agent: 'claude', thinking: true, running: true, intake: WIN, you: 'What does Adaptive brightness do here?', blocks: [{ type: 'answer', html: ANSWER_ADAPTIVE_INK, caret: true }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Answering' }), { at: PTR }); anno(b, PTR[0] + 20, PTR[1] - 40, 'words arrive as ink: opacity 0 → 1, 2 dp rise, 160 ms, 24 ms apart'); } };

S['steps'] = { caption: '<b>Tool steps (Q6).</b> “Open Chrome and go to Fox News”: the agent acts through Quire’s tools without asking. Each call is one line with its kind; the running mark is an ink dot, a done mark is a tick drawn as a stroke (180 ms).',
  build(b, H) { desktop(b, { activeWin: 'browser', windows: ['browser'], browserGeo: { left: 120, top: 80, width: 1100, height: H - 80 - 140 } }); pointer(b, [1300, 400]); place(b, note({ agent: 'claude', thinking: true, running: true, intake: { kind: 'none' }, you: 'Open Chrome and go to Fox News', blocks: [{ type: 'steps', list: STEPS_CHROME }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Working' }), { at: [1300, 400] }); } };

S['setting-undo'] = { caption: '<b>A setting changed, with its undo (Q6).</b> “Turn on dark theme”: no card, no question. The step names the setting and its new value, and carries its own Undo on paper. The change stays undoable from the note and from the Quire button for 24 h.',
  build(b, H) { desktop(b, { activeWin: 'settings', settings: { dark: true, changed: 'dark' } }); pointer(b, PTR); place(b, note({ agent: 'claude', intake: WIN, you: 'Turn on dark theme', blocks: [{ type: 'steps', list: STEPS_DARK }, { type: 'result', msg: 'Dark theme is on.', sub: 'Changed 1 setting · 2 s' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Done' }), { at: PTR }); anno(b, PTR[0] + 20, PTR[1] - 40, 'a change made without asking carries its undo on the step itself'); } };

S['plan'] = { caption: '<b>A plan.</b> An ACP <code>plan</code> update becomes a numbered checklist on paper that updates in place. Priority shows only when the agent sets it.',
  build(b, H) { desktop(b, { activeWin: 'settings' }); pointer(b, PTR); place(b, note({ agent: 'claude', thinking: true, running: true, intake: WIN, you: 'Set this laptop up for my talk tomorrow', blocks: [{ type: 'plan', entries: [{ st: 'done', t: 'Check the HDMI output and mirror mode' }, { st: 'active', t: 'Turn off notifications during the talk', pri: 'high' }, { st: 'pending', t: 'Set screen timeout to 30 minutes' }, { st: 'pending', t: 'Open the slides in a new window' }] }, { type: 'steps', list: [{ st: 'done', kind: 'read', t: 'Reading Display settings' }, { st: 'running', kind: 'read', t: 'Reading Notification settings' }] }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Working' }), { at: PTR }); } };

S['confirm-destructive'] = { caption: '<b>The one question: a destructive action (Q6).</b> “Delete the newest file in Downloads.” Quire’s own card names the file and what happens. Keep is filled and takes focus; Delete sits on error-container. Esc stops the run and deletes nothing.',
  build(b, H) { desktop(b, { activeWin: 'doc' }); pointer(b, [700, 420]); place(b, note({ agent: 'claude', intake: { kind: 'none' }, running: true, you: 'Delete the newest file in Downloads', blocks: [{ type: 'steps', list: [{ st: 'done', kind: 'read', t: 'Reading Downloads' }] }, { type: 'destructive', title: 'Delete this file?', file: { ic: 'picture_as_pdf', name: 'report-draft.pdf', sub: 'Downloads · 2.4 MB · today 11:40' }, why: 'It goes to the bin and can be restored from Files for 30 days.', go: 'Delete', keep: 'Keep it', focus: 'keep', focusCard: false }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Waiting for you' }), { at: [700, 420] }); anno(b, 720, 380, 'only destructive actions ask; the safe choice is the filled one and has focus'); } };

S['consent-command'] = { caption: '<b>An agent’s own request.</b> Quire’s tools don’t ask for a file write, but an ACP agent may ask before its own actions (<code>session/request_permission</code>). The card shows the diff and the agent’s own options, labelled by the agent.',
  build(b, H) { desktop(b, { activeWin: 'doc' }); pointer(b, [700, 520]); place(b, note({ agent: 'claude', cls: 'wide', running: true, intake: { kind: 'selection', text: 'Things to pack: the HDMI adapter…' }, you: 'Turn this into a checklist file in my Documents', blocks: [{ type: 'steps', list: [{ st: 'done', kind: 'read', t: 'Reading the selection' }] }, { type: 'consent', title: 'Write a file', meta: 'Documents/Lisbon-packing.md', focus: 'deny', diff: [['', '# Lisbon packing list'], ['add', '+ [ ] HDMI adapter'], ['add', '+ [ ] Second laptop charger'], ['add', '+ [ ] Walking shoes'], ['add', '+ [ ] Light jacket for the evenings']], why: 'Creates a new file. Nothing else in Documents changes.' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Waiting for you' }), { at: [700, 520] }); } };

S['consent-system'] = { caption: '<b>Platform consent for computer control.</b> The system’s own dialog (platform-owned, drawn here only for context) asks before any app is automated. The note waits and says so.',
  build(b, H) { desktop(b, { activeWin: 'settings' }); pointer(b, PTR); place(b, note({ agent: 'claude', running: true, intake: { kind: 'window', text: 'Settings' }, you: 'In Settings, find Bluetooth and turn it off', blocks: [{ type: 'steps', list: [{ st: 'done', kind: 'read', t: 'Listing apps' }, { st: 'running', kind: 'app', t: 'Asking to use Settings' }] }, { type: 'result', icon: 'shield', cls: 'warn', msg: 'Waiting for your permission', sub: 'The system is asking whether Claude Code may use Settings.' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Waiting for you' }), { at: PTR }); const d = h('div', 'sysdialog', `<span class="lbl">System dialog (platform)</span>${ms('shield', 'big fill')}<h3>Allow Claude Code to use Settings?</h3><p>Quire will run Settings on a separate screen that you can watch. Claude Code can tap, type and take screenshots there. Secure screens stay hidden, and you can take over at any time.</p><div class="btns"><button type="button" class="btn text">Don’t allow</button><button type="button" class="btn filled">Allow</button></div>`); d.style.left = '750px'; d.style.top = '360px'; b.appendChild(d); } };

S['mirror'] = { caption: '<b>The live mirror.</b> The note expands to 760 dp and the session display shows as a pane set into the glass (<code>InteractiveMirror</code>, 1920×1200 dp on the G14, C): the whole display at 0.383, zoomed 2× on the control the agent acts on. The agent’s pointer is drawn in brand blue with a tap ring.',
  build(b, H) { desktop(b, { activeWin: 'doc', windows: ['doc'], tbRunning: true }); pointer(b, [1400, 300]); place(b, note({ agent: 'claude', thinking: true, intake: { kind: 'window', text: 'Settings' }, you: 'In Settings, find Bluetooth and turn it off', mirror: { title: 'Settings', target: '.nav .row:nth-of-type(3)', tap: true, settings: { page: 'display' }, steps: [{ st: 'done', kind: 'app', t: 'Opened Settings' }, { st: 'running', kind: 'execute', t: 'Tapping Connected devices' }], status: 'Step 2 of 4 · 11 s' } }), { at: [1400, 300] }); anno(b, 1000, 240, 'automation indicator: the taskbar button breathes while an app is driven', 't'); anno(b, 1000, 290, 'the view is zoomed 2× on the control the agent acts on; Pause shows the whole session display', 't'); } };

S['mirror-paused'] = { caption: '<b>Paused.</b> <code>notifyBlocked()</code>: the platform drops the agent’s input, the mirror becomes interactive (it only is while blocked, C), and the view returns to the whole session display. Resume (<code>requestUnblock()</code>) gives control back. Take over moves the app to their screen.',
  build(b, H) { desktop(b, { activeWin: 'doc', windows: ['doc'], tbRunning: true }); pointer(b, [1400, 300]); place(b, note({ agent: 'claude', intake: { kind: 'window', text: 'Settings' }, you: 'In Settings, find Bluetooth and turn it off', mirror: { paused: true, title: 'Connected devices', settings: { page: 'devices' }, steps: [{ st: 'done', kind: 'app', t: 'Opened Settings' }, { st: 'done', kind: 'execute', t: 'Tapped Connected devices' }, { st: 'pending', kind: 'execute', t: 'Turn off Bluetooth' }], status: 'Paused by you · 14 s', focusTake: true } }), { at: [1400, 300] }); } };

S['done'] = { caption: '<b>Done.</b> The result in one line, the steps folded, and Undo for anything that changed. The note stays until the person closes it; closing folds the sheet back into the pen.',
  build(b, H) { desktop(b, { activeWin: 'settings', settings: { page: 'battery', saver: true } }); pointer(b, PTR); place(b, note({ agent: 'claude', intake: WIN, you: 'Turn on Battery saver and lower the brightness', blocks: [{ type: 'steps', folded: true, list: [1, 2, 3, 4] }, { type: 'result', msg: 'Battery saver is on and brightness is at 40%.', sub: 'Changed 2 settings · 8 s' }, { type: 'btns', html: '<button type="button" class="btn paper">' + ms('undo') + 'Undo both</button><button type="button" class="btn text">Show changes</button>' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Done' }), { at: PTR }); } };

S['stopped'] = { caption: '<b>Stopped by the person.</b> Esc or Stop cancels the run and answers any open request as cancelled. The copy says what was done before the stop, what was interrupted, and what to check. Hiding the note (Meta+Space, the ×) is a different action: the task keeps running behind the taskbar button.',
  build(b, H) { desktop(b, { activeWin: 'settings', settings: { page: 'battery', saver: true } }); pointer(b, PTR); place(b, note({ agent: 'claude', intake: WIN, you: 'Turn on Battery saver and lower the brightness', blocks: [{ type: 'steps', list: [STEPS_BATTERY[0], STEPS_BATTERY[1], { st: 'done', kind: 'setting', t: 'Settings: Battery saver', val: 'on', undo: true }, { st: 'failed', kind: 'setting', t: 'Settings: Brightness', val: '40%' }] }, { type: 'result', icon: 'stop_circle', cls: 'warn', msg: 'Stopped after 3 of 4 steps.', sub: 'Battery saver was turned on. Lowering brightness to 40% was interrupted and may be partly applied; check Settings · Display.' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Stopped' }), { at: PTR }); } };

S['error'] = { caption: '<b>Error.</b> What stopped, in a sentence, with details behind a disclosure and a retry. Stop reasons other than <code>end_turn</code> (refusal, max tokens, cancelled) use the same card.',
  build(b, H) { desktop(b, { activeWin: 'settings' }); pointer(b, PTR); place(b, note({ agent: 'claude', intake: WIN, you: 'Turn on Battery saver and lower the brightness', blocks: [{ type: 'steps', list: [STEPS_BATTERY[0], { st: 'failed', kind: 'read', t: 'Reading Battery settings' }] }, { type: 'error', title: 'Claude Code stopped', meta: '7 s', msg: 'The agent closed the connection before finishing. Nothing was changed.', details: 'quired: agent exited with status 1\nstderr: Error: fetch failed (ECONNRESET)', btns: '<button type="button" class="btn text">Show log</button><button type="button" class="btn paper">' + ms('refresh') + 'Try again</button>' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Stopped' }), { at: PTR }); } };

S['signin'] = { caption: '<b>Agent not signed in.</b> ACP <code>authenticate</code> with the agent’s <code>authMethods</code>. Sign-in happens in the agent’s own flow; Quire never handles the secret.',
  build(b, H) { desktop(b, { activeWin: 'settings' }); pointer(b, PTR); place(b, note({ agent: 'cursor', intake: WIN, you: 'Make my screen easier to read at night', blocks: [{ type: 'auth', title: 'Cursor needs to sign in', msg: 'Choose how to sign in. It opens in the Linux environment and comes back here when it’s done.', methods: [{ ic: 'open_in_browser', t: 'Sign in with the browser', sub: 'cursor login' }, { ic: 'key', t: 'Use an API key', sub: 'stays in Cursor' }] }, { type: 'btns', end: true, html: '<button type="button" class="btn text">Use Claude Code instead</button><button type="button" class="btn filled">Sign in</button>' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Not signed in' }), { at: PTR }); } };

S['background'] = { caption: '<b>Running in the background.</b> The note folded into the taskbar button, which shows progress and a count. The tray, in the same glass, lists running and finished tasks; one needs an answer.',
  build(b, H) { desktop(b, { activeWin: 'doc', tbRing: 0.6, tbBadge: '2', tbRunning: true }); pointer(b, [960, H - 38]); const t = h('div', 'tray', `<div class="hd">${LEAF}Quire<span class="spacer"></span><div class="ibtn">${ms('settings')}</div></div>
    <div class="task"><span class="st ask">${ms('delete', 'fill')}</span><div class="w"><b>Delete the newest file in Downloads</b><small>Needs your answer · Delete this file?</small></div><span class="agent-mini">Claude Code</span>${ms('chevron_right', 'chev')}</div>
    <div class="task"><span class="st run"></span><div class="w"><b>Rename the photos in Lisbon by date</b><small>Step 3 of 5 · 48 s</small></div><span class="agent-mini">opencode</span>${ms('chevron_right', 'chev')}</div>
    <div class="task"><span class="st ok">${ms('check_circle', 'fill')}</span><div class="w"><b>Set this laptop up for my talk tomorrow</b><small>Done 4 min ago · 3 changes, undo available</small></div><span class="agent-mini">Claude Code</span>${ms('chevron_right', 'chev')}</div>
    <div class="foot"><button type="button" class="btn paper">${ms('add')}New</button><button type="button" class="btn text">History</button></div>`); place(b, t, { from: 'taskbar' }, { dx: -58 }); } };

S['settings-help'] = { caption: '<b>Several settings changed.</b> A card on paper lists each with old → new and its own undo, and Undo all. The changed rows are outlined in Settings.',
  build(b, H) { desktop(b, { activeWin: 'settings', settings: { dark: true, night: true, font: true, changed: 'night' } }); pointer(b, PTR); place(b, note({ agent: 'claude', intake: WIN, you: 'Make my screen easier to read at night', blocks: [{ type: 'steps', folded: true, list: [1, 2, 3] }, { type: 'changes', title: 'Changed 3 settings', meta: 'just now', mode: 'undo', list: [{ k: 'Dark theme', w: 'Settings · Display', old: 'Off', nu: 'On' }, { k: 'Night Light', w: 'Settings · Display', old: 'Off', nu: 'Sunset to sunrise' }, { k: 'Text size', w: 'Display size and text', old: 'Default', nu: 'Large' }], foot: `<div class="btns end"><button type="button" class="btn text">${ms('undo')}Undo all</button></div>` }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Done' }), { at: PTR }); } };

S['long-output'] = { caption: '<b>Long output.</b> The note caps at 60 % of the screen height and scrolls inside. A Jump to latest pill appears when the person scrolls up while text streams; Open as a document moves it to a window.',
  build(b, H) { desktop(b, { activeWin: 'doc' }); pointer(b, [700, 300]); const paras = ['<p><b>Summary of the trip notes</b></p>', '<p>Travel is settled: flights on the 14th at 07:40 and an apartment in Alfama with check-in from 15:00. The walk from Santa Apolónia is about ten minutes.</p>', '<p>The conference runs Tuesday to Thursday. Registration opens at 08:30 on Tuesday and the keynote is at 09:15; badges can also be collected on Monday afternoon.</p>', '<p>Two things are still open: the dinner with the Porto team, and whether Thursday’s workshop needs its own ticket.</p>', '<p>Packing: HDMI adapter, a second charger, walking shoes and a light jacket. The forecast is 18 °C and mostly dry.</p>', '<p>Suggested next steps:</p><ul><li>Confirm the Porto dinner by Friday.</li><li>Email the organisers about the workshop ticket.</li><li>Check the Belém tram times for Thursday afternoon.</li></ul>', '<p>If you want, I can add the registration and keynote to your calendar and draft the email'].join(''); place(b, note({ agent: 'claude', cls: 'wide', scroll: true, running: true, intake: { kind: 'window', text: 'Notes · Trip planning' }, you: 'Summarise this document and suggest next steps', blocks: [{ type: 'answer', html: paras, caret: true }, { type: 'jump' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Answering', footRight: '<button type="button" class="btn text" style="height:24px;padding:0 8px;font-size:12px">' + ms('open_in_new') + 'Open as a document</button>' }), { at: [700, 300] }); b.querySelector('.note .scroll').scrollTop = 40; } };

S['code'] = { caption: '<b>Code.</b> Google Sans Code at 12.5/18 in a block with the language and a copy button. The note widens to 480 dp when a block arrives. Running it would be a step, with its own stop.',
  build(b, H) { desktop(b, { activeWin: 'doc' }); pointer(b, [700, 300]); place(b, note({ agent: 'opencode', cls: 'wide', intake: { kind: 'window', text: 'Files · Lisbon' }, you: 'Write a script that renames these photos by the date they were taken', blocks: [{ type: 'answer', html: '<p>This uses the date in each photo’s metadata and keeps the originals if a name already exists:</p>' }, { type: 'code', lang: 'bash', src: CODE_RENAME }, { type: 'btns', html: '<button type="button" class="btn paper">' + ms('play_arrow') + 'Run it</button><button type="button" class="btn text">' + ms('save') + 'Save as file</button>' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Done' }), { at: [700, 300] }); } };

S['images'] = { caption: '<b>Images.</b> An image the agent returns, or one the person took in, shows as a thumbnail with a caption and expands in place. A pointer region intake is cropped to the region, never the whole screen.',
  build(b, H) { desktop(b, { activeWin: 'doc', windows: ['settings', 'doc'] }); intake(b, { left: 172, top: 344, width: 560, height: 210 }, true); pointer(b, [726, 548], { halo: true }); place(b, note({ agent: 'claude', intake: { kind: 'region', text: 'Region · Notes' }, you: 'What’s the schedule here, as a table?', blocks: [{ type: 'image', h: 150, cap: 'Region you pointed at · 560×210', html: '<div style="position:absolute;inset:0;padding:14px 18px;font-size:11px;line-height:16px;color:var(--on-surface-variant);overflow:hidden"><div style="width:70%;height:8px;background:var(--outline-variant);border-radius:4px;margin:6px 0"></div><div style="width:90%;height:8px;background:var(--outline-variant);border-radius:4px;margin:6px 0"></div><div style="width:85%;height:8px;background:var(--outline-variant);border-radius:4px;margin:6px 0"></div><div style="width:60%;height:8px;background:var(--outline-variant);border-radius:4px;margin:6px 0"></div><div style="width:88%;height:8px;background:var(--outline-variant);border-radius:4px;margin:6px 0"></div></div>' }, { type: 'answer', html: '<p>From the region you pointed at:</p><table style="border-collapse:collapse;width:100%;font-size:13px"><tr><td style="padding:4px 0;color:var(--ink-soft)">Mon</td><td>Badge collection, afternoon</td></tr><tr><td style="padding:4px 0;color:var(--ink-soft)">Tue</td><td>Registration 08:30 · Keynote 09:15</td></tr><tr><td style="padding:4px 0;color:var(--ink-soft)">Wed–Thu</td><td>Conference sessions</td></tr></table>' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Done' }), { at: [726, 548] }); } };

S['no-agent'] = { caption: '<b>No agent connected.</b> First run. Quire lists the agents it found (<code>quired agents</code>) and offers to pair a computer. Nothing is connected until the person chooses.',
  build(b, H) { desktop(b, { activeWin: 'settings' }); pointer(b, PTR, { halo: true }); place(b, note({ agent: 'claude', noAgent: true, intake: WIN, blocks: [{ type: 'agents', title: 'Connect an agent', msg: 'Quire works with the agents you already have. These are installed in your Linux environment:', list: [{ ini: 'CC', col: '#5B5D72', t: 'Claude Code', sub: 'v2.1 · signed in' }, { ini: 'oc', col: '#72557B', t: 'opencode', sub: 'v1.4 · signed in' }, { ini: 'Cu', col: '#5E5E68', t: 'Cursor', sub: 'needs sign-in' }], foot: `<div class="btns end"><button type="button" class="btn text">${ms('computer')}Pair a computer</button><button type="button" class="btn filled">Connect Claude Code</button></div>` }], composer: false, foot: '' }), { at: PTR }); } };

S['offline'] = { caption: '<b>Offline.</b> A paired computer or a cloud agent is unreachable. The note says which, keeps the prompt, and offers a local agent. Local agents are unaffected.',
  build(b, H) { desktop(b, { activeWin: 'settings' }); pointer(b, PTR); place(b, note({ agent: 'codex', intake: WIN, you: 'Make my screen easier to read at night', blocks: [{ type: 'result', icon: 'cloud_off', cls: 'warn', msg: 'Brian’s desk can’t be reached', sub: 'No connection to the paired computer. Your prompt is kept.' }, { type: 'btns', end: true, html: '<button type="button" class="btn text">' + ms('refresh') + 'Retry</button><button type="button" class="btn paper">Use Claude Code on this laptop</button>' }], composer: { text: 'Make my screen easier to read at night' }, foot: 'Offline' }), { at: PTR }); } };

S['glass-off'] = { caption: '<b>Blur off.</b> Battery saver, thermal SEVERE, Developer options or the platform’s own switch turn window blur off (<code>WindowManager.isCrossWindowBlurEnabled()</code>, C). The note becomes paper at 96 %, keeps its shadow and a dimmer rim, and loses the bloom. Every loop stops too (economy).',
  build(b, H) { b.dataset.glass = 'off'; b.dataset.motion = 'off'; desktop(b, { activeWin: 'settings' }); pointer(b, PTR); place(b, note({ agent: 'claude', intake: WIN, you: 'Turn on dark theme', blocks: [{ type: 'steps', list: STEPS_DARK }, { type: 'result', msg: 'Dark theme is on.', sub: 'Changed 1 setting · 2 s' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Done' }), { at: PTR }); anno(b, PTR[0] + 20, PTR[1] - 40, 'blur off: paper at 96 %, no bloom, rim at 60 %, no loops'); } };

const ORDER = ['idle', 'invoke-shake', 'invoke-key', 'open', 'invoke-taskbar', 'invoke-secure', 'invoke-voice', 'invoke-selection', 'compose', 'agent-picker', 'streaming', 'steps', 'setting-undo', 'plan', 'confirm-destructive', 'consent-command', 'consent-system', 'mirror', 'mirror-paused', 'done', 'stopped', 'error', 'signin', 'background', 'settings-help', 'long-output', 'code', 'images', 'no-agent', 'offline', 'glass-off'];

/* ------------------------------------------------------------------------------------------ gallery / single */
function makeBoard(id, theme, size, frozen = true) {
  const fig = h('figure');
  const board = h('div', 'artboard' + (frozen ? ' frozen' : ''));
  board.dataset.theme = theme; board.dataset.size = size; board.id = 'b-' + id + '-' + theme;
  if (qs.get('wall')) board.dataset.wall = qs.get('wall');
  fig.appendChild(board);
  const cap = h('figcaption', '', (S[id].caption || '') + `<span class="id">${id}${theme === 'dark' ? ' · dark' : ''}</span>`);
  fig.appendChild(cap);
  return { fig, board };
}
function renderScreen(id, theme, size, frozen = true, noAnno = false) {
  const { fig, board } = makeBoard(id, theme, size, frozen);
  document.getElementById('gallery').appendChild(fig);
  if (noAnno) board.classList.add('no-anno');
  S[id].build(board, size === 'g14' ? 1200 : 1080, theme);
  return board;
}

/* ------------------------------------------------------------------------------------------ spring solver */
function spring(opts) { // {from,to,stiffness,damping,velocity,onUpdate,onEnd}
  if (PLAY.reduce) { opts.onUpdate(opts.to); opts.onEnd && opts.onEnd(); return { stop() {} }; }
  let x = opts.from, v = opts.velocity || 0, t0 = null, raf, stopped = false;
  const k = opts.stiffness, c = 2 * opts.damping * Math.sqrt(k); // mass 1
  function frame(t) {
    if (stopped) return;
    if (t0 == null) t0 = t;
    let dt = Math.min(0.064, (t - t0) / 1000); t0 = t;
    const steps = Math.max(1, Math.ceil(dt / 0.004)); const sdt = dt / steps;
    for (let i = 0; i < steps; i++) { const a = -k * (x - opts.to) - c * v; v += a * sdt; x += v * sdt; }
    if (Math.abs(x - opts.to) < 0.0015 && Math.abs(v) < 0.01) { x = opts.to; opts.onUpdate(x); opts.onEnd && opts.onEnd(); return; }
    opts.onUpdate(x); raf = requestAnimationFrame(frame);
  }
  raf = requestAnimationFrame(frame);
  return { stop() { stopped = true; cancelAnimationFrame(raf); } };
}

/* ------------------------------------------------------------------------------------------ play mode */
// States: idle · halo · compose · listening · working · consent · sysconsent · mirror · done.
// `running` is true from send until the run ends. `hidden` is true while the note is folded behind the taskbar
// button with the task still running (backgrounded); it is never true for a stopped task.
// Esc never hides a running task: it stops it (and answers an open permission request as cancelled).
// Hiding is a separate action: the quiet line's ×, Meta+Space, the taskbar button, or a click elsewhere.
const PLAY = { reduce: false, board: null, state: 'idle', note: null, ptr: [960, 540], halo: null, intakeEl: null, timers: [], anchor: null, running: false, hidden: false, agent: 'claude', last: null, lastCls: '', trace: [] };
function clearTimers() { PLAY.timers.forEach(clearTimeout); PLAY.timers = []; }
function later(fn, t) { const id = setTimeout(fn, PLAY.reduce ? 0 : t); PLAY.timers.push(id); return id; }
function trace(ev, data) { const e = Object.assign({ t: Math.round(performance.now()), ev, state: PLAY.state, running: PLAY.running, hidden: PLAY.hidden }, data || {}); PLAY.trace.push(e); console.log('quire:' + JSON.stringify(e)); }
window.QUIRE_PLAY = PLAY;

function playInit(theme, size) {
  document.body.classList.add('play');
  const { fig, board } = makeBoard('idle', theme, size, false);
  document.getElementById('gallery').appendChild(fig);
  board.classList.add('no-anno');
  PLAY.board = board;
  const H = size === 'g14' ? 1200 : 1080;
  const tb = desktop(board, { activeWin: 'settings' });
  board.querySelector('.taskbar .tb-quire').addEventListener('click', e => { e.stopPropagation(); onTaskbar(); });
  const p = pointer(board, PLAY.ptr); PLAY.ptrEl = p;
  board.style.cursor = 'none';
  const hud = h('div', 'hud', `<label><input type="checkbox" id="reduce"> Remove animations</label><label><input type="checkbox" id="glass"> Blur off</label><span class="k">shake · Meta/Alt+Space · click the leaf · hold the mic · select text · Esc stops · Meta+Space hides</span>`);
  document.body.appendChild(hud);
  hud.querySelector('#reduce').addEventListener('change', e => { PLAY.reduce = e.target.checked; board.classList.toggle('frozen', PLAY.reduce); });
  hud.querySelector('#glass').addEventListener('change', e => { document.body.dataset.glass = e.target.checked ? 'off' : ''; document.body.dataset.motion = e.target.checked ? 'off' : ''; });
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) { PLAY.reduce = true; hud.querySelector('#reduce').checked = true; board.classList.add('frozen'); }
  if (qs.get('glass') === '0') { hud.querySelector('#glass').checked = true; document.body.dataset.glass = 'off'; document.body.dataset.motion = 'off'; }

  // pointer + shake detection (range + reversals, after GestureDetectionInteractor's idea; each stroke must travel)
  const hist = [];
  board.addEventListener('mousemove', e => {
    const r = board.getBoundingClientRect(); const x = e.clientX - r.left, y = e.clientY - r.top;
    PLAY.ptr = [x, y]; p.style.left = x + 'px'; p.style.top = y + 'px';
    if (PLAY.halo && PLAY.state === 'halo') { PLAY.halo.style.left = (x + 4) + 'px'; PLAY.halo.style.top = (y + 3) + 'px'; }
    const now = performance.now(); hist.push({ x, t: now }); while (hist.length && now - hist[0].t > 450) hist.shift();
    if (PLAY.state !== 'idle' || PLAY.hidden || hist.length < 6) return;
    let rev = 0, min = 1e9, max = -1e9;
    for (let i = 2; i < hist.length; i++) { const a = hist[i - 1].x - hist[i - 2].x, b = hist[i].x - hist[i - 1].x; if (a * b < 0 && Math.abs(b) > 3) rev++; }
    for (const q of hist) { min = Math.min(min, q.x); max = Math.max(max, q.x); }
    if (rev >= 3 && max - min > 60) { hist.length = 0; invoke({ at: PLAY.ptr.slice(), via: 'shake' }); }
  });
  document.addEventListener('keydown', e => {
    if ((e.metaKey || e.altKey || e.ctrlKey) && e.code === 'Space') { e.preventDefault(); onAssistKey(); return; }
    if (e.key === 'Escape') { e.preventDefault(); onEscape(); return; }
    if (PLAY.state === 'compose' && PLAY.field && !PLAY.hidden) {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); return; }
      if (e.key === 'Backspace') { PLAY.text = PLAY.text.slice(0, -1); drawField(); return; }
      if (e.key.length === 1 && !e.metaKey && !e.ctrlKey && !e.altKey) { PLAY.text += e.key; drawField(); }
    }
  });
  // Mouse: the mic is press-and-hold (mousedown/mouseup); everything else activates on click, so a focused
  // button's Enter or Space (which fire click) takes the same path as the mouse.
  board.addEventListener('mousedown', e => {
    const t = e.target.closest('[data-act]');
    if (t) { if (t.dataset.act === 'mic') act('mic', t); return; }
    if (e.target.closest('.note, .tray, .sel-toolbar, .sel-menu, .sysdialog, .taskbar')) return;
    if (PLAY.state === 'halo') { cancelHalo(); return; }
    if (PLAY.state !== 'idle' && !PLAY.hidden) { if (PLAY.running) background('click elsewhere'); else closeNote(); }
  });
  board.addEventListener('click', e => { const t = e.target.closest('[data-act]'); if (t && t.dataset.act !== 'mic') act(t.dataset.act, t); });
  board.addEventListener('mouseup', () => { if (PLAY.state === 'listening') releaseMic(); });
  // text selection in the doc → floating toolbar
  board.addEventListener('mouseup', e => {
    const sel = window.getSelection(); if (PLAY.state !== 'idle' || PLAY.hidden || !sel || sel.isCollapsed || !sel.anchorNode) return;
    const docEl = board.querySelector('.doc .doc-body'); if (!docEl || !docEl.contains(sel.anchorNode)) return;
    const rect = sel.getRangeAt(0).getBoundingClientRect(), r = board.getBoundingClientRect();
    const [tb, menu] = selToolbar(board, rect.left - r.left, rect.top - r.top - 52, false);
    PLAY.selText = sel.toString().trim().slice(0, 80); PLAY.selTb = tb; PLAY.selMenu = menu;
  });
}
function onTaskbar() {
  if (PLAY.hidden) return reopen();
  if (PLAY.state === 'idle') return invoke({ from: 'taskbar' });
  if (PLAY.running) return background('taskbar button');
  closeNote();
}
function onAssistKey() {
  if (PLAY.hidden) return reopen();
  if (PLAY.state === 'idle') return invoke({ at: PLAY.ptr.slice(), via: 'key' });
  if (PLAY.running) return background('Meta+Space');
}
function onEscape() {
  if (PLAY.hidden) return;                       // the note is away; Esc belongs to whatever has focus
  switch (PLAY.state) {
    case 'idle': return;
    case 'halo': return cancelHalo();
    case 'listening': return cancelMic();
    case 'compose': if (PLAY.note && PLAY.note.querySelector('.picker')) return act('picker'); return closeNote();
    case 'done': return closeNote();
    default: return stopRun('Esc');            // working · consent · sysconsent · mirror
  }
}
function cancelHalo() { clearTimers(); PLAY.halo && PLAY.halo.remove(); PLAY.halo = null; PLAY.intakeEl && PLAY.intakeEl.remove(); PLAY.intakeEl = null; PLAY.label && PLAY.label.remove(); PLAY.label = null; PLAY.state = 'idle'; trace('halo cancelled'); }

function invoke(anchor) {
  const b = PLAY.board; PLAY.anchor = anchor; PLAY.state = 'halo'; PLAY.text = ''; PLAY.last = null; PLAY.lastCls = '';
  if (anchor.at) {
    const [x, y] = anchor.at;
    const ha = h('div', 'halo'); ha.style.left = (x + 4) + 'px'; ha.style.top = (y + 3) + 'px'; ha.style.transform = 'scale(0)'; b.appendChild(ha); PLAY.halo = ha;
    spring({ from: 0, to: 1, ...MOTION.spring.tick, onUpdate: v => ha.style.transform = `scale(${v})` });
    if (anchor.via === 'key') { const l = h('div', 'halo-label', `${LEAF}Quire <kbd>Meta</kbd><kbd>Space</kbd>`); l.style.left = (x + 28) + 'px'; l.style.top = (y - 6) + 'px'; l.style.opacity = 0; l.style.transition = `opacity ${MOTION.fade}ms ${MOTION.easing.standard}`; b.appendChild(l); requestAnimationFrame(() => l.style.opacity = 1); PLAY.label = l; }
    // intake: the window under the pointer
    const win = [...b.querySelectorAll('.window')].reverse().find(w => { const r = w.getBoundingClientRect(), rb = b.getBoundingClientRect(); const px = x + rb.left, py = y + rb.top; return px >= r.left && px <= r.right && py >= r.top && py <= r.bottom; });
    if (win) { const i = intake(b, { left: win.offsetLeft, top: win.offsetTop, width: win.offsetWidth, height: win.offsetHeight }); i.style.opacity = 0; i.style.transition = `opacity ${MOTION.fade}ms`; requestAnimationFrame(() => i.style.opacity = 1); PLAY.intakeEl = i; PLAY.intakeName = win.classList.contains('settings') ? 'Settings · Display' : win.classList.contains('browser') ? 'Chrome' : 'Notes · Trip planning'; }
    else PLAY.intakeName = null;
    later(() => openNote(anchor), MOTION.halo + 60);
  } else { PLAY.intakeName = null; openNote(anchor); }
}
function noteState(extra = {}) {
  const base = { agent: PLAY.agent, running: PLAY.running, intake: PLAY.intakeName ? { kind: 'window', text: PLAY.intakeName } : (PLAY.anchor && PLAY.anchor.selection ? { kind: 'selection', text: PLAY.anchor.selection } : { kind: 'none' }) };
  return Object.assign(base, extra);
}
// Out from the pen tip (§5.2): the sheet unrolls from its origin (clip from 0 to full height, 220 ms, emphasised
// decelerate) while it scales 0.6 → 1 with spring.unfold and fades in over 120 ms; the rim lights up over the
// last 200 ms. With Remove animations, a cut.
function unfold(n) {
  n.style.opacity = 0; n.style.transform = 'scale(.6)';
  const oy = n.style.getPropertyValue('--oy'), fromBottom = oy === '100%';
  n.style.setProperty('--holo-a', '0');
  if (!PLAY.reduce) n.style.clipPath = fromBottom ? `inset(100% 0 0 0 round 28px)` : `inset(0 0 100% 0 round 28px)`;
  requestAnimationFrame(() => {
    n.style.transition = `opacity ${MOTION.fade}ms ${MOTION.easing.standard}, clip-path ${MOTION.unroll}ms ${MOTION.easing.decel}`; n.style.opacity = 1; n.style.clipPath = 'inset(0 0 0 0 round 28px)';
    later(() => { n.style.transition += `, --holo-a ${MOTION.rim}ms ${MOTION.easing.standard}`; n.style.removeProperty('--holo-a'); }, MOTION.unroll - 60);
  });
  spring({ from: 0.6, to: 1, ...MOTION.spring.unfold, onUpdate: v => n.style.transform = `scale(${v})`, onEnd: () => { n.style.transform = ''; n.style.clipPath = ''; n.style.transition = ''; } });
}
function openNote(anchor) {
  const b = PLAY.board; PLAY.state = 'compose';
  PLAY.label && (PLAY.label.style.opacity = 0, later(() => PLAY.label && PLAY.label.remove(), MOTION.fade));
  const n = note(noteState({ composer: { focus: true } }));
  const geo = place(b, n, anchor); PLAY.note = n; PLAY.geo = geo; wire(n); unfold(n);
  if (PLAY.halo) { const ha = PLAY.halo; later(() => { ha.style.transition = `opacity ${MOTION.fadeSlow}ms`; ha.style.opacity = 0; later(() => ha.remove(), MOTION.fadeSlow); }, 240); PLAY.halo = null; }
  trace('note opened', { via: anchor.via || anchor.from });
}
function wire(n) {
  n.querySelectorAll('[data-role="close"]').forEach(e => e.dataset.act = 'close');
  n.querySelectorAll('[data-role="background"]').forEach(e => e.dataset.act = 'background');
  const mic = n.querySelector('.mic'); if (mic) { mic.dataset.act = 'mic'; }
  const send = n.querySelector('.send'); if (send) send.dataset.act = 'send';
  const agent = n.querySelector('[data-role="agent"]'); if (agent) agent.dataset.act = 'picker';
  n.querySelectorAll('.btn').forEach(bt => {
    const t = bt.textContent.trim(), k = bt.dataset.kind;
    if (k) { bt.dataset.act = /^allow/.test(k) ? 'allow' : 'deny'; return; }   // consent options, by ACP kind
    if (bt.dataset.act) return;                                                   // mirror and destructive controls carry data-act in their markup
    if (/Undo|Turn it back on/.test(t)) bt.dataset.act = 'undo'; if (/Try again/.test(t)) bt.dataset.act = 'retry';
  });
  n.querySelectorAll('.picker .it').forEach((it, i) => { it.dataset.act = 'pick'; it.dataset.agent = ['claude', 'opencode', 'cursor', 'codex', 'add'][i]; });
  PLAY.field = n.querySelector('.field .text');
}
function drawField() { if (!PLAY.field) return; PLAY.field.className = 'text' + (PLAY.text ? '' : ' ph'); PLAY.field.innerHTML = (PLAY.text || 'Ask Quire') + '<span class="caret"></span>'; const s = PLAY.note.querySelector('.send'); s && s.classList.toggle('disabled', !PLAY.text); }
// focus: the consent card when it arrives (its first Tab stop is the agent's reject option); the destructive card's
// Keep; Resume when paused; the result's first button when a run ends (§6.2)
function focusConsent() { const c = PLAY.note && PLAY.note.querySelector('.card.consent, .card.destructive'); if (c) { c.focus(); trace('focus', { on: c.classList.contains('destructive') ? 'destructive card' : 'consent card' }); } }
function focusAct(a) { const b = PLAY.note && PLAY.note.querySelector(`[data-act="${a}"]`); if (b) { b.focus(); trace('focus', { on: a }); } }
function focusResult() { const b = PLAY.note && PLAY.note.querySelector('.n-body .btns .btn, .n-body .undo-pill'); if (b) { b.focus(); trace('focus', { on: b.textContent.trim() }); } }

function swap(extra, cls) { // re-render the note in place and spring its size; while hidden, only remember the state
  PLAY.last = extra; PLAY.lastCls = cls || (extra.mirror ? 'mirror' : extra.listening ? 'listening' : '');
  if (PLAY.hidden || !PLAY.note) { tbIndicator(); return null; }
  const b = PLAY.board, old = PLAY.note; const n = note(noteState(extra)); if (cls) n.classList.add(cls);
  const ox = old.style.getPropertyValue('--ox'), oy = old.style.getPropertyValue('--oy');
  n.style.left = old.style.left; n.style.top = old.style.top; n.style.setProperty('--ox', ox); n.style.setProperty('--oy', oy);
  const h0 = old.offsetHeight, w0 = old.offsetWidth; old.replaceWith(n); PLAY.note = n; wire(n); mirrorLayout(n);
  const h1 = n.offsetHeight, w1 = n.offsetWidth;
  // keep the note on screen when it grows
  const W = b.clientWidth, H = b.clientHeight; let x = parseFloat(n.style.left), y = parseFloat(n.style.top);
  if (x + w1 > W - 24) x = Math.max(24, W - 24 - w1); if (y + h1 > H - 80) y = Math.max(40, H - 80 - h1);
  n.style.left = x + 'px'; n.style.top = y + 'px';
  if (h0 !== h1 || w0 !== w1) { const sp = w1 !== w0 ? MOTION.spring.expand : MOTION.spring.settle; n.style.overflow = 'hidden'; spring({ from: 0, to: 1, ...sp, onUpdate: v => { n.style.height = (h0 + (h1 - h0) * v) + 'px'; n.style.width = (w0 + (w1 - w0) * v) + 'px'; }, onEnd: () => { n.style.height = ''; n.style.width = ''; n.style.overflow = ''; } }); }
  // the marks that were just drawn are drawn once; the next re-render shows them at rest
  (extra.blocks || []).forEach(bl => (bl.list || []).forEach(s => { delete s.fresh; }));
  if (extra.mirror) extra.mirror.steps.forEach(s => { delete s.fresh; });
  delete extra.fresh;
  tbIndicator();
  return n;
}
// The taskbar button: breathes while an app is driven (mirror) or while a hidden task runs; a ring shows a hidden
// task's progress; a badge counts hidden tasks that need an answer. Nothing shows for a stopped or finished task.
function tbIndicator() {
  const tb = PLAY.board.querySelector('.taskbar .tb-quire'); tb.querySelectorAll('.badge, .ring').forEach(e => e.remove());
  const needs = PLAY.state === 'consent' || PLAY.state === 'sysconsent';
  tb.classList.toggle('running', PLAY.running && (PLAY.state === 'mirror' || PLAY.hidden));
  if (!PLAY.hidden || !PLAY.running) { tb.setAttribute('aria-label', 'Quire'); return; }
  if (needs) { tb.insertAdjacentHTML('beforeend', '<span class="badge">1</span>'); tb.setAttribute('aria-label', 'Quire, 1 task running, 1 needs your answer'); return; }
  const steps = PLAY.m ? PLAY.m.steps : (PLAY.last && (PLAY.last.blocks || []).filter(b => b.type === 'steps').map(b => b.list)[0]);
  if (steps && steps.length) tb.insertAdjacentHTML('beforeend', ring(steps.filter(s => s.st === 'done').length / steps.length));
  tb.setAttribute('aria-label', 'Quire, 1 task running');
}
function send() {
  const t = PLAY.text.trim(); if (!t) return;
  PLAY.state = 'working'; PLAY.running = true; const you = t; PLAY.you = you; PLAY.sent = true; trace('send', { you });
  const lower = t.toLowerCase();
  if (/delete|remove|uninstall|clear/.test(lower)) return runDestructive(you);
  if (/chrome|browser|go to|open .* and|news|\.com/.test(lower)) return runTools(you);
  if (/bluetooth|in settings|find/.test(lower)) return runMirror(you);
  if (/battery|bright|night|read|dark|text|bigger|setting|theme/.test(lower)) return runSetting(you);
  return runAnswer(you);
}
// the first re-render after send writes the prompt in ink and draws the rule; later ones show it at rest
function firstDraw(extra) { if (PLAY.sent) { extra.fresh = true; PLAY.sent = false; } return extra; }
function runAnswer(you) {
  swap(firstDraw({ you, thinking: true, blocks: [{ type: 'thought', t: 'Thinking' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Thinking' }));
  const words = ANSWER_ADAPTIVE.replace(/<[^>]+>/g, '').split(' '); let i = 0, shown = 0;
  later(function tick() { const from = shown; i = Math.min(words.length, i + 3); const end = i >= words.length; if (end) { PLAY.running = false; PLAY.state = 'done'; }
    swap({ you, thinking: !end, blocks: [{ type: 'answer', html: '<p>' + inkWords(words.slice(0, i).join(' '), from) + '</p>', caret: !end }], composer: { placeholder: 'Ask a follow-up' }, foot: end ? 'Done' : 'Answering' }); shown = i;
    if (!end) later(tick, 90); else trace('run ended', { how: 'end_turn' }); }, 700);
}
// Q6: "turn on dark theme" is a tool call that acts at once; the step carries its undo. No card.
function runSetting(you) {
  const list = STEPS_DARK.map(s => ({ ...s, st: 'pending', undo: false }));
  const draw = (extra) => swap(firstDraw(Object.assign({ you, thinking: true, blocks: [{ type: 'steps', list }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Working' }, extra)));
  draw();
  later(() => { list[0].st = 'running'; draw(); }, 500);
  later(() => { list[0].st = 'done'; list[0].fresh = true; list[1].st = 'running'; draw(); }, 1300);
  later(() => { list[1].st = 'done'; list[1].fresh = true; list[1].undo = true; PLAY.running = false; PLAY.state = 'done'; PLAY.steps = list;
    const sw = PLAY.board.querySelector('.window.settings'); if (sw) sw.replaceWith(settingsWindow({ settings: { dark: true, changed: 'dark' } }, PLAY.board.clientHeight));
    swap({ you, blocks: [{ type: 'steps', list }, { type: 'result', msg: 'Dark theme is on.', sub: 'Changed 1 setting · 2 s' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Done' }); focusResult(); trace('run ended', { how: 'end_turn' }); }, 2100);
}
// Q6: "open chrome and go to fox news": two tool calls, no question; Chrome appears behind the note.
function runTools(you) {
  const list = STEPS_CHROME.map(s => ({ ...s, st: 'pending' }));
  const draw = () => swap(firstDraw({ you, thinking: true, blocks: [{ type: 'steps', list }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Working' }));
  draw();
  later(() => { list[0].st = 'running'; draw(); }, 400);
  later(() => { list[0].st = 'done'; list[0].fresh = true; list[1].st = 'running'; draw(); const b = PLAY.board; if (!b.querySelector('.window.browser')) { const w = browserWindow({}, b.clientHeight); w.style.opacity = 0; w.style.transition = `opacity ${MOTION.fadeSlow}ms`; b.insertBefore(w, b.querySelector('.taskbar')); requestAnimationFrame(() => w.style.opacity = 1); } }, 1300);
  later(() => { list[1].st = 'done'; list[1].fresh = true; PLAY.running = false; PLAY.state = 'done'; PLAY.steps = list;
    swap({ you, blocks: [{ type: 'steps', list }, { type: 'result', msg: 'Chrome is on foxnews.com.', sub: '2 steps · 3 s' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Done' }); focusResult(); trace('run ended', { how: 'end_turn' }); }, 2400);
}
// Q6: a destructive action is the one thing that asks first. Quire's own card; Keep is the default.
function runDestructive(you) {
  const list = [{ st: 'running', kind: 'read', t: 'Reading Downloads' }];
  swap(firstDraw({ you, thinking: true, blocks: [{ type: 'steps', list }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Working' }));
  later(() => { list[0].st = 'done'; list[0].fresh = true; PLAY.state = 'consent'; PLAY.pending = { list, you, destructive: true }; trace('destructive confirmation shown', { file: 'report-draft.pdf' });
    swap({ you, blocks: [{ type: 'steps', list }, { type: 'destructive', title: 'Delete this file?', file: { ic: 'picture_as_pdf', name: 'report-draft.pdf', sub: 'Downloads · 2.4 MB · today 11:40' }, why: 'It goes to the bin and can be restored from Files for 30 days.', go: 'Delete', keep: 'Keep it' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Waiting for you' });
    focusConsent(); later(() => focusAct('keep'), 0); }, 1100);
}
function afterDestroy(go) {
  const { list, you } = PLAY.pending; PLAY.pending = null; trace('destructive confirmation answered', { outcome: go ? 'delete' : 'keep' });
  if (!go) { PLAY.running = false; PLAY.state = 'done'; swap({ you, blocks: [{ type: 'steps', list }, { type: 'result', icon: 'block', cls: 'warn', msg: 'Nothing was deleted.', sub: 'You kept the file. The agent stopped.' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Stopped' }); focusResult(); trace('run ended', { how: 'kept' }); return; }
  PLAY.state = 'working'; list.push({ st: 'running', kind: 'delete', t: 'Deleting', val: 'report-draft.pdf' });
  swap({ you, thinking: true, blocks: [{ type: 'steps', list }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Working' });
  later(() => { list[1].st = 'done'; list[1].fresh = true; list[1].undo = true; PLAY.running = false; PLAY.state = 'done'; swap({ you, blocks: [{ type: 'steps', list }, { type: 'result', msg: 'report-draft.pdf is in the bin.', sub: 'Restore it from Files within 30 days, or undo here.' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Done' }); focusResult(); trace('run ended', { how: 'end_turn' }); }, 900);
}
function answerPermission(outcome, optionId) { // what goes back on the wire: {outcome:'selected', optionId} or {outcome:'cancelled'}
  trace('request_permission answered', optionId ? { outcome, optionId } : { outcome }); PLAY.pending = null;
}
// Honest copy for a stop: what was done, what was interrupted (and may be partly applied), what to check.
function stopCopy(st, steps) {
  if (st === 'consent') return { msg: 'Stopped.', sub: 'You stopped the task before answering. Nothing was deleted or changed.' };
  if (st === 'sysconsent') return { msg: 'Stopped.', sub: 'Settings was not opened. Nothing was changed.' };
  if (!steps) return { msg: 'Stopped.', sub: 'The answer was cut off. Nothing was changed.' };
  const done = steps.filter(s => s.st === 'done' && s.effect).map(s => s.effect), cut = steps.find(s => s.st === 'running');
  const n = steps.filter(s => s.st === 'done').length, parts = [];
  if (st === 'mirror') parts.push('Settings was closed.');
  if (done.length) parts.push(done.join('. ') + '.');
  if (cut && cut.effect) parts.push(`${cut.t} ${cut.val || ''} was interrupted and may be partly applied; check ${cut.where || 'Settings'}.`);
  else if (cut) parts.push(`${cut.t} was interrupted.`);
  if (!done.length && !(cut && cut.effect)) parts.push('Nothing was changed.');
  return { msg: `Stopped after ${n} of ${steps.length} steps.`, sub: parts.join(' '), undo: done.length > 0 };
}
function stopRun(how) { // Esc or Stop: cancel the run. Not hiding; the task ends here.
  const b = PLAY.board, st = PLAY.state; clearTimers();
  PLAY.sys && PLAY.sys.remove(); PLAY.sys = null;
  if (st === 'consent' && PLAY.pending && !PLAY.pending.destructive) answerPermission('cancelled');
  const steps = st === 'mirror' && PLAY.m ? PLAY.m.steps : (PLAY.pending ? PLAY.pending.list : (PLAY.steps || ((PLAY.last && PLAY.last.blocks || []).filter(x => x.type === 'steps').map(x => x.list)[0])));
  const copy = stopCopy(st, steps);
  const shown = steps ? steps.filter(s => s.st !== 'pending').map(s => s.st === 'running' ? { ...s, st: 'failed' } : s) : null;
  const prior = (PLAY.last && PLAY.last.blocks || []).filter(x => x.type === 'answer' || x.type === 'plan').map(x => x.type === 'answer' ? { ...x, caret: false } : x);
  PLAY.running = false; PLAY.state = 'done'; PLAY.m = null; PLAY.pending = null; PLAY.steps = null;
  swap({ you: PLAY.you, blocks: [...prior, ...(shown ? [{ type: 'steps', list: shown }] : []), { type: 'result', icon: 'stop_circle', cls: 'warn', msg: copy.msg, sub: copy.sub }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Stopped' });
  focusResult(); trace('run ended', { how: 'cancelled by ' + how, from: st });
}
function runMirror(you) {
  const list = [{ st: 'running', kind: 'read', t: 'Listing apps' }, { st: 'pending', kind: 'app', t: 'Asking to use Settings' }];
  swap(firstDraw({ you, thinking: true, blocks: [{ type: 'steps', list }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Working' }));
  later(() => { list[0].st = 'done'; list[0].fresh = true; list[1].st = 'running'; PLAY.state = 'sysconsent'; PLAY.you = you; swap({ you, thinking: true, blocks: [{ type: 'steps', list }, { type: 'result', icon: 'shield', cls: 'warn', msg: 'Waiting for your permission', sub: 'The system is asking whether Claude Code may use Settings.' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Waiting for you' });
    const d = h('div', 'sysdialog', `<span class="lbl">System dialog (platform)</span>${ms('shield', 'big fill')}<h3>Allow Claude Code to use Settings?</h3><p>Quire will run Settings on a separate screen that you can watch. Claude Code can tap, type and take screenshots there. Secure screens stay hidden, and you can take over at any time.</p><div class="btns"><button type="button" class="btn text" data-act="sys-deny">Don’t allow</button><button type="button" class="btn filled" data-act="sys-allow">Allow</button></div>`);
    d.setAttribute('role', 'dialog'); d.setAttribute('aria-label', 'Allow Claude Code to use Settings?');
    const b = PLAY.board; d.style.left = (b.clientWidth / 2 - 210) + 'px'; d.style.top = (b.clientHeight / 2 - 140) + 'px'; d.style.opacity = 0; d.style.transition = `opacity ${MOTION.fadeSlow}ms`; b.appendChild(d); requestAnimationFrame(() => d.style.opacity = 1); PLAY.sys = d;
    d.querySelector('[data-act="sys-deny"]').focus(); trace('platform consent shown'); }, 900);
}
function mirrorOpen() {
  const you = PLAY.you; PLAY.state = 'mirror';
  const steps = [{ st: 'done', kind: 'app', t: 'Opened Settings' }, { st: 'running', kind: 'execute', t: 'Tapping Connected devices' }, { st: 'pending', kind: 'execute', t: 'Turning off Bluetooth', effect: 'Bluetooth was turned off', where: 'Settings · Connected devices' }];
  const m = { title: 'Settings', ghost: [960, 640], tap: false, target: null, settings: { page: 'display' }, steps, status: 'Step 1 of 3' };
  const draw = () => swap({ you, thinking: !m.paused, mirror: m }, 'mirror');
  draw(); PLAY.m = m; PLAY.mDraw = draw;
  later(() => { m.ghost = null; m.tap = true; m.target = '.nav .row:nth-of-type(3)'; m.status = 'Step 2 of 3'; draw(); }, 1200);
  later(() => { if (m.paused) return; steps[1].st = 'done'; steps[1].fresh = true; steps[2].st = 'running'; m.title = 'Connected devices'; m.settings = { page: 'devices' }; m.ghost = null; m.tap = true; m.target = '.page .pref:nth-of-type(1)'; m.status = 'Step 3 of 3'; draw(); }, 2600);
  later(() => { if (m.paused) return; mirrorDone(); }, 4200);
}
function mirrorDone() {
  const m = PLAY.m, steps = m.steps; steps.forEach(s => { if (s.st === 'running') { s.st = 'done'; s.fresh = true; } }); m.ghost = null; m.target = null; m.status = 'Done'; PLAY.running = false; PLAY.state = 'done'; PLAY.m = null;
  swap({ you: PLAY.you, blocks: [{ type: 'steps', folded: true, list: steps }, { type: 'result', msg: 'Bluetooth is off.', sub: 'Settings was returned to you · 3 steps' }, { type: 'btns', html: '<button type="button" class="btn paper">' + ms('undo') + 'Turn it back on</button>' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Done' });
  focusResult(); trace('run ended', { how: 'end_turn' });
}
function act(a, el) {
  const b = PLAY.board;
  switch (a) {
    case 'close': if (PLAY.running) background('hide button'); else closeNote(); break;
    case 'background': background('hide button'); break;
    case 'send': send(); break;
    case 'mic': if (PLAY.state === 'compose') startMic(); break;
    case 'picker': { const open = !!PLAY.note.querySelector('.picker'); swap({ composer: { text: PLAY.text, focus: !open }, picker: open ? null : { sel: PLAY.agent } }); break; }
    case 'pick': if (el.dataset.agent && el.dataset.agent !== 'add') PLAY.agent = el.dataset.agent; swap({ composer: { text: PLAY.text, focus: true } }); break;
    case 'allow': if (PLAY.state === 'consent' && PLAY.pending && !PLAY.pending.destructive) answerPermission('selected', el.dataset.option); break;
    case 'deny': if (PLAY.state === 'consent' && PLAY.pending && !PLAY.pending.destructive) answerPermission('selected', el.dataset.option); break;
    case 'keep': if (PLAY.state === 'consent' && PLAY.pending && PLAY.pending.destructive) afterDestroy(false); break;
    case 'destroy': if (PLAY.state === 'consent' && PLAY.pending && PLAY.pending.destructive) afterDestroy(true); break;
    case 'sys-allow': PLAY.sys.remove(); PLAY.sys = null; trace('platform consent', { outcome: 'allowed' }); mirrorOpen(); break;
    case 'sys-deny': PLAY.sys.remove(); PLAY.sys = null; PLAY.running = false; PLAY.state = 'done'; trace('platform consent', { outcome: 'denied' }); swap({ you: PLAY.you, blocks: [{ type: 'result', icon: 'block', cls: 'warn', msg: 'Settings was not opened.', sub: 'You didn’t allow computer control. The agent stopped.' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Stopped' }); break;
    case 'pause': if (PLAY.m) { PLAY.m.paused = !PLAY.m.paused; PLAY.m.status = PLAY.m.paused ? 'Paused by you' : 'Resuming'; PLAY.mDraw(); trace(PLAY.m.paused ? 'paused' : 'resumed'); if (PLAY.m.paused) focusAct('pause'); else later(() => { if (PLAY.m) mirrorDone(); }, 1500); } break;
    case 'stop': if (PLAY.m) stopRun('Stop button'); break;
    case 'takeover': if (PLAY.m) { clearTimers(); const steps = PLAY.m.steps, done = steps.filter(s => s.st === 'done' && s.effect).map(s => s.effect); PLAY.running = false; PLAY.state = 'done'; PLAY.m = null;
      swap({ you: PLAY.you, blocks: [{ type: 'steps', folded: true, list: steps }, { type: 'result', icon: 'open_in_full', msg: 'Settings is on your screen now.', sub: 'The agent stopped. ' + (done.length ? done.join('. ') + '.' : 'Bluetooth was not changed yet.') }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Handed over' });
      const H = b.clientHeight; const w = settingsWindow({ settings: {} }, H); w.style.opacity = 0; w.style.transition = `opacity ${MOTION.fadeSlow}ms`; b.insertBefore(w, b.querySelector('.taskbar')); requestAnimationFrame(() => w.style.opacity = 1); focusResult(); trace('run ended', { how: 'taken over' }); } break;
    case 'undo-step': { const list = PLAY.steps || ((PLAY.last && PLAY.last.blocks || []).filter(x => x.type === 'steps').map(x => x.list)[0]); if (list) { const row = [...PLAY.note.querySelectorAll('.step')].indexOf(el.closest('.step')); const s = list[row]; if (s && !s.undone) { s.undone = true; swap(Object.assign({}, PLAY.last, { blocks: PLAY.last.blocks.map(x => x.type === 'result' ? { type: 'result', icon: 'undo', msg: 'Undone.', sub: 'The setting is back to what it was.' } : x) })); const sw = b.querySelector('.window.settings'); if (sw) sw.replaceWith(settingsWindow({ settings: {} }, b.clientHeight)); trace('undone', { step: s.t }); } } break; }
    case 'undo': swap({ you: PLAY.you, blocks: [{ type: 'result', icon: 'undo', msg: 'Undone.', sub: 'The settings are back to what they were.' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Undone' }); { const sw = b.querySelector('.window.settings'); if (sw) sw.replaceWith(settingsWindow({ settings: {} }, b.clientHeight)); } trace('undone'); break;
    case 'ask-selection': { PLAY.selTb && PLAY.selTb.remove(); PLAY.selMenu && PLAY.selMenu.remove(); window.getSelection().removeAllRanges(); invoke({ at: PLAY.ptr.slice(), via: 'selection', selection: PLAY.selText }); break; }
  }
}
function startMic() {
  PLAY.state = 'listening'; PLAY.micWords = ['Make', 'my', 'screen', 'easier', 'to', 'read', 'at', 'night']; PLAY.micI = 0;
  PLAY.board.insertAdjacentHTML('beforeend', `<div class="priv-dot"></div><div class="mic-indicator">${ms('mic', 'fill')}Quire</div>`);
  const draw = () => swap({ listening: { final: PLAY.micWords.slice(0, PLAY.micI).join(' ') + ' ', partial: PLAY.micWords[PLAY.micI] || '' } }, 'listening');
  draw();
  const tick = () => { if (PLAY.state !== 'listening') return; PLAY.micI = Math.min(PLAY.micWords.length, PLAY.micI + 1); draw(); if (PLAY.micI < PLAY.micWords.length) later(tick, 260); };
  later(tick, 300);
}
function releaseMic() {
  PLAY.board.querySelectorAll('.priv-dot, .mic-indicator').forEach(e => e.remove());
  PLAY.text = PLAY.micWords.slice(0, Math.max(1, PLAY.micI)).join(' '); PLAY.state = 'compose';
  swap({ composer: { text: PLAY.text, focus: true }, spoken: true }); send();
}
function cancelMic() { // Esc while holding: nothing is sent; back to composing with what was there before
  clearTimers(); PLAY.board.querySelectorAll('.priv-dot, .mic-indicator').forEach(e => e.remove()); PLAY.state = 'compose';
  swap({ composer: { text: PLAY.text, focus: true } }); trace('listening cancelled');
}
// Fold back (§5.2): the rim goes dark first (160 ms), then the sheet rolls up towards its origin with spring.fold
// while it fades over the last 60 % of the travel. Into the taskbar, it also travels to the button.
function foldAnim(n, to, onDone) {
  const b = PLAY.board;
  n.style.transition = PLAY.reduce ? '' : `--holo-a ${MOTION.unwrite}ms ${MOTION.easing.accel}`; n.style.setProperty('--holo-a', '0');
  if (to === 'taskbar') { const tb = b.querySelector('.taskbar .tb-quire'); const r = tb.getBoundingClientRect(), rb = b.getBoundingClientRect(); const tx = r.left - rb.left + 22 - (parseFloat(n.style.left) + n.offsetWidth / 2), ty = r.top - rb.top + 22 - (parseFloat(n.style.top) + n.offsetHeight / 2); n.style.transformOrigin = '50% 50%'; spring({ from: 0, to: 1, ...MOTION.spring.fold, onUpdate: v => { n.style.transform = `translate(${tx * v}px, ${ty * v}px) scale(${1 - 0.9 * v})`; n.style.opacity = 1 - Math.max(0, (v - 0.4) / 0.6); }, onEnd: () => { n.remove(); onDone && onDone(); } }); }
  else { const fromBottom = n.style.getPropertyValue('--oy') === '100%'; spring({ from: 1, to: 0, ...MOTION.spring.fold, onUpdate: v => { const s = 0.6 + 0.4 * v; n.style.transform = `scale(${s})`; n.style.clipPath = fromBottom ? `inset(${(100 * (1 - v)).toFixed(1)}% 0 0 0 round 28px)` : `inset(0 0 ${(100 * (1 - v)).toFixed(1)}% 0 round 28px)`; n.style.opacity = Math.min(1, v / 0.6); }, onEnd: () => { n.remove(); onDone && onDone(); } }); }
}
function closeNote() { // only for a note with no task running (compose, done, stopped)
  const n = PLAY.note; clearTimers(); PLAY.sys && PLAY.sys.remove(); PLAY.sys = null; PLAY.intakeEl && PLAY.intakeEl.remove(); PLAY.intakeEl = null;
  if (n) foldAnim(n, 'pointer');
  PLAY.note = null; PLAY.state = 'idle'; PLAY.running = false; PLAY.hidden = false; PLAY.m = null; PLAY.pending = null; PLAY.text = ''; PLAY.last = null; PLAY.lastCls = ''; PLAY.steps = null;
  tbIndicator(); trace('note closed');
}
function background(how) { // hide a running task behind the taskbar button; it keeps running and can be reopened
  if (!PLAY.running || PLAY.hidden || !PLAY.note) return;
  const n = PLAY.note; PLAY.hidden = true; PLAY.note = null; PLAY.intakeEl && PLAY.intakeEl.remove(); PLAY.intakeEl = null;
  foldAnim(n, 'taskbar'); tbIndicator(); trace('hidden', { how });
}
function reopen() { // the hidden task's note, at the taskbar anchor, in its current state
  if (!PLAY.hidden) return; PLAY.hidden = false;
  const n = note(noteState(PLAY.last || {})); if (PLAY.lastCls) n.classList.add(PLAY.lastCls);
  PLAY.anchor = { from: 'taskbar' }; place(PLAY.board, n, PLAY.anchor); PLAY.note = n; wire(n); unfold(n); tbIndicator();
  trace('reopened'); if (PLAY.state === 'consent') focusConsent(); else if (PLAY.state === 'done') focusResult();
}

/* ------------------------------------------------------------------------------------------ boot */
(function main() {
  const theme = qs.get('theme') === 'dark' ? 'dark' : 'light';
  const size = qs.get('size') === 'g14' ? 'g14' : 'fhd';
  if (qs.get('glass') === '0') { document.body.dataset.glass = 'off'; document.body.dataset.motion = 'off'; }
  if (qs.get('play')) { playInit(theme, size); return; }
  const one = qs.get('screen');
  if (one && S[one]) { document.body.classList.add('single'); renderScreen(one, theme, size, true, qs.get('anno') !== '1'); return; }
  for (const id of ORDER) { renderScreen(id, 'light', size); renderScreen(id, 'dark', size); }
})();
