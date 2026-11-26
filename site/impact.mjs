const $ = id => document.getElementById(id);
const el = (tag, attrs = {}, ...kids) => { const e = document.createElement(tag); for (const [k, v] of Object.entries(attrs)) { if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v; else if (k === 'style') e.style.cssText = v; else e.setAttribute(k, v); } for (const k of kids) e.append(k); return e; };
const svgEl = (tag, attrs = {}) => { const e = document.createElementNS('http://www.w3.org/2000/svg', tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); return e; };
const pct = x => (100 * x).toFixed(0) + '%';
const LABEL = { retest_all: 'Retest all (baseline)', declared_manifest: 'Hand-declared manifest', static_call_graph: 'Static call graph (direct calls)', static_with_fn_pointers: 'Static + function pointers', dynamic_coverage: 'Dynamic per-test coverage', hybrid: 'Hybrid (recommended)', learned_logreg_random5fold: 'Learned (log. regression, 5-fold)', learned_logreg_leave_one_file_out: 'Learned (leave-one-file-out)' };
let D;

async function main() {
  D = await (await fetch('impact-data.json')).json();
  const r = D.rts;
  $('rts-scope').textContent = `${r.compilable_changes} compilable single-token changes across 7 files (${r.generated_mutants - r.compilable_changes} did not compile). Retest-all ground truth: ${r.faulty_changes} break at least one of the ${r.tests} tests; ${r.undetected_by_full_suite} break none.`;
  const sel = $('change');
  const groups = {};
  for (const c of D.changes) (groups[c.file] ??= []).push(c);
  for (const [file, cs] of Object.entries(groups)) {
    const g = el('optgroup', { label: file });
    for (const c of cs) g.append(el('option', { value: c.id, text: `L${c.line} ${c.operator}: ${c.after.slice(0, 60)}${c.failing.length ? '' : '  (no test fails)'}` }));
    sel.append(g);
  }
  const start = D.changes.find(c => c.entity.name === 'clamp_int' && c.failing.length > 4) || D.changes[0];
  sel.value = start.id;
  sel.addEventListener('change', () => showChange(sel.value));
  showChange(start.id);
  techTable(); adequacy(); assistant(); limits();
}

function layout() {
  const cols = { pipeline_step: [190, 40], telemetry_dispatch: [480, 40], validate_sample: [65, 140], clamp_command: [190, 140], rate_limit: [305, 140], encode_status: [445, 140], encode_age: [575, 140], age_ms: [150, 250], clamp_int: [330, 250] };
  return cols;
}

function drawGraph(change) {
  const svg = $('graph'); svg.replaceChildren();
  const pos = layout(), g = D.graph, hot = change.entity.kind === 'function' ? change.entity.name : null;
  const reach = new Set();
  for (const t of change.failing) for (const f of D.graph.coverage[t] || []) reach.add(f);
  const edge = (a, b, ptr) => { const [x1, y1] = pos[a], [x2, y2] = pos[b]; svg.append(svgEl('path', { class: 'edge' + (ptr ? ' ptr' : ''), d: `M${x1} ${y1 + 14} C${x1} ${(y1 + y2) / 2} ${x2} ${(y1 + y2) / 2} ${x2} ${y2 - 14}` })); };
  for (const [a, bs] of Object.entries(g.direct)) for (const b of bs) if (pos[a] && pos[b]) edge(a, b, false);
  for (const a of g.indirect_callers) for (const b of g.address_taken) if (pos[a] && pos[b]) edge(a, b, true);
  for (const [name, [x, y]] of Object.entries(pos)) {
    const w = Math.max(80, name.length * 6.6 + 16);
    const n = svgEl('g', { class: 'node' + (name === hot ? ' hot' : reach.has(name) ? ' reach' : '') });
    n.append(svgEl('rect', { x: x - w / 2, y: y - 14, width: w, height: 28, rx: 6 }));
    const t = svgEl('text', { x, y: y + 4, 'text-anchor': 'middle' }); t.textContent = name; n.append(t);
    const span = g.spans[name]; const title = svgEl('title'); title.textContent = `${name} · ${span ? span.file : ''}`; n.append(title);
    svg.append(n);
  }
}

function showChange(id) {
  const c = D.changes.find(x => x.id === id);
  $('diff').replaceChildren(el('span', { class: 'del', text: `- ${c.file}:${c.line}  ${c.before}\n` }), el('span', { class: 'add', text: `+ ${c.file}:${c.line}  ${c.after}` }));
  const where = c.entity.kind === 'function' ? `function ${c.entity.name}` : c.entity.kind === 'global' ? `non-executable constant ${c.entity.name}` : 'unlocalised line';
  $('truth').textContent = `Changed: ${where}. Full suite: ${c.failing.length ? c.failing.length + ' failing test(s) — ' + c.failing.join(', ') : 'no test fails (a gap in the suite, or an equivalent change).'}`;
  drawGraph(c);
  const box = $('selections'); box.replaceChildren();
  const fail = new Set(c.failing);
  for (const [tech, tests] of Object.entries(c.selected)) {
    const s = new Set(tests), missed = c.failing.filter(t => !s.has(t));
    const head = el('div', {}, el('b', { text: LABEL[tech] || tech }), el('span', { class: 'small muted', text: `  ${tests.length}/${D.rts.tests} tests` }));
    if (c.failing.length) head.append(el('span', { class: 'verdict ' + (missed.length ? 'bad' : 'ok'), text: missed.length ? `✗ misses ${missed.length}` : '✓ safe' }));
    const chips = el('div', { class: 'chips' });
    for (const t of c.failing) chips.append(el('span', { class: 'chip ' + (s.has(t) ? 'caught' : 'missed'), text: (s.has(t) ? '✓ ' : '✗ ') + t.replace(/^t_/, '') }));
    const extra = tests.filter(t => !fail.has(t));
    if (extra.length) chips.append(el('span', { class: 'chip extra', text: `+${extra.length} extra` }));
    box.append(el('div', { class: 'tech' }, head, chips));
  }
}

function techTable() {
  const t = $('tech-table');
  t.append(el('thead', {}, el('tr', {}, ...['Technique', 'Tests rerun (mean)', 'Faulty changes detected', 'Fully safe', 'Failing-test recall'].map(h => el('th', { text: h })))));
  const body = el('tbody');
  for (const s of D.rts.summaries) {
    body.append(el('tr', { class: s.technique === 'hybrid' ? 'rec' : '' }, el('td', { text: LABEL[s.technique] || s.technique }), el('td', { class: 'num', text: pct(s.mean_fraction_selected) }),
      el('td', { class: 'num', text: `${s.faulty_changes_detected}/${s.faulty_changes}` }), el('td', { class: 'num', text: `${s.faulty_changes_fully_safe}/${s.faulty_changes}` }), el('td', { class: 'num', text: pct(s.failing_test_recall) })));
  }
  t.append(body);
  const seeds = D.rts.learned_seed_sensitivity;
  const det = seeds.map(s => s.detected), safe = seeds.map(s => s.safe);
  $('seed-note').textContent = `Learned selector over ${seeds.length} fold seeds: detected ${Math.min(...det)}–${Math.max(...det)}, fully safe ${Math.min(...safe)}–${Math.max(...safe)} of ${D.rts.faulty_changes}. Trained on ~56 synthetic changes per fold; it never matched the deterministic hybrid here.`;
}

function adequacy() {
  const A = D.adequacy, bars = $('adequacy-bars'), table = $('adequacy-table');
  table.append(el('thead', {}, el('tr', {}, ...['Strategy', 'Oracle', 'Calls', 'Seeds', 'Killed (mean ± sd)', 'Score'].map(h => el('th', { text: h })))));
  const body = el('tbody');
  for (const s of A.strategies) {
    const name = `${s.strategy.replaceAll('_', ' ')} · ${s.budget_calls} calls`;
    const row = el('div', { class: 'bar-row', title: `${s.killed_mean.toFixed(1)} ± ${s.killed_sd.toFixed(1)} of ${s.live_mutants} live changes · oracle: ${s.oracle} · ${s.seeds} seed(s)` });
    const track = el('div', { class: 'bar-track' }, el('div', { class: 'bar-fill', style: `width:${100 * s.mutation_score_mean}%` }));
    if (s.killed_sd > 0) { const lo = (s.killed_mean - s.killed_sd) / s.live_mutants, hi = Math.min(1, (s.killed_mean + s.killed_sd) / s.live_mutants); track.append(el('div', { class: 'bar-sd', style: `left:${100 * lo}%;width:${100 * (hi - lo)}%` })); }
    row.append(el('span', { text: name }), track, el('span', { class: 'val', text: `${pct(s.mutation_score_mean)}${s.oracle === 'reference' ? '' : ' (no oracle)'}` }));
    bars.append(row);
    body.append(el('tr', {}, el('td', { text: s.strategy }), el('td', { text: s.oracle }), el('td', { class: 'num', text: s.budget_calls }), el('td', { class: 'num', text: s.seeds }), el('td', { class: 'num', text: `${s.killed_mean.toFixed(1)} ± ${s.killed_sd.toFixed(1)} / ${s.live_mutants}` }), el('td', { class: 'num', text: pct(s.mutation_score_mean) })));
  }
  table.append(body);
  const box = $('suggestions');
  for (const s of A.suite_survivor_suggestions) {
    const d = el('div', { class: 'sug' }, el('code', { text: s.edit }), el('br'), el('b', { text: s.status }));
    if (s.suggested_test_input) d.append(el('div', { class: 'small', text: `Suggested pipeline test: ${JSON.stringify(s.suggested_test_input)} → requirements say ${s.expected_by_requirements}, changed code returns ${s.observed_on_changed_code}` }));
    if (s.suggested_unit_test) d.append(el('div', { class: 'small', text: `Suggested ${s.suggested_unit_test.abi} test: ${JSON.stringify(s.suggested_unit_test.input)} → expected ${s.suggested_unit_test.expected_reason_code ?? s.suggested_unit_test.expected}, observed ${s.suggested_unit_test.observed_reason_code ?? s.suggested_unit_test.observed}` }));
    box.append(d);
  }
}

function assistant() {
  const A = D.assistant, cats = A.categories;
  const llm = A.llm_backed_run.status;
  $('assistant-note').textContent = `${A.cases} cases in ${cats.length} categories. Reference assistant plus ${A.variants_total} variants that each inject one known failure; ${A.variants_detected}/${A.variants_total} variants are caught. LLM-backed run: ${llm === 'RUN' ? 'see results' : 'not run (no model credentials configured) — no LLM score is claimed'}.`;
  const t = $('matrix');
  t.append(el('thead', {}, el('tr', {}, el('th', { text: 'Assistant' }), el('th', { text: 'Total' }), ...cats.map(c => el('th', { text: c.replaceAll('_', ' ') })))));
  const body = el('tbody');
  for (const a of A.assistants) {
    const tr = el('tr', {}, el('td', { text: a.assistant + (a.is_reference ? ' (reference)' : '') }), el('td', { class: 'num', text: `${a.passed}/${a.total}` }));
    for (const c of cats) { const s = a.by_category[c]; const bad = s.passed < s.total; tr.append(el('td', { class: 'cell' + (bad ? ' fail' : ''), text: `${bad ? '✗ ' : ''}${s.passed}/${s.total}` })); }
    tr.addEventListener('click', () => { const r = $('reasons'); r.hidden = false; r.textContent = a.failures.length ? `${a.assistant}:\n` + a.failures.map(f => `  ${f.case}: ${f.reasons.join('; ')}`).join('\n') : `${a.assistant}: all cases pass`; });
    body.append(tr);
  }
  t.append(body);
}

function limits() {
  const ul = $('limit-list');
  for (const l of [...D.rts.limits, ...D.adequacy.limits, ...D.assistant.limits]) ul.append(el('li', { text: l }));
}

main().catch(e => { $('error').hidden = false; $('error').textContent = 'Could not load results: ' + e.message; });
