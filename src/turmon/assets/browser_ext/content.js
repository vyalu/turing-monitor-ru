// Пересылает данные со страницы в фоновую часть расширения (она отдаёт их программе на этом ПК).
window.addEventListener("turmon-media", (e) => {
  let data = null;
  try { data = JSON.parse(e.detail); } catch (err) { return; }
  try { chrome.runtime.sendMessage({ type: "media", data }); } catch (err) { /* расширение перезагружено */ }
});
window.addEventListener("pagehide", () => {
  try { chrome.runtime.sendMessage({ type: "media", data: null }); } catch (err) { /* ничего */ }
});
