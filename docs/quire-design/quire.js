/* Quire design prototype (ANAL-215). Renders every state of the note as static screens (gallery, single screen)
   and runs the clickable prototype (?play=1). Motion tokens here are the ones in docs/quire-design.md §5. */
'use strict';

/* ------------------------------------------------------------------------------------------ tokens (motion) */
const MOTION = {
  // springs: stiffness (N/m) and damping ratio, as Compose spring() / SpringForce take them
  spring: {
    unfold:  { stiffness: 380,  damping: 0.80 },  // note out of the pointer; one gentle overshoot
    settle:  { stiffness: 700,  damping: 0.90 },  // reflow when content grows, agent picker, tray
    expand:  { stiffness: 300,  damping: 0.85 },  // note → mirror and back
    fold:    { stiffness: 900,  damping: 1.00 },  // note → pointer or taskbar; no overshoot
    tick:    { stiffness: 1400, damping: 0.70 },  // step check-mark pop, halo bloom
  },
  // fixed durations (ms) for fades and non-spatial changes; easing from Material 3
  halo: 90, tick: 160, fade: 120, fadeSlow: 200,
  easing: { standard: 'cubic-bezier(.2,0,0,1)', decel: 'cubic-bezier(.05,.7,.1,1)', accel: 'cubic-bezier(.3,0,.8,.15)' },
};

/* ------------------------------------------------------------------------------------------ helpers */
const qs = new URLSearchParams(location.search);
const h = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
const ms = (name, cls = '') => `<span class="ms ${cls}" aria-hidden="true">${name}</span>`;
const LEAF = `<svg class="leaf" viewBox="0 0 24 24" aria-hidden="true"><path d="M7.5 3H14l6 6v8.5A3.5 3.5 0 0 1 16.5 21h-9A3.5 3.5 0 0 1 4 17.5v-11A3.5 3.5 0 0 1 7.5 3Z" fill="url(#leafA)"/><path d="M14 3v4.5A1.5 1.5 0 0 0 15.5 9H20Z" fill="url(#leafB)"/></svg>`;
const leaf = (cls = '') => `<span class="leaf-wrap ${cls}">${LEAF}</span>`;
const POINTER = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4.33 4.07 Q4.33 3.07 5.02 3.79 L14.27 13.47 Q15.03 14.27 13.93 14.3 L12.77 14.32 Q10.93 14.37 9.62 14.64 L8.91 14.79 Q8.03 14.97 7.36 15.57 L5.15 17.54 Q4.33 18.27 4.33 17.17 L4.33 4.07 Z" fill="#fff" stroke="#fff" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/><path d="M4.33 4.07 Q4.33 3.07 5.02 3.79 L14.27 13.47 Q15.03 14.27 13.93 14.3 L12.77 14.32 Q10.93 14.37 9.62 14.64 L8.91 14.79 Q8.03 14.97 7.36 15.57 L5.15 17.54 Q4.33 18.27 4.33 17.17 L4.33 4.07 Z" fill="#000"/></svg>`;

const AGENTS = {
  claude:   { name: 'Claude Code', ini: 'CC', col: '#5B5D72', where: 'on this laptop' },
  opencode: { name: 'opencode',    ini: 'oc', col: '#72557B', where: 'on this laptop' },
  copilot:  { name: 'Copilot',     ini: 'Cp', col: '#4F5065', where: 'on this laptop' },
  cursor:   { name: 'Cursor',      ini: 'Cu', col: '#5E5E68', where: 'on this laptop' },
  gemini:   { name: 'Gemini CLI',  ini: 'G',  col: '#565B8C', where: 'on this laptop' },
  codex:    { name: 'Codex',       ini: 'Cx', col: '#7A7A84', where: 'on Brian’s desk' },
};
const KIND_ICON = { read: 'visibility', edit: 'edit', delete: 'delete', move: 'drive_file_move', search: 'search', execute: 'terminal', think: 'psychology', fetch: 'language', other: 'more_horiz', setting: 'tune', app: 'apps', window: 'select_window' };

/* ------------------------------------------------------------------------------------------ desktop */
function desktop(board, o) {
  const size = board.dataset.size;
  const H = size === 'g14' ? 1200 : 1080;
  board.innerHTML = '';
  board.insertAdjacentHTML('beforeend', `<div class="statusbar"><span>12:22</span><span>Sat, Oct 17</span>
    <div class="right">${o.mic ? '' : ''}${ms('notifications')}${ms('wifi')}<span class="batt">35</span></div></div>`);
  if (o.mic) board.insertAdjacentHTML('beforeend', `<div class="priv-dot"></div><div class="mic-indicator">${ms('mic', 'fill')}Quire</div>`);

  // windows
  const wins = o.windows || ['doc', 'settings'];
  for (const w of wins) {
    if (w === 'settings') board.appendChild(settingsWindow(o, H));
    if (w === 'doc') board.appendChild(docWindow(o, H));
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
    <div class="tb-btn app" style="background:#FBF8FE;color:#A8364B">${ms('calendar_month', 'fill')}</div>`;
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

/* ------------------------------------------------------------------------------------------ note blocks */
function agentChip(id, opts = {}) {
  const a = AGENTS[id];
  return `<div class="agent ${opts.open ? 'open' : ''}" data-role="agent"><span class="av" style="background:${a.col}">${a.ini}</span>${a.name}<span class="where">${opts.where || a.where}</span>${ms('arrow_drop_down')}</div>`;
}
function head(n) {
  return `<div class="n-head">${leaf(n.thinking ? 'thinking' : '')}${agentChip(n.agent || 'claude', { open: n.picker, where: n.where })}<span class="spacer"></span>
    ${n.running ? `<button type="button" class="ibtn" data-role="background" title="Hide · keeps running (Meta+Space)" aria-label="Hide the note; the task keeps running">${ms('open_in_new_down')}</button>` : ''}
    <button type="button" class="ibtn ${n.focusClose ? 'focus' : ''}" data-role="close" title="${n.running ? 'Hide · keeps running' : 'Close (Esc)'}" aria-label="${n.running ? 'Hide the note; the task keeps running' : 'Close'}">${ms('close')}</button></div>`;
}
function intakeChip(i) {
  if (!i) return '';
  if (i.kind === 'selection') return `<span class="intake-chip">${ms('format_quote')}<q>${i.text}</q>${ms('close', 'x')}</span>`;
  if (i.kind === 'window') return `<span class="intake-chip"><span class="thumb"><i></i><i></i></span>${i.text}${ms('close', 'x')}</span>`;
  if (i.kind === 'region') return `<span class="intake-chip"><span class="thumb"><i></i><i></i></span>${i.text}${ms('close', 'x')}</span>`;
  if (i.kind === 'secure') return `<span class="intake-chip" style="background:transparent;outline:1px solid var(--outline-variant);color:var(--on-surface-variant)">${ms('lock')}Secure window · not taken in</span>`;
  if (i.kind === 'none') return `<span class="intake-chip" style="background:transparent;outline:1px solid var(--outline-variant);color:var(--on-surface-variant)">${ms('add_a_photo')}Add what’s on screen</span>`;
  return '';
}
function prompt(n) {
  if (!n.intake && !n.you) return '';
  return `<div class="n-prompt">${intakeChip(n.intake)}${n.you ? `<div class="you ${n.spoken ? 'spoken' : ''}">${n.you}</div>` : ''}</div>`;
}
function steps(list, folded) {
  if (folded) return `<span class="steps-folded">${ms('check_circle', 'fill')}${list.length} steps ${ms('expand_more', 'chev')}</span>`;
  return `<div class="steps">${list.map(s => `<div class="step ${s.st}"><span class="st">${s.st === 'done' ? ms('check_circle', 'fill') : s.st === 'failed' ? ms('cancel', 'fill') : ''}</span>${ms(KIND_ICON[s.kind] || 'more_horiz', 'kind')}<span class="t">${s.t}</span></div>`).join('')}</div>`;
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
function composer(c = {}) {
  return `<div class="composer"><div class="field ${c.focus ? 'focus' : ''}"><span class="text ${c.text ? '' : 'ph'}">${c.text || c.placeholder || 'Ask Quire'}${c.focus ? '<span class="caret"></span>' : ''}</span></div>
    <div class="mic ${c.mic ? 'on' : ''}" title="Hold to talk">${ms('mic')}</div><div class="send ${c.text ? '' : 'disabled'}" title="Send (Enter)">${ms('arrow_upward')}</div></div>`;
}
function foot(n) {
  if (!n.foot) return '';
  return `<div class="n-foot">${n.foot}<span class="spacer"></span>${n.footRight || ''}</div>`;
}

/* ------------------------------------------------------------------------------------------ the note */
function note(n) {
  const el = h('div', 'note ' + (n.cls || '') + (n.mirror ? ' mirror' : '') + (n.listening ? ' listening' : ''));
  el.setAttribute('role', 'dialog'); el.setAttribute('aria-label', 'Quire');
  const scroll = n.scroll ? 'scroll' : '';
  let body = '';
  if (n.listening) {
    body = `<div class="listen"><div class="levels"><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div><div class="tx">${n.listening.final || ''}<span class="partial">${n.listening.partial || ''}</span></div></div>
            <div class="n-foot">Listening · release to send<span class="spacer"></span><kbd>Esc</kbd> cancel</div>`;
    el.innerHTML = head(n) + prompt(n) + body;
    return el;
  }
  if (n.mirror) {
    const m = n.mirror;
    el.innerHTML = `<div class="n-head">${leaf(n.thinking ? 'thinking' : '')}${agentChip(n.agent || 'claude')}<span class="spacer"></span><button type="button" class="ibtn" data-role="background" title="Hide · keeps running (Meta+Space)" aria-label="Hide the note; the task keeps running">${ms('open_in_new_down')}</button><button type="button" class="ibtn" data-role="close" title="Hide · keeps running" aria-label="Hide the note; the task keeps running">${ms('close')}</button></div>
      ${prompt(n)}
      <div class="mirror-bar"><span class="auto ${m.paused ? 'paused' : ''}"><span class="dot"></span>${m.paused ? 'Paused' : 'Using Settings'}</span><span>${m.title}</span><span class="spacer"></span></div>
      <div class="mirror-view">
        <div class="stage"><div class="desk"></div>${settingsWindow({ settings: m.settings, settingsGeo: { left: 0, top: 0, width: SESSION[0], height: SESSION[1] } }, 0).outerHTML}</div>
        <div class="overlay"></div>
        ${m.paused ? `<div class="paused-scrim"><span>${ms('pause')}Paused · click in the mirror to act, or Take over</span></div>` : ''}
      </div>
      <div class="mirror-step">${steps(m.steps)}</div>
      <div class="mirror-foot"><span class="status">${m.status}</span>
        <button type="button" class="btn text danger" data-act="stop">Stop</button><button type="button" class="btn tonal" data-act="pause" aria-label="${m.paused ? 'Resume' : 'Pause'}">${ms(m.paused ? 'play_arrow' : 'pause')}${m.paused ? 'Resume' : 'Pause'}</button><button type="button" class="btn filled ${m.focusTake ? 'focus' : ''}" data-act="takeover" aria-label="Take over">${ms('open_in_full')}Take over</button></div>`;
    el._mirror = m;
    return el;
  }
  body = (n.blocks || []).map(b => {
    switch (b.type) {
      case 'thought': return `<div class="thought">${leaf()}${b.t}<span class="ellipsis">…</span></div>`;
      case 'answer': return `<div class="answer">${b.html}${b.caret ? '<span class="caret"></span>' : ''}</div>`;
      case 'steps': return steps(b.list, b.folded);
      case 'plan': return plan(b.entries);
      case 'consent': return consent(b);
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
  el.innerHTML = head(n) + prompt(n) + (body ? `<div class="${scroll}"><div class="n-body">${body}</div></div>` : '') + (n.suggest ? `<div class="suggest">${n.suggest.map(s => `<span>${ms(s[0])}${s[1]}</span>`).join('')}</div>` : '') + (n.composer === false ? '' : composer(n.composer)) + foot(n);
  if (n.picker) el.appendChild(picker(n.picker));
  return el;
}
function picker(p) {
  const el = h('div', 'picker');
  el.innerHTML = `<div class="hd">On this laptop</div>
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
const STEPS_BATTERY = [
  { st: 'done', kind: 'read', t: 'Reading Display settings' },
  { st: 'done', kind: 'read', t: 'Reading Battery settings' },
  { st: 'running', kind: 'setting', t: 'Turning on Battery saver', effect: 'Battery saver was turned on', where: 'Settings · Battery' },
  { st: 'pending', kind: 'setting', t: 'Lowering brightness to 40%', effect: 'Brightness was lowered to 40%', where: 'Settings · Display' },
];
const ANSWER_ADAPTIVE = `<p><b>Adaptive brightness</b> uses the light sensor to set the screen's brightness for the room you are in, and learns from the adjustments you make.</p><p>On this laptop it is on. It will not change the brightness while Battery saver is active, which is why the slider`;
const CODE_RENAME = `<span class="c"># Rename photos in ~/Pictures/Lisbon by the date they were taken</span>
<span class="k">for</span> f <span class="k">in</span> ~/Pictures/Lisbon/*.jpg; <span class="k">do</span>
  d=$(exiftool -s3 -DateTimeOriginal <span class="s">"$f"</span> | tr <span class="s">': '</span> <span class="s">'--'</span>)
  mv -n <span class="s">"$f"</span> <span class="s">"$(dirname "$f")/$d.jpg"</span>
<span class="k">done</span>`;

/* ------------------------------------------------------------------------------------------ screens */
const PTR = [1010, 470];           // pointer over the Settings window's Display page
const SETTINGS_GEO = H => ({ left: 560, top: 96, width: 1180, height: H - 96 - 120 });
const S = {}; // id -> { caption, build(board, H, theme) }

S['idle'] = { caption: '<b>Idle.</b> Quire’s button sits in the taskbar’s system group, after All apps. Nothing else is on screen until the person calls it.',
  build(b) { desktop(b, {}); pointer(b, PTR); } };

S['invoke-shake'] = { caption: '<b>Shake, first 100 ms.</b> The halo blooms around the hotspot (90 ms), and the window under the pointer gets the intake outline. The note has not appeared yet.',
  build(b, H) { desktop(b, { activeWin: 'settings' }); intake(b, SETTINGS_GEO(H)); pointer(b, PTR, { halo: true, label: `${LEAF}Ask Quire` }); anno(b, PTR[0] - 40, PTR[1] - 60, 'halo: 0 → 32 dp in 90 ms, then the note unfolds'); anno(b, 600, 60, 'intake outline: the window under the pointer, 2 dp primary at 55 %', 't'); } };

S['invoke-key'] = { caption: '<b>Meta+Space or the assist key, first 100 ms.</b> The pointer was used in the last 10 s, so the halo appears there with the shortcut label; otherwise the note rises from the taskbar button. Intake is the focused window.',
  build(b, H) { desktop(b, { activeWin: 'settings' }); intake(b, SETTINGS_GEO(H)); pointer(b, PTR, { halo: true, label: `${LEAF}Quire <kbd>Meta</kbd><kbd>Space</kbd>` }); } };

S['invoke-secure'] = { caption: '<b>Secure window.</b> The pointer is over a window with FLAG_SECURE. The halo still answers, but nothing is taken in: no screenshot, no selection. The chip says so.',
  build(b, H) { desktop(b, { activeWin: 'settings', secure: true }); pointer(b, PTR, { halo: true }); place(b, note({ agent: 'claude', intake: { kind: 'secure' }, composer: { focus: true }, suggest: [['tune', 'Change a setting'], ['help', 'What can you do here?']], foot: 'This window is protected by the app', footRight: '<kbd>Esc</kbd> close' }), { at: PTR }); } };

S['invoke-taskbar'] = { caption: '<b>Taskbar button.</b> The note rises from the button and settles 12 dp above the taskbar. Nothing is taken in; the chip offers to add what is on screen.',
  build(b, H) { desktop(b, { activeWin: 'doc' }); pointer(b, [960, H - 36]); place(b, note({ agent: 'claude', intake: { kind: 'none' }, composer: { focus: true }, suggest: [['tune', 'Change a setting'], ['select_window', 'Tidy my windows'], ['help', 'What can you do here?']], foot: '<kbd>Enter</kbd> send · <kbd>Shift</kbd><kbd>Enter</kbd> new line', footRight: '<kbd>Esc</kbd> close' }), { from: 'taskbar' }); } };

S['invoke-voice'] = { caption: '<b>Hold to talk.</b> The halo becomes a mic ring; the mic indicator and privacy dot appear in the status bar (Q7). Words arrive as they are recognised; release sends.',
  build(b, H) { desktop(b, { activeWin: 'settings', mic: true }); intake(b, SETTINGS_GEO(H)); pointer(b, PTR, { halo: 'listening', breathe: true }); place(b, note({ agent: 'claude', intake: { kind: 'window', text: 'Settings · Display' }, listening: { final: 'Make my screen easier to read ', partial: 'at night' } }), { at: PTR }); } };

S['invoke-selection'] = { caption: '<b>Ask Quire on a selection.</b> Android lists an <code>ACTION_PROCESS_TEXT</code> handler in the text toolbar’s overflow menu as a plain label, no icon (C). The selection stays highlighted and becomes a quoted chip; the note opens at the pointer, which just chose the item.',
  build(b, H) { desktop(b, { activeWin: 'doc', selection: true, windows: ['settings', 'doc'] }); selToolbar(b, 184, 306, true); pointer(b, [470, 388], { halo: true }); place(b, note({ agent: 'claude', intake: { kind: 'selection', text: 'The conference runs Tuesday to Thursday at the Centro de Congressos…' }, composer: { focus: true, placeholder: 'Ask about the selection' }, suggest: [['event', 'Add to calendar'], ['summarize', 'Summarise'], ['translate', 'Translate']], foot: 'Selection from Notes' }), { at: [470, 388] }); } };

S['compose'] = { caption: '<b>Composing.</b> The note has settled beside the pointer. Agent chip, intake chip, suggestions for this window, and the field with focus.',
  build(b, H) { desktop(b, { activeWin: 'settings' }); intake(b, SETTINGS_GEO(H)); pointer(b, PTR, { halo: true }); place(b, note({ agent: 'claude', intake: { kind: 'window', text: 'Settings · Display' }, composer: { focus: true, text: 'Make my screen easier to read at ni' }, suggest: [['dark_mode', 'Turn on dark theme'], ['format_size', 'Make text bigger'], ['help', 'Explain this page']], foot: '<kbd>Enter</kbd> send', footRight: '<kbd>Esc</kbd> close' }), { at: PTR }); } };

S['agent-picker'] = { caption: '<b>Choosing the agent.</b> The chip opens a list grouped by where agents run. Sign-in state shows per agent (ACP <code>authMethods</code>). The last used agent is preselected.',
  build(b, H) { desktop(b, { activeWin: 'settings' }); intake(b, SETTINGS_GEO(H)); pointer(b, PTR); place(b, note({ agent: 'claude', picker: { sel: 'claude' }, intake: { kind: 'window', text: 'Settings · Display' }, composer: { text: 'Make my screen easier to read at night' }, foot: '' }), { at: PTR }); } };

S['streaming'] = { caption: '<b>Streaming.</b> Thought chunks collapse to one breathing line; message chunks append as they arrive with a caret. No per-character animation.',
  build(b, H) { desktop(b, { activeWin: 'settings' }); pointer(b, PTR); place(b, note({ agent: 'claude', thinking: true, intake: { kind: 'window', text: 'Settings · Display' }, you: 'What does Adaptive brightness do here?', blocks: [{ type: 'answer', html: ANSWER_ADAPTIVE, caret: true }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Answering · 2 s', footRight: '<kbd>Esc</kbd> stop' }), { at: PTR }); } };

S['steps'] = { caption: '<b>Steps ticking.</b> Each tool call is a line with its kind. Done steps get a check that pops (160 ms spring); the running step spins; pending steps wait in outline.',
  build(b, H) { desktop(b, { activeWin: 'settings', settings: { page: 'battery', saver: false } }); pointer(b, PTR); place(b, note({ agent: 'claude', thinking: true, intake: { kind: 'window', text: 'Settings · Display' }, you: 'Turn on Battery saver and lower the brightness', blocks: [{ type: 'steps', list: STEPS_BATTERY }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Working · 6 s', footRight: '<kbd>Esc</kbd> stop' }), { at: PTR }); } };

S['plan'] = { caption: '<b>A plan.</b> An ACP <code>plan</code> update becomes a numbered checklist that updates in place. Priority shows only when the agent sets it. Showing a plan needs no consent.',
  build(b, H) { desktop(b, { activeWin: 'settings' }); pointer(b, PTR); place(b, note({ agent: 'claude', thinking: true, intake: { kind: 'window', text: 'Settings · Display' }, you: 'Set this laptop up for my talk tomorrow', blocks: [{ type: 'plan', entries: [{ st: 'done', t: 'Check the HDMI output and mirror mode' }, { st: 'active', t: 'Turn off notifications during the talk', pri: 'high' }, { st: 'pending', t: 'Set screen timeout to 30 minutes' }, { st: 'pending', t: 'Open the slides in a new window' }] }, { type: 'steps', list: [{ st: 'done', kind: 'read', t: 'Reading Display settings' }, { st: 'running', kind: 'read', t: 'Reading Notification settings' }] }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Working · 9 s', footRight: '<kbd>Esc</kbd> stop' }), { at: PTR }); } };

S['consent'] = { caption: '<b>Inline consent.</b> The step stops and the card names exactly what will change. Focus lands on the card; the first Tab stop is the agent’s reject option. The buttons are ACP <code>session/request_permission</code> options, labelled by the agent.',
  build(b, H) { desktop(b, { activeWin: 'settings', settings: { page: 'battery', saver: false } }); pointer(b, PTR); place(b, note({ agent: 'claude', intake: { kind: 'window', text: 'Settings · Display' }, you: 'Turn on Battery saver and lower the brightness', blocks: [{ type: 'steps', list: [STEPS_BATTERY[0], STEPS_BATTERY[1]] }, { type: 'consent', title: 'Change 2 settings', meta: 'Settings tool', focusCard: true, changes: [{ k: 'Battery saver', w: 'Settings · Battery', old: 'Off', nu: 'On' }, { k: 'Brightness level', w: 'Settings · Display', old: '80%', nu: '40%' }], why: 'You can undo this from the note or from the Quire button.' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Waiting for you', footRight: '<kbd>Esc</kbd> stop' }), { at: PTR }); } };

S['consent-command'] = { caption: '<b>Consent for a command or a file edit.</b> The same card shows the command, or a diff, instead of settings rows. The buttons are the agent’s own options (<code>options[].name</code>); their scope is whatever the agent enforces.',
  build(b, H) { desktop(b, { activeWin: 'doc' }); pointer(b, [700, 520]); place(b, note({ agent: 'claude', cls: 'wide', intake: { kind: 'selection', text: 'Things to pack: the HDMI adapter…' }, you: 'Turn this into a checklist file in my Documents', blocks: [{ type: 'steps', list: [{ st: 'done', kind: 'read', t: 'Reading the selection' }] }, { type: 'consent', title: 'Write a file', meta: 'Documents/Lisbon-packing.md', focus: 'deny', diff: [['', '# Lisbon packing list'], ['add', '+ [ ] HDMI adapter'], ['add', '+ [ ] Second laptop charger'], ['add', '+ [ ] Walking shoes'], ['add', '+ [ ] Light jacket for the evenings']], why: 'Creates a new file. Nothing else in Documents changes.' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Waiting for you', footRight: '<kbd>Esc</kbd> stop' }), { at: [700, 520] }); } };

S['consent-system'] = { caption: '<b>Platform consent for computer control.</b> The system’s own dialog (platform-owned, drawn here only for context) asks before any app is automated. The note waits and says so.',
  build(b, H) { desktop(b, { activeWin: 'settings' }); pointer(b, PTR); place(b, note({ agent: 'claude', intake: { kind: 'window', text: 'Settings' }, you: 'In Settings, find Bluetooth and turn it off', blocks: [{ type: 'steps', list: [{ st: 'done', kind: 'read', t: 'Listing apps' }, { st: 'running', kind: 'app', t: 'Asking to use Settings' }] }, { type: 'result', icon: 'shield', cls: 'warn', msg: 'Waiting for your permission', sub: 'The system is asking whether Claude Code may use Settings.' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Waiting for you', footRight: '<kbd>Esc</kbd> stop' }), { at: PTR }); const d = h('div', 'sysdialog', `<span class="lbl">System dialog (platform)</span>${ms('shield', 'big fill')}<h3>Allow Claude Code to use Settings?</h3><p>Quire will run Settings on a separate screen that you can watch. Claude Code can tap, type and take screenshots there. Secure screens stay hidden, and you can take over at any time.</p><div class="btns"><button type="button" class="btn text">Don’t allow</button><button type="button" class="btn filled">Allow</button></div>`); d.style.left = '750px'; d.style.top = '360px'; b.appendChild(d); } };

S['mirror'] = { caption: '<b>The live mirror.</b> The note expands to 760 dp and shows the session display (<code>InteractiveMirror</code>), which has the reference display’s size (1920×1200 dp on the G14, C): the whole display at 0.383, zoomed 2× on the control the agent acts on. The agent’s pointer is drawn in brand blue with a tap ring. Pause, Stop and Take over are always visible.',
  build(b, H) { desktop(b, { activeWin: 'doc', windows: ['doc'], tbRunning: true }); pointer(b, [1400, 300]); place(b, note({ agent: 'claude', thinking: true, intake: { kind: 'window', text: 'Settings' }, you: 'In Settings, find Bluetooth and turn it off', mirror: { title: 'Settings', target: '.nav .row:nth-of-type(3)', tap: true, settings: { page: 'display' }, steps: [{ st: 'done', kind: 'app', t: 'Opened Settings' }, { st: 'running', kind: 'execute', t: 'Tapping Connected devices' }], status: 'Step 2 of 4 · 11 s' } }), { at: [1400, 300] }); anno(b, 1000, 240, 'automation indicator: the taskbar button breathes while an app is driven', 't'); anno(b, 1000, 290, 'the view is zoomed 2× on the control the agent acts on; Pause shows the whole session display', 't'); } };

S['mirror-paused'] = { caption: '<b>Paused.</b> <code>notifyBlocked()</code>: the platform drops the agent’s input, the mirror becomes interactive (it only is while blocked, C), and the view returns to the whole session display. Resume (<code>requestUnblock()</code>) gives control back. Take over moves the app to their screen.',
  build(b, H) { desktop(b, { activeWin: 'doc', windows: ['doc'], tbRunning: true }); pointer(b, [1400, 300]); place(b, note({ agent: 'claude', intake: { kind: 'window', text: 'Settings' }, you: 'In Settings, find Bluetooth and turn it off', mirror: { paused: true, title: 'Connected devices', settings: { page: 'devices' }, steps: [{ st: 'done', kind: 'app', t: 'Opened Settings' }, { st: 'done', kind: 'execute', t: 'Tapped Connected devices' }, { st: 'pending', kind: 'execute', t: 'Turn off Bluetooth' }], status: 'Paused by you · 14 s', focusTake: true } }), { at: [1400, 300] }); } };

S['done'] = { caption: '<b>Done.</b> The result in one line, the steps folded, and Undo for anything that changed. The note stays until the person closes it; closing folds it into the pointer.',
  build(b, H) { desktop(b, { activeWin: 'settings', settings: { page: 'battery', saver: true } }); pointer(b, PTR); place(b, note({ agent: 'claude', intake: { kind: 'window', text: 'Settings · Display' }, you: 'Turn on Battery saver and lower the brightness', blocks: [{ type: 'steps', folded: true, list: [1, 2, 3, 4] }, { type: 'result', msg: 'Battery saver is on and brightness is at 40%.', sub: 'Changed 2 settings · 8 s' }, { type: 'btns', html: '<button type="button" class="btn tonal">' + ms('undo') + 'Undo both</button><button type="button" class="btn text">Show changes</button>' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Done', footRight: '<kbd>Esc</kbd> close' }), { at: PTR }); } };

S['stopped'] = { caption: '<b>Stopped by the person.</b> Esc or Stop cancels the run and answers any open permission request as cancelled. The card says what was done before the stop, what was interrupted, and what to check. Hiding the note (Meta+Space, the Hide button) is a different action: the task keeps running behind the taskbar button.',
  build(b, H) { desktop(b, { activeWin: 'settings', settings: { page: 'battery', saver: true } }); pointer(b, PTR); place(b, note({ agent: 'claude', intake: { kind: 'window', text: 'Settings · Display' }, you: 'Turn on Battery saver and lower the brightness', blocks: [{ type: 'steps', list: [STEPS_BATTERY[0], STEPS_BATTERY[1], { st: 'done', kind: 'setting', t: 'Turning on Battery saver' }, { st: 'failed', kind: 'setting', t: 'Lowering brightness to 40%' }] }, { type: 'result', icon: 'stop_circle', cls: 'warn', msg: 'Stopped after 3 of 4 steps.', sub: 'Battery saver was turned on. Lowering brightness to 40% was interrupted and may be partly applied; check Settings · Display.' }, { type: 'btns', html: '<button type="button" class="btn tonal">' + ms('undo') + 'Undo</button><button type="button" class="btn text">Show changes</button>' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Stopped', footRight: '<kbd>Esc</kbd> close' }), { at: PTR }); } };

S['error'] = { caption: '<b>Error.</b> What stopped, in a sentence, with details behind a disclosure and a retry. Stop reasons other than <code>end_turn</code> (refusal, max tokens, cancelled) use the same card.',
  build(b, H) { desktop(b, { activeWin: 'settings' }); pointer(b, PTR); place(b, note({ agent: 'claude', intake: { kind: 'window', text: 'Settings · Display' }, you: 'Turn on Battery saver and lower the brightness', blocks: [{ type: 'steps', list: [STEPS_BATTERY[0], { st: 'failed', kind: 'read', t: 'Reading Battery settings' }] }, { type: 'error', title: 'Claude Code stopped', meta: '7 s', msg: 'The agent closed the connection before finishing. Nothing was changed.', details: 'quired: agent exited with status 1\nstderr: Error: fetch failed (ECONNRESET)', btns: '<button type="button" class="btn text">Show log</button><button type="button" class="btn tonal">' + ms('refresh') + 'Try again</button>' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Stopped', footRight: '<kbd>Esc</kbd> close' }), { at: PTR }); } };

S['signin'] = { caption: '<b>Agent not signed in.</b> ACP <code>authenticate</code> with the agent’s <code>authMethods</code>. Sign-in happens in the agent’s own flow; Quire never handles the secret.',
  build(b, H) { desktop(b, { activeWin: 'settings' }); pointer(b, PTR); place(b, note({ agent: 'cursor', intake: { kind: 'window', text: 'Settings · Display' }, you: 'Make my screen easier to read at night', blocks: [{ type: 'auth', title: 'Cursor needs to sign in', msg: 'Choose how to sign in. It opens in the Linux environment and comes back here when it’s done.', methods: [{ ic: 'open_in_browser', t: 'Sign in with the browser', sub: 'cursor login' }, { ic: 'key', t: 'Use an API key', sub: 'stays in Cursor' }] }, { type: 'btns', end: true, html: '<button type="button" class="btn text">Use Claude Code instead</button><button type="button" class="btn filled">Sign in</button>' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Not signed in', footRight: '<kbd>Esc</kbd> close' }), { at: PTR }); } };

S['background'] = { caption: '<b>Running in the background.</b> The note folded into the taskbar button, which shows progress and a count. The tray lists running and finished tasks; one needs an answer.',
  build(b, H) { desktop(b, { activeWin: 'doc', tbRing: 0.6, tbBadge: '2', tbRunning: true }); pointer(b, [960, H - 38]); const t = h('div', 'tray', `<div class="hd">${LEAF}Quire<span class="spacer"></span><div class="ibtn">${ms('settings')}</div></div>
    <div class="task"><span class="st ask">${ms('shield', 'fill')}</span><div class="w"><b>Turn on Battery saver and lower the brightness</b><small>Needs your answer · Change 2 settings</small></div><span class="agent-mini">Claude Code</span>${ms('chevron_right', 'chev')}</div>
    <div class="task"><span class="st run"></span><div class="w"><b>Rename the photos in Lisbon by date</b><small>Step 3 of 5 · 48 s</small></div><span class="agent-mini">opencode</span>${ms('chevron_right', 'chev')}</div>
    <div class="task"><span class="st ok">${ms('check_circle', 'fill')}</span><div class="w"><b>Set this laptop up for my talk tomorrow</b><small>Done 4 min ago · 3 changes, undo available</small></div><span class="agent-mini">Claude Code</span>${ms('chevron_right', 'chev')}</div>
    <div class="foot"><button type="button" class="btn tonal">${ms('add')}New</button><button type="button" class="btn text">History</button></div>`); place(b, t, { from: 'taskbar' }, { dx: -58 }); } };

S['settings-help'] = { caption: '<b>Settings help.</b> Current versus new values before Allow; after Allow the same rows show the applied values with per-row undo and Undo all. The changed rows are outlined in Settings.',
  build(b, H) { desktop(b, { activeWin: 'settings', settings: { dark: true, night: true, font: true, changed: 'night' } }); pointer(b, PTR); place(b, note({ agent: 'claude', intake: { kind: 'window', text: 'Settings · Display' }, you: 'Make my screen easier to read at night', blocks: [{ type: 'steps', folded: true, list: [1, 2, 3] }, { type: 'changes', title: 'Changed 3 settings', meta: 'just now', mode: 'undo', list: [{ k: 'Dark theme', w: 'Settings · Display', old: 'Off', nu: 'On' }, { k: 'Night Light', w: 'Settings · Display', old: 'Off', nu: 'Sunset to sunrise' }, { k: 'Text size', w: 'Display size and text', old: 'Default', nu: 'Large' }], foot: `<div class="btns end"><button type="button" class="btn text">${ms('undo')}Undo all</button></div>` }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Done · undo stays available for 24 h from the Quire button', footRight: '<kbd>Esc</kbd> close' }), { at: PTR }); } };

S['long-output'] = { caption: '<b>Long output.</b> The note caps at 60 % of the screen height and scrolls inside. A Jump to latest pill appears when the person scrolls up while text streams; Open as a document moves it to a window.',
  build(b, H) { desktop(b, { activeWin: 'doc' }); pointer(b, [700, 300]); const paras = ['<p><b>Summary of the trip notes</b></p>', '<p>Travel is settled: flights on the 14th at 07:40 and an apartment in Alfama with check-in from 15:00. The walk from Santa Apolónia is about ten minutes.</p>', '<p>The conference runs Tuesday to Thursday. Registration opens at 08:30 on Tuesday and the keynote is at 09:15; badges can also be collected on Monday afternoon.</p>', '<p>Two things are still open: the dinner with the Porto team, and whether Thursday’s workshop needs its own ticket.</p>', '<p>Packing: HDMI adapter, a second charger, walking shoes and a light jacket. The forecast is 18 °C and mostly dry.</p>', '<p>Suggested next steps:</p><ul><li>Confirm the Porto dinner by Friday.</li><li>Email the organisers about the workshop ticket.</li><li>Check the Belém tram times for Thursday afternoon.</li></ul>', '<p>If you want, I can add the registration and keynote to your calendar and draft the email'].join(''); place(b, note({ agent: 'claude', cls: 'wide', scroll: true, intake: { kind: 'window', text: 'Notes · Trip planning' }, you: 'Summarise this document and suggest next steps', blocks: [{ type: 'answer', html: paras, caret: true }, { type: 'jump' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Answering · 4 s', footRight: '<button type="button" class="btn text" style="height:24px;padding:0 8px;font-size:12px">' + ms('open_in_new') + 'Open as a document</button>' }), { at: [700, 300] }); b.querySelector('.note .scroll').scrollTop = 40; } };

S['code'] = { caption: '<b>Code.</b> Google Sans Code at 12.5/18 in a block with the language and a copy button. The note widens to 440 dp when a block arrives. Running it would be a consent step.',
  build(b, H) { desktop(b, { activeWin: 'doc' }); pointer(b, [700, 300]); place(b, note({ agent: 'opencode', cls: 'wide', intake: { kind: 'window', text: 'Files · Lisbon' }, you: 'Write a script that renames these photos by the date they were taken', blocks: [{ type: 'answer', html: '<p>This uses the date in each photo’s metadata and keeps the originals if a name already exists:</p>' }, { type: 'code', lang: 'bash', src: CODE_RENAME }, { type: 'btns', html: '<button type="button" class="btn tonal">' + ms('play_arrow') + 'Run it</button><button type="button" class="btn text">' + ms('save') + 'Save as file</button>' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Done', footRight: '<kbd>Esc</kbd> close' }), { at: [700, 300] }); } };

S['images'] = { caption: '<b>Images.</b> An image the agent returns, or one the person took in, shows as a thumbnail with a caption and expands in place. A pointer region intake is cropped to the region, never the whole screen.',
  build(b, H) { desktop(b, { activeWin: 'doc', windows: ['settings', 'doc'] }); intake(b, { left: 172, top: 344, width: 560, height: 210 }, true); pointer(b, [726, 548], { halo: true }); place(b, note({ agent: 'claude', intake: { kind: 'region', text: 'Region · Notes' }, you: 'What’s the schedule here, as a table?', blocks: [{ type: 'image', h: 150, cap: 'Region you pointed at · 560×210', html: '<div style="position:absolute;inset:0;padding:14px 18px;font-size:11px;line-height:16px;color:var(--on-surface-variant);overflow:hidden"><div style="width:70%;height:8px;background:var(--outline-variant);border-radius:4px;margin:6px 0"></div><div style="width:90%;height:8px;background:var(--outline-variant);border-radius:4px;margin:6px 0"></div><div style="width:85%;height:8px;background:var(--outline-variant);border-radius:4px;margin:6px 0"></div><div style="width:60%;height:8px;background:var(--outline-variant);border-radius:4px;margin:6px 0"></div><div style="width:88%;height:8px;background:var(--outline-variant);border-radius:4px;margin:6px 0"></div></div>' }, { type: 'answer', html: '<p>From the region you pointed at:</p><table style="border-collapse:collapse;width:100%;font-size:13px"><tr><td style="padding:4px 0;color:var(--on-surface-variant)">Mon</td><td>Badge collection, afternoon</td></tr><tr><td style="padding:4px 0;color:var(--on-surface-variant)">Tue</td><td>Registration 08:30 · Keynote 09:15</td></tr><tr><td style="padding:4px 0;color:var(--on-surface-variant)">Wed–Thu</td><td>Conference sessions</td></tr></table>' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Done', footRight: '<kbd>Esc</kbd> close' }), { at: [726, 548] }); } };

S['no-agent'] = { caption: '<b>No agent connected.</b> First run. Quire lists the agents it found (<code>quired agents</code>) and offers to pair a computer. Nothing is connected until the person chooses.',
  build(b, H) { desktop(b, { activeWin: 'settings' }); pointer(b, PTR, { halo: true }); place(b, note({ agent: 'claude', where: 'not connected', intake: { kind: 'window', text: 'Settings · Display' }, blocks: [{ type: 'agents', title: 'Connect an agent', msg: 'Quire works with the agents you already have. These are installed in your Linux environment:', list: [{ ini: 'CC', col: '#5B5D72', t: 'Claude Code', sub: 'v2.1 · signed in' }, { ini: 'oc', col: '#72557B', t: 'opencode', sub: 'v1.4 · signed in' }, { ini: 'Cu', col: '#5E5E68', t: 'Cursor', sub: 'needs sign-in' }], foot: `<div class="btns end"><button type="button" class="btn text">${ms('computer')}Pair a computer</button><button type="button" class="btn filled">Connect Claude Code</button></div>` }], composer: false, foot: 'Nothing is sent until you connect an agent', footRight: '<kbd>Esc</kbd> close' }), { at: PTR }); } };

S['offline'] = { caption: '<b>Offline.</b> A paired computer or a cloud agent is unreachable. The note says which, keeps the prompt, and offers a local agent. Local agents are unaffected.',
  build(b, H) { desktop(b, { activeWin: 'settings' }); pointer(b, PTR); place(b, note({ agent: 'codex', intake: { kind: 'window', text: 'Settings · Display' }, you: 'Make my screen easier to read at night', blocks: [{ type: 'result', icon: 'cloud_off', cls: 'warn', msg: 'Brian’s desk can’t be reached', sub: 'No connection to the paired computer. Your prompt is kept.' }, { type: 'btns', end: true, html: '<button type="button" class="btn text">' + ms('refresh') + 'Retry</button><button type="button" class="btn tonal">Use Claude Code on this laptop</button>' }], composer: { text: 'Make my screen easier to read at night' }, foot: 'Offline', footRight: '<kbd>Esc</kbd> close' }), { at: PTR }); } };

const ORDER = ['idle', 'invoke-shake', 'invoke-key', 'invoke-secure', 'invoke-taskbar', 'invoke-voice', 'invoke-selection', 'compose', 'agent-picker', 'streaming', 'steps', 'plan', 'consent', 'consent-command', 'consent-system', 'mirror', 'mirror-paused', 'done', 'stopped', 'error', 'signin', 'background', 'settings-help', 'long-output', 'code', 'images', 'no-agent', 'offline'];

/* ------------------------------------------------------------------------------------------ gallery / single */
function makeBoard(id, theme, size, frozen = true) {
  const fig = h('figure');
  const board = h('div', 'artboard' + (frozen ? ' frozen' : ''));
  board.dataset.theme = theme; board.dataset.size = size; board.id = 'b-' + id + '-' + theme;
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
// Hiding is a separate action: the header's Hide button, Meta+Space, the taskbar button, or a click elsewhere.
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
  const hud = h('div', 'hud', `<label><input type="checkbox" id="reduce"> Remove animations</label><span class="k">shake · Meta/Alt+Space · click the leaf · hold the mic · select text · Esc stops · Meta+Space hides</span>`);
  document.body.appendChild(hud);
  hud.querySelector('#reduce').addEventListener('change', e => { PLAY.reduce = e.target.checked; board.classList.toggle('frozen', PLAY.reduce); });
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) { PLAY.reduce = true; hud.querySelector('#reduce').checked = true; board.classList.add('frozen'); }

  // pointer + shake detection (range + reversals, after GestureDetectionInteractor's idea)
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
    if (win) { const i = intake(b, { left: win.offsetLeft, top: win.offsetTop, width: win.offsetWidth, height: win.offsetHeight }); i.style.opacity = 0; i.style.transition = `opacity ${MOTION.fade}ms`; requestAnimationFrame(() => i.style.opacity = 1); PLAY.intakeEl = i; PLAY.intakeName = win.classList.contains('settings') ? 'Settings · Display' : 'Notes · Trip planning'; }
    else PLAY.intakeName = null;
    later(() => openNote(anchor), MOTION.halo + 60);
  } else { PLAY.intakeName = null; openNote(anchor); }
}
function noteState(extra = {}) {
  const base = { agent: PLAY.agent, running: PLAY.running, intake: PLAY.intakeName ? { kind: 'window', text: PLAY.intakeName } : (PLAY.anchor && PLAY.anchor.selection ? { kind: 'selection', text: PLAY.anchor.selection } : { kind: 'none' }), foot: '<kbd>Enter</kbd> send · hold ' + ms('mic') + ' to talk', footRight: '<kbd>Esc</kbd> close' };
  return Object.assign(base, extra);
}
function unfold(n) { // the note out of its anchor: fade + spring.unfold on scale
  n.style.opacity = 0; n.style.transform = 'scale(.2)';
  requestAnimationFrame(() => { n.style.transition = `opacity ${MOTION.fade}ms ${MOTION.easing.standard}`; n.style.opacity = 1; });
  spring({ from: 0.2, to: 1, ...MOTION.spring.unfold, onUpdate: v => n.style.transform = `scale(${v})`, onEnd: () => { n.style.transform = ''; } });
}
function openNote(anchor) {
  const b = PLAY.board; PLAY.state = 'compose';
  PLAY.label && (PLAY.label.style.opacity = 0, later(() => PLAY.label && PLAY.label.remove(), MOTION.fade));
  const n = note(noteState({ composer: { focus: true }, suggest: PLAY.intakeName === 'Settings · Display' ? [['dark_mode', 'Turn on dark theme'], ['format_size', 'Make text bigger'], ['battery_saver', 'Turn on Battery saver']] : [['tune', 'Change a setting'], ['summarize', 'Summarise this'], ['help', 'What can you do here?']] }));
  const geo = place(b, n, anchor); PLAY.note = n; PLAY.geo = geo; wire(n); unfold(n);
  if (PLAY.halo) { const ha = PLAY.halo; later(() => { ha.style.transition = `opacity ${MOTION.fadeSlow}ms`; ha.style.opacity = 0; later(() => ha.remove(), MOTION.fadeSlow); }, 240); PLAY.halo = null; }
  trace('note opened', { via: anchor.via || anchor.from });
}
function wire(n) {
  n.querySelectorAll('.suggest span').forEach(s => { s.dataset.act = 'suggest'; });
  n.querySelectorAll('[data-role="close"]').forEach(e => e.dataset.act = 'close');
  n.querySelectorAll('[data-role="background"]').forEach(e => e.dataset.act = 'background');
  const mic = n.querySelector('.mic'); if (mic) { mic.dataset.act = 'mic'; }
  const send = n.querySelector('.send'); if (send) send.dataset.act = 'send';
  const agent = n.querySelector('[data-role="agent"]'); if (agent) agent.dataset.act = 'picker';
  n.querySelectorAll('.btn').forEach(bt => {
    const t = bt.textContent.trim(), k = bt.dataset.kind;
    if (k) { bt.dataset.act = /^allow/.test(k) ? 'allow' : 'deny'; return; }   // consent options, by ACP kind
    if (bt.dataset.act) return;                                                   // mirror controls carry data-act in their markup
    if (/Undo|Turn it back on/.test(t)) bt.dataset.act = 'undo'; if (/Try again/.test(t)) bt.dataset.act = 'retry';
  });
  n.querySelectorAll('.picker .it').forEach((it, i) => { it.dataset.act = 'pick'; it.dataset.agent = ['claude', 'opencode', 'cursor', 'codex', 'add'][i]; });
  PLAY.field = n.querySelector('.field .text');
}
function drawField() { if (!PLAY.field) return; PLAY.field.className = 'text' + (PLAY.text ? '' : ' ph'); PLAY.field.innerHTML = (PLAY.text || 'Ask Quire') + '<span class="caret"></span>'; const s = PLAY.note.querySelector('.send'); s && s.classList.toggle('disabled', !PLAY.text); }
// focus: the consent card when it arrives (its first Tab stop is the agent's reject option); Resume when paused;
// the result's first button when a run ends (§6.2)
function focusConsent() { const c = PLAY.note && PLAY.note.querySelector('.card.consent'); if (c) { c.focus(); trace('focus', { on: 'consent card' }); } }
function focusAct(a) { const b = PLAY.note && PLAY.note.querySelector(`[data-act="${a}"]`); if (b) { b.focus(); trace('focus', { on: a }); } }
function focusResult() { const b = PLAY.note && PLAY.note.querySelector('.n-body .btns .btn'); if (b) { b.focus(); trace('focus', { on: b.textContent.trim() }); } }

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
  PLAY.state = 'working'; PLAY.running = true; const you = t; PLAY.you = you; trace('send', { you });
  const lower = t.toLowerCase();
  if (/bluetooth|in settings|find/.test(lower)) return runMirror(you);
  if (/battery|bright|night|read|dark|text|bigger|setting/.test(lower)) return runSettings(you);
  return runAnswer(you);
}
function runAnswer(you) {
  swap({ you, thinking: true, blocks: [{ type: 'thought', t: 'Thinking' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Answering', footRight: '<kbd>Esc</kbd> stop' });
  const words = ANSWER_ADAPTIVE.replace(/<[^>]+>/g, '').split(' '); let i = 0;
  later(function tick() { i = Math.min(words.length, i + 3); const end = i >= words.length; if (end) { PLAY.running = false; PLAY.state = 'done'; } swap({ you, thinking: !end, blocks: [{ type: 'answer', html: '<p>' + words.slice(0, i).join(' ') + '</p>', caret: !end }], composer: { placeholder: 'Ask a follow-up' }, foot: end ? 'Done' : 'Answering', footRight: '<kbd>Esc</kbd> ' + (end ? 'close' : 'stop') }); if (!end) later(tick, 90); else trace('run ended', { how: 'end_turn' }); }, 700);
}
function runSettings(you) {
  const list = STEPS_BATTERY.map(s => ({ ...s, st: 'pending' }));
  const draw = (extra) => swap(Object.assign({ you, thinking: true, blocks: [{ type: 'steps', list }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Working', footRight: '<kbd>Esc</kbd> stop' }, extra));
  draw();
  later(() => { list[0].st = 'running'; draw(); }, 500);
  later(() => { list[0].st = 'done'; list[1].st = 'running'; draw(); }, 1400);
  later(() => { list[1].st = 'done'; draw(); }, 2200);
  later(() => { PLAY.state = 'consent'; PLAY.pending = { list, you, options: OPTIONS_CLAUDE }; trace('request_permission', { options: OPTIONS_CLAUDE.map(o => o.optionId) });
    swap({ you, blocks: [{ type: 'steps', list: list.slice(0, 2) }, { type: 'consent', title: 'Change 2 settings', meta: 'Settings tool', options: OPTIONS_CLAUDE, changes: [{ k: 'Battery saver', w: 'Settings · Battery', old: 'Off', nu: 'On' }, { k: 'Brightness level', w: 'Settings · Display', old: '80%', nu: '40%' }], why: 'You can undo this from the note or from the Quire button.' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Waiting for you', footRight: '<kbd>Esc</kbd> stop' });
    focusConsent(); }, 2700);
}
function answerPermission(outcome, optionId) { // what goes back on the wire: {outcome:'selected', optionId} or {outcome:'cancelled'}
  trace('request_permission answered', optionId ? { outcome, optionId } : { outcome }); PLAY.pending = null;
}
function afterAllow(optionId) {
  const { list, you } = PLAY.pending; answerPermission('selected', optionId); PLAY.state = 'working';
  const draw = () => swap({ you, thinking: true, blocks: [{ type: 'steps', list }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Working', footRight: '<kbd>Esc</kbd> stop' });
  list[2].st = 'running'; draw();
  later(() => { list[2].st = 'done'; list[3].st = 'running'; draw(); const sw = PLAY.board.querySelector('.window.settings'); if (sw) sw.replaceWith(settingsWindow({ settings: { page: 'battery', saver: true } }, PLAY.board.clientHeight)); }, 900);
  later(() => { list[3].st = 'done'; PLAY.running = false; PLAY.state = 'done'; const sw = PLAY.board.querySelector('.window.settings'); if (sw) { sw.replaceWith(settingsWindow({ settings: { brightness: 40, changed: 'brightness' } }, PLAY.board.clientHeight)); }
    swap({ you, blocks: [{ type: 'steps', folded: true, list }, { type: 'result', msg: 'Battery saver is on and brightness is at 40%.', sub: 'Changed 2 settings' }, { type: 'btns', html: '<button type="button" class="btn tonal">' + ms('undo') + 'Undo both</button><button type="button" class="btn text">Show changes</button>' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Done', footRight: '<kbd>Esc</kbd> close' }); focusResult(); trace('run ended', { how: 'end_turn' }); }, 1900);
}
function afterDeny(optionId) {
  const { list, you } = PLAY.pending; answerPermission('selected', optionId); PLAY.running = false; PLAY.state = 'done';
  swap({ you, blocks: [{ type: 'steps', list: list.slice(0, 2) }, { type: 'result', icon: 'block', cls: 'warn', msg: 'Nothing was changed.', sub: 'You didn’t allow the change. The agent stopped.' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Stopped', footRight: '<kbd>Esc</kbd> close' });
  focusResult(); trace('run ended', { how: 'denied' });
}
// Honest copy for a stop: what was done, what was interrupted (and may be partly applied), what to check.
function stopCopy(st, steps) {
  if (st === 'consent') return { msg: 'Stopped.', sub: 'You stopped the task before answering. The agent was told the request was cancelled. Nothing was changed.' };
  if (st === 'sysconsent') return { msg: 'Stopped.', sub: 'Settings was not opened. Nothing was changed.' };
  if (!steps) return { msg: 'Stopped.', sub: 'The answer was cut off. Nothing was changed.' };
  const done = steps.filter(s => s.st === 'done' && s.effect).map(s => s.effect), cut = steps.find(s => s.st === 'running');
  const n = steps.filter(s => s.st === 'done').length, parts = [];
  if (st === 'mirror') parts.push('Settings was closed.');
  if (done.length) parts.push(done.join('. ') + '.');
  if (cut && cut.effect) parts.push(`${cut.t} was interrupted and may be partly applied; check ${cut.where || 'Settings'}.`);
  else if (cut) parts.push(`${cut.t} was interrupted.`);
  if (!done.length && !(cut && cut.effect)) parts.push('Nothing was changed.');
  return { msg: `Stopped after ${n} of ${steps.length} steps.`, sub: parts.join(' '), undo: done.length > 0 };
}
function stopRun(how) { // Esc or Stop: cancel the run. Not hiding; the task ends here.
  const b = PLAY.board, st = PLAY.state; clearTimers();
  PLAY.sys && PLAY.sys.remove(); PLAY.sys = null;
  if (st === 'consent' && PLAY.pending) answerPermission('cancelled');
  const steps = st === 'mirror' && PLAY.m ? PLAY.m.steps : (PLAY.pending ? PLAY.pending.list : (PLAY.steps || ((PLAY.last && PLAY.last.blocks || []).filter(x => x.type === 'steps').map(x => x.list)[0])));
  const copy = stopCopy(st, steps);
  const shown = steps ? steps.filter(s => s.st !== 'pending').map(s => s.st === 'running' ? { ...s, st: 'failed' } : s) : null;
  const prior = (PLAY.last && PLAY.last.blocks || []).filter(x => x.type === 'answer' || x.type === 'plan').map(x => x.type === 'answer' ? { ...x, caret: false } : x);
  PLAY.running = false; PLAY.state = 'done'; PLAY.m = null; PLAY.pending = null; PLAY.steps = null;
  swap({ you: PLAY.you, blocks: [...prior, ...(shown ? [{ type: 'steps', list: shown }] : []), { type: 'result', icon: 'stop_circle', cls: 'warn', msg: copy.msg, sub: copy.sub }, ...(copy.undo ? [{ type: 'btns', html: '<button type="button" class="btn tonal">' + ms('undo') + 'Undo</button><button type="button" class="btn text">Show changes</button>' }] : [])], composer: { placeholder: 'Ask a follow-up' }, foot: 'Stopped', footRight: '<kbd>Esc</kbd> close' });
  focusResult(); trace('run ended', { how: 'cancelled by ' + how, from: st });
}
function runMirror(you) {
  const list = [{ st: 'running', kind: 'read', t: 'Listing apps' }, { st: 'pending', kind: 'app', t: 'Asking to use Settings' }];
  swap({ you, thinking: true, blocks: [{ type: 'steps', list }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Working', footRight: '<kbd>Esc</kbd> stop' });
  later(() => { list[0].st = 'done'; list[1].st = 'running'; PLAY.state = 'sysconsent'; PLAY.you = you; swap({ you, thinking: true, blocks: [{ type: 'steps', list }, { type: 'result', icon: 'shield', cls: 'warn', msg: 'Waiting for your permission', sub: 'The system is asking whether Claude Code may use Settings.' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Waiting for you', footRight: '<kbd>Esc</kbd> stop' });
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
  later(() => { if (m.paused) return; steps[1].st = 'done'; steps[2].st = 'running'; m.title = 'Connected devices'; m.settings = { page: 'devices' }; m.ghost = null; m.tap = true; m.target = '.page .pref:nth-of-type(1)'; m.status = 'Step 3 of 3'; draw(); }, 2600);
  later(() => { if (m.paused) return; mirrorDone(); }, 4200);
}
function mirrorDone() {
  const m = PLAY.m, steps = m.steps; steps.forEach(s => { if (s.st === 'running') s.st = 'done'; }); m.ghost = null; m.target = null; m.status = 'Done'; PLAY.running = false; PLAY.state = 'done'; PLAY.m = null;
  swap({ you: PLAY.you, blocks: [{ type: 'steps', folded: true, list: steps }, { type: 'result', msg: 'Bluetooth is off.', sub: 'Settings was returned to you · 3 steps' }, { type: 'btns', html: '<button type="button" class="btn tonal">' + ms('undo') + 'Turn it back on</button>' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Done', footRight: '<kbd>Esc</kbd> close' });
  focusResult(); trace('run ended', { how: 'end_turn' });
}
function act(a, el) {
  const b = PLAY.board;
  switch (a) {
    case 'close': if (PLAY.running) background('hide button'); else closeNote(); break;
    case 'background': background('hide button'); break;
    case 'suggest': PLAY.text = el.textContent.trim(); drawField(); send(); break;
    case 'send': send(); break;
    case 'mic': if (PLAY.state === 'compose') startMic(); break;
    case 'picker': { const open = !!PLAY.note.querySelector('.picker'); swap({ composer: { text: PLAY.text, focus: !open }, picker: open ? null : { sel: PLAY.agent }, suggest: null }); break; }
    case 'pick': if (el.dataset.agent && el.dataset.agent !== 'add') PLAY.agent = el.dataset.agent; swap({ composer: { text: PLAY.text, focus: true } }); break;
    case 'allow': if (PLAY.state === 'consent') afterAllow(el.dataset.option); break;
    case 'deny': if (PLAY.state === 'consent') afterDeny(el.dataset.option); break;
    case 'sys-allow': PLAY.sys.remove(); PLAY.sys = null; trace('platform consent', { outcome: 'allowed' }); mirrorOpen(); break;
    case 'sys-deny': PLAY.sys.remove(); PLAY.sys = null; PLAY.running = false; PLAY.state = 'done'; trace('platform consent', { outcome: 'denied' }); swap({ you: PLAY.you, blocks: [{ type: 'result', icon: 'block', cls: 'warn', msg: 'Settings was not opened.', sub: 'You didn’t allow computer control. The agent stopped.' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Stopped', footRight: '<kbd>Esc</kbd> close' }); break;
    case 'pause': if (PLAY.m) { PLAY.m.paused = !PLAY.m.paused; PLAY.m.status = PLAY.m.paused ? 'Paused by you' : 'Resuming'; PLAY.mDraw(); trace(PLAY.m.paused ? 'paused' : 'resumed'); if (PLAY.m.paused) focusAct('pause'); else later(() => { if (PLAY.m) mirrorDone(); }, 1500); } break;
    case 'stop': if (PLAY.m) stopRun('Stop button'); break;
    case 'takeover': if (PLAY.m) { clearTimers(); const steps = PLAY.m.steps, done = steps.filter(s => s.st === 'done' && s.effect).map(s => s.effect); PLAY.running = false; PLAY.state = 'done'; PLAY.m = null;
      swap({ you: PLAY.you, blocks: [{ type: 'steps', folded: true, list: steps }, { type: 'result', icon: 'open_in_full', msg: 'Settings is on your screen now.', sub: 'The agent stopped. ' + (done.length ? done.join('. ') + '.' : 'Bluetooth was not changed yet.') }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Handed over', footRight: '<kbd>Esc</kbd> close' });
      const H = b.clientHeight; const w = settingsWindow({ settings: {} }, H); w.style.opacity = 0; w.style.transition = `opacity ${MOTION.fadeSlow}ms`; b.insertBefore(w, b.querySelector('.taskbar')); requestAnimationFrame(() => w.style.opacity = 1); focusResult(); trace('run ended', { how: 'taken over' }); } break;
    case 'undo': swap({ you: PLAY.you, blocks: [{ type: 'result', icon: 'undo', msg: 'Undone.', sub: 'The settings are back to what they were.' }], composer: { placeholder: 'Ask a follow-up' }, foot: 'Undone', footRight: '<kbd>Esc</kbd> close' }); { const sw = b.querySelector('.window.settings'); if (sw) sw.replaceWith(settingsWindow({ settings: {} }, b.clientHeight)); } trace('undone'); break;
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
function foldAnim(n, to, onDone) { // the note into the pointer (scale to its origin) or into the taskbar button
  const b = PLAY.board;
  if (to === 'taskbar') { const tb = b.querySelector('.taskbar .tb-quire'); const r = tb.getBoundingClientRect(), rb = b.getBoundingClientRect(); const tx = r.left - rb.left + 22 - (parseFloat(n.style.left) + n.offsetWidth / 2), ty = r.top - rb.top + 22 - (parseFloat(n.style.top) + n.offsetHeight / 2); n.style.transformOrigin = '50% 50%'; spring({ from: 0, to: 1, ...MOTION.spring.fold, onUpdate: v => { n.style.transform = `translate(${tx * v}px, ${ty * v}px) scale(${1 - 0.9 * v})`; n.style.opacity = 1 - v * 0.9; }, onEnd: () => { n.remove(); onDone && onDone(); } }); }
  else { spring({ from: 1, to: 0.2, ...MOTION.spring.fold, onUpdate: v => { n.style.transform = `scale(${v})`; n.style.opacity = (v - 0.2) / 0.8; }, onEnd: () => { n.remove(); onDone && onDone(); } }); }
}
function closeNote() { // only for a note with no task running (compose, done, stopped)
  const n = PLAY.note; clearTimers(); PLAY.sys && PLAY.sys.remove(); PLAY.sys = null; PLAY.intakeEl && PLAY.intakeEl.remove(); PLAY.intakeEl = null;
  if (n) foldAnim(n, 'pointer');
  PLAY.note = null; PLAY.state = 'idle'; PLAY.running = false; PLAY.hidden = false; PLAY.m = null; PLAY.pending = null; PLAY.text = ''; PLAY.last = null; PLAY.lastCls = '';
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
  if (qs.get('play')) { playInit(theme, size); return; }
  const one = qs.get('screen');
  if (one && S[one]) { document.body.classList.add('single'); renderScreen(one, theme, size, true, qs.get('anno') !== '1'); return; }
  for (const id of ORDER) { renderScreen(id, 'light', size); renderScreen(id, 'dark', size); }
})();
