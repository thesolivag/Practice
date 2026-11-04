const API = "https://slk-backtest-viewer.onrender.com";
chrome.storage.local.setAccessLevel({accessLevel: "TRUSTED_CONTEXTS"});
const routes = {
  schema: ["/api/settings/schema", "GET"],
  listAlerts: ["/api/alerts", "GET"],
  alertsSchema: ["/api/alerts/schema", "GET"],
  createAlert: ["/api/alerts", "POST"],
};
async function handle(message, sender) {
  if (sender.id !== chrome.runtime.id) throw new Error("Unknown extension sender");
  const fromPopup = !sender.tab;
  if (message.action === "pair") {
    if (!fromPopup) throw new Error("Connect using the extension popup");
    const result = await request("/api/auth/redeem", "POST", {code: String(message.code || ""), client: "extension", name: "SLK Chrome extension"}, false);
    if (!result.token) throw new Error("No extension session returned");
    await chrome.storage.local.set({slkToken: result.token, slkExpires: result.expires_at});
    return {connected: true};
  }
  if (message.action === "status") {
    const saved = await chrome.storage.local.get(["slkToken", "slkExpires"]);
    return {connected: !!saved.slkToken && Number(saved.slkExpires) * 1000 > Date.now(), expires_at: saved.slkExpires};
  }
  if (message.action === "logout") {
    if (!fromPopup) throw new Error("Disconnect using the extension popup");
    try { await request("/api/auth/logout", "POST", {}); }
    finally { await chrome.storage.local.remove(["slkToken", "slkExpires"]); }
    return {connected: false};
  }
  if (message.action === "quote") {
    if (typeof message.pair !== "string" || !/^[A-Z0-9]{2,32}$/.test(message.pair)) throw new Error("Choose a valid market");
    return request("/api/alerts/quote?pair=" + encodeURIComponent(message.pair), "GET");
  }
  if (message.action === "cancelAlert") {
    if (!Number.isSafeInteger(message.id) || message.id <= 0) throw new Error("Invalid alert");
    return request(`/api/alerts/${message.id}/cancel`, "POST", {});
  }
  const route = routes[message.action];
  if (!route) throw new Error("Unsupported operation");
  return request(route[0], route[1], message.action === "createAlert" ? message.body : undefined);
}
async function request(path, method, body, authenticated = true) {
  const headers = {"Content-Type": "application/json"};
  if (authenticated) {
    const {slkToken} = await chrome.storage.local.get("slkToken");
    if (!slkToken) throw new Error("Connect this extension using a code from Telegram");
    headers.Authorization = `Bearer ${slkToken}`;
  }
  const response = await fetch(API + path, {method, headers, credentials: "omit", body: body ? JSON.stringify(body) : undefined});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) await chrome.storage.local.remove(["slkToken", "slkExpires"]);
    throw new Error(typeof data.detail === "string" ? data.detail : `Request failed (${response.status})`);
  }
  return data;
}
chrome.runtime.onMessage.addListener((message, sender, reply) => {
  handle(message || {}, sender).then((data) => reply({ok: true, data}), (error) => reply({ok: false, error: error.message}));
  return true;
});
