(() => {
  if (document.querySelector("#slk-chart-alerts-host")) return;
  const host = document.createElement("div"); host.id = "slk-chart-alerts-host";
  host.style.cssText = "position:fixed;right:20px;top:100px;z-index:2147483000;max-width:calc(100vw - 24px)";
  const shadow = host.attachShadow({mode: "closed"});
  shadow.innerHTML = `<style>
    :host { color: #f2f5f8; font: 13px/1.4 system-ui,sans-serif; } * { box-sizing: border-box; }
    button,input,select { font: inherit; } button { cursor:pointer; border:0; border-radius:7px; padding:9px 12px; background:#287cc2; color:white; }
    [aria-pressed="true"] { outline:2px solid #a5d8ff; } #market-tabs { display:flex;gap:4px;flex-wrap:wrap; } #market-tabs button { padding:7px; } #pill { box-shadow:0 3px 20px #0006; } #panel { width:300px; max-width:calc(100vw - 24px); max-height:calc(100vh - 40px); overflow:auto; padding:14px; border:1px solid #526070; border-radius:12px; background:#17212b; box-shadow:0 6px 28px #0008; }
    #handle { display:flex; justify-content:space-between; align-items:center; cursor:move; touch-action:none; margin-bottom:12px; } #handle button { padding:3px 8px; background:#334455; }
    label { display:block; margin:10px 0; } input,select { width:100%; padding:7px; margin-top:4px; color:#f2f5f8; background:#263544; border:1px solid #526070; border-radius:6px; } input[type=checkbox] { width:auto; }
    fieldset { border:1px solid #526070; border-radius:6px; margin:10px 0; padding:8px; } #models label,#timeframes label { display:inline-block; margin:5px 7px 5px 0; }
    small { color:#bcc7d2; display:block; } #feedback { white-space:pre-wrap; overflow-wrap:anywhere; } [hidden] { display:none !important; }
  </style><button id="pill">SLK alerts</button><section id="panel" hidden>
    <div id="handle"><strong>SLK personal alerts</strong><button id="close" type="button" aria-label="Collapse">×</button></div>
    <p id="connection"></p><form id="form" hidden>
    <div id="market-tabs" role="group" aria-label="Market category"><button type="button" data-market="all" aria-pressed="true">All</button> <button type="button" data-market="regular" aria-pressed="false">Regular</button> <button type="button" data-market="deriv" aria-pressed="false">Deriv</button> <button type="button" data-market="crypto" aria-pressed="false">Crypto</button></div><label>Market<select id="pair" required><option value="">Choose a market</option></select></label><small id="detection">Choose the broker market explicitly when chart detection is unavailable.</small><button id="follow" type="button">Follow chart</button>
    <label>Alert me about<select id="kind"><option value="price">Price</option><option value="confirmation">Confirmation</option></select></label>
    <div id="price-controls"><label>Price condition<select id="condition" required></select></label><label>Timeframe<select id="timeframe"><option>H1</option><option>H2</option><option>H4</option></select></label></div>
    <div id="confirmation-controls" hidden>
      <fieldset><legend>Models</legend><label><input id="any-model" type="checkbox" checked> Any of these models</label><div id="models"></div></fieldset>
      <fieldset><legend>Timeframes (up to 6)</legend><div id="timeframes"></div></fieldset>
      <label>Where to look<select id="scope"><option value="anywhere">Anywhere on this market</option><option value="level">At a level</option></select></label>
      <label>Notify me<select id="repeat"><option value="once">First matching event</option><option value="each">Each new event until expiry</option></select></label>
      <label><input id="engulfing" type="checkbox"> Also require lower-timeframe engulfing</label>
    </div>
    <label>Direction<select id="side"><option>EITHER</option><option>BUY</option><option>SELL</option></select></label>
    <label id="level-row">Price level<input id="level" type="number" min="0.00000001" step="any" required></label>
    <small id="quote" role="status">Broker price unavailable.</small><button id="refresh-quote" type="button">Refresh price</button><button id="use-price" type="button" disabled>Use price</button><small id="definition"></small>
    <label>Expires<select id="expires"><option value="24">1 day</option><option value="168">1 week</option></select></label>
    <label>Note<input id="note" maxlength="240"></label>
    <small>SLK evaluates its broker feed, which may differ from this chart. Candle conditions require completed candles. Sampled price crossings can miss moves between checks.</small>
    <button id="save" type="submit">Create Telegram alert</button></form><p id="feedback" role="status"></p><section id="watches" hidden><h3>Active alerts</h3><label><input id="all-alerts" type="checkbox"> All my markets</label><button id="refresh-alerts" type="button">Refresh alerts</button><p id="alerts-status" role="status"></p><div id="alert-list"></div></section></section>`;
  document.documentElement.append(host);
  const $ = (id) => shadow.querySelector(id);
  let markets = null, conditions = null, manuallySelected = false;
  let marketTab = "all", quoteGeneration = 0, listGeneration = 0, latestQuote = null, currentMarket = null, levelEdited = false;
  function category(pair) {
    if ((markets.groups?.[pair] || "").toLowerCase().includes("cryptocurr")) return "crypto";
    return pair.startsWith("DV") ? "deriv" : "regular";
  }
  function renderMarkets(selected = "") {
    const filtered = markets.choices.filter(p => marketTab === "all" || category(p) === marketTab);
    $("#pair").replaceChildren(new Option("Choose a market", ""), ...filtered.map(p => new Option(markets.labels?.[p] || `IC Markets · ${p}`,p)));
    $("#pair").value = filtered.includes(selected) ? selected : "";
    shadow.querySelectorAll("[data-market]").forEach(b => b.setAttribute("aria-pressed",String(b.dataset.market === marketTab)));
  }
  function marketChanged() {
    if (currentMarket === $("#pair").value) return;
    currentMarket = $("#pair").value; levelEdited = false;
    refreshQuote(); refreshAlerts();
  }
  async function refreshQuote() {
    const generation = ++quoteGeneration, pair = $("#pair").value;
    latestQuote = null; $("#use-price").disabled = true;
    $("#quote").textContent = pair ? "Loading broker price…" : "Choose a market for its broker price.";
    if (!pair) return;
    try {
      const data = await send({action:"quote",pair});
      if (generation !== quoteGeneration || pair !== $("#pair").value) return;
      if (!data.price || !data.timestamp || !data.fresh) { $("#quote").textContent = data.reason || "Fresh broker price unavailable. Try again later."; return; }
      latestQuote = {...data,pair}; $("#use-price").disabled = false;
      if (!levelEdited && !$("#level-row").hidden && !$("#level").value) $("#level").value = data.price;
      $("#quote").textContent = `${pair}: ${data.price} · Broker sample ${new Date(data.timestamp*1000).toLocaleTimeString()}`;
    } catch (error) { if (generation === quoteGeneration) $("#quote").textContent = `Price unavailable: ${error.message}`; }
  }
  async function refreshAlerts() {
    const generation = ++listGeneration;
    $("#alerts-status").textContent = "Loading alerts…"; $("#alert-list").replaceChildren();
    try {
      const rows = await send({action:"listAlerts"});
      if (generation !== listGeneration) return;
      const active = rows.filter(r => r.status === "TRIGGERED" || (r.status === "ACTIVE" && Number(r.expires_at)*1000 > Date.now()));
      const shown = active.filter(r => $("#all-alerts").checked || r.pair === $("#pair").value);
      $("#alerts-status").textContent = `${shown.length} shown · ${active.length} active across your markets`;
      for (const row of shown) {
        const card = document.createElement("p"), text = document.createElement("span"), stop = document.createElement("button");
        text.textContent = `${row.pair} · ${(row.models?.length ? row.models.join(", ") : row.condition)} · ${(row.timeframes || [row.timeframe]).join(", ")} · ${row.level == null ? "Anywhere" : row.level} · ${row.status}${row.error ? " · "+row.error : ""} `;
        stop.type = "button"; stop.textContent = "Stop"; stop.setAttribute("aria-label",`Stop alert ${row.id}`);
        stop.addEventListener("click", async () => {
          stop.disabled = true;
          try { await send({action:"cancelAlert",id:row.id}); await refreshAlerts(); }
          catch (error) { $("#alerts-status").textContent = error.message; stop.disabled = false; }
        });
        card.append(text,stop); $("#alert-list").append(card);
      }
    } catch (error) { if (generation === listGeneration) $("#alerts-status").textContent = `Alerts unavailable: ${error.message}`; }
  }
  async function send(message) {
    const result = await chrome.runtime.sendMessage(message);
    if (!result?.ok) throw new Error(result?.error || "Extension unavailable. Reload this chart after updating the extension.");
    return result.data;
  }
  function chartTexts() {
    // Read only chart symbol controls; never scan page/account text or chart canvases.
    const selectors = location.hostname.endsWith("deriv.com")
      ? ['[data-testid="dt_chart_symbol_selector"]', '[data-testid="chart-symbol"]', '.cq-symbol-select-btn .cq-symbol', '.cq-symbol-select-btn', '[data-underlying-symbol]']
      : ['[data-name="header-toolbar-symbol-search"]', '[data-name="legend-source-title"]', '[data-symbol-full]', '[data-name="legend-source-item"] [data-symbol]'];
    const texts = [];
    for (const selector of selectors) {
      for (const node of [...document.querySelectorAll(selector)].slice(0, 8)) {
        if (!node.getClientRects().length) continue;
        texts.push(node.getAttribute("data-symbol-full"), node.getAttribute("data-symbol"), node.getAttribute("data-underlying-symbol"), node.textContent);
      }
    }
    texts.push(document.title);
    const url = new URL(location.href);
    texts.push(...['symbol', 'underlying_symbol', 'underlying', 'instrument'].map((key) => url.searchParams.get(key)));
    return texts.filter(Boolean);
  }
  function detect() {
    if (!markets || manuallySelected) return;
    const deriv = location.hostname.endsWith("deriv.com");
    const symbols = markets.choices;
    let candidate = null;
    for (const text of chartTexts()) {
      const value = String(text).trim();
      const raw = (value.includes(":") ? value.split(":").pop() : value).toUpperCase().match(/^[A-Z0-9_]+/)?.[0] || "";
      const normalized = raw.replace(/[^A-Z0-9]/g, "");
      const key = deriv ? `DV${normalized}` : normalized;
      if (symbols.includes(key) && (deriv === key.startsWith("DV"))) { candidate = key; break; }
      if (deriv) {
        const normalizedText = value.toLowerCase().replace(/[^a-z0-9]/g, "");
        const matches = symbols.filter((symbol) => {
          if (!symbol.startsWith("DV")) return false;
          const name = (markets.labels?.[symbol] || "").replace(/^Deriv\s*·\s*/i, "").replace(/\s*\(DV[A-Z0-9]+\)$/, "");
          const normalizedName = name.toLowerCase().replace(/[^a-z0-9]/g, "");
          return normalizedName.length > 5 && normalizedText.startsWith(normalizedName);
        });
        if (matches.length === 1) { candidate = matches[0]; break; }
      }
    }
    if ((candidate || "") !== $("#pair").value) {
      $("#level").value = ""; $("#note").value = "";
      $("#feedback").textContent = "Chart market changed. Review the alert settings for this market.";
    }
    if (candidate) { if (marketTab !== "all" && category(candidate) !== marketTab) { marketTab = category(candidate); renderMarkets(candidate); } $("#pair").value = candidate; $("#detection").textContent = "Following chart market. Confirm the selected broker before saving."; }
    else { $("#pair").value = ""; $("#detection").textContent = "Chart market could not be matched reliably. Choose the broker market yourself."; }
    marketChanged();
  }
  const checked = (id) => [...$(id).querySelectorAll("input:checked")].map((input) => input.value);
  const models = () => conditions?.confirmation_models || (conditions?.conditions || []).filter((c) => ["breakout","engulfing","fourth_man"].includes(c.value));
  function definition() {
    const confirmation = $("#kind").value === "confirmation", scoped = confirmation && $("#scope").value === "level";
    $("#price-controls").hidden = confirmation; $("#confirmation-controls").hidden = !confirmation;
    $("#level-row").hidden = confirmation && !scoped; $("#level").required = !confirmation || scoped; $("#condition").required = !confirmation;
    $("#engulfing").disabled = !confirmation; if (!confirmation) $("#engulfing").checked = false;
    const names = checked("#models").map((value) => models().find((c) => c.value === value)?.label || value);
    const description = (conditions?.price_conditions || conditions?.conditions || []).find((c) => c.value === $("#condition").value)?.description || "Choose a price condition.";
    $("#definition").textContent = confirmation ? `${$("#repeat").value === "each" ? "Each new matching event until expiry" : "First matching event only"}. Any selected model (${names.join(", ") || "choose a model"}) on ${checked("#timeframes").join(", ") || "choose a timeframe"}, ${scoped ? "at the price you specify" : "anywhere on this market"}.${$("#engulfing").checked ? " Lower-timeframe engulfing required." : ""}` : description;
    clampPosition();
  }
  function choices() {
    const prices = conditions.price_conditions || conditions.conditions.filter((c) => !["breakout","engulfing","fourth_man"].includes(c.value));
    $("#condition").replaceChildren(...prices.map((c) => new Option(c.label,c.value)));
    $("#timeframe").replaceChildren(...conditions.timeframes.map((tf) => new Option(tf,tf)));
    for (const model of models()) {
      const label = document.createElement("label"), input = document.createElement("input"); input.type = "checkbox"; input.value = model.value; input.checked = true;
      label.append(input, document.createTextNode(` ${model.label}`)); $("#models").append(label);
    }
    const tfs = conditions.confirmation_timeframes || conditions.timeframes;
    for (const [i,tf] of tfs.entries()) {
      const label = document.createElement("label"), input = document.createElement("input"); input.type = "checkbox"; input.value = tf; input.checked = tfs.includes("H1") ? tf === "H1" : i === 0;
      label.append(input,document.createTextNode(` ${tf}`)); $("#timeframes").append(label);
    }
  }
  let opening = null;
  async function open() {
    if (opening) return opening;
    opening = openPanel();
    try { await opening; } finally { opening = null; }
  }
  async function openPanel() {
    $("#pill").hidden = true; $("#panel").hidden = false; $("#feedback").textContent = "";
    clampPosition();
    try {
      const status = await send({action: "status"});
      if (!status.connected) { $("#watches").hidden = true; $("#form").hidden = true; $("#connection").textContent = "Click the SLK extension icon and enter an extension code from Telegram Mini App → Browsers."; return; }
      if (!markets) {
        const [schema, alertSchema] = await Promise.all([send({action: "schema"}), send({action: "alertsSchema"})]);
        markets = schema.settings.find((f) => f.name === "pairs"); conditions = alertSchema;
        renderMarkets();
        choices();
      }
      $("#connection").textContent = "Connected to your Telegram account."; $("#form").hidden = false;
      $("#watches").hidden = false; detect(); definition(); clampPosition(); refreshQuote(); refreshAlerts();
    } catch (error) { $("#feedback").textContent = error.message; }
  }
  $("#market-tabs").addEventListener("click", event => {
    const tab = event.target.closest("[data-market]"); if (!tab || !markets) return;
    marketTab = tab.dataset.market; manuallySelected = true; renderMarkets($("#pair").value);
    $("#level").value = ""; $("#note").value = ""; marketChanged();
  });
  $("#level").addEventListener("input", () => { levelEdited = true; });
  $("#refresh-quote").addEventListener("click", refreshQuote);
  $("#refresh-alerts").addEventListener("click", refreshAlerts);
  $("#all-alerts").addEventListener("change", refreshAlerts);
  $("#use-price").addEventListener("click", () => {
    if (!latestQuote || latestQuote.pair !== $("#pair").value || Date.now()/1000-latestQuote.timestamp > 120) { refreshQuote(); return; }
    if ($("#level-row").hidden) { $("#scope").value = "level"; definition(); }
    $("#level").value = latestQuote.price;
  });
  setInterval(() => { if (!$("#panel").hidden && !$("#form").hidden) { refreshQuote(); refreshAlerts(); } },60000);
  $("#pill").addEventListener("click", open);
  $("#pill").addEventListener("pointerenter", open);
  $("#pill").addEventListener("focus", open);
  $("#close").addEventListener("click", () => { $("#panel").hidden = true; $("#pill").hidden = false; });
  $("#follow").addEventListener("click", () => { manuallySelected = false; detect(); });
  $("#pair").addEventListener("change", () => { manuallySelected = true; $("#level").value = ""; $("#note").value = ""; $("#feedback").textContent = "Market changed. Review your alert settings."; $("#detection").textContent = "Using your manually selected market."; marketChanged(); });
  ["#condition","#timeframe","#scope","#repeat","#engulfing"].forEach((id) => $(id).addEventListener("change", () => { if (id === "#scope" && $(id).value === "anywhere") $("#level").value = ""; definition(); }));
  $("#kind").addEventListener("change", () => { $("#level").value = ""; $("#engulfing").checked = false; $("#feedback").textContent = ""; definition(); });
  $("#any-model").addEventListener("change", () => { $("#models").querySelectorAll("input").forEach((input) => { input.checked = $("#any-model").checked; }); definition(); });
  $("#models").addEventListener("change", () => { const inputs = [...$("#models").querySelectorAll("input")]; $("#any-model").checked = inputs.length > 0 && inputs.every((input) => input.checked); definition(); });
  $("#timeframes").addEventListener("change", (event) => { if (checked("#timeframes").length > 6) { event.target.checked = false; $("#feedback").textContent = "Choose up to six timeframes."; } definition(); });
  $("#form").addEventListener("submit", async (event) => {
    event.preventDefault(); $("#save").disabled = true;
    try {
      const kind = $("#kind").value;
      const body = {kind,pair:$("#pair").value,side:$("#side").value,expires_hours:Number($("#expires").value),note:$("#note").value};
      if (kind === "price") Object.assign(body,{condition:$("#condition").value,timeframe:$("#timeframe").value,level:Number($("#level").value)});
      else {
        const selectedModels = checked("#models"), timeframes = checked("#timeframes");
        if (!selectedModels.length || !timeframes.length || timeframes.length > 6) throw new Error("Choose at least one model and between one and six timeframes.");
        Object.assign(body,{models:selectedModels,timeframes,scope:$("#scope").value,repeat:$("#repeat").value,engulfing:$("#engulfing").checked});
        if (body.scope === "level") body.level = Number($("#level").value);
      }
      await send({action:"createAlert",body});
      $("#feedback").textContent = `${kind === "price" ? "Price" : "Confirmation"} alert saved. View or stop it in Active alerts below.`;
      refreshAlerts();
    } catch (error) { $("#feedback").textContent = error.message; }
    finally { $("#save").disabled = false; }
  });
  function clampPosition() {
    const rect = host.getBoundingClientRect();
    host.style.right = "auto";
    host.style.left = `${Math.max(0, Math.min(window.innerWidth - host.offsetWidth, rect.left))}px`;
    host.style.top = `${Math.max(0, Math.min(window.innerHeight - host.offsetHeight, rect.top))}px`;
  }
  window.addEventListener("resize", clampPosition);
  let drag = null;
  $("#handle").addEventListener("pointerdown", (event) => {
    if (event.target.closest("button")) return;
    const rect = host.getBoundingClientRect(); drag = {x: event.clientX - rect.left, y: event.clientY - rect.top};
    $("#handle").setPointerCapture(event.pointerId);
  });
  $("#handle").addEventListener("pointermove", (event) => {
    if (!drag) return;
    host.style.right = "auto";
    host.style.left = `${Math.max(0, Math.min(window.innerWidth - host.offsetWidth, event.clientX - drag.x))}px`;
    host.style.top = `${Math.max(0, Math.min(window.innerHeight - host.offsetHeight, event.clientY - drag.y))}px`;
  });
  $("#handle").addEventListener("pointerup", () => { drag = null; });
  $("#handle").addEventListener("pointercancel", () => { drag = null; });
  let detectionQueued = false;
  const observer = new MutationObserver(() => {
    if (detectionQueued || $("#panel").hidden) return;
    detectionQueued = true;
    setTimeout(() => { detectionQueued = false; detect(); }, 150);
  });
  observer.observe(document.documentElement, {subtree:true, childList:true, characterData:true, attributes:true, attributeFilter:["data-symbol", "data-symbol-full", "data-underlying-symbol"]});
  setInterval(() => { if (!$("#panel").hidden) detect(); }, 1500);
})();
