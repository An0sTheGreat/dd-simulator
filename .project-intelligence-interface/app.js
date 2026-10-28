/* Buildless, offline project intelligence dashboard. All project text is escaped before insertion.
   Data: window.PROJECT_DATA from data/project-data.js (written by refresh.py). When that file is
   missing, examples/demo-project-data.js is loaded instead and a demo banner is shown. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const inline = value => esc(value).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  const plain = value => String(value ?? '').replace(/[*`]/g, '');
  const list = value => Array.isArray(value) ? value : [];
  const record = value => value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  const text = value => value == null ? '' : String(value);
  const num = value => Number(value).toLocaleString('en-US');
  const compactFormat = new Intl.NumberFormat('en-US', {notation:'compact', maximumFractionDigits:1});
  const compact = value => compactFormat.format(Number(value) || 0);
  const share = (part, total) => total ? (part / total * 100) : 0;
  const pad2 = n => String(n).padStart(2, '0');
  const plural = (n, word, many = `${word}s`) => `${num(n)} ${n === 1 ? word : many}`;
  const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi);
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const icon = (name, cls = '') => `<svg class="ico${cls ? ` ${cls}` : ''}" aria-hidden="true"><use href="#i-${name}"/></svg>`;

  // Every key the page reads gets a safe default, so a partial or older snapshot never throws.
  function normalize(raw) {
    const d = record(raw);
    const project = {name:'Project', subtitle:'', description:'', repository:'', timezone:'', accent:'', stage:'', version:'', ...record(d.project)};
    project.name = text(project.name).trim() || 'Project';
    project.version = text(project.version);
    project.repository = text(project.repository).replace(/\/+$/, '');
    project.flow = list(project.flow).map(text).filter(Boolean);
    project.facts = list(project.facts).filter(f => f && typeof f === 'object').map(f => ({...f, label: text(f.label), value: text(f.value), group: text(f.group)}));
    const brief = {currentState:'', inProgress:'', handoff:'', rules:'', ...record(d.brief)};
    for (const key of ['nextSteps', 'pillars', 'phases', 'roadmap', 'decisions', 'health', 'systems']) brief[key] = list(brief[key]).filter(Boolean);
    brief.roadmap.forEach(r => { r.tests = list(r.tests); r.id = text(r.id); r.title = text(r.title); });
    brief.systems.forEach(s => { s.name = text(s.name); s.status = text(s.status) || 'stable'; s.paths = list(s.paths).map(text).filter(Boolean); s.tags = list(s.tags).map(text).filter(Boolean); });
    brief.health.forEach(h => { h.label = text(h.label); h.value = text(h.value); h.status = text(h.status) || 'unknown'; });
    const git = {branch:'', head:'', tag:'', firstCommit:null, latestCommit:null, ...record(d.git)};
    git.commits = list(git.commits).filter(c => c && c.sha);
    git.commits.forEach(c => {
      c.sha = text(c.sha); c.short = c.short || c.sha.slice(0, 7); c.subject = text(c.subject); c.date = text(c.date);
      c.files = list(c.files).filter(Boolean); c.added = Number(c.added) || 0; c.deleted = Number(c.deleted) || 0;
    });
    git.workingTree = list(git.workingTree).filter(Boolean);
    git.head = text(git.head); git.tag = text(git.tag);
    const numbers = {...record(d.numbers)};
    for (const key of ['content', 'sourceLines', 'areas']) numbers[key] = record(numbers[key]);
    numbers.projectSize = numbers.projectSize && typeof numbers.projectSize === 'object' ? {groups:{}, skipped:[], fileCount:0, totalBytes:0, ...numbers.projectSize} : null;
    return {
      ...d, project, brief, git, numbers,
      dashboard: record(d.dashboard),
      milestones: list(d.milestones).map(m => ({title:'', body:'', date:null, ...m, commits: list(m && m.commits)})),
      plan: list(d.plan).map((s, i) => ({number: i + 1, title:'', status:'design', note:'', ...s, paragraphs: list(s && s.paragraphs)})),
      sessions: list(d.sessions).filter(s => s && typeof s === 'object').map(s => ({...s, commits: list(s.commits).map(text)})),
      media: list(d.media).filter(m => m && m.path),
      sources: list(d.sources).filter(s => s && s.path),
      banner: d.banner && d.banner.path ? d.banner : null
    };
  }

  function start(raw, fromExample) {
    const data = normalize(raw);
    const {project, brief, git} = data;
    const commits = git.commits;

    /* ---------- Time zone and dates ---------- */
    const browserZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const zone = (() => {
      if (!project.timezone) return browserZone;
      try { new Intl.DateTimeFormat('en-US', {timeZone: project.timezone}); return project.timezone; }
      catch { return browserZone; }
    })();
    const dayOnly = value => /^\d{4}-\d{2}-\d{2}$/.test(value);
    // Calendar days (YYYY-MM-DD) are formatted at noon UTC in UTC so they never shift a day.
    const fmt = (value, options) => {
      const day = dayOnly(value);
      const when = new Date(day ? `${value}T12:00:00Z` : value);
      if (isNaN(when)) return text(value);
      return new Intl.DateTimeFormat('en-US', {timeZone: day ? 'UTC' : zone, ...options}).format(when);
    };
    const date = (value, withTime = false) => value ? fmt(text(value), {month:'short', day:'numeric', year:'numeric',
      ...(withTime ? {hour:'numeric', minute:'2-digit', timeZoneName:'short'} : {})}) : 'Date not recorded';
    const shortDate = value => value ? fmt(text(value), {month:'short', day:'numeric'}) : '';
    const weekday = day => fmt(day, {weekday:'long', month:'long', day:'numeric', year:'numeric'});
    const clock = value => fmt(value, {hour:'numeric', minute:'2-digit'});
    const dayFormat = new Intl.DateTimeFormat('en-CA', {timeZone: zone, year:'numeric', month:'2-digit', day:'2-digit'});
    const localDay = iso => { const when = new Date(iso); return isNaN(when) ? '' : dayFormat.format(when); };
    const dayNum = day => Math.floor(Date.parse(`${day}T12:00:00Z`) / 864e5);
    const numDay = n => new Date(n * 864e5 + 432e5).toISOString().slice(0, 10);
    const rtf = new Intl.RelativeTimeFormat('en', {numeric:'auto'});
    const ago = value => {
      const t = Date.parse(value);
      if (isNaN(t)) return '';
      const s = (t - Date.now()) / 1000, a = Math.abs(s);
      const [unit, n] = a < 60 ? ['second', s] : a < 3600 ? ['minute', s / 60] : a < 86400 ? ['hour', s / 3600]
        : a < 86400 * 45 ? ['day', s / 86400] : a < 86400 * 365 ? ['month', s / 2592000] : ['year', s / 31536000];
      return rtf.format(Math.round(n), unit);
    };
    const duration = minutes => { const m = Math.round(minutes); return m >= 60 ? `${Math.floor(m / 60)}h ${pad2(m % 60)}m` : `${m}m`; };
    const money = v => `$${Number(v).toFixed(2)}`;

    /* ---------- Derived data ---------- */
    const TYPES = {feat:'Feature', fix:'Fix', test:'Test', docs:'Docs', refactor:'Refactor', chore:'Chore', other:'Other'};
    const TYPE_ALIASES = {perf:'refactor', style:'refactor', build:'chore', ci:'chore', revert:'fix', tests:'test', doc:'docs', feature:'feat'};
    // Categorical slots in a fixed, validated order (dark-surface steps); the 9th+ series folds into "Other".
    const SERIES = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767'];
    const OTHER = '#6e7681';
    const TYPE_COLOR = {feat:SERIES[0], fix:SERIES[1], test:SERIES[2], docs:SERIES[3], refactor:SERIES[4], chore:SERIES[5], other:OTHER};
    const parseSubject = subject => {
      const m = text(subject).match(/^(\w+)(?:\(([^)]*)\))?(!)?:\s*(.*)$/);
      if (!m) return {type:'other', scope:'', rest:text(subject)};
      const t = m[1].toLowerCase();
      return {type: TYPES[t] ? t : TYPE_ALIASES[t] || 'other', scope: m[2] || '', rest: m[4] || text(subject)};
    };
    commits.forEach(c => { c.day = localDay(c.date); c.dayN = c.day ? dayNum(c.day) : NaN; Object.assign(c, {parsed: parseSubject(c.subject)}); });
    const byShort = new Map(commits.map(c => [c.short, c]));
    const findCommit = id => byShort.get(text(id).slice(0, 7)) || commits.find(c => c.sha.startsWith(text(id)));
    const daily = new Map();
    commits.forEach(c => { if (!c.day) return; const e = daily.get(c.day) || {n:0, added:0, deleted:0}; e.n++; e.added += c.added; e.deleted += c.deleted; daily.set(c.day, e); });
    const refDay = localDay(data.generatedAt) || (git.latestCommit && localDay(git.latestCommit)) || dayFormat.format(new Date());
    const refN = dayNum(refDay);
    const inLast = (c, days) => c.dayN > refN - days && c.dayN <= refN;
    const weeks = (count, items = commits) => Array.from({length: count}, (_, i) => {
      const end = refN - (count - 1 - i) * 7, begin = end - 6;
      return {begin, end, items: items.filter(c => c.dayN >= begin && c.dayN <= end)};
    });
    const globRe = glob => new RegExp(`^${[...glob].map(ch => ch === '*' ? '.*' : ch === '?' ? '.' : ch.replace(/[.+^${}()|[\]\\]/g, '\\$&')).join('')}$`);
    const areaOf = path => { const parts = text(path).split('/'); return parts.length > 1 ? parts.slice(0, 2).join('/') : '(root files)'; };
    const areaCounts = items => {
      const counts = new Map();
      items.forEach(c => c.files.forEach(f => { const a = areaOf(f.path); counts.set(a, (counts.get(a) || 0) + 1); }));
      return [...counts].sort((a, b) => b[1] - a[1]);
    };

    const road = brief.roadmap, decisions = brief.decisions;
    const mainRoad = road.filter(r => !r.side);
    const doneMain = mainRoad.filter(r => r.status === 'done').length;
    const nextNode = road.find(r => r.status === 'next');
    const datedDays = [...new Set(road.filter(r => dayOnly(text(r.date))).map(r => r.date))].sort();
    // Approximate window: (previous distinct roadmap date, this date]; the first dated node covers its own day,
    // the "next" node covers everything after the last dated node. Undated future nodes have no window.
    function windowFor(r) {
      if (dayOnly(text(r.date))) { const i = datedDays.indexOf(r.date); return {from: i > 0 ? datedDays[i - 1] : null, to: r.date, first: i === 0}; }
      if (r.status === 'next' && datedDays.length) return {from: datedDays[datedDays.length - 1], to: null};
      return null;
    }
    const inWindow = (day, w) => w.first ? day === w.to : (!w.from || day > w.from) && (!w.to || day <= w.to);
    const tagPattern = id => new RegExp(`(^|[^\\w-])${id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?!\\w)`, 'i');
    function roadCommits(r) {
      const w = windowFor(r), tag = r.id ? tagPattern(r.id) : null;
      const tagged = tag ? commits.filter(c => tag.test(c.subject)) : [];
      const windowed = w ? commits.filter(c => inWindow(c.day, w) && !tagged.includes(c)) : [];
      return {w, tagged, windowed};
    }

    const systems = brief.systems.map((s, i) => {
      const patterns = s.paths.map(globRe);
      const hit = f => patterns.some(re => re.test(text(f.path)));
      const touching = patterns.length ? commits.filter(c => c.files.some(hit)) : [];
      const lines = touching.reduce((t, c) => t + c.files.filter(hit).reduce((a, f) => a + (f.added || 0) + (f.deleted || 0), 0), 0);
      return {...s, index: i, touching, lines, last: touching[0] ? touching[0].date : null, weekly: weeks(8, touching).map(w => w.items.length)};
    });

    const aiKeys = ['model', 'provider', 'role', 'tokens', 'toolCalls', 'costUsd'];
    const sessions = data.sessions.map((s, i) => ({...s, index: i})).sort((a, b) => text(b.date).localeCompare(text(a.date)));
    const aiSessions = sessions.filter(s => aiKeys.some(k => s[k] != null && s[k] !== '') || typeof s.local === 'boolean');
    const metric = key => { const r = data.sessions.filter(s => typeof s[key] === 'number'); return r.length ? {total: r.reduce((t, s) => t + s[key], 0), count: r.length} : null; };
    const models = (() => {
      const map = new Map();
      aiSessions.filter(s => s.model || s.agent).forEach(s => {
        const key = text(s.model || s.agent);
        const m = map.get(key) || {name: key, provider: text(s.provider), local: s.local, roles: new Set(), runs: 0, tokens: 0, cost: 0};
        m.runs++; m.tokens += Number(s.tokens) || 0; m.cost += Number(s.costUsd) || 0;
        if (s.role) m.roles.add(text(s.role));
        if (typeof s.local === 'boolean') m.local = s.local;
        map.set(key, m);
      });
      return [...map.values()].sort((a, b) => b.runs - a.runs || b.tokens - a.tokens);
    })();

    /* ---------- Status language ---------- */
    // [tone, icon, label]. Every status carries an icon and a word, never colour alone.
    const STATUS = {
      done:['ok', 'check', 'Complete'], next:['active', 'pulse', 'In progress'], planned:['muted', 'ring', 'Upcoming'], gated:['gated', 'lock', 'Gated'],
      implemented:['ok', 'check', 'Implemented'], partial:['active', 'half', 'Partial'], design:['muted', 'ring', 'Design reference'],
      healthy:['ok', 'check', 'Healthy'], warning:['warn', 'alert', 'Warning'], danger:['danger', 'x', 'Failing'], unknown:['muted', 'question', 'Unknown'],
      stable:['ok', 'check', 'Stable'], active:['active', 'pulse', 'Active'], blocked:['danger', 'lock', 'Blocked']
    };
    const statusOf = s => STATUS[s] || ['muted', 'ring', text(s) || 'Unknown'];
    const PLAN_LABELS = {implemented:'Implemented', partial:'Partial', planned:'Planned', design:'Design reference'};
    const pill = (status, label) => { const [tone, ic, l] = statusOf(status); return `<span class="st st-${tone}">${icon(ic)}${esc(label || l)}</span>`; };

    /* ---------- Components ---------- */
    let uid = 0;
    const card = o => `<article class="card ${o.span || 'c-12'}${o.cls ? ` ${o.cls}` : ''}"${o.id ? ` id="${o.id}"` : ''}>${o.title ? `<header class="card-head"><h2 class="card-title">${o.icon ? icon(o.icon) : ''}<span>${o.title}</span></h2>${o.meta ? `<span class="card-meta">${o.meta}</span>` : ''}${o.action || ''}</header>` : ''}<div class="card-body">${o.body}</div></article>`;
    const actLink = (act, label) => `<button class="card-link" data-act="${esc(act)}">${esc(label)}${icon('chevron', 'sm')}</button>`;
    const viewHead = (id, title, sub, extra = '') => `<header class="view-head c-12"><div><h1 id="${id}-title">${title}</h1>${sub ? `<p>${sub}</p>` : ''}</div>${extra}</header>`;
    // Lay optional cards out in rows of 12: when the next card does not fit, the previous one widens to close the gap.
    const pack = cards => {
      const out = [];
      let used = 0;
      const widen = gap => { if (gap > 0 && out.length) out[out.length - 1] = out[out.length - 1].replace(/\bc-(\d+)\b/, (_, n) => `c-${Number(n) + gap}`); };
      for (const html of cards.filter(Boolean)) {
        const span = Number((html.match(/\bc-(\d+)\b/) || [])[1]) || 12;
        if (used + span > 12) { widen(12 - used); used = 0; }
        out.push(html); used = (used + span) % 12;
      }
      if (used) widen(12 - used);
      return `<div class="grid">${out.join('')}</div>`;
    };
    const empty = message => `<p class="empty">${esc(message)}</p>`;
    const firstPara = value => text(value).split(/\r?\n\s*\r?\n/)[0].replace(/\s*\r?\n\s*/g, ' ').trim();
    const fmtCount = (v, dec) => Number(v).toLocaleString('en-US', {minimumFractionDigits: dec, maximumFractionDigits: dec});
    // Animated number; screen readers get the final value immediately.
    const counter = (value, {dec = 0, prefix = '', suffix = ''} = {}) => `<span class="sr">${esc(prefix + fmtCount(value, dec) + suffix)}</span><span aria-hidden="true">${esc(prefix)}<span data-count="${Number(value)}" data-dec="${dec}">${fmtCount(reduced.matches ? value : 0, dec)}</span>${esc(suffix)}</span>`;
    const stat = ({label, value, shown, note = '', ...opts}) => `<div class="stat"><div class="stat-label">${esc(label)}</div><div class="stat-value">${shown != null ? shown : counter(value, opts)}</div>${note ? `<div class="stat-note">${note}</div>` : ''}</div>`;
    const markdown = source => {
      let html = '', open = '', para = [];
      const closeList = () => { if (open) { html += `</${open}>`; open = ''; } };
      // Hard-wrapped lines belong to one paragraph until a blank line or another block starts.
      const closePara = () => { if (para.length) { html += `<p>${inline(para.join(' '))}</p>`; para = []; } };
      for (const line of text(source).split(/\r?\n/)) {
        const bullet = line.match(/^\s*(?:[-*] |\d+\. )(.+)/);
        if (bullet) {
          closePara();
          const type = /^\s*\d+\./.test(line) ? 'ol' : 'ul';
          if (open !== type) { closeList(); open = type; html += `<${type}>`; }
          html += `<li>${inline(bullet[1])}</li>`;
          continue;
        }
        closeList();
        if (!line.trim() || line.trim() === '---') { closePara(); continue; }
        const heading = line.match(/^(#{1,6}) (.+)/);
        if (heading || line.startsWith('>')) closePara();
        if (heading) html += `<h${heading[1].length < 3 ? 3 : 4}>${inline(heading[2])}</h${heading[1].length < 3 ? 3 : 4}>`;
        else if (line.startsWith('>')) html += `<blockquote>${inline(line.replace(/^>\s*/, ''))}</blockquote>`;
        else para.push(line.trim());
      }
      closePara();
      closeList();
      return html;
    };
    const commitLink = sha => {
      const id = text(sha);
      if (!/^https?:\/\//i.test(project.repository)) return `<code>${esc(id.slice(0, 7))}</code>`;
      return `<a class="ext" href="${esc(`${project.repository}/commit/${encodeURIComponent(id)}`)}" target="_blank" rel="noopener noreferrer"><code>${esc(id.slice(0, 7))}</code>${icon('external', 'sm')}</a>`;
    };
    const subjectHtml = c => `<span class="ctype" style="--c:${TYPE_COLOR[c.parsed.type]}">${TYPES[c.parsed.type]}</span>${c.parsed.scope ? `<span class="cscope">${esc(c.parsed.scope)}</span>` : ''}<span class="csubj">${esc(c.parsed.rest)}</span>`;
    const commitRow = c => `<li><button class="crow" data-act="commit:${esc(c.sha)}">${subjectHtml(c)}<span class="crow-meta"><code>${esc(c.short)}</code><span class="add">+${compact(c.added)}</span><span class="del">−${compact(c.deleted)}</span><time datetime="${esc(c.date)}" title="${esc(date(c.date, true))}">${esc(ago(c.date))}</time></span></button></li>`;

    // Sparkline: one series, area under a 2px line; the whole mark carries a summary tooltip.
    const spark = (values, label, h = 44) => {
      if (values.length < 2) return '';
      const max = Math.max(1, ...values), W = 100, id = `sg${++uid}`;
      const line = values.map((v, i) => `${i ? 'L' : 'M'}${(i / (values.length - 1) * W).toFixed(2)},${(h - 2 - v / max * (h - 6)).toFixed(2)}`).join('');
      return `<svg class="spark" viewBox="0 0 ${W} ${h}" preserveAspectRatio="none" role="img" aria-label="${esc(label)}" data-tip="${esc(label)}"><defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" style="stop-color:var(--accent);stop-opacity:.32"/><stop offset="1" style="stop-color:var(--accent);stop-opacity:0"/></linearGradient></defs><path class="spark-area" d="${line}L${W},${h}L0,${h}Z" style="fill:url(#${id})"/><path class="spark-line" d="${line}"/></svg>`;
    };
    // Column chart in HTML so it reflows at any width. Each non-empty column is a focusable button.
    const columns = (buckets, label, unit = 'commit') => {
      const max = Math.max(1, ...buckets.map(b => b.value));
      const every = Math.max(1, Math.ceil(buckets.length / 10));
      const ticks = [...new Set([max, Math.round(max / 2)])].filter(v => v > 0);
      return `<div class="cols" role="group" aria-label="${esc(label)}"><div class="cols-grid" aria-hidden="true">${ticks.map(v => `<span style="--y:${(v / max * 100).toFixed(1)}%"><em>${compact(v)}</em></span>`).join('')}</div><div class="cols-plot">${buckets.map((b, i) => b.value
        ? `<button class="col" style="--h:${(b.value / max * 100).toFixed(1)}%;--i:${i}"${b.act ? ` data-act="${esc(b.act)}"` : ''} data-tip-title="${esc(b.title)}" data-tip="${esc(b.tip)}" aria-label="${esc(`${b.title}: ${plural(b.value, unit)}`)}"><i></i></button>`
        : '<span class="col empty" aria-hidden="true"><i></i></span>').join('')}</div><div class="cols-axis" aria-hidden="true">${buckets.map((b, i) => `<span>${i % every === 0 ? esc(b.short) : ''}</span>`).join('')}</div></div>`;
    };
    // Additions above the midline, deletions below, on one shared scale.
    const churn = buckets => {
      const max = Math.max(1, ...buckets.flatMap(b => [b.added, b.deleted]));
      const every = Math.max(1, Math.ceil(buckets.length / 8));
      return `<div class="churn" role="img" aria-label="${esc(`Lines added and removed per week. ${buckets.map(b => `${b.title}: +${b.added} −${b.deleted}`).join('; ')}`)}"><div class="churn-plot">${buckets.map((b, i) => `<span class="churn-col" style="--i:${i}" data-tip-title="${esc(b.title)}" data-tip="${esc(`+${num(b.added)} added\n−${num(b.deleted)} removed`)}"><i class="up" style="--h:${(b.added / max * 100).toFixed(1)}%"></i><i class="down" style="--h:${(b.deleted / max * 100).toFixed(1)}%"></i></span>`).join('')}</div><div class="cols-axis" aria-hidden="true">${buckets.map((b, i) => `<span>${i % every === 0 ? esc(b.short) : ''}</span>`).join('')}</div></div>`;
    };
    const stack = (entries, label, show = num) => {
      const total = entries.reduce((a, e) => a + e.value, 0) || 1;
      return `<div class="stack" role="img" aria-label="${esc(`${label}: ${entries.map(e => `${e.label} ${show(e.value)} (${share(e.value, total).toFixed(1)}%)`).join(', ')}`)}">${entries.map((e, i) => `<span style="--w:${share(e.value, total).toFixed(2)}%;--c:${e.color};--i:${i}" data-tip-title="${esc(e.label)}" data-tip="${esc(`${show(e.value)} · ${share(e.value, total).toFixed(1)}%`)}"></span>`).join('')}</div>`;
    };
    const legend = (entries, show = num, act) => {
      const total = entries.reduce((a, e) => a + e.value, 0) || 1;
      return `<ul class="legend">${entries.map(e => { const inner = `<i class="sw" style="--c:${e.color}"></i><span class="lg-label">${esc(e.label)}</span><b>${show(e.value)}</b><small>${share(e.value, total).toFixed(1)}%</small>`;
        return `<li>${act ? `<button data-act="${esc(act(e))}" aria-label="${esc(`Show ${e.label} commits`)}">${inner}</button>` : inner}</li>`; }).join('')}</ul>`;
    };
    const hbars = (entries, show = num) => {
      const max = Math.max(1, ...entries.map(e => e[1]));
      return `<ul class="hbars">${entries.map(([label, value], i) => `<li style="--i:${i}"><span class="hb-label" title="${esc(label)}">${esc(label)}</span><span class="hb-track"><i style="--w:${(value / max * 100).toFixed(1)}%"></i></span><b>${show(value)}</b></li>`).join('')}</ul>`;
    };
    const ring = (value, total, label, inner) => {
      const r = 27, C = 2 * Math.PI * r, p = total ? value / total : 0;
      return `<div class="ring"><svg viewBox="0 0 64 64" role="img" aria-label="${esc(label)}"><circle class="ring-bg" cx="32" cy="32" r="${r}"/><circle class="ring-fg" cx="32" cy="32" r="${r}" style="--c:${C.toFixed(2)};--o:${(C * (1 - p)).toFixed(2)}"/></svg><span aria-hidden="true">${inner}</span></div>`;
    };
    // Fold a sorted [label, value] list into at most `limit` coloured entries plus "Other".
    const fold = (pairs, limit = 7) => {
      const top = pairs.slice(0, limit).map(([label, value], i) => ({label, value, color: SERIES[i]}));
      const rest = pairs.slice(limit).reduce((t, [, v]) => t + v, 0);
      return rest ? [...top, {label:'Other', value:rest, color:OTHER}] : top;
    };
    const entriesOf = obj => Object.entries(obj).map(([k, v]) => [k, Number(v) || 0]).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
    const sizeUnit = total => [['GB', 1e9], ['MB', 1e6], ['KB', 1e3]].find(([, b]) => total >= b) || ['bytes', 1];
    const bytes = (value, total = value) => { const [unit, scale] = sizeUnit(total); return `${(value / scale).toFixed(unit === 'bytes' ? 0 : unit === 'KB' ? 0 : 1)} ${unit}`; };
    const sourceOf = key => data.sources.find(s => s.key === key);

    /* ---------- Shared modules ---------- */
    function autoHealth() {
      const out = [];
      if (git.latestCommit) {
        const age = (Date.now() - Date.parse(git.latestCommit)) / 864e5;
        out.push({label:'Last commit', value: ago(git.latestCommit), status: age <= 14 ? 'healthy' : age <= 60 ? 'warning' : 'unknown', detail:'From Git history. Quiet after 14 days, dormant after 60.', auto:true});
      }
      const tree = git.workingTree.length;
      out.push({label:'Working tree', value: tree ? plural(tree, 'change') : 'Clean', status: tree ? 'active' : 'healthy', detail: tree ? 'Uncommitted changes at snapshot time.' : 'No uncommitted changes at snapshot time.', auto:true});
      return out;
    }
    const signals = () => [...brief.health, ...autoHealth()];
    const signalList = (items, detailed = false) => `<ul class="signals">${items.map(s => { const [tone, ic, l] = statusOf(s.status);
      return `<li class="sig t-${tone}"${!detailed && s.detail ? ` data-tip-title="${esc(s.label)}" data-tip="${esc(s.detail)}" tabindex="0"` : ''}><span class="sig-icon">${icon(ic)}</span><span class="sig-text"><span class="sig-label">${esc(s.label)}${s.auto ? '<em class="auto">auto</em>' : ''}</span>${detailed && s.detail ? `<small>${inline(s.detail)}</small>` : ''}</span><span class="sig-value"><span class="sr">${esc(l)}: </span>${esc(s.value || l)}</span></li>`; }).join('')}</ul>`;
    const factGroups = () => { const groups = new Map(); project.facts.forEach(f => { const g = f.group || 'Facts'; groups.set(g, [...(groups.get(g) || []), f]); }); return groups; };
    const factsHtml = () => `<div class="fact-groups">${[...factGroups()].map(([group, facts]) => `<div class="fact-group">${factGroups().size > 1 ? `<h3 class="kicker">${esc(group)}</h3>` : ''}<dl class="facts">${facts.map(f => `<div><dt>${esc(f.label)}</dt><dd>${f.status ? `${icon(statusOf(f.status)[1], `t-${statusOf(f.status)[0]}`)}` : ''}${esc(f.value)}</dd></div>`).join('')}</dl></div>`).join('')}</div>`;
    const languages = fold(entriesOf(data.numbers.sourceLines));
    const flowHtml = () => {
      const stageMain = text(project.stage).split(' - ')[0].trim().toLowerCase();
      const at = project.flow.findIndex(s => s.toLowerCase() === stageMain || (stageMain && stageMain.startsWith(s.toLowerCase())));
      return project.flow.length ? `<ol class="flow" aria-label="Project stage">${project.flow.map((s, i) => `<li class="${at < 0 ? '' : i < at ? 'done' : i === at ? 'current' : ''}"${i === at ? ' aria-current="step"' : ''}><span>${esc(s)}</span></li>`).join('')}</ol>` : '';
    };
    const sessionMeta = s => [s.model || s.agent, s.role, s.local === true ? 'Local' : s.local === false ? 'API' : ''].filter(Boolean).map(esc).join(' · ');
    const sessionRow = s => `<li><button class="srow" data-act="session:${s.index}"><span class="srow-date">${esc(shortDate(s.date))}</span><span class="srow-main"><span class="srow-title">${esc(s.title)}</span><span class="srow-meta">${sessionMeta(s)}</span></span><span class="srow-stats">${s.tokens != null ? `<span>${compact(s.tokens)} tok</span>` : ''}${s.minutes != null ? `<span>${duration(s.minutes)}</span>` : ''}</span></button></li>`;
    const modelTable = rows => `<ul class="models">${rows.map(m => `<li><span class="model-icon">${icon('cpu')}</span><span class="model-main"><strong>${esc(m.name)}</strong><small>${[m.provider, [...m.roles].join(', ')].filter(Boolean).map(esc).join(' · ')}</small></span>${typeof m.local === 'boolean' ? `<span class="pill ${m.local ? 'local' : ''}">${m.local ? 'Local' : 'API'}</span>` : ''}<span class="model-runs">${plural(m.runs, 'run')}</span></li>`).join('')}</ul>`;
    const aiTotals = () => {
      const t = metric('tokens'), calls = metric('toolCalls'), cost = metric('costUsd'), mins = metric('minutes');
      return [
        stat({label:'Sessions', value: data.sessions.length}),
        t ? stat({label:'Tokens', shown: esc(compact(t.total)), note: `${t.count} of ${data.sessions.length} report`}) : '',
        calls ? stat({label:'Tool calls', value: calls.total, note: `${calls.count} of ${data.sessions.length} report`}) : '',
        cost ? stat({label:'API cost', value: cost.total, dec: 2, prefix: '$', note: `${cost.count} of ${data.sessions.length} report`}) : '',
        mins ? stat({label:'Session time', shown: esc(duration(mins.total)), note: `${mins.count} of ${data.sessions.length} report`}) : ''
      ].join('');
    };

    /* ---------- Overview ---------- */
    function renderOverview() {
      const version = project.version || git.tag;
      const stageMain = text(project.stage).split(' - ')[0].trim();
      const tree = git.workingTree.length;
      const meta = [
        git.branch && ['branch', esc(git.branch), 'Branch'],
        git.head && ['commit', `<code>${esc(git.head.slice(0, 7))}</code>`, 'HEAD'],
        git.latestCommit && ['clock', `Updated ${esc(ago(git.latestCommit))}`, 'Last commit'],
        commits.length && ['layers', tree ? plural(tree, 'uncommitted change') : 'Working tree clean', 'Repository status']
      ].filter(Boolean).map(([ic, v, l]) => `<li>${icon(ic)}<span class="sr">${l}: </span>${v}</li>`).join('');
      const b = data.banner;
      const identity = `<article class="card c-8 identity${b ? ' has-art' : ''}">${b ? `<div class="identity-art" aria-hidden="true"><img src="${esc(b.path)}" alt=""></div>` : ''}<div class="identity-copy">
        <div class="identity-tags">${stageMain ? `<span class="pill accent">${icon('target')}${esc(stageMain)}</span>` : ''}${version ? `<span class="pill">${icon('tag')}${esc(version)}</span>` : ''}${fromExample || data.demo === true ? '<span class="pill">Demo data</span>' : ''}</div>
        <h1 id="overview-title">${esc(project.name)}</h1>${project.subtitle ? `<p class="identity-sub">${esc(project.subtitle)}</p>` : ''}${project.description ? `<p class="identity-desc">${esc(project.description)}</p>` : ''}
        <ul class="identity-meta">${meta}</ul>${flowHtml()}</div></article>`;

      let pulse = '';
      if (commits.length) {
        const last30 = commits.filter(c => inLast(c, 30)), prev30 = commits.filter(c => inLast(c, 60) && !inLast(c, 30));
        const series = Array.from({length: 30}, (_, i) => (daily.get(numDay(refN - 29 + i)) || {n:0}).n);
        const delta = last30.length - prev30.length;
        const added = last30.reduce((t, c) => t + c.added, 0), deleted = last30.reduce((t, c) => t + c.deleted, 0);
        pulse = card({span:'c-4', cls:'pulse', title:'Development pulse', icon:'pulse', action: actLink('go:development', 'Activity'), body:
          `<div class="pulse-head"><div class="big">${counter(last30.length)}</div><div class="pulse-label">commits in the last 30 days<span class="delta ${delta > 0 ? 'up' : delta < 0 ? 'down' : ''}">${delta > 0 ? '▲' : delta < 0 ? '▼' : '•'} ${Math.abs(delta)} vs previous 30</span></div></div>
          ${spark(series, `Commits per day, last 30 days: ${last30.length} in total`)}
          <dl class="mini"><div><dt>Active days</dt><dd>${new Set(last30.map(c => c.day)).size} / 30</dd></div><div><dt>Lines changed</dt><dd><span class="add">+${compact(added)}</span> <span class="del">−${compact(deleted)}</span></dd></div><div><dt>All time</dt><dd>${plural(commits.length, 'commit')}</dd></div></dl>`});
      }

      const progress = firstPara(brief.inProgress), current = firstPara(brief.currentState), steps = brief.nextSteps;
      const focus = progress || current || steps.length ? card({span:'c-5', cls:'focus', title:'Current focus', icon:'target', action: brief.handoff.trim() ? actLink('drawer:handoff', 'Full handoff') : '', body:
        `${progress ? `<div class="focus-now"><span class="kicker live"><span class="live-dot" aria-hidden="true"></span>In progress</span><p>${inline(progress)}</p></div>` : ''}
        ${current ? `<div><span class="kicker">Current state</span><p class="clamp-3">${inline(current)}</p></div>` : ''}
        ${steps.length ? `<div><span class="kicker">Next steps</span><ol class="steps">${steps.slice(0, 3).map(s => `<li>${inline(s)}</li>`).join('')}</ol>${steps.length > 3 ? actLink('go:intelligence', `${steps.length - 3} more steps`) : ''}</div>` : ''}`}) : '';

      let milestone = '';
      if (mainRoad.length) {
        const n = nextNode, rc = n ? roadCommits(n) : null;
        const segs = mainRoad.map(r => `<span class="seg s-${esc(r.status)}${r === n ? ' current' : ''}" data-tip-title="${esc(`${r.id} · ${r.title}`)}" data-tip="${esc(statusOf(r.status)[2])}"></span>`).join('');
        milestone = card({span:'c-4', cls:'milestone', title:'Next milestone', icon:'roadmap', action: actLink(`roadmap:${Math.max(0, road.indexOf(n))}`, 'Roadmap'), body:
          `${n ? `<div class="ms-top"><span class="ms-id">${esc(n.id)}</span>${pill(n.status)}</div><h3 class="ms-title">${esc(n.title)}</h3>${n.summary ? `<p class="clamp-3">${inline(n.summary)}</p>` : ''}
            <dl class="mini"><div><dt>Tests</dt><dd>${n.tests.length}</dd></div><div><dt>Commits so far</dt><dd>${rc.tagged.length + rc.windowed.length}</dd></div>${n.date ? `<div><dt>Target</dt><dd>${esc(shortDate(n.date))}</dd></div>` : ''}</dl>`
          : `<p class="ms-done">${doneMain === mainRoad.length ? 'Every roadmap milestone is complete.' : 'No milestone is marked as next.'}</p>`}
          <div class="segbar" role="img" aria-label="${esc(`${doneMain} of ${mainRoad.length} milestones complete`)}">${segs}</div><div class="segbar-label"><span>${doneMain} of ${mainRoad.length} complete</span><span>${Math.round(share(doneMain, mainRoad.length))}%</span></div>`});
      }

      const health = card({span:'c-3', cls:'health', title:'Health', icon:'heart', body: signalList(signals())});

      const activity = commits.length ? card({span:'c-7', title:'Recent activity', icon:'commit', meta: esc(`${plural(commits.length, 'commit')}`), action: actLink('go:development', 'All commits'), body:
        `<ul class="crows">${commits.slice(0, 7).map(commitRow).join('')}</ul>`}) : '';

      const lines = languages.reduce((t, e) => t + e.value, 0), size = data.numbers.projectSize;
      const composition = lines || Number(data.numbers.trackedFiles) ? card({span:'c-5', title:'Composition', icon:'layers', action: actLink('go:development', 'Details'), body:
        `${lines ? `${stack(languages, 'Lines of code by language')}${legend(languages.slice(0, 5))}` : ''}
        <dl class="mini">${Number(data.numbers.trackedFiles) ? `<div><dt>Tracked files</dt><dd>${num(data.numbers.trackedFiles)}</dd></div>` : ''}${lines ? `<div><dt>Lines of code</dt><dd>${compact(lines)}</dd></div>` : ''}${size && size.totalBytes ? `<div><dt>On disk</dt><dd>${bytes(size.totalBytes)}</dd></div>` : ''}</dl>`}) : '';

      const systemsCard = systems.length ? card({span:'c-8', title:'Major systems', icon:'box', meta: esc(plural(systems.length, 'system')), action: actLink('go:intelligence', 'All systems'), body:
        `<ul class="sys-grid">${systems.slice(0, 6).map(s => `<li><button class="sys" data-act="system:${s.index}"><span class="sys-top"><strong>${esc(s.name)}</strong>${pill(s.status)}</span>${s.summary ? `<span class="sys-sum">${esc(s.summary)}</span>` : ''}<span class="sys-foot">${s.paths.length ? `${spark(s.weekly, `${s.name}: commits per week, last 8 weeks`, 24)}<span>${plural(s.touching.length, 'commit')}${s.last ? ` · ${esc(ago(s.last))}` : ''}</span>` : '<span>No tracked paths yet</span>'}</span></button></li>`).join('')}</ul>`}) : '';

      const decisionsCard = decisions.length ? card({span:'c-4', cls:'decisions', title:'Open decisions', icon:'decision', meta:`<span class="count">${decisions.length}</span>`, body:
        `<ul class="dlist">${decisions.map((d, i) => `<li><button data-act="decision:${i}"><span class="dnum">D${pad2(i + 1)}</span><span class="dtitle">${esc(d.title)}</span>${icon('chevron', 'sm')}</button></li>`).join('')}</ul>`}) : '';

      const captures = data.media.length ? card({span:'c-8', cls:'captures', title:'Latest captures', icon:'media', meta: esc(plural(data.media.length, 'capture')), action: actLink('go:media', 'Gallery'), body:
        `<div class="thumbs n-${Math.min(5, data.media.length)}">${data.media.slice(0, 5).map((m, i) => `<button class="thumb" data-act="capture:${i}" aria-label="${esc(`View ${m.title}`)}"><img src="${esc(m.path)}" alt="" loading="lazy" decoding="async"><span>${esc(m.title)}</span></button>`).join('')}</div>`}) : '';

      const ai = aiSessions.length ? card({span:'c-4', cls:'ai', title:'AI activity', icon:'cpu', action: actLink('go:development/sessions', 'Sessions'), body:
        `${modelTable(models.slice(0, 3))}<div class="stats tight">${aiTotals()}</div>`})
        : sessions.length ? card({span:'c-4', title:'Recent sessions', icon:'session', action: actLink('go:development/sessions', 'All'), body: `<ul class="srows">${sessions.slice(0, 4).map(sessionRow).join('')}</ul>`}) : '';

      const facts = project.facts.length ? card({span:'c-4', title:'Project facts', icon:'file', body: factsHtml()}) : '';

      const cards = {identity, pulse, focus, milestone, health, activity, composition, systems: systemsCard, decisions: decisionsCard, captures, ai, facts};
      const keyed = Object.entries(cards).map(([key, html]) => html && html.replace('<article ', `<article data-key="${key}" `));
      return `<div class="edit-bar" id="edit-bar" role="region" aria-label="Layout editor" hidden><span class="edit-bar-icon">${icon('grip')}</span><div class="edit-bar-text"><strong>Arrange your overview</strong><span>Drag cards, or use their arrow buttons. Widths adjust so every row spans the page. Saved in this browser.</span></div><button class="btn" data-layout="reset">Reset</button><button class="btn primary" data-layout="done">Done</button></div>${pack(keyed).replace('<div class="grid">', '<div class="grid" id="ov-grid">')}`;
    }

    /* ---------- Overview layout editing ---------- */
    // Preferred and minimum spans (of 12 columns) per card; the minimum keeps each card's content readable.
    const SIZES = {identity:[8, 6], pulse:[4, 3], focus:[5, 4], milestone:[4, 3], health:[3, 3], activity:[7, 5], composition:[5, 4], systems:[8, 6], decisions:[4, 3], captures:[8, 5], ai:[4, 3], facts:[4, 3]};
    const LAYOUT_KEY = `project-dashboard:overview-layout:${project.name}`;
    let layoutOrder = (() => { try { const v = JSON.parse(localStorage.getItem(LAYOUT_KEY)); return Array.isArray(v) ? v : null; } catch { return null; } })();
    const saveOrder = () => { try { if (layoutOrder) localStorage.setItem(LAYOUT_KEY, JSON.stringify(layoutOrder)); else localStorage.removeItem(LAYOUT_KEY); } catch { /* no storage: the layout lasts for this visit */ } };
    // A card joins the current row while the preferred widths fit, or overflow by at most two columns with every
    // minimum still met. Each row is then squeezed (most room above minimum first) or stretched (furthest below its
    // preferred share first) to exactly 12 columns, so the page width is always filled.
    function rowSpans(keys) {
      const rows = [];
      const sum = (row, i) => row.reduce((t, k) => t + SIZES[k][i], 0);
      for (const k of keys) {
        const row = rows[rows.length - 1];
        if (row && sum(row, 1) + SIZES[k][1] <= 12 && sum(row, 0) + SIZES[k][0] <= 14) row.push(k); else rows.push([k]);
      }
      const spans = {};
      for (const row of rows) {
        const s = row.map(k => SIZES[k][0]), room = j => s[j] - SIZES[row[j]][1];
        let total = s.reduce((a, b) => a + b, 0);
        for (; total > 12; total--) { let i = 0; s.forEach((_, j) => { if (room(j) > room(i)) i = j; }); s[i]--; }
        for (; total < 12; total++) { let i = 0; s.forEach((v, j) => { if (v / SIZES[row[j]][0] < s[i] / SIZES[row[i]][0]) i = j; }); s[i]++; }
        row.forEach((k, j) => { spans[k] = s[j]; });
      }
      return spans;
    }
    function applyLayout(animate = false) {
      const grid = $('ov-grid');
      if (!grid) return;
      const present = [...grid.children].map(el => el.dataset.key), saved = (layoutOrder || []).filter(k => present.includes(k));
      const order = [...saved, ...Object.keys(SIZES).filter(k => present.includes(k) && !saved.includes(k))];
      const spans = rowSpans(order), els = [...grid.children];
      const before = animate && !reduced.matches ? new Map(els.map(el => [el, el.getBoundingClientRect()])) : null;
      order.forEach(k => { const el = grid.querySelector(`[data-key="${k}"]`); el.className = el.className.replace(/\bc-\d+\b/, `c-${spans[k]}`); grid.append(el); });
      // FLIP: slide every card from where it was to where it landed.
      if (before) els.forEach(el => { const a = before.get(el), b = el.getBoundingClientRect(); if (a.left !== b.left || a.top !== b.top) el.animate([{transform: `translate(${a.left - b.left}px, ${a.top - b.top}px)`}, {transform: 'none'}], {duration: 380, easing: 'cubic-bezier(.16,1,.3,1)'}); });
    }
    const reorder = (key, target, after) => {
      const order = [...$('ov-grid').children].map(el => el.dataset.key).filter(k => k !== key);
      order.splice(order.indexOf(target) + (after ? 1 : 0), 0, key);
      layoutOrder = order; saveOrder(); applyLayout(true);
    };
    let editing = false, dragKey = null;
    function setEditing(on) {
      const grid = $('ov-grid');
      if (!grid) return;
      editing = on;
      $('edit-layout').setAttribute('aria-pressed', String(on));
      $('edit-layout').querySelector('.label').textContent = on ? 'Done' : 'Customize layout';
      $('edit-bar').hidden = !on;
      grid.classList.toggle('editing', on);
      [...grid.children].forEach(el => {
        const name = (el.querySelector('.card-title span, h1') || {}).textContent || el.dataset.key;
        el.querySelector(':scope > .edit-handle')?.remove();
        // Content is inert while arranging so clicks and Tab reach only the move controls.
        [...el.children].forEach(child => { child.inert = on; });
        el.draggable = on;
        if (on) el.insertAdjacentHTML('afterbegin', `<div class="edit-handle"><span class="grip" title="Drag to move">${icon('grip')}</span><span class="edit-name">${esc(name)}</span><button data-move="-1" aria-label="${esc(`Move ${name} earlier`)}">${icon('left', 'sm')}</button><button data-move="1" aria-label="${esc(`Move ${name} later`)}">${icon('chevron', 'sm')}</button></div>`);
      });
      if (on) toast('Layout editing on. Drag cards or use the arrows; press Done or Esc when finished.');
    }
    function bindOverview() {
      applyLayout();
      const grid = $('ov-grid'), clearMarks = () => grid.querySelectorAll('.drop-before, .drop-after, .dragging').forEach(el => el.classList.remove('drop-before', 'drop-after', 'dragging'));
      $('edit-bar').addEventListener('click', e => {
        const b = e.target.closest('[data-layout]');
        if (!b) return;
        if (b.dataset.layout === 'reset') { layoutOrder = null; saveOrder(); applyLayout(true); toast('Overview layout reset to the default.'); }
        else setEditing(false);
      });
      grid.addEventListener('click', e => {
        const b = e.target.closest('[data-move]');
        if (!b || !editing) return;
        const key = b.closest('[data-key]').dataset.key, keys = [...grid.children].map(el => el.dataset.key), i = keys.indexOf(key), j = i + Number(b.dataset.move);
        if (j < 0 || j >= keys.length) return;
        reorder(key, keys[j], j > i);
        grid.querySelector(`[data-key="${key}"] [data-move="${b.dataset.move}"]`).focus();
      });
      grid.addEventListener('dragstart', e => {
        const el = e.target.closest && e.target.closest('[data-key]');
        if (!editing || !el) return;
        dragKey = el.dataset.key;
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', dragKey);
        requestAnimationFrame(() => el.classList.add('dragging'));
      });
      const dropTarget = e => { const el = e.target.closest && e.target.closest('[data-key]'); if (!dragKey || !el || el.dataset.key === dragKey) return null; const r = el.getBoundingClientRect(); return {el, after: e.clientX > r.left + r.width / 2}; };
      grid.addEventListener('dragover', e => {
        const t = dropTarget(e);
        if (!t) return;
        e.preventDefault();
        grid.querySelectorAll('.drop-before, .drop-after').forEach(el => { if (el !== t.el) el.classList.remove('drop-before', 'drop-after'); });
        t.el.classList.toggle('drop-after', t.after); t.el.classList.toggle('drop-before', !t.after);
      });
      grid.addEventListener('drop', e => {
        const t = dropTarget(e);
        if (!t) return;
        e.preventDefault();
        const key = dragKey;
        clearMarks(); dragKey = null;
        reorder(key, t.el.dataset.key, t.after);
      });
      grid.addEventListener('dragend', () => { clearMarks(); dragKey = null; });
    }

    /* ---------- Development ---------- */
    const PAGE = 40;
    const hist = {query:'', type:'all', range:null, newest:true, limit:PAGE, areas:'all'};
    function activityBuckets() {
      if (!commits.length) return {buckets: [], unit: 'day'};
      const first = Math.min(...commits.map(c => c.dayN).filter(Number.isFinite)), last = Math.max(refN, ...commits.map(c => c.dayN).filter(Number.isFinite));
      const span = last - first + 1;
      if (span <= 120) {
        return {unit:'day', buckets: Array.from({length: span}, (_, i) => {
          const day = numDay(first + i), e = daily.get(day) || {n:0, added:0, deleted:0};
          return {value: e.n, title: weekday(day), tip: `${plural(e.n, 'commit')}\n+${num(e.added)} −${num(e.deleted)} lines`, short: shortDate(day), act: `range:${day}`};
        })};
      }
      const count = Math.min(104, Math.ceil(span / 7));
      return {unit:'week', buckets: weeks(count).map(w => ({value: w.items.length, title: `Week of ${date(numDay(w.begin))}`, tip: `${plural(w.items.length, 'commit')}\n+${num(w.items.reduce((t, c) => t + c.added, 0))} −${num(w.items.reduce((t, c) => t + c.deleted, 0))} lines`, short: shortDate(numDay(w.begin)), act: `range:${numDay(w.begin)}..${numDay(w.end)}`}))};
    }

    function renderDevelopment() {
      const n = data.numbers, added = Number(n.added) || 0, deleted = Number(n.deleted) || 0;
      const activeDays = daily.size;
      const kpis = card({span:'c-12', cls:'kpis', body: `<div class="stats">${[
        stat({label:'Commits', value: commits.length, note: `${commits.filter(c => inLast(c, 30)).length} in the last 30 days`}),
        stat({label:'Active days', value: activeDays, note: git.firstCommit ? `since ${esc(date(git.firstCommit))}` : ''}),
        stat({label:'Lines added', value: added, note: 'cumulative, binaries excluded'}),
        stat({label:'Lines removed', value: deleted, note: `net ${added - deleted >= 0 ? '+' : '−'}${compact(Math.abs(added - deleted))}`}),
        stat({label:'Tracked files', value: Number(n.trackedFiles) || 0, note: `${num(Number(n.sourceFiles) || 0)} counted as source`})
      ].join('')}</div>`});

      const {buckets, unit} = activityBuckets();
      const activity = commits.length ? card({span:'c-8', cls:'activity', title:'Commit activity', icon:'pulse', meta: esc(`Per ${unit} · ${zone}`), body:
        `${columns(buckets, `Commits per ${unit}`)}<p class="note">Hover or focus a ${unit} for details; select it to filter the commit list. Timestamps describe recorded commits, not working time.</p>`}) : '';

      const typeCounts = Object.keys(TYPES).map(t => ({key: t, label: TYPES[t], value: commits.filter(c => c.parsed.type === t).length, color: TYPE_COLOR[t]})).filter(e => e.value);
      const types = typeCounts.length ? card({span:'c-4', title:'Commit categories', icon:'tag', meta:'Conventional prefixes', body:
        `${stack(typeCounts, 'Commits by category')}${legend(typeCounts, num, e => `type:${e.key}`)}`}) : '';

      const churnCard = commits.length ? card({span:'c-6', title:'Additions vs deletions', icon:'layers', meta:'Per week, last 12 weeks', body:
        `${churn(weeks(12).map(w => ({title: `Week of ${date(numDay(w.begin))}`, short: shortDate(numDay(w.begin)), added: w.items.reduce((t, c) => t + c.added, 0), deleted: w.items.reduce((t, c) => t + c.deleted, 0)})))}
        <div class="key"><span><i class="sw add-sw"></i>Lines added</span><span><i class="sw del-sw"></i>Lines removed</span></div>`}) : '';

      const areas = commits.some(c => c.files.length) ? card({span:'c-6', title:'Development areas', icon:'box', action: `<div class="seg-toggle" role="group" aria-label="Area time range"><button data-areas="all" aria-pressed="true">All time</button><button data-areas="recent" aria-pressed="false">Last 30 days</button></div>`, body:
        '<div id="area-bars"></div><p class="note">File changes per folder; a file changed twice counts twice.</p>'}) : '';

      const content = entriesOf(n.content);
      const lines = languages.reduce((t, e) => t + e.value, 0);
      const comp = lines || content.length ? card({span:'c-6', title:'Repository composition', icon:'layers', body:
        `${lines ? `<h3 class="kicker">Lines of code · ${num(lines)}</h3>${stack(languages, 'Lines of code by language')}${legend(languages)}` : ''}
        ${content.length ? `<h3 class="kicker">Content</h3>${hbars(content)}` : ''}`}) : '';

      const size = n.projectSize;
      let sizeCard = '';
      if (size && size.totalBytes > 0) {
        const groups = fold(entriesOf(size.groups), 7);
        const skipped = list(size.skipped).length;
        sizeCard = card({span:'c-6', title:'Size on disk', icon:'download', meta: esc(`${bytes(size.totalBytes)} · ${plural(size.fileCount, 'file')}`), body:
          `${stack(groups, 'Folder size by category', v => bytes(v, size.totalBytes))}${legend(groups, v => bytes(v, size.totalBytes))}<p class="note">Logical sizes of the working folder, ignored files included; 1 GB = 10⁹ bytes.${skipped ? ` ${skipped} links or unreadable entries skipped.` : ''}</p>`});
      }

      let sessionsCard = '';
      if (sessions.length) {
        const tokenRuns = [...sessions].reverse().filter(s => typeof s.tokens === 'number');
        sessionsCard = card({span:'c-12', id:'sessions', cls:'sessions', title: aiSessions.length ? 'Sessions & AI activity' : 'Session notes', icon:'cpu', body:
          `<div class="stats">${aiTotals()}</div>
          <div class="sessions-grid">${models.length ? `<div><h3 class="kicker">Models and agents</h3>${modelTable(models)}${tokenRuns.length > 1 ? `<h3 class="kicker">Tokens per session</h3>${columns(tokenRuns.map(s => ({value: s.tokens, title: s.title, tip: `${num(s.tokens)} tokens · ${shortDate(s.date)}`, short: shortDate(s.date), act: `session:${s.index}`})), 'Tokens per session', 'token')}` : ''}</div>` : ''}
          <div><h3 class="kicker">Recent sessions</h3><ul class="srows">${sessions.map(sessionRow).join('')}</ul></div></div>
          <p class="note">Only explicitly recorded session metrics are summed. Git timestamps do not establish active agent time, token usage or billing.</p>`});
      }

      const tree = git.workingTree.length ? card({span:'c-6', title:'Working tree', icon:'file', meta: esc(plural(git.workingTree.length, 'change')), body:
        `<ul class="tree">${git.workingTree.slice(0, 200).map(f => `<li><code class="tree-st">${esc(text(f.status).trim() || '?')}</code><span>${esc(f.path)}</span></li>`).join('')}</ul>`}) : '';

      const explorer = card({span:'c-12', id:'commits', cls:'explorer', title:'Commit history', icon:'commit', body: commits.length ? `
        <div class="ex-controls"><label class="field">${icon('search')}<input id="ex-search" type="search" placeholder="Filter by message, hash or file" aria-label="Filter commits"></label>
          <div class="chip-row" id="ex-types" role="group" aria-label="Commit category"></div>
          <button class="btn ghost" id="ex-order"></button></div>
        <div class="ex-status"><span id="ex-result" aria-live="polite"></span><span id="ex-range"></span></div>
        <div id="ex-list" class="ex-list"></div><button id="ex-more" class="btn ghost wide" hidden></button>` : empty('No commits recorded yet.')});

      return pack([viewHead('development', 'Development', git.firstCommit ? esc(`${date(git.firstCommit)} — ${date(git.latestCommit)} · ${plural(commits.length, 'commit')} on ${git.branch || 'HEAD'}`) : 'Local Git activity'), kpis, activity, types, churnCard, areas, comp, sizeCard, sessionsCard, tree, explorer]);
    }

    function renderAreas() {
      const el = $('area-bars');
      if (!el) return;
      const rows = areaCounts(hist.areas === 'recent' ? commits.filter(c => inLast(c, 30)) : commits).slice(0, 10);
      el.innerHTML = rows.length ? hbars(rows) : empty('No changes in the last 30 days.');
      document.querySelectorAll('[data-areas]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.areas === hist.areas)));
    }

    const explorerItems = () => {
      const q = hist.query.toLowerCase().trim();
      const items = commits.filter(c => (hist.type === 'all' || c.parsed.type === hist.type)
        && (!hist.range || (c.dayN >= hist.range.from && c.dayN <= hist.range.to))
        && (!q || `${c.subject} ${c.sha} ${c.files.map(f => f.path).join(' ')}`.toLowerCase().includes(q)));
      return hist.newest ? items : items.reverse();
    };
    function renderExplorer() {
      if (!$('ex-list')) return;
      const counts = {all: commits.length};
      commits.forEach(c => { counts[c.parsed.type] = (counts[c.parsed.type] || 0) + 1; });
      $('ex-types').innerHTML = ['all', ...Object.keys(TYPES).filter(t => counts[t])].map(t => `<button class="chip${t === hist.type ? ' on' : ''}" data-ex-type="${t}" aria-pressed="${t === hist.type}">${t === 'all' ? '' : `<i class="sw" style="--c:${TYPE_COLOR[t]}"></i>`}${t === 'all' ? 'All' : TYPES[t]}<small>${counts[t]}</small></button>`).join('');
      $('ex-order').textContent = hist.newest ? 'Newest first' : 'Oldest first';
      $('ex-search').value = hist.query;
      $('ex-range').innerHTML = hist.range ? `<button class="chip on removable" id="ex-clear-range" aria-label="${esc(`Remove date filter ${hist.range.label}`)}">${icon('clock', 'sm')}${esc(hist.range.label)}${icon('x', 'sm')}</button>` : '';
      const items = explorerItems(), shown = items.slice(0, hist.limit);
      $('ex-result').textContent = `${num(items.length)} of ${plural(commits.length, 'commit')}`;
      const perDay = {};
      items.forEach(c => { perDay[c.day] = (perDay[c.day] || 0) + 1; });
      let html = '', lastDay = null;
      for (const c of shown) {
        if (c.day !== lastDay) { html += `<div class="day-sep"><span>${esc(c.day ? weekday(c.day) : 'Date not recorded')}</span><b>${plural(perDay[c.day], 'commit')}</b></div>`; lastDay = c.day; }
        html += `<details class="commit" id="c-${esc(c.sha)}" data-sha="${esc(c.sha)}"><summary><i class="tdot" style="--c:${TYPE_COLOR[c.parsed.type]}" aria-hidden="true"></i><span class="commit-main">${subjectHtml(c)}</span><span class="commit-meta"><code>${esc(c.short)}</code><span>${plural(c.files.length, 'file')}</span><span class="add">+${num(c.added)}</span><span class="del">−${num(c.deleted)}</span><time datetime="${esc(c.date)}">${esc(clock(c.date))}</time></span>${icon('chevron', 'chev')}</summary><div class="changes"></div></details>`;
      }
      $('ex-list').innerHTML = items.length ? html : empty('No commits match this filter.');
      $('ex-more').hidden = items.length <= shown.length;
      $('ex-more').textContent = `Show ${Math.min(PAGE, items.length - shown.length)} more · ${num(items.length - shown.length)} remaining`;
    }
    // File tables are built only when a commit is opened; large commits show the first rows until asked.
    function fileTable(c, limit) {
      const max = Math.max(1, ...c.files.map(f => (f.added || 0) + (f.deleted || 0)));
      const rows = c.files.slice(0, limit).map(f => {
        const binary = f.added == null;
        const bar = binary ? '<span class="fbar binary" title="Binary file"></span>' : `<span class="fbar" title="+${Number(f.added)} / −${Number(f.deleted)}"><i class="a" style="width:${(f.added / max * 100).toFixed(1)}%"></i><i class="d" style="width:${((f.deleted || 0) / max * 100).toFixed(1)}%"></i></span>`;
        return `<tr><td class="path">${esc(f.path)}</td><td>${bar}</td><td class="add">${binary ? 'bin' : `+${num(f.added)}`}</td><td class="del">${f.deleted == null ? 'bin' : `−${num(f.deleted)}`}</td></tr>`;
      }).join('');
      return `<div class="changes-head"><span>${esc(date(c.date, true))}</span>${commitLink(c.sha)}</div>${c.files.length ? `<div class="table-wrap"><table class="ftable"><thead><tr><th scope="col">File</th><th scope="col"><span class="sr">Change size</span></th><th scope="col">Added</th><th scope="col">Removed</th></tr></thead><tbody>${rows}</tbody></table></div>${c.files.length > limit ? `<button class="btn ghost" data-all-files>Show all ${num(c.files.length)} files</button>` : ''}` : '<p class="muted">Merge commit: no file changes of its own.</p>'}`;
    }
    function bindDevelopment() {
      renderAreas();
      document.querySelectorAll('[data-areas]').forEach(b => b.addEventListener('click', () => { hist.areas = b.dataset.areas; renderAreas(); }));
      if (!$('ex-list')) return;
      renderExplorer();
      $('ex-search').addEventListener('input', () => { hist.query = $('ex-search').value; hist.limit = PAGE; renderExplorer(); });
      $('ex-order').addEventListener('click', () => { hist.newest = !hist.newest; renderExplorer(); });
      $('ex-more').addEventListener('click', () => { hist.limit += PAGE; renderExplorer(); });
      $('ex-types').addEventListener('click', e => { const b = e.target.closest('[data-ex-type]'); if (!b) return; hist.type = b.dataset.exType; hist.limit = PAGE; renderExplorer(); $(`ex-types`).querySelector(`[data-ex-type="${hist.type}"]`).focus(); });
      $('ex-range').addEventListener('click', e => { if (e.target.closest('#ex-clear-range')) { hist.range = null; renderExplorer(); $('ex-search').focus(); } });
      const listEl = $('ex-list');
      const commitOf = el => commits.find(c => c.sha === el.dataset.sha);
      listEl.addEventListener('toggle', e => {
        const el = e.target;
        if (!el.matches('details.commit') || !el.open || el.dataset.ready) return;
        el.dataset.ready = '1';
        el.querySelector('.changes').innerHTML = fileTable(commitOf(el), 150);
      }, true);
      listEl.addEventListener('click', e => { const more = e.target.closest('[data-all-files]'); if (more) { const el = more.closest('details.commit'); el.querySelector('.changes').innerHTML = fileTable(commitOf(el), Infinity); } });
    }

    /* ---------- Roadmap ---------- */
    let selectedNode = Math.max(0, road.indexOf(nextNode));
    function renderRoadmapView() {
      let lastDone = -1;
      road.forEach((r, i) => { if (r.status === 'done') lastDone = i; });
      const head = viewHead('roadmap', 'Roadmap', mainRoad.length ? esc(`${doneMain} of ${mainRoad.length} milestones complete${nextNode ? ` · now building ${nextNode.id} ${nextNode.title}` : ''}`) : 'How the project has evolved',
        mainRoad.length ? `<div class="head-ring">${ring(doneMain, mainRoad.length, `${doneMain} of ${mainRoad.length} milestones complete`, `<b>${Math.round(share(doneMain, mainRoad.length))}%</b>`)}</div>` : '');
      const nodes = road.map((r, i) => {
        const [, ic] = statusOf(r.status);
        return `<button role="tab" id="node-${i}" class="node n-${esc(r.status)}${r.side ? ' side' : ''}" aria-selected="false" aria-controls="road-detail" tabindex="-1" aria-label="${esc(`${r.id}: ${r.title} (${statusOf(r.status)[2]})`)}"><span class="node-dot" aria-hidden="true">${icon(ic)}</span><span class="node-text" aria-hidden="true"><span class="node-id">${esc(r.id)}${r.status === 'next' ? '<em>Now</em>' : ''}</span><span class="node-title">${esc(r.title)}</span><span class="node-date">${esc(r.date ? shortDate(r.date) : statusOf(r.status)[2])}</span></span></button>`;
      }).join('');
      const timeline = road.length ? card({span:'c-12', cls:'timeline-card', id:'timeline', title:'Product evolution', icon:'roadmap', meta:'Arrow keys walk the path', body:
        `<div class="track-scroll"><div class="track" id="road-track" role="tablist" aria-label="Roadmap milestones" style="--n:${road.length};--fill:${lastDone < 0 ? 0 : ((lastDone + .5) / road.length * 100).toFixed(2)}%">${nodes}</div></div><div class="road-detail" id="road-detail" role="tabpanel" tabindex="0" aria-live="polite"></div>`}) : '';
      const phases = brief.phases.length ? card({span:'c-5', title:'Phases', icon:'layers', body:
        `<ol class="phases">${brief.phases.map((p, i) => `<li><span class="phase-num">${pad2(p.number ?? i + 1)}</span><span class="phase-title">${esc(p.title)}${p.commit ? ` ${commitLink(p.commit)}` : ''}</span>${pill(text(p.status || 'done'))}</li>`).join('')}</ol><p class="note">Phases are curated implementation steps, not a completion percentage.</p>`}) : '';
      const archiveSource = sourceOf('completed');
      const archive = data.milestones.length ? card({span: phases ? 'c-7' : 'c-12', title:'Completed archive', icon:'check', meta: esc(plural(data.milestones.length, 'entry', 'entries')), action: archiveSource ? `<a class="card-link" href="${esc(archiveSource.path)}">${esc(archiveSource.label)}${icon('external', 'sm')}</a>` : '', body:
        `<ul class="archive">${data.milestones.map((m, i) => [m, i]).reverse().map(([m, i]) => `<li><button data-act="milestone:${i}"><span class="arc-dot">${icon('check')}</span><span class="arc-main"><strong>${inline(m.title)}</strong><small>${esc(m.date ? `${date(m.date)} · ${plural(m.commits.length, 'linked commit')}` : 'No commit date matched')}</small></span>${icon('chevron', 'sm')}</button></li>`).join('')}</ul>`}) : '';
      return pack([head, timeline, phases, archive]);
    }
    function bindRoadmap() {
      const tabs = [...document.querySelectorAll('#road-track [role=tab]')];
      tabs.forEach((tab, i) => {
        tab.addEventListener('click', () => selectNode(i));
        tab.addEventListener('keydown', event => {
          const keys = {ArrowRight:1, ArrowDown:1, ArrowLeft:-1, ArrowUp:-1};
          if (!(event.key in keys) && event.key !== 'Home' && event.key !== 'End') return;
          event.preventDefault();
          selectNode(event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (i + keys[event.key] + tabs.length) % tabs.length, true);
        });
      });
      if (tabs.length) selectNode(selectedNode);
    }
    function selectNode(i, focus = false) {
      selectedNode = i;
      const tabs = document.querySelectorAll('#road-track [role=tab]');
      if (!tabs.length) return;
      tabs.forEach((tab, j) => { tab.setAttribute('aria-selected', String(j === i)); tab.tabIndex = j === i ? 0 : -1; });
      tabs[i].scrollIntoView({block:'nearest', inline:'nearest', behavior: reduced.matches ? 'auto' : 'smooth'});
      if (focus) tabs[i].focus({preventScroll:true});
      const r = road[i], {w, tagged, windowed} = roadCommits(r), all = [...tagged, ...windowed];
      const span = !w ? 'No date window yet' : w.first ? date(w.to) : !w.to ? `after ${date(w.from)}` : `${date(w.from)} → ${date(w.to)}`;
      const added = all.reduce((t, c) => t + c.added, 0), deleted = all.reduce((t, c) => t + c.deleted, 0);
      $('road-detail').setAttribute('aria-labelledby', `node-${i}`);
      $('road-detail').innerHTML = `<div class="rd-main"><div class="rd-top"><span class="ms-id">${esc(r.id)}</span>${pill(r.status)}${r.side ? '<span class="pill">Side item</span>' : ''}<span class="muted">${esc(r.date ? date(r.date) : 'Not yet dated')}</span></div>
        <h3 class="rd-title">${esc(r.title)}</h3>${r.summary ? `<p>${inline(r.summary)}</p>` : ''}
        <h4 class="kicker">Validation · ${plural(r.tests.length, 'test')}</h4>${r.tests.length ? `<div class="chip-row">${r.tests.map(t => `<span class="chip test">${icon('check', 'sm')}${esc(t)}</span>`).join('')}</div>` : '<p class="muted">No tests recorded for this milestone yet.</p>'}
        <dl class="mini"><div><dt>Commits</dt><dd>${all.length}</dd></div><div><dt>Lines</dt><dd><span class="add">+${compact(added)}</span> <span class="del">−${compact(deleted)}</span></dd></div><div><dt>Window</dt><dd>${esc(span)}</dd></div></dl></div>
        <div class="rd-commits"><h4 class="kicker">Associated commits <span class="approx">approximate</span></h4>${all.length ? `<ul class="crows">${all.slice(0, 12).map(c => commitRow(c).replace('<li>', `<li${tagged.includes(c) ? ' class="tagged"' : ''}>`)).join('')}</ul>${all.length > 12 ? `<p class="note">${all.length - 12} more in the commit history.</p>` : ''}` : `<p class="muted">${r.status === 'done' ? 'No commits matched this milestone.' : 'No commits yet. This milestone has not started.'}</p>`}
        <p class="note">${tagged.length} tagged with ${esc(r.id)} in the subject, ${windowed.length} dated inside the milestone window.</p></div>`;
    }

    /* ---------- Intelligence ---------- */
    const planState = {query:'', status:'all'};
    function renderIntelligence() {
      const head = viewHead('intelligence', 'Intelligence', 'What the project knows about itself: state, decisions, systems, plan and rules.');
      const state = brief.currentState.trim() || brief.inProgress.trim() || project.flow.length ? card({span:'c-7', cls:'state', title:'Current state', icon:'target', action: brief.handoff.trim() ? actLink('drawer:handoff', 'Full handoff') : '', body:
        `${flowHtml()}${brief.currentState.trim() ? `<div class="prose">${markdown(brief.currentState)}</div>` : ''}${brief.inProgress.trim() ? `<div class="focus-now"><span class="kicker live"><span class="live-dot" aria-hidden="true"></span>In progress</span><div class="prose">${markdown(brief.inProgress)}</div></div>` : ''}`}) : '';
      const next = brief.nextSteps.length ? card({span: state ? 'c-5' : 'c-12', title:'Next steps', icon:'chevron', meta: esc(plural(brief.nextSteps.length, 'step')), body:
        `<ol class="steps roomy">${brief.nextSteps.map(s => `<li>${inline(s)}</li>`).join('')}</ol>`}) : '';
      const decisionCards = decisions.length ? card({span:'c-12', id:'decisions', title:'Open decisions', icon:'decision', meta: esc(`${decisions.length} awaiting`), body:
        `<div class="decision-grid">${decisions.map((d, i) => `<article class="decision" id="decision-${i}"><span class="dnum">Decision ${pad2(i + 1)}</span><h3>${esc(d.title)}</h3>${d.detail ? `<p>${inline(d.detail)}</p>` : ''}</article>`).join('')}</div>`}) : '';
      const pillars = brief.pillars.length ? card({span:'c-12', title:'Pillars', icon:'layers', body:
        `<div class="pillar-grid">${brief.pillars.map((p, i) => `<article class="pillar"><span class="pillar-num">${pad2(i + 1)}</span><h3>${esc(p.name)}</h3>${p.text ? `<p>${inline(p.text)}</p>` : ''}</article>`).join('')}</div>`}) : '';
      const sys = systems.length ? card({span:'c-12', id:'systems', title:'Systems', icon:'box', meta: esc(plural(systems.length, 'system')), body:
        `<ul class="sys-list">${systems.map(s => `<li class="sys-row" id="system-${s.index}"><div class="sys-row-main"><div class="sys-top"><h3>${esc(s.name)}</h3>${pill(s.status)}</div>${s.summary ? `<p>${inline(s.summary)}</p>` : ''}${s.tags.length || s.paths.length ? `<div class="chip-row">${s.tags.map(t => `<span class="chip">${esc(t)}</span>`).join('')}${s.paths.map(p => `<code class="path-chip">${esc(p)}</code>`).join('')}</div>` : ''}</div>
          <div class="sys-row-stats">${s.paths.length ? `${spark(s.weekly, `${s.name}: commits per week, last 8 weeks`, 32)}<dl class="mini"><div><dt>Commits</dt><dd>${s.touching.length}</dd></div><div><dt>Lines changed</dt><dd>${compact(s.lines)}</dd></div><div><dt>Last touched</dt><dd>${esc(s.last ? ago(s.last) : '—')}</dd></div></dl>` : '<p class="muted">No paths configured, so no Git activity is attributed.</p>'}</div></li>`).join('')}</ul>`}) : '';
      const health = card({span:'c-6', title:'Health signals', icon:'heart', body: signalList(signals(), true)});
      const facts = project.facts.length ? card({span:'c-6', title:'Project facts', icon:'file', body: factsHtml()}) : '';
      const planSource = sourceOf('plan');
      const plan = data.plan.length ? (() => {
        const order = ['implemented', 'partial', 'planned', 'design'], colors = {implemented:'var(--ok)', partial:'var(--accent)', planned:'#8b949e', design:'#484f58'};
        const cov = order.map(s => ({key:s, label: PLAN_LABELS[s], value: data.plan.filter(p => p.status === s).length, color: colors[s]})).filter(e => e.value);
        return card({span:'c-12', id:'plan', cls:'plan', title:'Plan coverage', icon:'file', meta: esc(plural(data.plan.length, 'section')), action: planSource ? `<a class="card-link" href="${esc(planSource.path)}">Original plan${icon('external', 'sm')}</a>` : '', body:
          `${stack(cov, 'Plan sections by coverage')}${legend(cov)}
          <div class="ex-controls"><label class="field">${icon('search')}<input id="plan-search" type="search" placeholder="Search the plan" aria-label="Search the plan"></label>
          <label class="select">Coverage<select id="plan-status"><option value="all">All sections</option>${order.map(s => `<option value="${s}">${PLAN_LABELS[s]}</option>`).join('')}</select></label></div>
          <div id="plan-result" class="ex-status" aria-live="polite"></div><div id="plan-list" class="plan-list"></div>`});
      })() : '';
      const docs = data.sources.length || brief.rules.trim() ? card({span:'c-6', title:'Source documents', icon:'file', body:
        `<ul class="docs">${brief.handoff.trim() ? `<li><button data-act="drawer:handoff">${icon('file')}<span><strong>Handoff</strong><small>${esc(sourceOf('handoff') ? `${sourceOf('handoff').label} · modified ${ago(sourceOf('handoff').modifiedAt)}` : 'Full notes')}</small></span>${icon('chevron', 'sm')}</button></li>` : ''}${brief.rules.trim() ? `<li><button data-act="drawer:rules">${icon('lock')}<span><strong>Rules &amp; constraints</strong><small>${esc(sourceOf('rules') ? `${sourceOf('rules').label} · modified ${ago(sourceOf('rules').modifiedAt)}` : 'Project rules')}</small></span>${icon('chevron', 'sm')}</button></li>` : ''}${data.sources.filter(s => !['handoff', 'rules'].includes(s.key)).map(s => `<li><a href="${esc(s.path)}">${icon('external')}<span><strong>${esc(s.label || s.path)}</strong><small>${esc(`${s.key} · modified ${ago(s.modifiedAt)}`)}</small></span></a></li>`).join('')}</ul>`}) : '';
      const rules = brief.rules.trim() ? card({span:'c-6', cls:'rules', title:'Rules & constraints', icon:'lock', action: actLink('drawer:rules', 'Read all'), body: `<div class="prose fade">${markdown(brief.rules)}</div>`}) : '';
      const curated = [state, next, decisionCards, sys, pillars, facts, plan, rules, docs].some(Boolean);
      const hint = curated ? '' : card({span:'c-6', title:'Nothing curated yet', icon:'file', body:
        '<p class="muted">Point <code>paths.handoff</code> in <code>dashboard.config.json</code> at your notes, and add decisions, systems, pillars and health signals to <code>data/curation.json</code>. Then run <code>refresh.py</code>; each module appears once it has data.</p>'});
      return pack([head, state, next, decisionCards, sys, pillars, health, hint, facts, plan, rules, docs]);
    }
    function renderPlan() {
      if (!$('plan-list')) return;
      const q = planState.query.toLowerCase().trim();
      const items = data.plan.filter(s => (planState.status === 'all' || s.status === planState.status) && `${s.title} ${s.note} ${s.paragraphs.join(' ')}`.toLowerCase().includes(q));
      $('plan-result').textContent = `${items.length} of ${plural(data.plan.length, 'plan section')}`;
      $('plan-list').innerHTML = items.length ? items.map(s => `<details id="plan-${esc(s.number)}" class="plan-item"><summary><span class="plan-num">${pad2(s.number)}</span><span class="plan-name">${esc(s.title)}</span>${pill(s.status, PLAN_LABELS[s.status])}${icon('chevron', 'chev')}</summary><div class="plan-body">${s.note ? `<p class="plan-note">${inline(s.note)}</p>` : ''}<h4 class="kicker">Original plan text</h4>${s.paragraphs.map(p => `<p>${esc(p)}</p>`).join('') || '<p class="muted">No text under this heading.</p>'}</div></details>`).join('') : empty('No plan sections match. Try another search or coverage filter.');
    }
    function bindIntelligence() {
      if (!$('plan-list')) return;
      renderPlan();
      $('plan-search').addEventListener('input', () => { planState.query = $('plan-search').value; renderPlan(); });
      $('plan-status').addEventListener('change', () => { planState.status = $('plan-status').value; renderPlan(); });
    }

    /* ---------- Media ---------- */
    function renderMedia() {
      const b = data.banner;
      const head = viewHead('media', 'Media', esc(`${plural(data.media.length, 'capture')} of the project as it looks today`));
      const feature = b ? `<figure class="card c-12 feature"><img src="${esc(b.path)}" alt="${esc([b.title, b.caption].filter(Boolean).join(': ') || 'Project banner')}"><figcaption>${b.title ? `<strong>${esc(b.title)}</strong>` : ''}${b.caption ? `<span>${esc(b.caption)}</span>` : ''}</figcaption></figure>` : '';
      const gallery = data.media.length ? `<div class="c-12 masonry">${data.media.map((m, i) => `<figure class="shot"><button data-act="capture:${i}" aria-label="${esc(`Enlarge ${m.title}`)}"><img src="${esc(m.path)}" alt="${esc([m.title, m.caption].filter(Boolean).join(': '))}" loading="lazy" decoding="async"><span class="shot-zoom" aria-hidden="true">${icon('expand')}</span></button><figcaption><strong>${esc(m.title)}</strong>${m.caption ? `<span>${esc(m.caption)}</span>` : ''}</figcaption></figure>`).join('')}</div>` : '';
      return pack([head, feature, gallery]);
    }

    /* ---------- Views and navigation ---------- */
    const VIEWS = {
      overview:{name:'Overview', render: renderOverview, bind: bindOverview, ok: true},
      development:{name:'Development', render: renderDevelopment, bind: bindDevelopment, ok: true},
      roadmap:{name:'Roadmap', render: renderRoadmapView, bind: bindRoadmap, ok: road.length || data.milestones.length || brief.phases.length},
      intelligence:{name:'Intelligence', render: renderIntelligence, bind: bindIntelligence, ok: true},
      media:{name:'Media', render: renderMedia, ok: data.media.length || data.banner}
    };
    const ALIASES = {brief:'overview', history:'development', numbers:'development', plan:'intelligence', decisions:'intelligence'};
    const rendered = {};
    let pending = null, current = null;
    function ensure(view) {
      if (rendered[view]) return;
      rendered[view] = true;
      const el = $(`view-${view}`);
      el.innerHTML = VIEWS[view].render();
      el.querySelectorAll('.card, .view-head, .masonry').forEach((c, i) => c.style.setProperty('--i', Math.min(i, 14)));
      if (VIEWS[view].bind) VIEWS[view].bind();
    }
    function animateCounts(root) {
      root.querySelectorAll('[data-count]:not([data-done])').forEach(el => {
        el.dataset.done = '1';
        const end = Number(el.dataset.count), dec = Number(el.dataset.dec);
        if (reduced.matches) { el.textContent = fmtCount(end, dec); return; }
        const t0 = performance.now();
        const step = now => { const p = Math.min(1, (now - t0) / 1100), e = 1 - Math.pow(1 - p, 4); el.textContent = fmtCount(dec ? end * e : Math.round(end * e), dec); if (p < 1) requestAnimationFrame(step); };
        requestAnimationFrame(step);
      });
    }
    function show() {
      const raw = decodeURIComponent(location.hash.slice(1));
      const [first, sub] = raw.split('/');
      const key = ALIASES[first] || first;
      const anchor = !VIEWS[key] && raw && document.getElementById(raw);
      let view = VIEWS[key] && VIEWS[key].ok ? key : anchor && anchor.closest('.view') ? anchor.closest('.view').id.replace('view-', '') : 'overview';
      if (!VIEWS[view].ok) view = 'overview';
      ensure(view);
      const changed = view !== current;
      current = view;
      document.querySelectorAll('.view').forEach(el => { el.hidden = el.id !== `view-${view}`; });
      const el = $(`view-${view}`);
      if (changed) { el.classList.remove('enter'); void el.offsetWidth; el.classList.add('enter'); window.scrollTo({top:0, behavior:'instant'}); }
      document.querySelectorAll('[data-view]').forEach(a => { const on = a.dataset.view === view; a.classList.toggle('active', on); if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
      $('view-name').textContent = VIEWS[view].name;
      $('edit-layout').hidden = view !== 'overview';
      if (view !== 'overview' && editing) setEditing(false);
      document.title = `${VIEWS[view].name} · ${project.name}`;
      animateCounts(el);
      if (pending) { const run = pending; pending = null; requestAnimationFrame(run); }
      else if (sub && $(sub)) $(sub).scrollIntoView({block:'start', behavior: reduced.matches ? 'auto' : 'smooth'});
      else if (anchor && !anchor.closest('[hidden]')) anchor.scrollIntoView();
    }
    function go(target, after) {
      const [view] = target.split('/');
      pending = after || null;
      if (location.hash === `#${target}`) show(); else location.hash = target;
      if (!VIEWS[view]) pending = null;
    }
    const highlight = el => {
      if (!el) return;
      if (el.tagName === 'DETAILS') el.open = true;
      el.scrollIntoView({block:'center', behavior: reduced.matches ? 'auto' : 'smooth'});
      el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash');
      const focusable = el.matches('details') ? el.querySelector('summary') : el;
      if (!focusable.matches('a,button,summary,[tabindex]')) focusable.tabIndex = -1;
      focusable.focus({preventScroll:true});
    };
    function openCommit(sha) {
      go('development', () => {
        Object.assign(hist, {query:'', type:'all', range:null});
        hist.limit = Math.max(PAGE, explorerItems().findIndex(c => c.sha === sha) + 1);
        renderExplorer();
        highlight($(`c-${sha}`));
      });
    }
    function filterRange(spec) {
      const [a, b = a] = spec.split('..');
      hist.range = {from: dayNum(a), to: dayNum(b), label: a === b ? date(a) : `${shortDate(a)} – ${date(b)}`};
      hist.limit = PAGE;
      go('development', () => { renderExplorer(); $('commits').scrollIntoView({block:'start', behavior: reduced.matches ? 'auto' : 'smooth'}); });
    }
    function filterType(type) {
      hist.type = type; hist.limit = PAGE;
      go('development', () => { renderExplorer(); $('commits').scrollIntoView({block:'start', behavior: reduced.matches ? 'auto' : 'smooth'}); });
    }
    const openRoadmap = i => go('roadmap', () => { selectNode(i, true); $('timeline').scrollIntoView({block:'start', behavior: reduced.matches ? 'auto' : 'smooth'}); });
    const openDecision = i => go('intelligence', () => highlight($(`decision-${i}`)));
    const openSystem = i => go('intelligence', () => highlight($(`system-${i}`)));
    const openPlan = num => go('intelligence', () => { planState.query = ''; planState.status = 'all'; $('plan-search').value = ''; $('plan-status').value = 'all'; renderPlan(); highlight($(`plan-${num}`)); });

    /* ---------- Drawer ---------- */
    function openDrawer(kicker, title, html) {
      $('drawer-kicker').textContent = kicker; $('drawer-title').textContent = title; $('drawer-body').innerHTML = html;
      const d = $('drawer');
      if (!d.open) d.showModal();
      $('drawer-body').scrollTop = 0;
    }
    const linkedCommits = ids => { const found = ids.map(findCommit).filter(Boolean); return found.length ? `<h3 class="kicker">Linked commits</h3><ul class="crows">${found.map(commitRow).join('')}</ul>` : ''; };
    function openDoc(key) {
      const src = sourceOf(key);
      if (key === 'rules') openDrawer(src ? src.label : 'Rules', 'Rules & constraints', `<div class="prose">${markdown(brief.rules)}</div>`);
      else openDrawer(src ? `${src.label} · modified ${ago(src.modifiedAt)}` : 'Handoff', 'Handoff notes', `<div class="prose">${markdown(brief.handoff)}</div>`);
    }
    function openSession(i) {
      const s = data.sessions[i];
      if (!s) return;
      const facts = [['Date', date(s.date)], ['Agent', s.agent], ['Model', s.model], ['Provider', s.provider], ['Role', s.role], ['Runs', s.local === true ? 'Locally' : s.local === false ? 'Through an API' : ''],
        ['Duration', s.minutes != null ? duration(s.minutes) : ''], ['Tokens', s.tokens != null ? num(s.tokens) : ''], ['Tool calls', s.toolCalls != null ? num(s.toolCalls) : ''], ['Cost', s.costUsd != null ? money(s.costUsd) : '']].filter(([, v]) => v !== '' && v != null);
      openDrawer('Session', text(s.title), `<p class="lead">${inline(s.summary)}</p><dl class="facts">${facts.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>${linkedCommits(s.commits)}`);
    }
    function openMilestone(i) {
      const m = data.milestones[i];
      if (!m) return;
      openDrawer(m.date ? `Archive · ${date(m.date)}` : 'Archive', plain(m.title), `<div class="prose">${markdown(m.body) || '<p class="muted">No notes under this heading.</p>'}</div>${linkedCommits(m.commits)}`);
    }

    /* ---------- Lightbox ---------- */
    let captureIndex = 0;
    function showCapture(i) {
      const media = data.media;
      captureIndex = (i + media.length) % media.length;
      const m = media[captureIndex];
      $('lightbox-image').src = m.path; $('lightbox-image').alt = [m.title, m.caption].filter(Boolean).join(': ');
      $('lightbox-title').textContent = text(m.title); $('lightbox-caption').textContent = text(m.caption);
      $('lightbox-count').textContent = `${captureIndex + 1} / ${media.length}`;
      $('lightbox-strip').querySelectorAll('button').forEach((b, j) => b.setAttribute('aria-current', String(j === captureIndex)));
    }
    function openCapture(i) {
      if (!data.media.length) return;
      if (!$('lightbox-strip').childElementCount) $('lightbox-strip').innerHTML = data.media.map((m, j) => `<button data-cap="${j}" aria-label="${esc(`Show ${m.title}`)}"><img src="${esc(m.path)}" alt="" loading="lazy"></button>`).join('');
      showCapture(i);
      if (!$('lightbox').open) $('lightbox').showModal();
    }

    /* ---------- Command palette ---------- */
    const KINDS = [['View', 'overview'], ['Action', 'chevron'], ['Roadmap', 'roadmap'], ['Decision', 'decision'], ['System', 'box'], ['Plan', 'file'], ['Capture', 'media'], ['Session', 'session'], ['Archive', 'check'], ['Commit', 'commit']];
    let searchIndex = null, results = [], active = 0;
    function buildIndex() {
      const entry = (kind, title, sub, act, boost = 0, extra = '') => ({kind, title: text(title), sub: text(sub), act, boost, hay: `${title} ${sub} ${extra}`.toLowerCase()});
      const views = Object.entries(VIEWS).filter(([, v]) => v.ok);
      const blurbs = {overview:'Identity, pulse, focus, health and highlights', development:'Activity, composition, sessions and commit history', roadmap:'Milestones, phases and the completed archive', intelligence:'State, decisions, systems, plan and rules', media:'Screenshots and captures'};
      searchIndex = [
        ...views.map(([k, v]) => entry('View', v.name, blurbs[k], () => go(k), 20)),
        entry('Action', 'Copy refresh command', text(data.dashboard.refreshCommand) || 'python refresh.py', copyCommand, 8),
        entry('Action', 'Reload snapshot', 'Re-read data/project-data.js', () => location.reload(), 4),
        ...(fromExample ? [] : [entry('Action', 'Export snapshot', 'Download data/project.json', () => $('export-link').click(), 4)]),
        ...(/^https?:\/\//i.test(project.repository) ? [entry('Action', 'Open repository', project.repository, () => window.open(project.repository, '_blank', 'noopener'), 4)] : []),
        ...(brief.handoff.trim() ? [entry('Action', 'Read handoff notes', 'Full handoff document', () => openDoc('handoff'), 6)] : []),
        ...(brief.rules.trim() ? [entry('Action', 'Read rules & constraints', 'Project rules document', () => openDoc('rules'), 6)] : []),
        ...Object.entries(THEMES).map(([key, [name]]) => entry('Action', `Theme: ${name}`, 'Change the dashboard colours', () => applyTheme(key, true), 2, 'theme colour color')),
        ...road.map((r, i) => entry('Roadmap', `${r.id} · ${r.title}`, `${statusOf(r.status)[2]} · ${plain(r.summary)}`, () => openRoadmap(i), r === nextNode ? 18 : 12, r.tests.join(' '))),
        ...decisions.map((d, i) => entry('Decision', d.title, plain(d.detail), () => openDecision(i), 10)),
        ...systems.map(s => entry('System', s.name, `${statusOf(s.status)[2]} · ${plain(s.summary)}`, () => openSystem(s.index), 10, `${s.tags.join(' ')} ${s.paths.join(' ')}`)),
        ...data.plan.map(s => entry('Plan', `${pad2(s.number)} · ${s.title}`, `${PLAN_LABELS[s.status] || s.status}${s.note ? ` · ${plain(s.note)}` : ''}`, () => openPlan(s.number), 4)),
        ...data.media.map((m, i) => entry('Capture', m.title, m.caption, () => openCapture(i), 6)),
        ...data.sessions.map((s, i) => entry('Session', s.title, `${[s.agent, s.model, s.role].filter(Boolean).join(' · ')} · ${date(s.date)}`, () => openSession(i), 4, plain(s.summary))),
        ...data.milestones.map((m, i) => entry('Archive', plain(m.title), m.date ? date(m.date) : 'Archive entry', () => openMilestone(i), 4)),
        ...commits.map(c => entry('Commit', c.subject, `${c.short} · ${date(c.date)}`, () => openCommit(c.sha), 0, c.sha))
      ];
    }
    // Every query token must appear as a substring (strong) or an in-order subsequence (weak, gaps penalised).
    function fuzzy(hay, query) {
      let score = 0;
      for (const token of query.split(/\s+/).filter(Boolean)) {
        const at = hay.indexOf(token);
        if (at >= 0) { score += 100 - Math.min(at, 60) + (at === 0 || hay[at - 1] === ' ' ? 20 : 0); continue; }
        let pos = -1, gaps = 0;
        for (const ch of token) { const next = hay.indexOf(ch, pos + 1); if (next < 0) return -1; if (pos >= 0) gaps += next - pos - 1; pos = next; }
        if (gaps > token.length * 4) return -1;
        score += 40 - gaps;
      }
      return score;
    }
    function renderPalette() {
      const q = $('palette-input').value.toLowerCase().trim();
      let picked;
      if (q) {
        const scored = searchIndex.map(item => [item, fuzzy(item.hay, q)]).filter(([, s]) => s >= 0).sort((a, b) => (b[1] + b[0].boost) - (a[1] + a[0].boost));
        const perKind = {};
        picked = scored.filter(([item]) => (perKind[item.kind] = (perKind[item.kind] || 0) + 1) <= (item.kind === 'Commit' ? 8 : 6)).map(([item]) => item);
      } else {
        picked = searchIndex.filter(item => item.kind === 'View' || item.kind === 'Action' || (item.kind === 'Roadmap' && item.boost === 18) || item.kind === 'Decision').slice(0, 16);
      }
      results = [];
      let html = '';
      for (const [kind, ic] of KINDS) {
        const items = picked.filter(item => item.kind === kind);
        if (!items.length) continue;
        html += `<div role="group" aria-labelledby="pg-${kind}"><div class="pal-group" id="pg-${kind}" role="presentation">${esc(kind === 'Archive' ? 'Archive' : `${kind}s`)}</div>${items.map(item => { const i = results.push(item) - 1;
          return `<div role="option" id="pal-${i}" data-i="${i}" aria-selected="false" class="pal-item"><span class="pal-icon">${icon(ic)}</span><span class="pal-text"><span class="pal-title">${esc(item.title)}</span><span class="pal-sub">${esc(item.sub)}</span></span><span class="pal-enter" aria-hidden="true">↵</span></div>`; }).join('')}</div>`;
      }
      $('palette-list').innerHTML = html || '<p class="pal-empty">Nothing found. Try fewer or shorter words.</p>';
      $('palette-count').textContent = q ? `${results.length} result${results.length === 1 ? '' : 's'}` : 'Suggestions';
      setActive(0);
    }
    function setActive(i) {
      if (!results.length) { $('palette-input').removeAttribute('aria-activedescendant'); return; }
      active = (i + results.length) % results.length;
      $('palette-list').querySelectorAll('[role=option]').forEach((el, j) => el.setAttribute('aria-selected', String(j === active)));
      $('palette-input').setAttribute('aria-activedescendant', `pal-${active}`);
      $(`pal-${active}`).scrollIntoView({block:'nearest'});
    }
    const groupStep = dir => {
      const kinds = [...new Set(results.map(r => r.kind))], k = kinds.indexOf(results[active].kind);
      const target = kinds[(k + dir + kinds.length) % kinds.length];
      setActive(results.findIndex(r => r.kind === target));
    };
    function choose(i) { const item = results[i]; if (!item) return; $('palette').close(); item.act(); }
    function openPalette() {
      if (!searchIndex) buildIndex();
      if ($('palette').open) { $('palette-input').select(); return; }
      for (const id of ['drawer', 'lightbox']) if ($(id).open) $(id).close();
      $('palette-input').value = ''; renderPalette(); $('palette').showModal(); $('palette-input').focus();
    }

    /* ---------- Toast and tooltip ---------- */
    let toastTimer = 0;
    const toast = message => { $('toast').textContent = message; $('toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { $('toast').hidden = true; }, 6000); };
    async function copyCommand() {
      const command = text(data.dashboard.refreshCommand) || 'python refresh.py';
      try { await navigator.clipboard.writeText(command); toast('Refresh command copied. Run it from the project root, then reload.'); }
      catch { toast(command); }
    }
    const tip = document.createElement('div');
    tip.className = 'tip'; tip.setAttribute('role', 'tooltip'); tip.hidden = true; document.body.append(tip);
    const showTip = el => {
      tip.innerHTML = `${el.dataset.tipTitle ? `<strong>${esc(el.dataset.tipTitle)}</strong>` : ''}<span>${esc(el.dataset.tip)}</span>`;
      tip.hidden = false;
      const r = el.getBoundingClientRect();
      const x = clamp(r.left + r.width / 2 - tip.offsetWidth / 2, 8, window.innerWidth - tip.offsetWidth - 8);
      const y = r.top - tip.offsetHeight - 10 < 8 ? r.bottom + 10 : r.top - tip.offsetHeight - 10;
      tip.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
    };
    const tipFor = e => { const el = e.target.closest && e.target.closest('[data-tip]'); if (el) showTip(el); else tip.hidden = true; };

    /* ---------- Themes ---------- */
    // [name, accent, background] per theme; colours here only draw the swatches, styles.css holds the tokens.
    const projectAccent = /^#[0-9a-f]{6}$/i.test(project.accent) ? project.accent : '#6ea8fe';
    const THEMES = {
      default:['Project default', projectAccent, '#10141b'], 'forest-green':['Forest Green', '#4cb782', '#0f1813'], 'light-blue':['Light Blue', '#7cc4fa', '#0f1620'],
      'track-gold':['Track Gold', '#e3b341', '#17140e'], orange:['Orange', '#f0883e', '#18120e'], purple:['Purple', '#a78bfa', '#15111e'], aqua:['Aqua', '#2dd4bf', '#0d1817']
    };
    const THEME_KEY = `project-dashboard:theme:${project.name}`;
    const storedTheme = (() => { try { return localStorage.getItem(THEME_KEY); } catch { return null; } })();
    let theme = THEMES[storedTheme] ? storedTheme : THEMES[project.theme] ? project.theme : 'default';
    function applyTheme(key, save = false) {
      theme = THEMES[key] ? key : 'default';
      const root = document.documentElement;
      if (theme === 'default') { delete root.dataset.theme; root.style.setProperty('--accent', projectAccent); }
      else { root.dataset.theme = theme; root.style.removeProperty('--accent'); }
      // Text on a filled accent must stay readable for both pale and deep accents.
      const accent = THEMES[theme][1];
      const lum = [1, 3, 5].map(i => parseInt(accent.slice(i, i + 2), 16) / 255).map(c => c <= .03928 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4);
      root.style.setProperty('--on-accent', .2126 * lum[0] + .7152 * lum[1] + .0722 * lum[2] > .2 ? '#0b0d12' : '#ffffff');
      $('theme-menu').querySelectorAll('[data-theme-key]').forEach(b => b.setAttribute('aria-checked', String(b.dataset.themeKey === theme)));
      $('theme-button').title = `Theme: ${THEMES[theme][0]}`;
      if (save) { try { localStorage.setItem(THEME_KEY, theme); } catch { /* no storage: theme lasts for this visit */ } }
    }
    function toggleThemeMenu(open = $('theme-menu').hidden) {
      $('theme-menu').hidden = !open;
      $('theme-button').setAttribute('aria-expanded', String(open));
      if (open) ($('theme-menu').querySelector('[aria-checked="true"]') || $('theme-menu').querySelector('button')).focus();
    }

    /* ---------- Boot ---------- */
    try {
      $('theme-menu').innerHTML = `<div class="theme-menu-title">Theme</div>${Object.entries(THEMES).map(([key, [name, accent, bg]]) => `<button class="theme-opt" role="menuitemradio" aria-checked="false" data-theme-key="${key}"><span class="theme-sw" style="--sw:${accent};--sw-bg:${bg}" aria-hidden="true"></span>${esc(name)}${icon('check', 'sm')}</button>`).join('')}`;
      applyTheme(theme);
      $('demo-banner').hidden = !(fromExample || data.demo === true);
      $('export-link').hidden = fromExample;
      $('brand-name').textContent = project.name;
      $('crumb-project').textContent = project.name;
      $('brand').setAttribute('aria-label', `${project.name}: overview`);
      if (/^https?:\/\//i.test(project.repository)) { $('repo-link').href = project.repository; $('repo-link').hidden = false; }
      $('snapshot-time').textContent = `${date(data.generatedAt, true)}`;
      $('generated-at').textContent = [`Snapshot ${date(data.generatedAt, true)}`, zone, git.head ? `HEAD ${git.head.slice(0, 7)}` : ''].filter(Boolean).join(' · ');
      $('top-meta').innerHTML = [git.branch ? `<span class="chip-meta">${icon('branch', 'sm')}${esc(git.branch)}</span>` : '', git.head ? `<span class="chip-meta">${icon('commit', 'sm')}<code>${esc(git.head.slice(0, 7))}</code></span>` : '', git.latestCommit ? `<span class="chip-meta">${icon('clock', 'sm')}${esc(ago(git.latestCommit))}</span>` : ''].join('');
      if (mainRoad.length) { $('rail-progress').hidden = false; $('rail-progress').innerHTML = `<div class="rp-label"><span>Roadmap</span><b>${doneMain}/${mainRoad.length}</b></div><div class="rp-bar" role="img" aria-label="${esc(`${doneMain} of ${mainRoad.length} milestones complete`)}"><i style="width:${share(doneMain, mainRoad.length).toFixed(1)}%"></i></div>`; }
      if (decisions.length) { $('nav-decisions').hidden = false; $('nav-decisions').textContent = decisions.length; $('nav-decisions').title = `${decisions.length} open decisions`; }
      document.querySelectorAll('#rail-nav [data-view]').forEach(a => { a.closest('li').hidden = !VIEWS[a.dataset.view].ok; });
      if (/Mac|iPhone|iPad/.test(navigator.platform)) document.querySelector('.search-btn kbd').textContent = '⌘ K';

      show();
      window.addEventListener('hashchange', show);

      const acts = {
        go: target => go(target), commit: openCommit, decision: i => openDecision(+i), plan: n => openPlan(n), capture: i => openCapture(+i),
        session: i => openSession(+i), milestone: i => openMilestone(+i), system: i => openSystem(+i), roadmap: i => openRoadmap(+i),
        drawer: openDoc, range: filterRange, type: filterType
      };
      const keepsDrawer = new Set(['drawer', 'session', 'milestone']);
      document.addEventListener('click', event => {
        const el = event.target.closest('[data-act]');
        if (!el) return;
        const [kind, ...rest] = el.dataset.act.split(':');
        if (!acts[kind]) return;
        event.preventDefault();
        if ($('drawer').open && !keepsDrawer.has(kind)) $('drawer').close();
        acts[kind](rest.join(':'));
      });

      $('open-palette').addEventListener('click', openPalette);
      $('edit-layout').addEventListener('click', () => setEditing(!editing));
      $('theme-button').addEventListener('click', () => toggleThemeMenu());
      $('theme-menu').addEventListener('click', event => {
        const b = event.target.closest('[data-theme-key]');
        if (!b) return;
        applyTheme(b.dataset.themeKey, true);
        toggleThemeMenu(false); $('theme-button').focus();
      });
      $('theme-menu').addEventListener('keydown', event => {
        const items = [...$('theme-menu').querySelectorAll('button')], i = items.indexOf(document.activeElement);
        const step = {ArrowDown: 1, ArrowUp: -1}[event.key];
        if (step) { event.preventDefault(); items[(i + step + items.length) % items.length].focus(); }
        if (event.key === 'Escape') { event.stopPropagation(); toggleThemeMenu(false); $('theme-button').focus(); }
      });
      document.addEventListener('click', event => { if (!$('theme-menu').hidden && !event.target.closest('.theme-wrap')) toggleThemeMenu(false); });
      document.addEventListener('keydown', event => {
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); openPalette(); return; }
        const typing = event.target.closest?.('input, textarea, select, [contenteditable]');
        if (typing || event.ctrlKey || event.metaKey || event.altKey || document.querySelector('dialog[open]')) return;
        if (event.key === 'Escape' && editing) { setEditing(false); $('edit-layout').focus(); return; }
        if (event.key === '/') { event.preventDefault(); openPalette(); }
        const views = Object.keys(VIEWS).filter(k => VIEWS[k].ok);
        if (/^[1-5]$/.test(event.key) && views[Number(event.key) - 1]) go(views[Number(event.key) - 1]);
      });
      $('palette-input').addEventListener('input', renderPalette);
      $('palette-input').addEventListener('keydown', event => {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); setActive(active + (event.key === 'ArrowDown' ? 1 : -1)); }
        else if (event.key === 'Home' && event.ctrlKey) { event.preventDefault(); setActive(0); }
        else if (event.key === 'End' && event.ctrlKey) { event.preventDefault(); setActive(results.length - 1); }
        else if (event.key === 'Tab' && results.length) { event.preventDefault(); groupStep(event.shiftKey ? -1 : 1); }
        else if (event.key === 'Enter') { event.preventDefault(); choose(active); }
      });
      $('palette-list').addEventListener('click', event => { const el = event.target.closest('[role=option]'); if (el) choose(Number(el.dataset.i)); });
      $('palette-list').addEventListener('pointermove', event => { const el = event.target.closest('[role=option]'); if (el && Number(el.dataset.i) !== active) setActive(Number(el.dataset.i)); });
      for (const id of ['palette', 'drawer', 'lightbox']) $(id).addEventListener('click', event => { if (event.target === $(id)) $(id).close(); });

      $('drawer-close').addEventListener('click', () => $('drawer').close());
      $('lightbox-close').addEventListener('click', () => $('lightbox').close());
      $('lightbox-prev').addEventListener('click', () => showCapture(captureIndex - 1));
      $('lightbox-next').addEventListener('click', () => showCapture(captureIndex + 1));
      $('lightbox-strip').addEventListener('click', event => { const b = event.target.closest('[data-cap]'); if (b) showCapture(Number(b.dataset.cap)); });
      $('lightbox').addEventListener('keydown', event => {
        const step = {ArrowLeft: -1, ArrowRight: 1}[event.key];
        if (step) { event.preventDefault(); showCapture(captureIndex + step); }
        if (event.key === 'Home' || event.key === 'End') { event.preventDefault(); showCapture(event.key === 'Home' ? 0 : data.media.length - 1); }
      });

      document.addEventListener('pointerover', tipFor);
      document.addEventListener('focusin', tipFor);
      document.addEventListener('pointerdown', () => { tip.hidden = true; });
      window.addEventListener('scroll', () => { tip.hidden = true; }, {passive: true});

      $('refresh').addEventListener('click', () => location.reload());
      $('copy-command').addEventListener('click', copyCommand);
      document.body.classList.add('ready');
    } catch (error) {
      $('fatal').hidden = false; $('fatal').textContent = `Could not render the dashboard: ${error.message}. Run refresh.py and reload.`;
      console.error(error);
    }
  }

  function fatal() {
    $('fatal').hidden = false;
    document.querySelectorAll('.view').forEach(v => { v.hidden = true; });
  }

  // data/project-data.js is optional: without it, fall back to the bundled demo snapshot.
  if (window.PROJECT_DATA) start(window.PROJECT_DATA, false);
  else {
    const script = document.createElement('script');
    script.src = 'examples/demo-project-data.js';
    script.onload = () => { if (window.PROJECT_DATA) start(window.PROJECT_DATA, true); else fatal(); };
    script.onerror = fatal;
    document.head.append(script);
  }
})();
