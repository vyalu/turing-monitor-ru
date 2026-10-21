// Работает в контексте страницы: видит navigator.mediaSession и все аудио/видео, даже не вставленные в страницу.
(() => {
  if (window.__turmonMedia) return;
  window.__turmonMedia = true;
  const els = new Set();
  const origPlay = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function (...a) {
    try { els.add(this); } catch (e) { /* ничего */ }
    return origPlay.apply(this, a);
  };
  document.addEventListener("play", (e) => { if (e.target instanceof HTMLMediaElement) els.add(e.target); }, true);

  function pickElement() {
    let best = null;
    for (const el of els) {
      if (!el.isConnected && el.paused && !el.currentTime) { els.delete(el); continue; }
      if (!el.paused && !el.ended) return el;
      if (!best || el.currentTime > 0) best = el;
    }
    if (best) return best;
    for (const el of document.querySelectorAll("audio,video")) {
      if (!el.paused && !el.ended) return el;
      if (!best && el.currentTime > 0) best = el;
    }
    return best;
  }

  function artwork(md) {
    const list = Array.from(md.artwork || []);
    if (!list.length) return "";
    const size = (a) => Math.max(0, ...String(a.sizes || "").split(/\s+/).map((s) => parseInt(s, 10) || 0));
    list.sort((a, b) => size(b) - size(a));
    return list[0].src || "";
  }

  function collect() {
    const ms = navigator.mediaSession;
    const md = ms && ms.metadata;
    if (!md || !md.title) return null;
    const el = pickElement();
    let playing = false;
    if (el) playing = !el.paused && !el.ended;
    if (ms.playbackState === "playing") playing = true;
    else if (ms.playbackState === "paused" && !(el && !el.paused)) playing = false;
    const d = el && isFinite(el.duration) ? el.duration : 0;
    return {
      title: md.title || "",
      artist: md.artist || "",
      album: md.album || "",
      art: artwork(md),
      playing,
      position: el ? el.currentTime || 0 : 0,
      duration: d > 0 ? d : 0,
      site: location.hostname,
    };
  }

  let last = "";
  setInterval(() => {
    let data = null;
    try { data = collect(); } catch (e) { data = null; }
    const s = JSON.stringify(data);
    if (data || last !== s) window.dispatchEvent(new CustomEvent("turmon-media", { detail: s }));
    last = s;
  }, 1000);
})();
