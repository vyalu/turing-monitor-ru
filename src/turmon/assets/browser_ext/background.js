// Отдаёт трек программе Turing Monitor RU по адресу 127.0.0.1 (только этот компьютер).
importScripts("config.js");

const covers = new Map(); // адрес обложки -> data: URL (несколько последних)

async function coverData(url) {
  if (!url) return "";
  if (url.startsWith("data:")) return url.length < 3_000_000 ? url : "";
  if (covers.has(url)) return covers.get(url);
  try {
    const r = await fetch(url, { credentials: "omit" });
    const b = await r.blob();
    if (b.size > 4 * 1024 * 1024) return "";
    const data = await new Promise((ok, fail) => {
      const fr = new FileReader();
      fr.onload = () => ok(fr.result);
      fr.onerror = fail;
      fr.readAsDataURL(b);
    });
    covers.set(url, data);
    while (covers.size > 8) covers.delete(covers.keys().next().value);
    return data;
  } catch (e) {
    return "";
  }
}

const sentCover = new Map(); // вкладка -> адрес обложки, уже отправленной программе
let port = TURMON.ports[0];

async function post(body) {
  const order = [port, ...TURMON.ports.filter((p) => p !== port)];
  for (const p of order) {
    try {
      const r = await fetch(`http://127.0.0.1:${p}/media`, {
        method: "POST",
        headers: { "Content-Type": "text/plain" },
        body: JSON.stringify(body),
      });
      if (r.ok) { port = p; return await r.json(); }
    } catch (e) { /* программа не запущена или другой порт */ }
  }
  return null;
}

chrome.runtime.onMessage.addListener((msg, sender) => {
  if (!msg || msg.type !== "media" || !sender.tab) return;
  const tab = sender.tab.id;
  const d = msg.data;
  (async () => {
    const body = { token: TURMON.token, tab, data: d, incognito: !!sender.tab.incognito };
    if (d && d.art && sentCover.get(tab) !== d.art) {
      body.cover = await coverData(d.art);
    }
    const res = await post(body);
    if (res && d && d.art) {
      if (res.have_cover) sentCover.set(tab, d.art);
      else sentCover.delete(tab);
    }
    if (!d) sentCover.delete(tab);
  })();
});

chrome.tabs && chrome.tabs.onRemoved && chrome.tabs.onRemoved.addListener((tab) => {
  sentCover.delete(tab);
  post({ token: TURMON.token, tab, data: null });
});
