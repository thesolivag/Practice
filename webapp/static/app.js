(() => {
  const tg = window.Telegram && window.Telegram.WebApp;
  const initData = (tg && tg.initData) || "";
  if (tg) { tg.ready(); tg.expand(); }
  let settings = {};
  let csrfToken = "", authMethod = initData ? "telegram" : "", alertSchema = null, alertSchemaPromise = null;
  let journalRows = [], replayState = null, replayTimer = null, replaySource = null, replayGeneration = 0;

  const $ = (s) => document.querySelector(s);
  const marketLabel = (pair) => (schema?.settings?.find((s) => s.name === "pairs")?.labels?.[pair]) || pair;
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const num = (v) => (v === null || v === undefined || v === "" ? "–" : Number(v).toFixed(Number(v) > 500 ? 2 : Number(v) > 20 ? 3 : 5));  // gold/indices 2, JPY/silver 3, FX 5
  // Times from the API are UTC. Shown in the display_tz setting (else the phone's zone) with a friendly day near
  // now (owner request 2026-10-15): "Today, Thu 15 Oct 10:00", "Yesterday, ...", "Monday, 12 Oct 22:00",
  // "Last week Monday, 5 Oct 22:00"; further away "Mon 28 Sep 22:00" (year added when not this year).
  const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const fmtParts = (d, tz) => new Intl.DateTimeFormat("en-GB", { timeZone: tz, year: "numeric", month: "numeric",
    day: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(d);
  const parts = (d) => {  // wall-clock parts of d in the display zone (unknown zone -> the phone's zone)
    let p;
    try { p = fmtParts(d, settings.display_tz || undefined); } catch (e) { p = fmtParts(d, undefined); }
    const g = (t) => Number(p.find((x) => x.type === t).value);
    return { y: g("year"), m: g("month"), d: g("day"), hh: String(g("hour")).padStart(2, "0"), mm: String(g("minute")).padStart(2, "0") };
  };
  const dayNo = (q) => Date.UTC(q.y, q.m - 1, q.d) / 86400000;  // calendar day number of wall-clock parts
  const dt = (v) => {
    if (!v) return "–";
    const s = String(v).replace(" ", "T");
    const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z");
    if (isNaN(d)) return String(v).slice(0, 16);
    const x = parts(d), n = parts(new Date());
    const dx = dayNo(x), dn = dayNo(n), wd = (k) => (new Date(k * 86400000).getUTCDay() + 6) % 7;  // Monday = 0
    const diff = dx - dn, weeks = Math.floor((dx - wd(dx) - (dn - wd(dn))) / 7);
    const name = DAYS[new Date(dx * 86400000).getUTCDay()];
    const yr = x.y !== n.y ? ` ${x.y}` : "";
    const date = `${x.d} ${MON[x.m - 1]}${yr} ${x.hh}:${x.mm}`;
    if (diff === 0) return `Today, ${name.slice(0, 3)} ${date}`;
    if (diff === -1) return `Yesterday, ${name.slice(0, 3)} ${date}`;
    if (diff === 1) return `Tomorrow, ${name.slice(0, 3)} ${date}`;
    if (weeks === 0) return `${name}, ${date}`;
    if (weeks === -1) return `Last week ${name}, ${date}`;
    if (weeks === 1) return `Next week ${name}, ${date}`;
    return `${name.slice(0, 3)} ${date}`;
  };
  // Which D/W/M candle a stored candle start is, the way a chart labels it: candles open at 17:00 New York, so the
  // D candle that opens Tue 22:00 WAT is Wednesday's (owner 2026-10-15: "it said tap on Tuesday ... I can't see").
  const nyParts = (d) => {
    const p = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", year: "numeric", month: "numeric",
      day: "numeric", hour: "2-digit", hourCycle: "h23" }).formatToParts(d);
    const g = (t) => Number(p.find((x) => x.type === t).value);
    return { y: g("year"), m: g("month"), d: g("day"), h: g("hour") };
  };
  const candleDay = (v, tf) => {
    if (!v) return "–";
    const s = String(v).replace(" ", "T");
    const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z");
    if (isNaN(d)) return String(v).slice(0, 10);
    const q = nyParts(d);
    let k = Date.UTC(q.y, q.m - 1, q.d) / 86400000 + (q.h >= 17 ? 1 : 0);  // trading day number
    const n = nyParts(new Date()), today = Date.UTC(n.y, n.m - 1, n.d) / 86400000 + (n.h >= 17 ? 1 : 0);
    const day = new Date(k * 86400000);
    if (tf === "M") return `${MON[day.getUTCMonth()]} ${day.getUTCFullYear()} (MN1 candle)`;
    if (tf === "W") { k += (8 - day.getUTCDay()) % 7; }  // weekly candle: the Monday it trades from
    const w = new Date(k * 86400000), name = DAYS[w.getUTCDay()];
    const yr = w.getUTCFullYear() !== new Date(today * 86400000).getUTCFullYear() ? ` ${w.getUTCFullYear()}` : "";
    const date = `${w.getUTCDate()} ${MON[w.getUTCMonth()]}${yr}`;
    if (tf === "W") return `week of Mon ${date} (W1 candle)`;
    const wd = (x) => (new Date(x * 86400000).getUTCDay() + 6) % 7, diff = k - today;
    const weeks = Math.floor((k - wd(k) - (today - wd(today))) / 7);
    const rel = diff === 0 ? `Today, ${name.slice(0, 3)}` : diff === -1 ? `Yesterday, ${name.slice(0, 3)}`
      : weeks === 0 ? `${name},` : weeks === -1 ? `Last week ${name},` : name.slice(0, 3);
    return `${rel} ${date} (D1 candle)`;
  };
  // continuation breaks 'level@YYYY-MM-DD HH:MM;...' (candle start, UTC) -> "0.92999 · H4 close Today, Thu 15 Oct 14:00"
  // 'level@time[@n@first]': one candle that cleared n V's (A's) is one break
  const contBreaks = (r) => String(r.cont_breaks || "").split(";").filter((x) => x.includes("@")).map((x) => {
    const [lv, t, n, first] = x.split("@");
    const many = Number(n) > 1 ? ` (cleared ${n}: ${num(first)} → ${num(lv)})` : "";
    if (r.story === "D") {
      const d = new Date(t.replace(" ", "T") + "Z"); d.setUTCHours(d.getUTCHours() + 4);
      return `${num(lv)}${many} · H4 close ${dt(d.toISOString())}`;
    }
    return `${num(lv)}${many} · ${r.story === "W" ? "D1" : "W1"} close ${candleDay(t, r.story === "W" ? "D" : "W")}`;
  });
  const KIND = { A: "A", V: "V", OC: "OC (open-close)", sweep: "sweep of previous candle", align: "alignment swing" };
  const kl = (r) => r.level_kind === "flip" ? `${KIND[r.level_src] || "KL"} · flipped` : (KIND[r.level_kind] || r.level_kind || "");

  const dur = (s) => {
    if (s === null || s === undefined) return "–";
    const a = Math.abs(s);
    const t = a < 120 ? `${Math.round(a)}s` : a < 7200 ? `${Math.round(a / 60)}m` : `${(a / 3600).toFixed(1)}h`;
    return s < 0 ? `-${t}` : t;
  };

  function msg(text, err) {
    const m = $("#msg");
    if (!text) { m.hidden = true; return; }
    m.hidden = false; m.textContent = text; m.className = "msg" + (err ? " err" : "");
  }

  function busyAction(handler) {
    return async function(event) {
      const button = event.submitter || event.target.closest?.("button");
      if (button?.getAttribute("aria-busy") === "true") { event.preventDefault(); return; }
      const disabled = button?.disabled;
      if (button) { button.disabled = true; button.setAttribute("aria-busy", "true"); }
      try { return await handler(event); }
      finally {
        if (button) { button.removeAttribute("aria-busy"); button.disabled = disabled || (button.id === "replay-next" && !!replayState?.finished); }
      }
    };
  }
  function loadingSection(section) {
    const panel = document.createElement("div");
    panel.className = "loading-skeleton"; panel.setAttribute("role", "status");
    panel.innerHTML = '<span class="loading-caption">Loading…</span><div class="skeleton-card"></div><div class="skeleton-card"></div><div class="skeleton-card"></div>';
    section.prepend(panel); section.setAttribute("aria-busy", "true");
    return () => { panel.remove(); if (!section.querySelector(".loading-skeleton")) section.removeAttribute("aria-busy"); };
  }

  async function api(path, opts = {}) {
    const res = await fetch(path, {
      credentials: "same-origin",
      ...opts,
      headers: { "Content-Type": "application/json", "X-Telegram-Init-Data": initData, ...(csrfToken ? {"X-CSRF-Token": csrfToken} : {}), ...(opts.headers || {}) },
    });
    if (!res.ok) {
      let d = res.statusText;
      try { d = (await res.json()).detail || d; } catch (_) {}
      throw new Error(`${res.status}: ${typeof d === "string" ? d : JSON.stringify(d)}`);
    }
    return res.json();
  }

  const field = (k, v) => `<div><span>${esc(k)}</span>${esc(v)}</div>`;
  const empty = (t) => `<div class="empty">${esc(t)}</div>`;

  // ---------------- Bias
  // Standing bias (slk/standing.py): stays after a target, ends on a confirmed opposite story or an invalidation
  function renderState(st) {
    const pf = $("#f-pair").value, sf = $("#f-story").value;
    const rows = (st || []).filter((b) => (!pf || b.pair === pf) && (!sf || b.story === sf));
    $("#bias-state").innerHTML = rows.length ? `
      <div class="card summary">
        <div class="top"><span class="title">Current bias</span><span class="tag">${esc(rows.filter((b) => b.side).length)} pairs/TFs</span></div>
        ${rows.map((b) => `<div class="bias-row"><span><b>${esc(marketLabel(b.pair))}</b> · ${esc(b.chain || b.story)}</span>
          <span class="${esc(b.side || "")}">${esc(b.bias)}</span>
          <span class="muted">${b.side ? `since ${esc((b.pair.startsWith("DV") ? dt(b.since) : candleDay(b.since, "D").replace(" (D1 candle)", "")))}${b.stories > 1 ? ` · ${esc(b.stories)} stories` : ""} · ${esc(b.state)}` : esc(b.state)}</span></div>`).join("")}
        <div class="muted">A bias stays after its target is reached (Kevin: "we are still bearish ... price is not ready to buy yet"). It changes only when a story the other way confirms, or a close back through the level invalidates it.</div>
      </div>` : "";
  }

  async function loadBias() {
    const q = new URLSearchParams({ pair: $("#f-pair").value, story: $("#f-story").value, status: $("#f-status").value });
    const [rows, st] = await Promise.all([api(`/api/bias?${q}`), api("/api/bias/state").catch(() => null)]);
    renderState(st);
    const sel = $("#f-pair");
    const known = new Set([...sel.options].map((o) => o.value));
    const pairs = new Set([...(settings.pairs || "").split(",").filter(Boolean), ...rows.map((r) => r.pair)]);
    [...pairs].sort().forEach((p) => { if (!known.has(p)) sel.add(new Option(marketLabel(p), p)); });
    $("#bias-list").innerHTML = rows.length ? rows.map((r) => `
      <div class="card">
        <div class="top"><span class="title"><span class="${esc(r.side)}">${esc(r.side)}</span> · ${esc(marketLabel(r.pair))} · ${esc(r.chain || r.story)}</span>
          <span>${Number(r.no_trade) ? `<span class="tag notrade" title="${esc(r.no_trade_reason || "")}">NO_TRADE</span> ` : ""}<span class="tag">${esc(r.status)}</span></span></div>
        ${Number(r.no_trade) ? `<div class="muted">No trade: ${esc(r.no_trade_reason || "filter")}</div>` : ""}
        ${(r.trend === "up" || r.trend === "down") && (r.side === "BUY") !== (r.trend === "up") ? `<div class="muted">↩ Pullback: against the ${esc({ D: "D1", W: "W1", M: "MN1" }[r.story] || r.story)} structure (${esc(r.trend === "up" ? "bullish" : "bearish")}), a retracement inside it, not a bias change</div>` : ""}
        <div class="grid">
          ${field("Level", `${num(r.level)} ${kl(r)}`)}${field("Point B", num(r.point_b))}
          ${r.level_candle ? field("KL candle", (r.pair.startsWith("DV") ? dt(r.level_candle) : candleDay(r.level_candle, r.story))) : ""}
          ${field("Target", num(r.target))}${field("Invalid", num(r.invalidation))}
          ${field("Tap candle", (r.pair.startsWith("DV") ? dt(r.tap_time) : candleDay(r.tap_time, r.story)))}${field("Confirm", dt(r.confirm_time))}
          ${field("Rule", r.rule || "standard")}${field("Updated", dt(r.updated_at))}
          ${r.breakout_time ? field("Breakout (open)", dt(r.breakout_time)) : ""}
          ${r.next_day == null ? "" : field("Next Day Rule", Number(r.next_day) ? "✅ next day" : "⚠ same day")}
        </div>${contBreaks(r).length ? `<div class="muted">Continuation breaks (after point B):<br>${contBreaks(r).map(esc).join("<br>")}</div>` : ""}${Number(r.retrace) ? `<div class="muted">⚠ Retrace: closed back beyond point B on the breakout day</div>` : ""}${r.end_reason ? `<div class="muted">Ended: ${esc(r.end_reason)}</div>` : ""}${r.line_end ? `<div class="muted">Story line ended after the target: ${esc((r.pair.startsWith("DV") ? dt(r.line_end) : candleDay(r.line_end, r.story)))} closed back through the level</div>` : (r.status === "TARGET_HIT" ? `<div class="muted">After the target: watching for the next break (continues) or a close back through the level (ends)</div>` : "")}</div>`).join("") : empty("No stories");
  }

  // ---------------- Entries (+ paper results of filled signals: slk.entry.paper_track, not broker trades)
  const OUTCOME = { TP1_HIT: "win", TP2_HIT: "win", SL_HIT: "loss", EXPIRED: "exp", TRIGGERED: "open", CANCELLED: "off", MISSED: "off" };
  const rr = (v) => (v === null || v === undefined || v === "" ? "–" : `${Number(v) > 0 ? "+" : ""}${Number(Number(v).toFixed(2))}R`);
  const rcls = (v) => (v === null || v === undefined ? "" : Number(v) > 0 ? "good" : Number(v) < 0 ? "bad" : "");
  const pct = (v) => (v === null || v === undefined ? "–" : `${v}%`);

  function renderSummary(s) {
    const m = (k, n) => { const x = (s.by_model || {})[k] || {}; return `${n}: ${x.closed || 0} closed · ${x.wins || 0}W/${x.losses || 0}L · ${rr(x.total_r)}`; };
    $("#entries-summary").innerHTML = `
      <div class="card summary">
        <div class="top"><span class="title">KK · ${esc(s.label || "Paper results (signals)")}</span><span class="tag">${esc(s.open || 0)} open</span></div>
        <div class="stats">
          <div><b>${esc(s.closed)}</b><span>closed</span></div>
          <div><b class="good">${esc(s.wins)}</b><span>wins</span></div>
          <div><b class="bad">${esc(s.losses)}</b><span>losses</span></div>
          <div><b>${esc(pct(s.win_pct))}</b><span>win%</span></div>
          <div><b class="${rcls(s.total_r)}">${esc(rr(s.total_r))}</b><span>total R</span></div>
        </div>
        <div class="muted">${esc(m("continuation", "Continuation"))}<br>${esc(m("qmr", "QMR"))}</div>
        <div class="muted">Bot signals tracked on closed H1 candles, not broker trades (those are under Orders). Win = TP1 reached, loss = stop before TP1${s.expired ? `, ${esc(s.expired)} expired` : ""}. R = exit at TP1; holding for TP2: ${esc(rr(s.total_r_tp2))} over ${esc(s.closed_tp2 || 0)} trades.</div>
      </div>`;
    if (s.bishop) {
      const b=s.bishop;
      $("#entries-summary").innerHTML+=`<div class="card summary"><strong>Bishop · Paper results</strong><p>${esc(b.closed)} resolved · ${esc(b.wins)} wins / ${esc(b.losses)} losses · ${esc(rr(b.total_r))}</p><p>${esc(b.open)} open · ${esc(b.unknown)} Unknown</p><p class="muted">Target-exit results, separate from KK's TP1/TP2 results. ${esc(b.cost_note)}. ${esc(b.scope)}. Unknown outcomes are excluded from wins/losses.</p></div>`;
    }
  }

  let entriesGeneration=0;
  async function loadEntries() {
    const generation=++entriesGeneration;
    const q = new URLSearchParams({ status: $("#f-estatus").value, strategy: $("#f-estrategy").value });
    const [rows, summary] = await Promise.all([api(`/api/entries?${q}`), api("/api/entries/summary").catch(() => null)]);
    if (generation!==entriesGeneration)return;
    const bishopStatus=await api('/api/bishop/status').catch(()=>null);
    if (generation!==entriesGeneration)return;
    if (bishopStatus) {
      const markets=(bishopStatus.markets || []).filter(r=>r.pair);
      $("#bishop-status").innerHTML=`<strong>Bishop · Paper</strong><p>${esc(bishopStatus.note || '')}</p><details><summary>${markets.length} markets registered · scan details</summary>${markets.length ? markets.map(r=>`<p>${esc(marketLabel(r.pair))}: ${esc(r.note || 'Waiting for the next scan')}</p>`).join('') : '<p>Activates on the next hourly scan when enabled in Settings → Entry rules.</p>'}</details>`;
    } else $("#bishop-status").textContent='Bishop paper scan status is temporarily unavailable.';
    if (summary) renderSummary(summary); else $("#entries-summary").innerHTML = "";
    const canApprove = settings.auto_trade === "confirm" && settings.kill_switch !== "on";
    $("#entries-list").innerHTML = rows.length ? rows.map((r) => `
      <div class="card">
        <div class="top"><span class="title"><span class="tag">${esc(r.strategy_label || "KK · Paper")}</span> ${esc(marketLabel(r.pair))} ${esc(r.tf || "")} <span class="${esc(r.side)}">${esc(r.side)}</span> ${esc(r.strategy === "bishop" ? r.model.replaceAll("_", " ") : r.model === "qmr" ? "QMR" : "Continuation")}</span>
          <span class="tag ${esc(OUTCOME[r.status] || "")}">${esc(r.status)}</span></div>
        <div class="grid">
          ${field("Entry", num(r.entry))}${field("Stop", num(r.stop))}
          ${r.strategy === "bishop" ? field("Target",num(r.tp2)) : field("TP1",num(r.tp1))+field("TP2",num(r.tp2))}
          ${r.strategy === "bishop" ? "" : field("Bias #",r.bias_id)}${field("Created",dt(r.created_at))}${r.strategy === "bishop" ? "" : field("Alerted",dt(r.alerted_at))}
          ${r.filled_at ? field("Filled", dt(r.filled_at)) : ""}${r.strategy === "bishop" && r.evaluated_at ? field("Paper checked",dt(r.evaluated_at)) : ""}
          ${r.result_r !== null && r.result_r !== undefined ? `<div><span>${r.strategy === "bishop" ? "Paper R (target exit)" : "R (TP1 exit)"}</span><b class="${rcls(r.result_r)}">${esc(rr(r.result_r))}</b></div>` : ""}
          ${r.result_r_tp2 !== null && r.result_r_tp2 !== undefined ? `<div><span>R (TP2 hold)</span><b class="${rcls(r.result_r_tp2)}">${esc(rr(r.result_r_tp2))}</b></div>` : ""}
          ${r.hit_price !== null && r.hit_price !== undefined ? field("Hit price", num(r.hit_price)) : ""}
          ${r.closed_at ? field("Closed", dt(r.closed_at)) : ""}
        </div>
        ${r.strategy === "bishop" ? `<div class="muted">${esc(r.cost_note)} · ${esc(r.note)} · No broker execution</div>` : ""}
        ${OUTCOME[r.status] && r.filled_at ? `<div class="muted">Paper result (signal), not a broker trade</div>` : ""}
        ${r.strategy !== "bishop" && r.status === "PENDING" && canApprove ? `<button class="approve" data-id="${esc(r.id)}">Confirm trade</button>` : ""}
      </div>`).join("") : empty("No entries");
  }

  $("#f-estrategy").addEventListener("change", () => loadEntries().catch(e => msg(e.message,true)));

  async function approve(id, btn) {
    const ok = await new Promise((resolve) =>
      tg && tg.showConfirm ? tg.showConfirm(`Approve entry #${id}? The trader job will place it.`, resolve) : resolve(confirm(`Approve entry #${id}?`)));
    if (!ok) return;
    btn.disabled = true;
    try {
      await api(`/api/entries/${id}/approve`, { method: "POST" });
      if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred("success");
      msg(`Entry #${id} approved`);
      await loadEntries();
    } catch (e) { msg(e.message, true); btn.disabled = false; }
  }

  // ---------------- Orders
  async function loadOrders() {
    const rows = await api("/api/orders");
    $("#orders-list").innerHTML = rows.length ? rows.map((r) => {
      const pnl = r.pnl === null || r.pnl === undefined ? "–" : Number(r.pnl).toFixed(2);
      return `<div class="card">
        <div class="top"><span class="title">#${esc(r.id)} · entry ${esc(r.entry_id)}</span><span class="tag">${esc(r.status)}</span></div>
        <div class="grid">
          ${field("Volume", r.volume)}${field("Position", r.ctrader_position_id ?? "–")}
          ${field("Opened", dt(r.opened_at))}${field("Closed", dt(r.closed_at))}
          <div><span>PnL</span><b class="${r.pnl > 0 ? "good" : r.pnl < 0 ? "bad" : ""}">${esc(pnl)}</b></div>
          ${field("Client id", r.client_order_id)}
        </div></div>`;
    }).join("") : empty("No orders");
  }

  // ---------------- Settings (form built from /api/settings/schema = slk/settings.py)
  let schema = null;
  let settingsDirty = false;
  let settingsSaving = false;
  function settingsFeedback(text, error = false) {
    const el = $("#settings-feedback");
    el.textContent = text;
    el.className = error ? "err" : "";
  }
  const fid = (n) => `s-${n}`;
  const csv = (v) => String(v || "").split(/[,\s;]+/).map((x) => x.trim().toUpperCase()).filter(Boolean);
  const ladder = (v) => Object.fromEntries(String(v || "").split(";").filter((p) => p.includes("="))
    .map((p) => { const [k, tfs] = p.split("="); return [k.trim(), tfs.trim()]; }));

  function renderField(s, v) {
    const id = fid(s.name);
    const label = s.name.replace(/_/g, " ");
    let input;
    if (s.type === "bool") {
      return `<label class="row"><span>${esc(label)}</span><input type="checkbox" id="${id}" class="switch" ${v === "on" ? "checked" : ""}></label>
        <p class="hint">${esc(s.help)}</p>`;
    }
    if (s.type === "choice") {
      input = `<select id="${id}">${s.choices.map((c) => `<option ${c === v ? "selected" : ""}>${esc(c)}</option>`).join("")}</select>`;
    } else if (s.type === "int" || s.type === "float") {
      const step = s.type === "int" ? 1 : s.max <= 5 ? 0.1 : 1;
      input = `<input type="number" id="${id}" value="${esc(v)}" min="${s.min}" max="${s.max}" step="${step}" inputmode="decimal">`;
    } else if (s.type === "multi" || s.type === "pairs") {
      const on = new Set(csv(v));
      const chip = (c) => `<label><input type="checkbox" class="${id}-c" value="${esc(c)}" ${on.has(String(c).toUpperCase()) ? "checked" : ""}> ${esc(s.labels?.[c] || c)}</label>`;
      const groups = [...new Set(s.choices.map((c) => s.groups?.[c] || "Other markets"))].sort();
      const chips = s.groups ? groups.map((g) => {
        const items = s.choices.filter((c) => (s.groups[c] || "Other markets") === g);
        const selected = items.filter((c) => on.has(c)).length;
        return `<details class="market-group" ${selected ? "open" : ""}><summary data-group-label="${esc(g)}">${esc(g)} · ${selected}/${items.length} selected</summary><div class="chips">${items.map(chip).join("")}</div></details>`;
      }).join("") : s.choices.map(chip).join("");
      const extra = s.type === "pairs" ? `<input type="text" id="${id}-x" placeholder="other symbols, comma separated" autocapitalize="characters" value="${esc([...on].filter((x) => !s.choices.map((c) => String(c).toUpperCase()).includes(x)).join(","))}">` : "";
      return `<div class="col"><span>${esc(label)}</span>${s.type === "pairs" ? `<input type="search" class="symbol-search" placeholder="Search broker symbols" aria-label="Search symbols">` : ""}<div class="${s.groups ? "market-groups" : "chips"}">${chips}</div>${extra}</div><p class="hint">${esc(s.help)}</p>`;
    } else if (s.type === "ladder") {
      const l = ladder(v);
      input = ["D", "W", "M"].map((k) => `<label class="row"><span>${k}</span><input type="text" id="${id}-${k}" value="${esc(l[k] || "")}" autocapitalize="characters"></label>`).join("");
      return `<div class="col"><span>${esc(label)}</span>${input}</div><p class="hint">${esc(s.help)}</p>`;
    } else {
      input = `<input type="text" id="${id}" value="${esc(v)}">`;
    }
    return `<label class="row"><span>${esc(label)}</span>${input}</label><p class="hint">${esc(s.help)}</p>`;
  }

  function readField(s) {
    const id = fid(s.name);
    if (s.type === "bool") return $(`#${id}`).checked ? "on" : "off";
    if (s.type === "multi" || s.type === "pairs") {
      const v = [...document.querySelectorAll(`.${id}-c:checked`)].map((c) => c.value);
      if (s.type === "pairs") v.push(...csv($(`#${id}-x`).value));
      return v.join(",");
    }
    if (s.type === "ladder") return ["D", "W", "M"].map((k) => `${k}=${$(`#${id}-${k}`).value.trim()}`).filter((x) => !x.endsWith("=")).join(";");
    return String($(`#${id}`).value).trim();
  }

  async function loadSettings() {
    if (settingsDirty || settingsSaving) return;
    if (!schema) schema = await api("/api/settings/schema");
    settings = await api("/api/settings");
    $("#settings-fields").innerHTML = schema.groups.map((g) => `
      <fieldset class="card form"><legend>${esc(g)}</legend>
        ${schema.settings.filter((s) => s.group === g).map((s) => renderField(s, settings[s.name])).join("")}
      </fieldset>`).join("");
  }

  async function saveSettings(ev) {
    ev.preventDefault();
    if (!schema || settingsSaving) return;
    settingsSaving = true;
    const button = $("#settings-save");
    button.disabled = true;
    button.textContent = "Saving…";
    settingsFeedback("Saving your settings…");
    try {
      const body = Object.fromEntries(schema.settings.map((s) => [s.name, readField(s)]));
      $("#settings-fields").querySelectorAll("input, select").forEach((el) => { el.disabled = true; });
      const saved = await api("/api/settings", { method: "POST", body: JSON.stringify(body) });
      const verified = await api("/api/settings", { cache: "no-store" });
      if (schema.settings.some((s) => verified[s.name] !== saved[s.name])) {
        throw new Error("Could not verify the saved settings. Please try again.");
      }
      settingsDirty = false;
      settingsSaving = false;
      await loadSettings();
      settingsFeedback("Saved ✓ Settings confirmed. The bot uses them from its next run.");
      button.textContent = "Saved ✓";
    } catch (e) {
      settingsDirty = true;
      settingsFeedback(`Save not confirmed: ${e.message}. Your changes are still here; try Save again.`, true);
      button.textContent = "Retry save";
    } finally {
      settingsSaving = false;
      button.disabled = false;
      $("#settings-fields").querySelectorAll("input, select").forEach((el) => { el.disabled = false; });
    }
  }

  // ---------------- Status
  async function loadRuns() {
    const rows = await api("/api/runs");
    $("#runs-list").innerHTML = rows.length ? rows.map((r) => {
      const startText = String(r.started_at);
      const startMs = Date.parse(/[zZ]|[+-]\d\d:?\d\d$/.test(startText) ? startText : startText + "Z");
      const stale = r.ok == null && Number.isFinite(startMs) && Date.now() - startMs > 30 * 60 * 1000;
      const okc = stale ? "bad" : r.ok === null || r.ok === undefined ? "" : r.ok ? "good" : "bad";
      const late = r.delay_s !== null && r.delay_s > 300 ? "late" : "";
      return `<div class="card">
        <div class="top"><span class="title">${esc(r.job)}</span>
          <span class="tag ${okc}">${r.ok === null || r.ok === undefined ? (stale ? "interrupted" : "running") : r.ok ? "ok" : "failed"}</span></div>
        <div class="grid">
          ${field("Planned", dt(r.planned_at))}${field("Started", dt(r.started_at))}
          <div><span>Delay</span><b class="${late}">${esc(dur(r.delay_s))}</b></div>
          ${field("Took", dur(r.duration_s))}
        </div>
        ${r.note ? `<div class="hint" style="margin-top:6px">${esc(r.note)}</div>` : ""}
      </div>`;
    }).join("") : empty("No runs yet");
  }

  async function loadNews() {
    const data = await api("/api/news");
    $("#news-list").innerHTML = `<div class="card"><p>Source: <a href="${esc(data.source_url)}" target="_blank" rel="noopener">${esc(data.source)}</a></p>
      <p>${data.stale ? "Cached calendar: refresh unavailable. " : ""}Updated ${dt(new Date(data.fetched_at * 1000).toISOString())}</p>
      <p>Telegram news alerts: ${data.alerts_enabled ? "on" : "off"}. Times ${esc(data.timezone)}. Scheduled times can change.</p></div>` +
      (data.events.length ? data.events.map((e) => `<div class="card"><div class="top"><strong>${esc(e.currency)} · ${esc(e.impact.toUpperCase())}</strong></div>
        <p>${esc(e.title)}</p><p>${dt(e.time)}</p><p>Forecast: ${esc(e.forecast || "—")} · Previous: ${esc(e.previous || "—")}</p></div>`).join("") :
        `<div class="card">${data.covered ? "No matching events for today in the available calendar." : "Calendar for the current week is not available yet."}</div>`);
  }

  // ---------------- Personal watches, browser pairing, journals and replay
  function feedback(id, text, error = false) {
    const el = $(id); el.textContent = text; el.classList.toggle("bad", error);
  }
  function fillMarkets(select) {
    const market = schema?.settings?.find((s) => s.name === "pairs");
    const old = select.value;
    select.replaceChildren(...(market?.choices || []).map((p) => new Option(market.labels?.[p] || p, p)));
    if ([...select.options].some((o) => o.value === old)) select.value = old;
    else if (settings.pairs) select.value = settings.pairs.split(",")[0];
  }
  const selectedValues = (selector) => [...document.querySelectorAll(`${selector} input:checked`)].map((input) => input.value);
  const confirmationModels = () => alertSchema?.confirmation_models || (alertSchema?.conditions || []).filter((c) => ["breakout", "engulfing", "fourth_man"].includes(c.value));
  function watchDefinition() {
    const confirmation = $("#watch-kind").value === "confirmation", scoped = confirmation && $("#watch-scope").value === "level";
    $("#watch-price-controls").hidden = confirmation;
    $("#watch-confirmation-controls").hidden = !confirmation;
    $("#watch-level-row").hidden = confirmation && !scoped;
    $("#watch-level").required = !confirmation || scoped;
    $("#watch-condition").required = !confirmation;
    const modelNames = selectedValues("#watch-models").map((value) => confirmationModels().find((c) => c.value === value)?.label || value);
    const timeframes = selectedValues("#watch-timeframes");
    const condition = (alertSchema?.price_conditions || alertSchema?.conditions || []).find((c) => c.value === $("#watch-condition").value);
    const repeat = $("#watch-repeat").value === "each" ? "Each new matching event until expiry" : "First matching event only";
    $("#watch-engulfing").disabled = !confirmation;
    if (!confirmation) $("#watch-engulfing").checked = false;
    $("#watch-definition").textContent = confirmation
      ? `${repeat}. Any selected model (${modelNames.join(", ") || "choose at least one"}) on ${timeframes.join(", ") || "choose a timeframe"}, ${scoped ? "at your specified level" : "anywhere on this market"}.${$("#watch-engulfing").checked ? " Also requires the matching lower-timeframe engulfing." : ""}`
      : condition?.description || "Choose a price condition and level. No confirmation model is required.";
  }
  function populateWatchSchema(data) {
    const condition = $("#watch-condition").value, timeframe = $("#watch-tf").value;
    const prices = data.price_conditions || data.conditions.filter((c) => !["breakout", "engulfing", "fourth_man"].includes(c.value));
    $("#watch-condition").replaceChildren(...prices.map((c) => new Option(c.label, c.value)));
    $("#watch-tf").replaceChildren(...data.timeframes.map((tf) => new Option(tf, tf)));
    if (prices.some((c) => c.value === condition)) $("#watch-condition").value = condition;
    if (data.timeframes.includes(timeframe)) $("#watch-tf").value = timeframe;
    const models = data.confirmation_models || data.conditions.filter((c) => ["breakout", "engulfing", "fourth_man"].includes(c.value));
    $("#watch-models").innerHTML = models.map((c) => `<label><input type="checkbox" value="${esc(c.value)}" checked> ${esc(c.label)}</label>`).join("");
    const tfs = data.confirmation_timeframes || data.timeframes;
    $("#watch-timeframes").innerHTML = tfs.map((tf, i) => `<label><input type="checkbox" value="${esc(tf)}" ${(tfs.includes("H1") ? tf === "H1" : i === 0) ? "checked" : ""}> ${esc(tf)}</label>`).join("");
  }
  function watchSummary(row) {
    const confirmation = row.kind === "confirmation" || (!row.kind && ["breakout", "engulfing", "fourth_man"].includes(row.condition));
    if (!confirmation) return `${(alertSchema.price_conditions || alertSchema.conditions).find((c) => c.value === row.condition)?.label || row.condition} · ${row.timeframe} · ${row.level}`;
    const models = row.models || [row.condition], timeframes = row.timeframes || [row.timeframe];
    const names = models.map((value) => confirmationModels().find((c) => c.value === value)?.label || value);
    return `${names.join(" / ")} · ${timeframes.join(", ")} · ${row.scope === "anywhere" ? "Anywhere on this market" : `At ${row.level}`} · ${row.repeat === "each" ? "Each new matching event" : "First event only"}${row.engulfing ? " · Lower-timeframe engulfing required" : ""}`;
  }
  async function loadWatches() {
    if (!schema) await loadSettings();
    fillMarkets($("#watch-pair"));
    if (!alertSchema) {
      if (!alertSchemaPromise) {
        alertSchemaPromise = api("/api/alerts/schema").then((data) => {
          populateWatchSchema(data); alertSchema = data;
        }).catch((error) => { alertSchemaPromise = null; throw error; });
      }
      await alertSchemaPromise;
    }
    watchDefinition();
    const rows = await api("/api/alerts");
    $("#watch-list").innerHTML = rows.length ? rows.map((r) => `<article class="card">
      <div class="top"><strong>${esc(marketLabel(r.pair))} · ${r.kind === "confirmation" || (!r.kind && ["breakout", "engulfing", "fourth_man"].includes(r.condition)) ? "Confirmation" : "Price"}</strong><span class="tag">${esc(r.status)}</span></div>
      <p>${esc(watchSummary(r))}</p><p>${esc(r.side || "EITHER")}</p>
      <p>${esc(r.note || "")}</p><p class="muted">Expires ${esc(dt(new Date(r.expires_at * 1000).toISOString()))}${r.event_time ? ` · Most recent event ${esc(dt(new Date(r.event_time * 1000).toISOString()))}` : ""}</p>
      ${r.error ? `<p class="bad">${esc(r.error)}</p>` : ""}
      <div class="action-row">${r.event_time ? `<button type="button" data-replay-watch="${Number(r.id)}">Replay event</button>` : ""}
      ${["ACTIVE", "PAUSED"].includes(r.status) && Number(r.expires_at)*1000 > Date.now() ? `<button type="button" data-toggle-watch="${Number(r.id)}" data-watch-action="${r.status === "PAUSED" ? "resume" : "pause"}">${r.status === "PAUSED" ? "Resume" : "Pause"}</button>` : ""}
      ${["ACTIVE", "TRIGGERED", "PAUSED"].includes(r.status) ? `<button type="button" data-cancel-watch="${Number(r.id)}">Cancel watch</button>` : ""}</div></article>`).join("") : empty("No personal alerts yet");
  }
  async function loadDevices() {
    const telegram = authMethod === "telegram";
    $("#create-pairing").disabled = !telegram;
    $("#browser-logout").hidden = telegram;
    if (!telegram) {
      $("#device-list").innerHTML = '<p>Manage connected browsers and generate new codes inside your Telegram Mini App.</p>';
      return;
    }
    const rows = await api("/api/auth/sessions");
    $("#device-list").innerHTML = rows.length ? rows.map((r) => `<article class="card"><div class="top"><strong>${esc(r.name)}</strong><span>${esc(r.client)}</span></div>
      <p class="muted">Connected ${esc(dt(new Date(r.created_at * 1000).toISOString()))} · Expires ${esc(dt(new Date(r.expires_at * 1000).toISOString()))}</p>
      <button type="button" data-revoke-session="${esc(r.id)}">Disconnect</button></article>`).join("") : empty("No connected browsers");
  }
  const sourceKey = (s) => `${s.kind}:${s.id}`;
  async function sources(select) {
    const rows = await api("/api/replay/sources");
    const old = select.value;
    select.replaceChildren(new Option(rows.length ? "Choose an alert" : "No eligible alerts yet", ""), ...rows.map((s) => new Option(s.label || `${marketLabel(s.pair)} · ${s.kind} #${s.id}`, sourceKey(s))));
    if ([...select.options].some((o) => o.value === old)) select.value = old;
    return rows;
  }
  async function loadJournal() {
    const selectedSource = $("#journal-source").value;
    await sources($("#journal-source"));
    $("#journal-source").prepend(new Option("Independent trade note", "manual:"));
    $("#journal-source").value = selectedSource || "manual:";
    fillMarkets($("#journal-pair"));
    journalRows = await api("/api/journal");
    $("#journal-list").innerHTML = journalRows.length ? journalRows.map((r) => `<article class="card"><div class="top"><strong>${esc(marketLabel(r.pair))}</strong><span class="tag">${esc(r.outcome)}</span></div>
      <div class="grid">${field("Entry", num(r.entry))}${field("Stop", num(r.stop))}${field("Target", num(r.target))}${field("Result", rr(r.result_r))}</div>
      <p class="journal-note">${esc(r.notes || "")}</p><div class="action-row"><button type="button" data-edit-journal="${Number(r.id)}">Edit</button><button type="button" data-delete-journal="${Number(r.id)}">Delete note</button></div></article>`).join("") : empty("No journal notes yet");
  }
  function resetJournal() {
    $("#journal-form").reset(); $("#journal-id").value = ""; $("#journal-source").disabled = false;
  }
  let chartSelected = -1, chartHistory = [], chartRedo = [], chartMoving = false;
  let replayViewport=null, replayOlder=[], historyBusy=false, historyBefore=null, historyMore=true, historyUser=false, selectReplayStart=false, replayProvider=null;
  let chartDrawings = [], chartPending = null, chartTransform = null, chartCount = 100, chartOffset = 0;
  const replayZone = () => settings.display_tz || Intl.DateTimeFormat().resolvedOptions().timeZone;
  function localReplayInput(date) {
    const p = new Intl.DateTimeFormat('en-CA', {timeZone: replayZone(), year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(date);
    const v = k => p.find(x => x.type === k).value;
    return `${v('year')}-${v('month')}-${v('day')}T${v('hour')}:${v('minute')}`;
  }
  function replayInstant(value) {
    const wall = Date.parse(value + 'Z'); let epoch = wall;
    for (let i=0;i<4;i++) { const shown=Date.parse(localReplayInput(new Date(epoch))+'Z'); epoch += wall-shown; }
    if (!Number.isFinite(epoch) || localReplayInput(new Date(epoch)) !== value) throw new Error('This local time does not exist in your selected timezone. Choose another time.');
    if ([epoch-3600000,epoch+3600000].some(other=>localReplayInput(new Date(other))===value)) throw new Error('This local time occurs twice during a daylight-saving change. Choose another time.');
    return new Date(epoch);
  }
  function chartFull(on) { $('#replay-panel').classList.toggle('chart-full',on); document.body.classList.toggle('chart-open',on); if(on) requestAnimationFrame(redrawChart); }
  const redrawChart = () => { if(replayState) paintReplayDrawings(); };
  const replaySeconds = {H1:3600,H2:7200,H3:10800,H4:14400,D:86400,W:604800};
  const replayDate = (value) => dt(typeof value === "number" ? new Date(value * 1000).toISOString() : value);
  function replayMode() {
    const price = $("#replay-mode").value === "price";
    $("#replay-alert-controls").hidden = price; $("#replay-price-controls").hidden = !price;
    $("#replay-source").required = !price; $("#replay-pair").required = price; $("#replay-start").required = price;
    $("#replay-reset").textContent = price ? "Back to start" : "Back to alert";
  }
  async function loadReplay() {
    if (!schema) await loadSettings(); fillMarkets($("#replay-pair"));
    if (!$("#replay-start").value) $("#replay-start").value = localReplayInput(new Date(Date.now() - 7 * 86400000));
    $("#replay-start").max = localReplayInput(new Date()).slice(0,13) + ":00";
    $("#replay-zone-label").textContent = `Start date and time (${replayZone()})`;
    replayMode(); if ($("#replay-mode").value === "alert") await sources($("#replay-source"));
  }
  function stopReplay() {
    if (replayTimer) clearInterval(replayTimer);
    replayTimer = null; $("#replay-play").textContent = "Play";
  }
  function clearReplay(message = "Choose settings and open a replay.") {
    stopReplay(); chartStatus(''); selectReplayStart=false; drawingDrag=null; drawingDragged=false; $('#chart-tool').value='cursor'; replayViewport?.interactions(true); chartTransform=null; replayViewport?.clear(); replayOlder=[]; replayProvider=null; historyBefore=null; historyMore=true; historyUser=false; historyBusy=false; chartFull(false); replayGeneration++; replayState = null; replaySource = null;
    $("#replay-panel").hidden = true;
    $("#replay-canvas").getContext("2d").clearRect(0,0,$("#replay-canvas").width,$("#replay-canvas").height);
    $("#replay-caption").textContent = ""; $("#replay-bar").textContent = ""; $("#replay-markers").textContent = "";
    feedback("#replay-feedback", message);
  }
  function replayRequest() {
    const timeframe = $("#replay-timeframe").value;
    if ($("#replay-mode").value === "price") {
      const value = $("#replay-start").value;
      if (!value || !$("#replay-pair").value) throw new Error("Choose a market and a start date/time in your settings timezone.");
      const start = replayInstant(value); if (!Number.isFinite(start.getTime())) throw new Error("Choose a valid local start date/time.");
      return {mode:"price",pair:$("#replay-pair").value,start:start.toISOString(),timeframe};
    }
    const [kind,id] = $("#replay-source").value.split(":");
    if (!kind || !Number(id)) throw new Error("Choose one of your saved alerts.");
    return {kind,id:Number(id),timeframe};
  }
  async function openReplay(body) {
    chartDrawings = []; chartHistory = []; chartRedo=[]; chartSelected = -1; chartMoving = false; chartPending = null; chartOffset = 0; syncDrawingEditor();
    clearReplay("Loading replay…"); const generation = replayGeneration;
    try {
      const data = await api("/api/replay/open", {method:"POST",body:JSON.stringify(body)});
      if (generation === replayGeneration) { replaySource = body; renderReplay(data); if(data.available) chartFull(true); }
    } catch (e) { if (generation === replayGeneration) feedback("#replay-feedback", e.message, true); }
  }
  function renderReplay(data) {
    if (!data.available) {
      if(replayState){stopReplay();chartStatus(data.message||'More candles are unavailable. Try again shortly.');return;}
      stopReplay(); replayState = null; $("#replay-panel").hidden = true;
      feedback("#replay-feedback", data.message || "Replay candles are queued for the next scanner run."); return;
    }
    if(replayProvider&&data.provider&&replayProvider!==data.provider){stopReplay();chartStatus('The broker feed changed. Reopen replay to avoid mixing prices.');return;}
    replayProvider=data.provider||replayProvider;
    replayState = data; $("#replay-panel").hidden = false;
    feedback("#replay-feedback", `${data.message || "Historical replay. Only revealed, completed candles are shown."}${data.gaps?.length ? ` ${data.gaps.length} data gap(s) remain visible.` : ""}${data.refresh_pending ? " Additional candles are queued for refresh." : ""}`);
    $("#replay-caption").textContent = `${data.mode === "price" ? "Price replay" : "Alert replay"} · ${marketLabel(data.pair)} · ${data.timeframe || "H1"} · Clock ${replayDate(data.clock ?? data.anchor)} (${replayZone()}) · ${data.feed || "closed broker candles"}`;
    const markers = Array.isArray(data.markers) ? data.markers : [];
    $("#replay-markers").textContent = markers.map((m) => `${m.label}: ${m.price}`).join(" · ");
    const clock=Number(data.clock??data.anchor),nominal=replaySeconds[data.timeframe]||3600;
    const merged=new Map([...replayOlder,...(data.bars||[])].filter(b=>Number.isFinite(b.time)&&(b.end||b.time+nominal)<=clock).map(b=>[b.time,b]));
    const bars=[...merged.values()].sort((a,b)=>a.time-b.time);replayOlder=bars;
    $('#chart-timeframe').value=data.timeframe||'H1';
    $('#replay-next').disabled=!!data.finished;$('#replay-play').disabled=!!data.finished;if(data.finished)stopReplay();
    if(!replayViewport){
      replayViewport=new ReplayViewport($('#replay-chart'),$('#replay-canvas'),{format:t=>replayDate(t),tick:(t,type)=>new Intl.DateTimeFormat('en-GB',{timeZone:replayZone(),...(type===0?{year:'numeric'}:type===1?{month:'short',year:'2-digit'}:type===2?{month:'short',day:'numeric'}:{hour:'2-digit',minute:'2-digit',hourCycle:'h23'})}).format(new Date(Number(t)*1000)),inspect:inspectReplayBar,draw:paintReplayDrawings,older:loadOlderReplay,select:selectStartAt});
      const stage=$('#replay-chart-stage');
      ['wheel','pointerdown','touchstart'].forEach(name=>stage.addEventListener(name,()=>{historyUser=true;replayViewport.schedule();},{passive:true}));
      stage.addEventListener('pointermove',()=>replayViewport.schedule(),{passive:true});
    }
    replayViewport.set(bars,`${data.pair}:${data.timeframe}:${replayGeneration}`);
    if(bars.length)inspectReplayBar(bars[bars.length-1]);else $('#replay-bar').textContent='No completed candles at this clock. Step forward or load earlier history.';
    paintReplayDrawings();
  }
  function inspectReplayBar(bar){$('#replay-bar').textContent=`${replayDate(bar.time)} · ${replayZone()} · O ${bar.open} H ${bar.high} L ${bar.low} C ${bar.close}`;}
  function chartStatus(message){const el=$('#replay-chart-status');if(el){el.textContent=message;el.hidden=!message;}}
  async function loadOlderReplay(){
    if(!historyUser||historyBusy||!historyMore||!replayState?.cursor)return;
    historyUser=false;historyBusy=true;const generation=replayGeneration;
    const before=historyBefore??replayViewport?.bars[0]?.time;
    chartStatus('Loading earlier candles…');
    try{
      const result=await api('/api/replay/history',{method:'POST',body:JSON.stringify({cursor:replayState.cursor,before})});
      if(generation!==replayGeneration)return;
      if(result.available&&replayProvider&&result.provider&&replayProvider!==result.provider){chartStatus('Earlier candles use a different broker feed and were not merged.');return;}
      if(result.available){replayOlder.push(...(result.bars||[]));historyBefore=result.before;historyMore=result.has_more!==false;renderReplay(replayState);}
      chartStatus(result.message||(!historyMore?'Oldest available history reached.':''));
    }catch(e){if(generation===replayGeneration)chartStatus(e.message);}
    finally{if(generation===replayGeneration)historyBusy=false;}
  }
  function selectStartAt(time){
    if(!selectReplayStart||!replayState)return;
    const bar=replayViewport.bars.find(b=>b.time===time);if(!bar)return;
    selectReplayStart=false;const pair=replayState.pair,timeframe=replayState.timeframe;
    $('#replay-mode').value='price';$('#replay-pair').value=pair;$('#replay-start').value=localReplayInput(new Date((bar.end||time+(replaySeconds[timeframe]||3600))*1000));replayMode();
    openReplay({mode:'price',pair,timeframe,start:new Date((bar.end||time+(replaySeconds[timeframe]||3600))*1000).toISOString()});
  }
  function paintReplayDrawings(){
    if(!replayViewport||!replayState)return;
    chartTransform=replayViewport.transform();
    const {x,y,w,h,padding}=chartTransform,ctx=$('#replay-canvas').getContext('2d');ctx.clearRect(0,0,$('#replay-canvas').width,$('#replay-canvas').height);
    ctx.save();ctx.beginPath();ctx.rect(0,0,w,h);ctx.clip();ctx.font='12px sans-serif';
    for(const marker of replayState.markers||[]){if(!Number.isFinite(marker.price)||(marker.time&&marker.time>(replayState.clock??replayState.anchor)))continue;ctx.strokeStyle=ctx.fillStyle='#be8b29';ctx.setLineDash([4,4]);ctx.beginPath();ctx.moveTo(0,y(marker.price));ctx.lineTo(w,y(marker.price));ctx.stroke();ctx.fillText(`${marker.label} ${marker.price}`,6,y(marker.price)-5);ctx.setLineDash([]);}
    const event=replayState.event;if(event&&event.time<=(replayState.clock??replayState.anchor)){const ex=x(event.time);if(Number.isFinite(ex)){ctx.strokeStyle=ctx.fillStyle='#367bda';ctx.setLineDash([4,4]);ctx.beginPath();ctx.moveTo(ex,0);ctx.lineTo(ex,h);ctx.stroke();ctx.fillText('Alert',ex+5,16);ctx.setLineDash([]);}}
    for(const [index,drawing] of chartDrawings.entries()) {
      ctx.save(); ctx.lineWidth=index===chartSelected?3:1; ctx.strokeStyle=ctx.fillStyle=index===chartSelected?'#ca8400':'#568ee8';
      if(drawing.kind==='vertical'){ctx.beginPath();ctx.moveTo(x(drawing.time),0);ctx.lineTo(x(drawing.time),h);ctx.stroke();}
      else if(drawing.kind==='fib'){
        const left=Math.min(x(drawing.time),x(drawing.time2)),right=Math.max(x(drawing.time),x(drawing.time2)),hi=Math.max(drawing.price,drawing.price2),lo=Math.min(drawing.price,drawing.price2),mid=(hi+lo)/2;
        ctx.fillStyle='#de565620';ctx.fillRect(left,y(hi),right-left,y(mid)-y(hi));ctx.fillStyle='#20a06b20';ctx.fillRect(left,y(mid),right-left,y(lo)-y(mid));
        ctx.fillStyle='#de5656';ctx.fillText('Premium',left+4,y(hi)+14);ctx.fillStyle='#20a06b';ctx.fillText('Discount',left+4,y(lo)-4);
        for(const level of [0,.236,.382,.5,.618,.705,.786,1]){const price=drawing.price+(drawing.price2-drawing.price)*level;ctx.strokeStyle=ctx.fillStyle=level===.5?'#ca8400':'#568ee8';ctx.beginPath();ctx.moveTo(left,y(price));ctx.lineTo(right,y(price));ctx.stroke();ctx.fillText(`${level===.5?'50% equilibrium':(level*100).toFixed(1)+'%'} · ${price.toFixed(5)}`,left+4,y(price)-4);}
      }
      else if(drawing.kind==='trend') {ctx.beginPath();ctx.moveTo(x(drawing.time),y(drawing.price));ctx.lineTo(x(drawing.time2),y(drawing.price2));ctx.stroke();}
      else if(drawing.kind==='rectangle') {const left=Math.min(x(drawing.time),x(drawing.time2)),top=Math.min(y(drawing.price),y(drawing.price2)),width=Math.abs(x(drawing.time2)-x(drawing.time)),height=Math.abs(y(drawing.price2)-y(drawing.price));ctx.strokeRect(left,top,width,height);ctx.fillStyle='#568ee822';ctx.fillRect(left,top,width,height);}
      else if(drawing.kind==='text') {ctx.fillText(drawing.text,x(drawing.time),y(drawing.price));if(index===chartSelected)ctx.strokeRect(x(drawing.time)-3,y(drawing.price)-17,ctx.measureText(drawing.text).width+6,22);}
      else {
      const line = (price,color,label) => { ctx.strokeStyle=ctx.fillStyle=color;ctx.beginPath();ctx.moveTo(padding,y(price));ctx.lineTo(w-padding,y(price));ctx.stroke();ctx.fillText(label+' '+price.toFixed(5),padding+8,y(price)-5); };
      if(drawing.kind==='line') line(drawing.price,'#568ee8','Level');
      else { const left=x(drawing.time),right=x(drawing.time2); ctx.fillStyle='#20a06b33';ctx.fillRect(left,Math.min(y(drawing.entry),y(drawing.target)),right-left,Math.abs(y(drawing.entry)-y(drawing.target)));ctx.fillStyle='#de565633';ctx.fillRect(left,Math.min(y(drawing.entry),y(drawing.stop)),right-left,Math.abs(y(drawing.entry)-y(drawing.stop)));line(drawing.entry,'#568ee8','Entry');line(drawing.stop,'#de5656','Stop');line(drawing.target,'#20a06b',`Target ${drawing.ratio}R`); }
      }
      ctx.restore();
    }
    if(chartPending){ctx.fillStyle='#568ee8';ctx.beginPath();ctx.arc(x(chartPending.time),y(chartPending.price),5,0,Math.PI*2);ctx.fill();}
    const selected=chartDrawings[chartSelected];
    if(selected){ctx.fillStyle='#ca8400';for(const point of drawingHandles(selected)){ctx.beginPath();ctx.arc(point.x,point.y,5,0,Math.PI*2);ctx.fill();}}
    ctx.restore();
  }
  let replayStepGeneration = null;
  async function stepReplay() {
    if (!replayState?.cursor || replayState.finished || replayStepGeneration === replayGeneration) return;
    const generation = replayGeneration; replayStepGeneration = generation; const previousClock=replayState.clock;
    chartStatus('Loading next completed candle…');
    try { const data = await api("/api/replay/step",{method:"POST",body:JSON.stringify({cursor:replayState.cursor,count:1})}); if (generation === replayGeneration) {renderReplay(data); if(data.available&&data.clock>previousClock)chartStatus('');else {stopReplay();chartStatus(data.available?'No later completed candle is available yet. Retry shortly or choose another date.':data.message);}} }
    catch (e) { if (generation === replayGeneration) { stopReplay(); chartStatus(e.message); } }
    finally { if (replayStepGeneration === generation) replayStepGeneration = null; }
  }
  function lockScreen() {
    stopReplay(); $("#tabs").hidden = true;
    document.querySelectorAll("main section").forEach((s) => { s.hidden = true; });
    $("#login-panel").hidden = false;
  }
  async function bootstrap() {
    try {
      const session = await api("/api/auth/session");
      csrfToken = session.csrf || ""; authMethod = initData ? "telegram" : session.auth_method;
      $("#login-panel").hidden = true;
      await loadSettings();
      // Start the initial view before enabling navigation. A later bootstrap
      // continuation must not reload a form the user has already begun editing.
      const initialView = show(current);
      $("#tabs").hidden = false;
      await initialView;
    } catch (e) {
      if (!initData) { lockScreen(); feedback("#login-feedback", /^(401|403):/.test(e.message) ? "Connect using a code from your Telegram Mini App." : e.message, !/^(401|403):/.test(e.message)); }
      else { msg(e.message, true); }
    }
  }

  // ---------------- Tabs
  const loaders = { alerts: loadWatches, devices: loadDevices, journal: loadJournal, replay: loadReplay, news: loadNews, bias: loadBias, entries: loadEntries, orders: loadOrders, settings: loadSettings, status: loadRuns };
  let current = "bias";
  async function show(tab) {
    if (tab !== "replay") { stopReplay(); historyBusy=false; historyUser=false; replayGeneration++; }
    current = tab;
    document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === tab));
    document.querySelectorAll("main section").forEach((s) => { s.hidden = s.id !== tab; });
    msg("");
    if ($("#" + tab).getAttribute("aria-busy") === "true") return;
    const done = loadingSection($("#" + tab));
    try { await loaders[tab](); } catch (e) { msg(e.message, true); } finally { done(); }
  }

  document.querySelectorAll("#tabs button").forEach((b) => b.addEventListener("click", () => show(b.dataset.tab)));
  ["#f-pair", "#f-story", "#f-status"].forEach((s) => $(s).addEventListener("change", () => show("bias")));
  $("#f-estatus").addEventListener("change", () => show("entries"));
  $("#entries-list").addEventListener("click", (e) => {
    const b = e.target.closest("button.approve");
    if (b) busyAction(() => approve(b.dataset.id, b))(e);
  });
  $("#settings-form").addEventListener("submit", busyAction(saveSettings));
  $("#settings-fields").addEventListener("input", (ev) => {
    if (ev.target.classList.contains("symbol-search")) {
      const query = ev.target.value.trim().toUpperCase();
      ev.target.parentElement.querySelectorAll(".chips label").forEach((label) => {
        label.hidden = !label.textContent.toUpperCase().includes(query);
      });
      ev.target.parentElement.querySelectorAll(".market-group").forEach((group) => {
        group.hidden = ![...group.querySelectorAll("label")].some((label) => !label.hidden);
        if (query && !group.hidden) group.open = true;
      });
      return;
    }
    const group = ev.target.closest(".market-group");
    if (group) {
      const summary = group.querySelector("summary");
      summary.textContent = `${summary.dataset.groupLabel} · ${group.querySelectorAll("input:checked").length}/${group.querySelectorAll("input").length} selected`;
    }
    settingsDirty = true;
    settingsFeedback("Unsaved changes — tap Save settings to apply.");
    $("#settings-save").textContent = "Save settings";
  });

  $("#send-eligible").addEventListener("click", busyAction(async () => {
    const button = $("#send-eligible"), feedback = $("#eligible-feedback");
    button.disabled = true;
    feedback.textContent = "Sending…";
    try {
      const result = await api("/api/bias/send-eligible", {method: "POST"});
      feedback.textContent = `Sent to your Telegram: ${result.count} eligible biases. Latest completed scan; bias only.`;
    } catch (e) { feedback.textContent = e.message; }
    finally { button.disabled = false; }
  }));
  $("#browser-login-form").addEventListener("submit", busyAction(async (event) => {
    event.preventDefault(); const button = event.submitter; button.disabled = true;
    feedback("#login-feedback", "Connecting…");
    try {
      const result = await api("/api/auth/redeem", {method: "POST", body: JSON.stringify({code: $("#browser-login-code").value.trim(), client: "browser", name: $("#browser-login-name").value.trim()})});
      $("#browser-login-code").value = ""; window.location.reload();
    } catch (e) { feedback("#login-feedback", e.message, true); }
    finally { button.disabled = false; }
  }));
  $("#create-pairing").addEventListener("click", busyAction(async () => {
    const button = $("#create-pairing"); button.disabled = true;
    try {
      const result = await api("/api/auth/pair-code", {method: "POST", body: JSON.stringify({client: $("#pairing-kind").value})});
      $("#pairing-code").textContent = result.code; $("#pairing-code").hidden = false;
      feedback("#pairing-feedback", `Single-use code expires ${dt(new Date(result.expires_at * 1000).toISOString())}.`);
    } catch (e) { feedback("#pairing-feedback", e.message, true); }
    finally { button.disabled = false; }
  }));
  $("#device-list").addEventListener("click", busyAction(async (event) => {
    const button = event.target.closest("[data-revoke-session]"); if (!button) return;
    button.disabled = true;
    try { await api(`/api/auth/sessions/${encodeURIComponent(button.dataset.revokeSession)}`, {method: "DELETE"}); await loadDevices(); }
    catch (e) { feedback("#pairing-feedback", e.message, true); button.disabled = false; }
  }));
  $("#browser-logout").addEventListener("click", busyAction(async () => {
    try { await api("/api/auth/logout", {method: "POST"}); window.location.reload(); }
    catch (e) { msg(e.message, true); }
  }));
  ["#watch-condition", "#watch-tf", "#watch-scope", "#watch-repeat", "#watch-engulfing"].forEach((id) => $(id).addEventListener("change", () => {
    if (id === "#watch-scope" && $(id).value === "anywhere") $("#watch-level").value = "";
    watchDefinition();
  }));
  $("#watch-kind").addEventListener("change", () => { if ($("#watch-kind").value === "confirmation") $("#watch-expiry").value = "24"; $("#watch-level").value = ""; $("#watch-engulfing").checked = false; feedback("#watch-feedback", ""); watchDefinition(); });
  $("#watch-pair").addEventListener("change", () => { $("#watch-level").value = ""; $("#watch-note").value = ""; feedback("#watch-feedback", "Market changed. Recheck the alert settings before saving."); });
  $("#watch-any-model").addEventListener("change", () => { $("#watch-models").querySelectorAll("input").forEach((input) => { input.checked = $("#watch-any-model").checked; }); watchDefinition(); });
  $("#watch-models").addEventListener("change", () => { const inputs = [...$("#watch-models").querySelectorAll("input")]; $("#watch-any-model").checked = inputs.length > 0 && inputs.every((input) => input.checked); watchDefinition(); });
  $("#watch-timeframes").addEventListener("change", (event) => { if (selectedValues("#watch-timeframes").length > 6) { event.target.checked = false; feedback("#watch-feedback", "Select up to six timeframes.", true); } watchDefinition(); });
  $("#watch-form").addEventListener("submit", busyAction(async (event) => {
    event.preventDefault(); const button = event.submitter; button.disabled = true;
    try {
      const kind = $("#watch-kind").value;
      const body = {kind, pair: $("#watch-pair").value, side: $("#watch-side").value, expires_hours: Number($("#watch-expiry").value), note: $("#watch-note").value};
      if (kind === "price") Object.assign(body, {condition: $("#watch-condition").value, timeframe: $("#watch-tf").value, level: Number($("#watch-level").value)});
      else {
        const models = selectedValues("#watch-models"), timeframes = selectedValues("#watch-timeframes");
        if (!models.length || !timeframes.length || timeframes.length > 6) throw new Error("Choose at least one model and between one and six timeframes.");
        Object.assign(body, {models, timeframes, scope: $("#watch-scope").value, repeat: $("#watch-repeat").value, engulfing: $("#watch-engulfing").checked});
        if (body.scope === "level") body.level = Number($("#watch-level").value);
      }
      await api("/api/alerts", {method: "POST", body: JSON.stringify(body)});
      feedback("#watch-feedback", `${kind === "price" ? "Price alert" : "Confirmation alert"} saved. Telegram will notify you when its selected condition is confirmed.`); await loadWatches();
    } catch (e) { feedback("#watch-feedback", e.message, true); }
    finally { button.disabled = false; }
  }));
  $("#watch-list").addEventListener("click", busyAction(async (event) => {
    const replayButton = event.target.closest("[data-replay-watch]");
    if (replayButton) {
      replayButton.disabled = true;
      try {
        const rows = await api("/api/replay/sources"), watchId = Number(replayButton.dataset.replayWatch);
        const immutable = rows.filter((row) => row.kind === "watch_event" && Number(row.watch_id) === watchId).sort((a,b) => Number(b.anchor)-Number(a.anchor));
        const source = immutable[0] || rows.find((row) => row.kind === "watch" && Number(row.id) === watchId);
        if (!source) throw new Error("No retained replay event is available for this watch. Its original event has not been replaced with the current market state.");
        clearReplay("Opening the recorded alert event…"); $("#replay-mode").value = "alert"; replayMode();
        await show("replay");
        const key = sourceKey(source);
        if (![...$("#replay-source").options].some((option) => option.value === key)) throw new Error("This replay event is no longer available. Refresh your event history.");
        $("#replay-source").value = key;
        await openReplay({kind:source.kind,id:Number(source.id),timeframe:$("#replay-timeframe").value});
      } catch (e) { feedback(current === "replay" ? "#replay-feedback" : "#watch-feedback",e.message,true); }
      finally { replayButton.disabled = false; }
      return;
    }
    const toggle = event.target.closest("[data-toggle-watch]");
    if (toggle) {
      toggle.disabled = true;
      try {
        await api(`/api/alerts/${Number(toggle.dataset.toggleWatch)}/${toggle.dataset.watchAction}`, {method:"POST"});
        feedback("#watch-feedback", toggle.dataset.watchAction === "pause" ? "Alert paused. Its original expiry still applies." : "Alert resumed. Signals during the pause are skipped.");
        await loadWatches();
      } catch (e) { feedback("#watch-feedback", e.message, true); toggle.disabled = false; }
      return;
    }
    const button = event.target.closest("[data-cancel-watch]"); if (!button) return;
    button.disabled = true;
    try { await api(`/api/alerts/${Number(button.dataset.cancelWatch)}/cancel`, {method: "POST"}); await loadWatches(); }
    catch (e) { feedback("#watch-feedback", e.message, true); button.disabled = false; }
  }));
  $("#journal-reset").addEventListener("click", resetJournal);
  $("#journal-form").addEventListener("submit", busyAction(async (event) => {
    event.preventDefault(); const button = event.submitter; button.disabled = true;
    const id = $("#journal-id").value, [source_kind, source_id] = $("#journal-source").value.split(":");
    const number = (field) => $(field).value === "" ? null : Number($(field).value);
    const body = {source_kind, source_id: source_kind === "manual" ? null : Number(source_id), pair: $("#journal-pair").value, side: $("#journal-side").value, entry: number("#journal-entry"), stop: number("#journal-stop"), target: number("#journal-target"), result_r: number("#journal-result"), outcome: $("#journal-outcome").value, notes: $("#journal-notes").value};
    if (id) { delete body.source_kind; delete body.source_id; delete body.pair; }
    try {
      await api(id ? `/api/journal/${Number(id)}` : "/api/journal", {method: id ? "PUT" : "POST", body: JSON.stringify(body)});
      feedback("#journal-feedback", "Journal note saved."); resetJournal(); await loadJournal();
    } catch (e) { feedback("#journal-feedback", e.message, true); }
    finally { button.disabled = false; }
  }));
  $("#journal-list").addEventListener("click", busyAction(async (event) => {
    const edit = event.target.closest("[data-edit-journal]"), remove = event.target.closest("[data-delete-journal]");
    if (edit) {
      const row = journalRows.find((r) => Number(r.id) === Number(edit.dataset.editJournal)); if (!row) return;
      $("#journal-id").value = row.id;
      const key = row.source_kind === "manual" ? "manual:" : `${row.source_kind}:${row.source_id}`, select = $("#journal-source");
      if (![...select.options].some((o) => o.value === key)) select.add(new Option(`${marketLabel(row.pair)} · ${row.source_kind} #${row.source_id}`, key));
      select.value = key; select.disabled = true;
      $("#journal-pair").value = row.pair; $("#journal-side").value = row.side || "BUY";
      [["entry",row.entry],["stop",row.stop],["target",row.target],["result",row.result_r],["outcome",row.outcome],["notes",row.notes]].forEach(([k,v]) => { $(`#journal-${k}`).value = v ?? ""; });
      $("#journal-form").scrollIntoView({behavior: "smooth"});
    }
    if (remove && window.confirm("Delete this journal note?")) {
      try { await api(`/api/journal/${Number(remove.dataset.deleteJournal)}`, {method: "DELETE"}); await loadJournal(); }
      catch (e) { feedback("#journal-feedback", e.message, true); }
    }
  }));
  $("#replay-mode").addEventListener("change", () => { clearReplay(); replayMode(); if ($("#replay-mode").value === "alert") sources($("#replay-source")).catch((e) => feedback("#replay-feedback",e.message,true)); });
  ["#replay-source","#replay-pair","#replay-start"].forEach((id) => $(id).addEventListener("change", () => clearReplay("Selection changed. Open a new replay.")));
  $("#replay-timeframe").addEventListener("change", async () => {
    const previous = replayState, source = replaySource, wasFull = $("#replay-panel").classList.contains("chart-full");
    stopReplay();historyBusy=false;historyUser=false;replayGeneration++;const generation=replayGeneration;chartStatus('Loading timeframe at the same replay clock…');
    if (!previous?.cursor) { feedback("#replay-feedback","Choose settings and open a replay."); return; }
    try {
      const data = await api("/api/replay/timeframe",{method:"POST",body:JSON.stringify({cursor:previous.cursor,timeframe:$("#replay-timeframe").value})});
      if (generation === replayGeneration) {
        if(replayProvider&&data.provider&&replayProvider!==data.provider){$('#chart-timeframe').value=previous.timeframe;$('#replay-timeframe').value=previous.timeframe;chartStatus('The broker feed changed. Reopen replay to avoid mixing prices.');return;}
        if(!data.available){$('#chart-timeframe').value=previous.timeframe;$('#replay-timeframe').value=previous.timeframe;chartStatus(data.message||'This timeframe is unavailable.');return;}
        replayOlder=[];historyBefore=null;historyMore=true;historyUser=false;historyBusy=false;replayProvider=null;
        replaySource = source; renderReplay(data); chartFull(wasFull);chartStatus('');
      }
    } catch (e) { if (generation === replayGeneration){$('#chart-timeframe').value=previous.timeframe;$('#replay-timeframe').value=previous.timeframe;chartStatus(e.message);} }
  });
  $("#replay-form").addEventListener("submit", busyAction(async (event) => {
    event.preventDefault(); try { await openReplay(replayRequest()); } catch (e) { feedback("#replay-feedback",e.message,true); }
  }));
  $("#replay-reset").addEventListener("click", busyAction(async () => {
    if (replaySource) await openReplay({...replaySource,timeframe:$("#replay-timeframe").value});
  }));
  $("#replay-next").addEventListener("click", busyAction(stepReplay));
  $("#replay-play").addEventListener("click", () => {
    if (replayTimer) stopReplay();
    else { $("#replay-play").textContent = "Pause"; replayTimer = setInterval(stepReplay, Number($("#replay-speed").value)); }
  });
  $('#replay-close').addEventListener('click',()=>{stopReplay();chartFull(false);});
  $('#replay-expand').addEventListener('click',()=>chartFull(true));
  $('#chart-timeframe').addEventListener('change',()=>{ $('#replay-timeframe').value=$('#chart-timeframe').value; $('#replay-timeframe').dispatchEvent(new Event('change')); });
  $('#replay-speed').addEventListener('change',()=>{if(replayTimer){stopReplay();$('#replay-play').click();}});
  const drawingNames = {vertical:'Vertical line',fib:'Fibonacci / premium–discount',line:'Horizontal line',trend:'Trend line',rectangle:'Rectangle',text:'Text',long:'Long risk/reward',short:'Short risk/reward'};
  function saveDrawingHistory() {chartRedo=[];chartHistory.push(JSON.stringify(chartDrawings));if(chartHistory.length>50)chartHistory.shift();}
  function syncDrawingEditor() {
    const select=$('#drawing-select');select.replaceChildren(new Option('None',''),...chartDrawings.map((d,i)=>new Option(`${i+1}. ${drawingNames[d.kind]}${d.kind==='text'?' · '+d.text:''}`,String(i))));
    const d=chartDrawings[chartSelected];select.value=d?String(chartSelected):'';
    $('#drawing-edit').hidden=!d;$('#drawing-move').disabled=$('#drawing-delete').disabled=!d;
    if(!d)return;
    const two=['trend','rectangle','fib'].includes(d.kind),risk=['long','short'].includes(d.kind),timed=two||d.kind==='text'||d.kind==='vertical';
    $('#drawing-price').value=d.price??d.entry;$('#drawing-second').value=d.price2??d.stop??'';
    $('#drawing-second-label').hidden=!(two||risk);$('#drawing-second').required=two||risk;
    $('#drawing-time-label').hidden=!timed;$('#drawing-time').required=timed;$('#drawing-time').value=timed?localReplayInput(new Date(d.time*1000)):'';
    $('#drawing-end-label').hidden=!two;$('#drawing-end').required=two;$('#drawing-end').value=two?localReplayInput(new Date(d.time2*1000)):'';
    $('#drawing-ratio-label').hidden=!risk;$('#drawing-ratio').required=risk;$('#drawing-ratio').value=d.ratio??2;
    if(d.kind==='text')$('#drawing-text').value=d.text;
  }
  function addedDrawing(d) {saveDrawingHistory();chartDrawings.push(d);chartSelected=chartDrawings.length-1;chartPending=null;$('#chart-tool').value='cursor';replayViewport?.interactions(true);$('#replay-chart-stage').classList.remove('drawing-active');syncDrawingEditor();redrawChart();$('#chart-help').textContent=drawingNames[d.kind]+' added. Drag its handles to adjust, or open Drawing tools to edit/delete.';}
  function drawingPoint(event) {const c=$('#replay-canvas'),b=c.getBoundingClientRect();return {px:(event.clientX-b.left)*c.width/b.width,py:(event.clientY-b.top)*c.height/b.height};}
  function hitDrawing(px,py) {
    const {x,y,w,padding}=chartTransform;
    for(let i=chartDrawings.length-1;i>=0;i--){const d=chartDrawings[i];
      if(d.kind==='vertical'&&Math.abs(px-x(d.time))<14)return i;
      if(d.kind==='line'&&Math.abs(py-y(d.price))<14)return i;
      if(['long','short'].includes(d.kind)&&[d.entry,d.stop,d.target].some(p=>Math.abs(py-y(p))<14))return i;
      if(d.kind==='text'&&px>=x(d.time)-10&&px<=x(d.time)+$('#replay-canvas').getContext('2d').measureText(d.text).width+10&&Math.abs(py-y(d.price))<22)return i;
      if(['trend','rectangle','fib'].includes(d.kind)){const ax=x(d.time),ay=y(d.price),bx=x(d.time2),by=y(d.price2);
        if(['rectangle','fib'].includes(d.kind)&&px>=Math.min(ax,bx)-10&&px<=Math.max(ax,bx)+10&&py>=Math.min(ay,by)-10&&py<=Math.max(ay,by)+10)return i;
        const t=Math.max(0,Math.min(1,((px-ax)*(bx-ax)+(py-ay)*(by-ay))/((bx-ax)**2+(by-ay)**2||1)));
        if(d.kind==='trend'&&Math.hypot(px-ax-t*(bx-ax),py-ay-t*(by-ay))<14)return i;
      }
    }return -1;
  }
  function drawingHandles(d){
    if(!chartTransform)return [];const {x,y,w}=chartTransform;
    if(['long','short'].includes(d.kind))return ['entry','stop','target'].map(field=>({x:x(d.time),y:y(d[field]),field}));
    if(d.kind==='vertical')return [{x:x(d.time),y:chartTransform.h/2,field:'price',time:'time'}];
    if(d.kind==='line')return [{x:w/2,y:y(d.price),field:'price'}];
    const handles=[{x:x(d.time),y:y(d.price),field:'price',time:'time'}];
    if(['trend','rectangle','fib'].includes(d.kind))handles.push({x:x(d.time2),y:y(d.price2),field:'price2',time:'time2'});
    if(d.kind==='rectangle')handles.push({x:x(d.time2),y:y(d.price),field:'price',time:'time2'},{x:x(d.time),y:y(d.price2),field:'price2',time:'time'});
    return handles;
  }
  let drawingDrag=null,drawingDragged=false;
  $('#replay-chart-stage').addEventListener('pointerdown',event=>{
    drawingDragged=false;if(!chartTransform||$('#chart-tool').value!=='cursor'||selectReplayStart||chartMoving)return;
    const {px,py}=drawingPoint(event);if(px<0||py<0||px>chartTransform.w||py>chartTransform.h)return;
    const selected=chartDrawings[chartSelected];const handle=selected&&drawingHandles(selected).find(h=>Math.hypot(h.x-px,h.y-py)<15);
    const index=handle?chartSelected:hitDrawing(px,py);if(index<0)return;
    stopReplay();chartSelected=index;const original={...chartDrawings[index]};
    drawingDrag={index,original,handle,startX:px,startY:py,price:chartTransform.price(py),time:chartTransform.time(px),saved:false};
    replayViewport.interactions(false);event.preventDefault();event.stopImmediatePropagation();event.currentTarget.setPointerCapture(event.pointerId);syncDrawingEditor();redrawChart();
  },true);
  $('#replay-chart-stage').addEventListener('pointermove',event=>{
    if(!drawingDrag)return;event.preventDefault();event.stopImmediatePropagation();
    const {px,py}=drawingPoint(event),drag=drawingDrag;
    if(Math.hypot(px-drag.startX,py-drag.startY)<3&&!drag.saved)return;
    const price=chartTransform.price(py),time=chartTransform.time(px);if(!Number.isFinite(price)||!Number.isFinite(time))return;
    const d={...drag.original};
    if(drag.handle){d[drag.handle.field]=price;if(drag.handle.time)d[drag.handle.time]=time;}
    else{const dp=price-drag.price,delta=time-drag.time;for(const k of ['price','price2','entry','stop','target'])if(d[k]!==undefined)d[k]+=dp;for(const k of ['time','time2'])if(d[k]!==undefined)d[k]+=delta;}
    if(['price','price2','entry','stop','target'].some(k=>d[k]!==undefined&&(!Number.isFinite(d[k])||d[k]<=0)))return;
    if(['long','short'].includes(d.kind)){
      if(d.kind==='long'?(d.stop>=d.entry||d.target<=d.entry):(d.stop<=d.entry||d.target>=d.entry))return;
      d.ratio=Math.round(Math.abs(d.target-d.entry)/Math.abs(d.entry-d.stop)*100)/100;
    }
    if(!drag.saved){saveDrawingHistory();drag.saved=true;}
    drawingDragged=true;chartDrawings[drag.index]=d;paintReplayDrawings();
  },true);
  function endDrawingDrag(event){if(!drawingDrag)return;event.preventDefault();event.stopImmediatePropagation();drawingDrag=null;replayViewport?.interactions(true);syncDrawingEditor();redrawChart();}
  $('#replay-chart-stage').addEventListener('pointerup',endDrawingDrag,true);
  $('#replay-chart-stage').addEventListener('pointercancel',endDrawingDrag,true);
  $('#drawing-select').addEventListener('change',()=>{chartSelected=$('#drawing-select').value===''?-1:Number($('#drawing-select').value);chartMoving=false;chartPending=null;syncDrawingEditor();redrawChart();});
  $('#drawing-move').addEventListener('click',()=>{stopReplay();chartMoving=true;chartPending=null;$('#chart-help').textContent='Tap the new position for the selected drawing’s first point (or entry).';});
  $('#drawing-delete').addEventListener('click',()=>{if(chartSelected<0)return;saveDrawingHistory();chartDrawings.splice(chartSelected,1);chartSelected=-1;chartMoving=false;syncDrawingEditor();redrawChart();});
  $('#drawing-edit').addEventListener('submit',event=>{
    event.preventDefault();const old=chartDrawings[chartSelected];if(!old)return;
    const d={...old},p=Number($('#drawing-price').value),p2=Number($('#drawing-second').value);
    try {
      if(!Number.isFinite(p)||p<=0)throw Error('Enter a positive price.');
      if(['long','short'].includes(d.kind)){const ratio=Number($('#drawing-ratio').value);if(!Number.isFinite(p2)||p2<=0||!Number.isFinite(ratio)||ratio<.1||ratio>100||(d.kind==='long'?p2>=p:p2<=p))throw Error('Check entry, stop direction and reward/risk ratio.');Object.assign(d,{entry:p,stop:p2,ratio,target:p+(d.kind==='long'?1:-1)*Math.abs(p-p2)*ratio});if(d.target<=0)throw Error('Target must be positive.');}
      else {d.price=p;if(d.kind!=='line')d.time=replayInstant($('#drawing-time').value).getTime()/1000;
        if(['trend','rectangle','fib'].includes(d.kind)){if(!Number.isFinite(p2)||p2<=0)throw Error('Enter a positive second price.');d.price2=p2;d.time2=replayInstant($('#drawing-end').value).getTime()/1000;}
        if(d.kind==='text'){d.text=$('#drawing-text').value.trim().slice(0,200);if(!d.text)throw Error('Enter note text.');}
      }
      saveDrawingHistory();chartDrawings[chartSelected]=d;chartMoving=false;chartPending=null;syncDrawingEditor();redrawChart();$('#chart-help').textContent='Drawing updated.';
    }catch(e){$('#chart-help').textContent=e.message;}
  });
  $('#chart-tool').addEventListener('change',()=>{stopReplay();replayViewport?.interactions($('#chart-tool').value==='cursor');chartPending=null;chartMoving=false;const kind=$('#chart-tool').value;$('#replay-chart-stage').classList.toggle('drawing-active',kind!=='cursor');if(kind==='text')$('#chart-editor').open=true;else if(kind!=='cursor')$('#chart-tools-panel').open=false;$('#chart-help').textContent={vertical:'Tap the candle/time for the vertical line.',fib:'Tap the swing start, then its end. Upper half is premium; lower half is discount.',line:'Tap the chart at the desired price.',cursor:'Tap a drawing to select it, or use the drawings list.',trend:'Tap the first point, then the second point.',rectangle:'Tap one corner, then the opposite corner.',text:'Enter note text in Drawings and editing, then tap the chart.'}[kind]||'Tap entry, then stop. Target uses your reward/risk ratio.';});
  function placeReplayDrawing(event){
    if(drawingDragged){drawingDragged=false;return;}if(selectReplayStart)return;
    if(!chartTransform||!replayState)return;
    const {px,py}=drawingPoint(event),price=chartTransform.price(py),time=chartTransform.time(px),kind=$('#chart-tool').value;
    if(px<chartTransform.padding||px>chartTransform.w-chartTransform.padding||py<chartTransform.padding||py>chartTransform.h-chartTransform.padding)return;
    if(!Number.isFinite(price)||price<=0)return;
    if(chartMoving&&chartDrawings[chartSelected]){
      const d={...chartDrawings[chartSelected]},dp=price-(d.price??d.entry),dt=time-(d.time??time);
      for(const k of ['price','price2','entry','stop','target'])if(d[k]!==undefined)d[k]+=dp;
      for(const k of ['time','time2'])if(d[k]!==undefined)d[k]+=dt;
      if(['price','price2','entry','stop','target'].some(k=>d[k]!==undefined&&d[k]<=0)){$('#chart-help').textContent='Move would put a price below zero. Choose another position.';return;}
      saveDrawingHistory();chartDrawings[chartSelected]=d;chartMoving=false;syncDrawingEditor();redrawChart();$('#chart-help').textContent='Drawing moved.';return;
    }
    if(kind==='cursor'){chartSelected=hitDrawing(px,py);syncDrawingEditor();redrawChart();$('#chart-help').textContent=chartSelected>=0?'Drawing selected. Use Drawings and editing to move, edit or delete it.':'No drawing selected.';return;}
    if(chartDrawings.length>=50){$('#chart-help').textContent='Drawing limit reached. Undo or clear a drawing.';return;}
    if(kind==='line'){addedDrawing({kind,price});return;}
    if(kind==='vertical'){addedDrawing({kind,price,time});return;}
    if(kind==='text'){const text=$('#drawing-text').value.trim().slice(0,200);if(!text){$('#chart-help').textContent='Enter note text first.';return;}addedDrawing({kind,price,time,text});return;}
    if(chartPending===null){chartPending={price,time};paintReplayDrawings();$('#chart-help').textContent=['trend','rectangle','fib'].includes(kind)?'Now tap the second point.':'Now tap the stop price.';return;}
    if(['trend','rectangle','fib'].includes(kind)){addedDrawing({kind,price:chartPending.price,time:chartPending.time,price2:price,time2:time});$('#chart-help').textContent='Drawing added.';return;}
    const entry=chartPending.price,ratio=Number($('#chart-ratio').value),risk=Math.abs(entry-price);
    if(!risk||ratio<.1||ratio>100||!Number.isFinite(ratio)||(kind==='long'?price>=entry:price<=entry)){$('#chart-help').textContent='Choose a valid ratio and a stop below a long entry or above a short entry.';return;}
    const target=entry+(kind==='long'?1:-1)*risk*ratio;if(target<=0){$('#chart-help').textContent='Target must be positive. Choose a smaller ratio.';return;}
    addedDrawing({kind,entry,stop:price,target,ratio,time:chartPending.time,time2:chartTransform.time(Math.min(chartTransform.w,chartTransform.x(chartPending.time)+120))});$('#chart-help').textContent='Risk/reward added. Drag entry, stop or target handles to adjust.';
  }
  // Capture drawing taps before the chart library consumes touch/click events.
  let placementStart=null,suppressPlacementClick=false;
  const placementStage=$('#replay-chart-stage');
  placementStage.addEventListener('pointerdown',event=>{
    if($('#chart-tool').value==='cursor'&&!chartMoving)return;
    if(!event.isPrimary||event.button>0)return;
    placementStart={x:event.clientX,y:event.clientY,id:event.pointerId};
    event.preventDefault();event.stopImmediatePropagation();placementStage.setPointerCapture(event.pointerId);
  },true);
  placementStage.addEventListener('pointerup',event=>{
    if(!placementStart||placementStart.id!==event.pointerId)return;
    const start=placementStart;placementStart=null;event.preventDefault();event.stopImmediatePropagation();
    suppressPlacementClick=true;setTimeout(()=>{suppressPlacementClick=false;},0);
    if(Math.hypot(event.clientX-start.x,event.clientY-start.y)<15)placeReplayDrawing(event);
  },true);
  placementStage.addEventListener('pointercancel',()=>{placementStart=null;},true);
  placementStage.addEventListener('click',event=>{if(suppressPlacementClick)return;if($('#chart-tool').value==='cursor'&&!chartMoving)placeReplayDrawing(event);});
  $('#chart-undo').addEventListener('click',()=>{chartPending=null;chartMoving=false;if(chartHistory.length){chartRedo.push(JSON.stringify(chartDrawings));chartDrawings=JSON.parse(chartHistory.pop());}chartSelected=-1;syncDrawingEditor();redrawChart();});
  $('#chart-clear').addEventListener('click',()=>{if(chartDrawings.length)saveDrawingHistory();chartPending=null;chartMoving=false;chartDrawings=[];chartSelected=-1;syncDrawingEditor();redrawChart();});
  $('#chart-in').addEventListener('click',()=>replayViewport?.zoom(1/1.5));
  $('#chart-out').addEventListener('click',()=>replayViewport?.zoom(1.5));
  $('#chart-left').addEventListener('click',()=>{historyUser=true;if(!replayViewport?.bars.length)loadOlderReplay();else replayViewport.pan(-1);});
  $('#chart-right').addEventListener('click',()=>replayViewport?.pan(1));
  $('#chart-fit')?.addEventListener('click',()=>replayViewport?.fit());
  $('#chart-head')?.addEventListener('click',()=>replayViewport?.head());
  $('#chart-redo')?.addEventListener('click',()=>{if(chartRedo.length){chartHistory.push(JSON.stringify(chartDrawings));chartDrawings=JSON.parse(chartRedo.pop());chartSelected=-1;syncDrawingEditor();redrawChart();}});
  $('#chart-select-start')?.addEventListener('click',()=>{stopReplay();selectReplayStart=true;$('#chart-tool').value='cursor';replayViewport?.interactions(true);chartStatus('Select a completed candle to start a price replay at its close.');});
  window.addEventListener('resize',()=>requestAnimationFrame(redrawChart));
  document.addEventListener('keydown',event=>{if(event.key==='Escape'){stopReplay();chartFull(false);}if(!replayState||!$('#replay-panel').classList.contains('chart-full')||/INPUT|TEXTAREA|SELECT/.test(event.target.tagName))return;if(event.shiftKey&&event.key==='ArrowRight'){event.preventDefault();stepReplay();}if(event.shiftKey&&event.key==='ArrowDown'){event.preventDefault();$('#replay-play').click();}});
  bootstrap();
})();
