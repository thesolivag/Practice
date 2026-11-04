const status = document.querySelector("#status"), form = document.querySelector("#connect"), disconnect = document.querySelector("#disconnect");
async function send(message) {
  if (!globalThis.chrome?.runtime?.id) throw new Error("Install this folder in Chrome first: chrome://extensions → Developer mode → Load unpacked → select the folder containing manifest.json. Then click the SLK extension icon and use a fresh Chrome extension code from Telegram → Browsers. Opening this HTML file cannot connect.");
  const result = await chrome.runtime.sendMessage(message);
  if (!result?.ok) throw new Error(result?.error || "Extension unavailable");
  return result.data;
}
function render(data) {
  form.hidden = data.connected; disconnect.hidden = !data.connected;
  status.textContent = data.connected ? "Connected. Manage or revoke this browser in your Telegram Mini App." : "Use a single-use extension code generated inside Telegram.";
}
send({action: "status"}).then(render).catch((e) => { status.textContent = e.message; });
form.addEventListener("submit", async (event) => {
  event.preventDefault(); const button = form.querySelector("button"); button.disabled = true;
  try { render(await send({action: "pair", code: document.querySelector("#code").value.trim()})); document.querySelector("#code").value = ""; }
  catch (e) { status.textContent = e.message; }
  finally { button.disabled = false; }
});
disconnect.addEventListener("click", async () => {
  try { render(await send({action: "logout"})); }
  catch (e) { status.textContent = e.message; }
});
