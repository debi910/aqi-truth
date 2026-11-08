// AQI Truth front end. Live mode talks to the FastAPI server; snapshot mode reads JSON exported from the same Db2 run.
const $ = s => document.querySelector(s);
const PARAMS = ["pm25","pm10","no2","so2","o3","co"];
const LABEL = {pm25:"PM2.5",pm10:"PM10",no2:"NO₂",so2:"SO₂",o3:"O₃",co:"CO",ALL:"all"};
let LIVE = true, STATIONS = [];
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const cat = a => a == null ? "" : a <= 50 ? "Good" : a <= 100 ? "Satisfactory" : a <= 200 ? "Moderate" : a <= 300 ? "Poor" : a <= 400 ? "Very Poor" : "Severe";

async function get(path, snap) {
  if (LIVE) { const r = await fetch(path); if (!r.ok) throw new Error((await r.json()).detail || r.status); return r.json(); }
  const r = await fetch(snap); if (!r.ok) throw new Error("not in snapshot"); return r.json();
}

async function init() {
  try { const r = await fetch("/api/stats"); if (!r.ok) throw 0; LIVE = true; }
  catch { LIVE = false; }
  if (!LIVE) {
    const m = $("#mode"); m.hidden = false;
    m.textContent = "Snapshot mode: a read-only export of the real Db2 audit run. Run it locally with Db2 for every day and the question box.";
  }
  const [stats, stations, calendar] = await Promise.all([
    get("/api/stats", "data/stats.json"), get("/api/stations", "data/stations.json"), get("/api/calendar", "data/calendar.json")]);
  STATIONS = stations;
  const short = s => s.name.split(",")[0];
  const dup = {}; for (const st of stations) dup[short(st)] = (dup[short(st)] || 0) + 1;
  for (const st of stations) st.label = dup[short(st)] > 1 ? `${short(st)} (${st.operator || "?"})` : short(st);
  $("#stats").innerHTML = `
    <div class="stat hot"><b>${stats.shown_anyway}</b><span>station-days where CPCB rules give no AQI but a plain average still shows one</span></div>
    <div class="stat"><b>${stats.shown_anyway_very_poor}</b><span>of those would have been shown as Very Poor or Severe</span></div>
    <div class="stat"><b>${stats.suspect}</b><span>days computed only after excluding impossible, stuck or jumping readings</span></div>
    <div class="stat"><b>${(stats.readings/1e6).toFixed(2)}M</b><span>15-minute readings from ${stations.length} Delhi stations, audited in Db2</span></div>`;
  $("#station").innerHTML = stations.map(s => `<option value="${s.id}">${esc(s.name)}</option>`).join("");
  $("#station").value = 11603;
  const quick = [["Chandni Chowk, 23 Oct", 11603, "2025-10-23"], ["Diwali night, ITO", 5613, "2025-10-21"],
                 ["Chandni Chowk, 27 Oct (zeros)", 11603, "2025-10-27"], ["Anand Vihar, 1 Nov", 235, "2025-11-01"]];
  $("#quick").innerHTML = quick.map(([t,s,d]) => `<button data-s="${s}" data-d="${d}">${t}</button>`).join("");
  $("#quick").onclick = e => { const b = e.target.closest("button"); if (b) pick(+b.dataset.s, b.dataset.d); };
  $("#station").onchange = $("#day").onchange = () => load();
  drawCalendar(calendar);
  results();
  $("#askform").onsubmit = askQ;
  if (!LIVE) snapshotAsk();
  load();
}

function pick(s, d) { $("#station").value = s; $("#day").value = d; load(); }

async function load() {
  const s = $("#station").value, d = $("#day").value;
  document.querySelectorAll(".d.sel").forEach(x => x.classList.remove("sel"));
  const cell = document.querySelector(`.d[data-s="${s}"][data-d="${d}"]`); if (cell) cell.classList.add("sel");
  $("#verdict").innerHTML = `<div>Loading the audit…</div>`;
  let v;
  try { v = await get(`/api/day?station=${s}&day=${d}`, `data/day/${s}_${d}.json`); }
  catch (e) { $("#verdict").innerHTML = `<div>${LIVE ? esc(e.message) : "This station-day is not in the snapshot. Pick a highlighted button or a red/amber calendar cell."}</div>`; return; }
  const nc = v.status === "NOT_COMPUTABLE";
  $("#verdict").innerHTML = `
    <div class="naive ${nc && v.naive_aqi != null ? "struck" : ""}"><h3>What a plain-average dashboard shows</h3>
      <div class="big">${v.naive_aqi ?? "—"}</div><div class="cat">${cat(v.naive_aqi)}</div>
      <p class="note">Averages every value that arrived, with no coverage or plausibility checks.</p></div>
    <div><h3>What Db2 says · ${esc(v.station)} · ${v.day}</h3>
      ${nc ? `<span class="stamp">NO AQI COMPUTABLE</span>` : `<div class="big">${v.aqi}</div><div class="cat">${cat(v.aqi)} · driven by ${LABEL[v.prominent]||v.prominent} · <span class="stamp ${v.status}" style="font-size:16px">${v.status}</span></div>`}
      <p class="reason">${esc(v.reason)}.</p></div>`;
  let g = `<div></div>` + Array.from({length:24}, (_, h) => `<div class="hdr">${h % 3 ? "" : h}</div>`).join("");
  for (const p of PARAMS) {
    g += `<div class="lab">${LABEL[p]}</div>` + v.grid[p].map((c, h) => c
      ? `<div class="cell ${c.k} ${c.j ? "j" : ""}" title="${LABEL[p]} ${h}:00–${h+1}:00 · ${c.k}${c.v != null ? " · " + c.v : ""}${c.raw != null && c.raw !== c.v ? " (raw " + c.raw + ")" : ""}"></div>`
      : `<div class="cell" title="${LABEL[p]} ${h}:00–${h+1}:00 · nothing arrived"></div>`).join("");
  }
  $("#grid").innerHTML = g;
  const ex = v.explanation;
  $("#explain").innerHTML = ex ? `${esc(ex.text)}<div class="badges">
      <span class="badge">${ex.model.startsWith("template") ? "template (LLM text rejected by checks)" : "IBM " + esc(ex.model)}</span>
      <span class="badge">numbers checked against evidence ✓</span>
      <span class="badge">${ex.vector_agrees ? "Db2 vector search found the same rule ✓" : "vector search disagreed; cited rule used"}</span>
      <span class="badge">rules: ${esc(ex.rules)}</span></div>` : `<span class="note">No explanation stored for this day.</span>`;
  $("#evidence").innerHTML = `<tr><th>Pollutant</th><th>Check</th><th>Observed</th><th>Rule</th></tr>` + v.evidence.map(e =>
    `<tr class="${e.passed ? "" : "fail"}"><td>${LABEL[e.param]||e.param}</td><td>${e.passed ? "✓" : "✗"} ${e.check}</td><td>${esc(String(e.observed ?? "").replace(/(^|[^\d])\.(\d)/g, "$10.$2"))}</td>
     <td>${e.url ? `<a href="${e.url}" target="_blank" rel="noopener" title="${esc(e.source)}">${e.rule}</a>` : e.rule}</td></tr>`).join("");
}

function drawCalendar(cal) {
  const days = []; for (let t = Date.UTC(2025,8,1); t <= Date.UTC(2025,11,31); t += 864e5) days.push(new Date(t).toISOString().slice(0,10));
  const by = {}; for (const c of cal) (by[c.s] ||= {})[c.d] = c;
  $("#cal").innerHTML = STATIONS.map(s => `<div class="calrow"><div class="nm" title="${esc(s.name)}">${esc(s.label)}</div>` +
    days.map(d => { const c = (by[s.id]||{})[d]; return `<div class="d ${c ? (c.st === "V" ? "" : c.st) : "x"}" data-s="${s.id}" data-d="${d}" title="${d}${c ? " · " + c.st + " · audited " + (c.a ?? "—") + " / plain " + (c.n ?? "—") : ""}"></div>`; }).join("") + `</div>`).join("");
  $("#cal").onclick = e => { const d = e.target.closest(".d"); if (d) { pick(+d.dataset.s, d.dataset.d); $("#verdict").scrollIntoView({behavior:"smooth"}); } };
}

let RECORDED = null;
async function snapshotAsk() {
  try { RECORDED = await (await fetch("data/asks.json")).json(); } catch { return; }
  $("#askblock").querySelector(".note").textContent =
    `This static copy has no live Db2 or Granite, so typed questions can't run here. These are real answers recorded from the live system on ${RECORDED.recorded}: Granite wrote the SQL, Db2 ran it as the read-only user. Pick one.`;
  $("#q").placeholder = "Pick a recorded question below (typing needs the Docker version)";
  const box = document.createElement("div"); box.className = "quick"; box.id = "askquick";
  box.innerHTML = RECORDED.answers.map((a, i) => `<button type="button" data-i="${i}">${esc(a.question)}</button>`).join("");
  $("#askform").after(box);
  box.onclick = e => { const b = e.target.closest("button"); if (b) { const a = RECORDED.answers[+b.dataset.i]; $("#q").value = a.question; show(a); } };
}

async function askQ(e) {
  e.preventDefault(); const q = $("#q").value.trim() || $("#q").placeholder;
  if (!LIVE) {
    const a = RECORDED && RECORDED.answers.find(x => x.question.toLowerCase() === q.toLowerCase());
    if (a) return show(a);
    $("#answer").innerHTML = `<p class="note">Typed questions need the live Db2 and Granite (run <code>docker compose up</code>). In this copy, pick one of the recorded questions.</p>`; return;
  }
  $("#answer").innerHTML = `<p class="note">Granite is writing SQL…</p>`;
  let r;
  try { const res = await fetch("/api/ask", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({question:q})}); r = await res.json(); }
  catch { $("#answer").innerHTML = `<p class="note">The question service did not answer. Is the app running?</p>`; return; }
  show(r);
}

function show(r) {
  if (r.refused) { $("#answer").innerHTML = `<div class="refuse"><b>Refused.</b> ${esc(r.why)}</div>${r.sql ? `<div class="sql">${esc(r.sql)}</div>` : ""}`; return; }
  $("#answer").innerHTML = `<div class="sql">${esc(r.sql)}</div><div class="tablewrap"><table><tr>${r.columns.map(c=>`<th>${esc(c)}</th>`).join("")}</tr>${r.rows.map(row=>`<tr>${row.map(c=>`<td>${esc(c)}</td>`).join("")}</tr>`).join("")}</table></div>`;
}

async function results() {
  try { $("#results").innerHTML = await (await fetch("data/results.html")).text(); } catch {}
}
init();
