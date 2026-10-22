// Svitlo Poltava card — the schedule panel from the "Графік на сьогодні" popup.
//
// WHY
//   The upstream svitlo card draws a compact timeline. Eugene's dashboard uses
//   the wider panel: one 24-hour rail, one row per window, the "now" line, the
//   plan and the measured hours. This file carries that panel as a standalone
//   card, so the component ships the design it is used with.
//
// DATA
//   entity             the schedule sensor; default sensor.svitlo_poltava_3_1_electricity
//   presence_entity    the real light; default binary_sensor.grid_present when it
//                      exists, otherwise binary_sensor.svitlo_poltava_3_1_power_present
//   off_today_entity   measured outage hours; default sensor.grid_off_today when it
//                      exists, otherwise the card prints "—"
//   title              header text; default follows hass.language
//
//   The schedule sensor must carry `today_48half` and `tomorrow_48half` in its
//   attributes. Both the old svitlo_live status sensor and the new
//   svitlo_poltava status sensor do.
//
// STATES
//   on        green slot
//   off       red slot
//   possible  hollow grey slot; a warning, never an outage
//
// LANGUAGE
//   hass.language: uk when it starts with "uk", otherwise en.

const TAG = 'svitlo-poltava-card';

const DEFAULTS = {
  entity: '',
  presence_entity: '',
  off_today_entity: '',
  title: '',
};

const TEXT = {
  uk: {
    title: 'Графік на сьогодні',
    tileTitle: 'Наявність світла',
    powerOn: 'Світло є', powerOff: 'Світла немає', noData: 'Немає даних',
    noWindows: 'вікон немає', close: 'Закрити',
    possible: 'можливе', now: 'зараз', next: 'наступне', later: 'далі',
    hours: 'год', minutes: 'хв', until: 'до',
    empty: 'На сьогодні графіка немає', tomorrow: 'Завтра',
    notPublished: 'ще не опубліковано',
    lightOn: 'Світло є', onSchedule: 'за графіком', outage: 'Відключення',
    possibleOutage: 'Можливе відключення', noPower: 'Світла немає',
    noMore: 'більше вікон немає', plan: 'План', actual: 'Фактично',
    possibleTail: ' + можливі',
  },
  en: {
    title: "Today's schedule",
    tileTitle: 'Power present',
    powerOn: 'Power on', powerOff: 'No power', noData: 'No data',
    noWindows: 'no windows', close: 'Close',
    possible: 'possible', now: 'now', next: 'next', later: 'later',
    hours: 'h', minutes: 'min', until: 'until',
    empty: 'No schedule for today', tomorrow: 'Tomorrow',
    notPublished: 'not published yet',
    lightOn: 'Light on', onSchedule: 'on schedule', outage: 'Outage',
    possibleOutage: 'Possible outage', noPower: 'No power',
    noMore: 'no more windows', plan: 'Plan', actual: 'Actual',
    possibleTail: ' + possible',
  },
};

const langOf = (hass) => (String((hass && hass.language) || 'en').toLowerCase().startsWith('uk') ? 'uk' : 'en');
const escape = (value) => String(value).replace(/[&<>"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
const STATE_RED = 'rgb(var(--rgb-red, 244, 67, 54))';
const STATE_GREEN = 'rgb(var(--rgb-green, 76, 175, 80))';
const STATE_GREY = 'rgb(var(--rgb-disabled, 107, 107, 107))';

function findScheduleEntity(states) {
  const ids = Object.keys(states).filter((id) => (
    /^sensor\.svitlo_poltava_.*_electricity$/.test(id)
    && Array.isArray(states[id].attributes && states[id].attributes.today_48half)
  ));
  ids.sort();
  return ids[0] || 'sensor.svitlo_poltava_3_1_electricity';
}

const CARD_STYLE = `
  :host { display: block; height: 100%; }
  ha-card.tile {
    display: flex; flex-direction: column; height: 100%; box-sizing: border-box;
    cursor: pointer; border: none;
    background: var(--ha-card-background, var(--card-background-color));
    text-align: left;
  }
  ha-card.tile:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
  .content {
    display: flex; flex-direction: row; align-items: center;
    padding: 0 10px; min-height: var(--row-height, 56px);
    flex: 1; min-width: 0; box-sizing: border-box; gap: 10px;
  }
  .content ha-tile-icon {
    flex: none;
    --tile-icon-color: var(--tile-color);
    --tile-icon-opacity: 0;
  }
  .content ha-tile-info { flex: 1; min-width: 0; }

  dialog.schedule-dialog {
    margin: 4vh auto auto;
    padding: 0;
    border: none;
    width: min(600px, calc(100vw - 24px));
    max-height: min(86vh, 900px);
    border-radius: 24px;
    background: #1c1c1c;
    color: #fff;
    box-shadow: 0 24px 64px rgba(0, 0, 0, .55);
    overflow: hidden;
  }
  dialog.schedule-dialog[open] { display: flex; flex-direction: column; }
  dialog.schedule-dialog::backdrop { background: rgba(0, 0, 0, .55); }
  .head {
    display: flex; align-items: center; gap: 8px;
    padding: 10px 10px 6px 10px;
    flex: none;
  }
  .heading {
    flex: 1; min-width: 0;
    font-size: 20px; font-weight: 600; color: #fff;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .close {
    flex: none; width: 40px; height: 40px;
    display: grid; place-items: center;
    border: none; border-radius: 50%;
    background: rgba(255, 255, 255, .08); color: rgba(255, 255, 255, .85);
    cursor: pointer;
  }
  .close:hover { background: rgba(255, 255, 255, .14); }
  .body { min-height: 0; overflow: auto; }
  @media (max-width: 600px) {
    dialog.schedule-dialog { margin: 2vh auto auto; }
  }
`;
function renderSchedule(hass, config) {
  const states = (hass && hass.states) || {};
  const L = TEXT[langOf(hass)];
  const E = config.entity || findScheduleEntity(states);
  const stateObj = states[E];
  const a = (stateObj && stateObj.attributes) || {};
  const today = a.today_48half || [];
  const tomorrow = a.tomorrow_48half || [];

  const presence = config.presence_entity
    || (states['binary_sensor.grid_present'] ? 'binary_sensor.grid_present' : 'binary_sensor.svitlo_poltava_3_1_power_present');
  const offToday = config.off_today_entity
    || (states['sensor.grid_off_today'] ? 'sensor.grid_off_today' : '');

  const pad = (k) => String(k).padStart(2, '0');
  const fmt = (i) => `${pad(Math.floor(i / 2))}:${i % 2 ? '30' : '00'}`;

  const runsOf = (series) => {
    const runs = [];
    let open = null;
    let kind = null;
    series.forEach((state, index) => {
      const next = state === 'off' || state === 'possible' ? state : null;
      if (next === kind && next !== null) return;
      if (open !== null) runs.push({ start: open, end: index, kind });
      open = next === null ? null : index;
      kind = next;
    });
    if (open !== null) runs.push({ start: open, end: series.length, kind });
    return runs;
  };

  const runs = runsOf(today);
  const runsTomorrow = runsOf(tomorrow);

  const groupRuns = (series) => {
    const out = [];
    series.forEach((run) => {
      const last = out[out.length - 1];
      if (last && last.end === run.start) {
        last.parts.push(run);
        last.end = run.end;
      } else {
        out.push({ start: run.start, end: run.end, parts: [run] });
      }
    });
    return out;
  };
  const blocks = groupRuns(runs);

  const d = new Date();
  const nowi = d.getHours() * 2 + (d.getMinutes() >= 30 ? 1 : 0);
  const nowPct = ((d.getHours() * 60 + d.getMinutes()) / 1440 * 100).toFixed(2);

  // The real light, when the user has a relay sensor. Without it the plan is
  // the only truth, so the current slot decides.
  const on = presence && states[presence]
    ? states[presence].state === 'on'
    : today[nowi] === 'on';

  const nextAt = blocks.findIndex((b) => b.start > nowi);
  const curAt = blocks.findIndex((b) => b.start <= nowi && nowi < b.end);
  const stateOf = (b, i) => (b.end <= nowi ? 'past' : i === curAt ? 'now' : i === nextAt ? 'next' : 'future');
  const shownState = (state) => (on && state === 'now' ? 'lit' : state);
  const allPossible = (b) => b.parts.every((part) => part.kind === 'possible');
  const wordOf = (b, i) => {
    const state = stateOf(b, i);
    if (state === 'past') return '';
    if (allPossible(b)) return L.possible;
    if (state === 'now') return L.now;
    if (state === 'next') return L.next;
    return L.later;
  };
  const timeOf = (b) => {
    const [first, ...rest] = b.parts;
    const head = `${fmt(first.start)}–${fmt(first.end)}`;
    const tails = rest.map((part) => `<span class="tail">${fmt(part.end)}</span>`).join('');
    return head + tails;
  };
  const durationOf = (b) => {
    const hours = (kind) => b.parts.filter((part) => part.kind === kind)
      .reduce((sum, part) => sum + (part.end - part.start), 0) * 0.5;
    const sure = hours('off');
    const maybe = hours('possible');
    const head = sure ? `${sure} ${L.hours}` : '';
    return head + (maybe ? `<span class="tail">${sure ? '+' : ''}${maybe}</span>` : '');
  };

  const style = `<style>
    .wrap { color: rgba(255,255,255,.92); text-align: left; padding: 4px 18px 14px; display: flex; flex-direction: column; }
    .tl { position: relative; height: 18px; border-radius: 9px; background: rgba(255,255,255,.07); flex: none; }
    .blk { position: absolute; top: 3px; height: 12px; border-radius: 6px; box-sizing: border-box; }
    .blk.past { background: rgba(245,166,35,.55); }
    .blk.now { background: #ff5c5c; box-shadow: 0 0 14px rgba(255,92,92,.55); }
    .blk.next { background: rgba(255,92,92,.62); }
    .blk.future { background: rgba(255,92,92,.30); }
    .blk.possible { background: rgba(255,255,255,.30); }
    .blk.lit { background: rgba(90,208,122,.45); box-shadow: none; }
    .nowline { position: absolute; top: -3px; height: 24px; width: 2px; border-radius: 1px; background: rgba(255,255,255,.85); }
    .ticks { display: flex; justify-content: space-between; margin-top: 7px; font-size: 11px; color: rgba(255,255,255,.35); font-variant-numeric: tabular-nums; flex: none; }
    .status { display: flex; align-items: center; gap: 8px; margin-top: 12px; font-size: 13px; letter-spacing: .1px; }
    .status i { width: 8px; height: 8px; border-radius: 50%; flex: none; }
    .status span { font-variant-numeric: tabular-nums; }
    .status.now { color: #ff9a9a; }
    .status.now i { background: #ff5c5c; box-shadow: 0 0 0 3px rgba(255,92,92,.22); }
    .status.possible { color: rgba(255,255,255,.62); }
    .status.possible i { background: rgba(255,255,255,.4); }
    .status.on { color: rgba(255,255,255,.66); }
    .status.on i { background: #5ad07a; }
    .rows { margin-top: 10px; }
    .row { display: grid; grid-template-columns: 8px minmax(0, 1fr) auto; grid-template-areas: 'dot time right'; align-items: center; gap: 10px; padding: 9px 0; }
    .right { grid-area: right; display: flex; align-items: center; gap: 8px; }
    .row i { grid-area: dot; width: 8px; height: 8px; border-radius: 50%; box-sizing: border-box; }
    .row b { grid-area: time; font-weight: 600; font-size: 14px; font-variant-numeric: tabular-nums; letter-spacing: .2px; justify-self: start; }
    .tail { color: rgba(255,255,255,.45); margin-left: 7px; padding-left: 7px; border-left: 1px solid rgba(255,255,255,.14); font-weight: 500; }
    .row span .tail { margin-left: 5px; padding-left: 5px; }
    .row .dur { font-size: 13px; color: rgba(255,255,255,.5); white-space: nowrap; font-variant-numeric: tabular-nums; }
    .row em { font-style: normal; font-size: 11px; text-transform: uppercase; letter-spacing: .5px; padding: 3px 9px; border-radius: 999px; color: rgba(255,255,255,.45); white-space: nowrap; justify-self: end; }
    .row.past i { background: #f5a623; }
    .row.past b { color: rgba(255,255,255,.62); }
    .row.past span { color: rgba(255,255,255,.38); }
    .row.now i { background: #ff5c5c; box-shadow: 0 0 0 3px rgba(255,92,92,.25); }
    .row.next i { background: #ff5c5c; }
    .row.future i { background: rgba(255,255,255,.30); }
    .row.now { background: rgba(255,92,92,.13); border-radius: 12px; padding: 9px 18px; margin: 0 -18px; }
    .row.now b { color: #fff; }
    .row.now em { background: #ff5c5c; color: #1a0d0d; font-weight: 700; }
    .row.next { background: rgba(255,92,92,.04); border-radius: 12px; padding: 9px 18px; margin: 0 -18px; }
    .row.next em { background: transparent; border: 1px solid rgba(255,92,92,.5); color: #ff9a9a; }
    .row.future b { color: rgba(255,255,255,.8); }
    .row.future em { background: none; color: rgba(255,255,255,.35); padding: 3px 0; }
    .row.possible b { font-weight: 500; color: rgba(255,255,255,.72); }
    .row.possible i { background: rgba(255,255,255,.35); }
    .row.possible em { background: rgba(255,255,255,.07); color: rgba(255,255,255,.58); }
    .row.possible.next { box-shadow: none; }
    .row.lit { background: rgba(90,208,122,.07); border-radius: 12px; padding: 9px 18px; margin: 0 -18px; }
    .row.lit i { background: #5ad07a; box-shadow: 0 0 0 3px rgba(90,208,122,.18); }
    .row.lit b { color: #fff; }
    .row.lit em { background: rgba(255,255,255,.09); color: rgba(255,255,255,.66); font-weight: 600; }
    .tomorrow { margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,.07); }
    .tomorrow .label { display: block; font-size: 11px; text-transform: uppercase; letter-spacing: .5px; color: rgba(255,255,255,.4); margin-bottom: 7px; }
    .chips { display: flex; flex-wrap: wrap; gap: 6px; }
    .group { display: inline-flex; border-radius: 999px; overflow: hidden; }
    .part { font-size: 11px; padding: 3px 8px; white-space: nowrap; font-variant-numeric: tabular-nums; }
    .part.off { background: rgba(255,92,92,.14); color: #ff9a9a; }
    .part.possible { background: rgba(255,255,255,.07); color: rgba(255,255,255,.55); }
    .group .part + .part { border-left: 1px solid rgba(0,0,0,.4); }
    .muted { font-size: 12px; color: rgba(255,255,255,.45); }
    .foot { display: flex; justify-content: space-between; gap: 12px; margin-top: 10px; padding-top: 11px; border-top: 1px solid rgba(255,255,255,.07); font-size: 12px; color: rgba(255,255,255,.5); }
    .empty { padding: 18px 0; color: rgba(255,255,255,.5); }
    @media (max-width: 600px) {
      .wrap { padding: 8px 16px 14px; }
      .row { padding: 13px 0; }
      .row b { font-size: 16px; }
      .row span, .row em { font-size: 12px; }
      .row.next, .row.now, .row.lit { padding: 13px 16px; margin: 0 -16px; }
      .ticks { font-size: 12px; margin-top: 9px; }
    }
  </style>`;

  if (!blocks.length) {
    return `${style}<div class="wrap"><div class="empty">${L.empty}</div></div>`;
  }

  const nextStart = (runs.find((r) => r.start > nowi) || {}).start;
  const runState = (r) => (r.end <= nowi ? 'past' : r.start <= nowi ? 'now' : r.start === nextStart ? 'next' : 'future');
  const rail = runs.map((r) => `<div class="blk ${shownState(runState(r))} ${r.kind}" style="left:${(r.start / 48 * 100).toFixed(2)}%;width:${((r.end - r.start) / 48 * 100).toFixed(2)}%"></div>`).join('');
  const rows = blocks.map((b, i) => {
    const state = shownState(stateOf(b, i));
    const word = wordOf(b, i);
    const pill = word ? `<em>${word}</em>` : '<em class="none"></em>';
    return `<div class="row ${state} ${allPossible(b) ? 'possible' : ''}"><i></i><b>${timeOf(b)}</b><div class="right">${pill}<span class="dur">${durationOf(b)}</span></div></div>`;
  }).join('');

  const curRun = runs.find((r) => r.start <= nowi && nowi < r.end) || null;
  const nextBlock = nextAt >= 0 ? blocks[nextAt] : null;
  let statusClass = 'on';
  let statusText;
  if (curRun) {
    const maybe = curRun.kind === 'possible';
    if (on) {
      statusClass = 'on';
      statusText = `${L.lightOn} · ${maybe ? L.possible : L.onSchedule} ${L.until} ${fmt(curRun.end)}`;
    } else {
      statusClass = maybe ? 'possible' : 'now';
      statusText = `${maybe ? L.possibleOutage : L.outage} ${L.until} ${fmt(curRun.end)}`;
    }
  } else if (!on) {
    statusClass = 'now';
    statusText = L.noPower;
  } else if (!nextBlock) {
    statusText = `${L.lightOn} · ${L.noMore}`;
  } else if (allPossible(nextBlock)) {
    statusText = `${L.lightOn} · ${L.possible} ${fmt(nextBlock.start)}`;
  } else {
    statusText = `${L.lightOn} · ${L.next} ${fmt(nextBlock.start)}`;
  }
  const status = `<div class="status ${statusClass}"><i></i><span>${statusText}</span></div>`;

  const plan = a.today_outage_hours == null ? '—' : `${a.today_outage_hours} ${L.hours}`;
  const gh = offToday && states[offToday] ? parseFloat(states[offToday].state) : NaN;
  const gm = Number.isNaN(gh) ? null : Math.round(gh * 60);
  const gtxt = gm === null
    ? '—'
    : gm >= 60
      ? `${Math.floor(gm / 60)} ${L.hours} ${gm % 60} ${L.minutes}`
      : `${gm} ${L.minutes}`;
  const possibleCount = runs.filter((r) => r.kind === 'possible').length;
  const groups = [];
  runsTomorrow.forEach((run) => {
    const last = groups[groups.length - 1];
    if (last && last.end === run.start) {
      last.parts.push(run);
      last.end = run.end;
    } else {
      groups.push({ start: run.start, end: run.end, parts: [run] });
    }
  });
  const chips = groups
    .map((group) => `<span class="group">${group.parts.map((run, i) => `<span class="part ${run.kind}">${i === 0 ? `${fmt(run.start)}–${fmt(run.end)}` : fmt(run.end)}</span>`).join('')}</span>`)
    .join('');
  const tomorrowBlock = runsTomorrow.length
    ? `<div class="tomorrow"><span class="label">${L.tomorrow}</span><div class="chips">${chips}</div></div>`
    : `<div class="tomorrow"><span class="label">${L.tomorrow}</span><span class="muted">${L.notPublished}</span></div>`;

  return `${style}<div class="wrap"><div class="tl">${rail}<div class="nowline" style="left:${nowPct}%"></div></div><div class="ticks"><span>00</span><span>06</span><span>12</span><span>18</span><span>24</span></div>${status}<div class="rows">${rows}</div>${tomorrowBlock}<div class="foot"><span>${L.plan} ${plan}${possibleCount ? L.possibleTail : ''}</span><span>${L.actual} ${gtxt}</span></div></div>`;
}

class SvitloPoltavaCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._config = { ...DEFAULTS };
    this._built = false;
  }

  setConfig(config) {
    this._config = { ...DEFAULTS, ...(config || {}) };
    if (this._hass) {
      if (!this._built) this._build();
      this._update();
    }
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._built) this._build();
    this._update();
  }

  getCardSize() {
    return 1;
  }

  getGridOptions() {
    return { columns: 6, rows: 1, min_columns: 4, min_rows: 1 };
  }

  static getStubConfig() {
    return {};
  }

  _build() {
    this.shadowRoot.innerHTML = `<style>${CARD_STYLE}</style>
      <ha-card class="tile" role="button" tabindex="0">
        <div class="content">
          <ha-tile-icon><ha-icon slot="icon"></ha-icon></ha-tile-icon>
          <ha-tile-info>
            <span slot="primary"></span>
            <span slot="secondary"></span>
          </ha-tile-info>
        </div>
      </ha-card>
      <dialog class="schedule-dialog">
        <div class="head">
          <button class="close" type="button"><ha-icon icon="mdi:close"></ha-icon></button>
          <div class="heading"></div>
        </div>
        <div class="body"></div>
      </dialog>`;

    const q = (sel) => this.shadowRoot.querySelector(sel);
    this._tile = q('ha-card.tile');
    this._icon = q('ha-tile-icon ha-icon');
    this._title = q('ha-tile-info span[slot="primary"]');
    this._secondary = q('ha-tile-info span[slot="secondary"]');
    this._dialog = q('dialog.schedule-dialog');
    this._heading = q('.heading');
    this._body = q('.body');
    this._close = q('.close');

    this._tile.addEventListener('click', () => this._open());
    this._tile.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      this._open();
    });
    this._close.addEventListener('click', () => this._dialog.close());
    this._dialog.addEventListener('click', (event) => {
      if (event.target === this._dialog) this._dialog.close();
    });

    const L = TEXT[langOf(this._hass)];
    this._close.title = L.close;
    this._close.setAttribute('aria-label', L.close);
    this._built = true;
  }

  _open() {
    if (!this._hass) return;
    this._body.innerHTML = renderSchedule(this._hass, this._config);
    if (!this._dialog.open) this._dialog.showModal();
  }

  _update() {
    if (!this._built || !this._hass) return;
    const L = TEXT[langOf(this._hass)];
    const view = this._view(L);
    this._title.textContent = view.title;
    this._secondary.textContent = view.secondary;
    this._icon.setAttribute('icon', view.icon);
    this._tile.style.setProperty('--tile-color', view.color);
    this._heading.textContent = this._config.dialog_title || L.title;
    if (this._dialog.open) {
      this._body.innerHTML = renderSchedule(this._hass, this._config);
    }
  }

  _view(L) {
    const states = (this._hass && this._hass.states) || {};
    const entity = this._config.entity || findScheduleEntity(states);
    const stateObj = states[entity];
    if (!stateObj) {
      return { title: this._config.title || L.tileTitle, secondary: L.noData, icon: 'mdi:transmission-tower-off', color: STATE_GREY };
    }

    const series = (stateObj.attributes && stateObj.attributes.today_48half) || [];
    const now = new Date();
    const idx = now.getHours() * 2 + (now.getMinutes() >= 30 ? 1 : 0);
    const presence = this._config.presence_entity
      || (states['binary_sensor.grid_present'] ? 'binary_sensor.grid_present' : 'binary_sensor.svitlo_poltava_3_1_power_present');
    const on = states[presence]
      ? states[presence].state === 'on'
      : series[idx] === 'on';

    return {
      title: this._config.title || L.tileTitle,
      secondary: on ? L.powerOn : L.powerOff,
      icon: on ? 'mdi:transmission-tower' : 'mdi:transmission-tower-off',
      color: on ? STATE_GREEN : STATE_RED,
    };
  }
}

if (!customElements.get(TAG)) customElements.define(TAG, SvitloPoltavaCard);

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === TAG)) {
  window.customCards.push({
    type: TAG,
    name: 'Svitlo Poltava',
    description: 'A power tile that opens the outage schedule in a native dialog.',
    preview: false,
  });
}
