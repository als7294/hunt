// Hunt Capture's service worker (docs/capture.md).
//
// While capture is on, it records the pages you open yourself on Facebook, Instagram, TikTok, X, LinkedIn
// and YouTube: a screenshot of what's on screen when a view settles, and an MHTML archive of the page
// (chrome.pageCapture: the page and the pictures your browser already loaded). Everything goes only to
// Hunt on this computer (127.0.0.1; the extension's CSP allows nothing else). It never navigates, clicks,
// scrolls, types, searches, likes, follows or messages, and has no code that could.

const SITE = /^https:\/\/([a-z0-9-]+\.)*(facebook|instagram|tiktok|x|twitter|linkedin|youtube)\.com\//i;
const SHOT_GAP = 2500;   // ms between automatic screenshots of one tab (Chrome allows 2 a second)
const FRAME_GAP = 2000;  // ms between screenshots while a video plays
const MAX_FRAMES = 90;   // per page, so a long video doesn't flood the case
const PAGE_GAP = 20000;  // ms before the same page is archived again
const CODE = /^(\d{2,5})-(\d{8})$/;

const DEFAULTS = { port: null, key: null, case: null, caseLabel: "", on: false, mode: "auto", recording: null };
chrome.storage.local.setAccessLevel?.({ accessLevel: "TRUSTED_CONTEXTS" }).catch(() => {});  // the key: never to content scripts
const get = () => chrome.storage.local.get(DEFAULTS);
const set = (values) => chrome.storage.local.set(values);
const tabs = {};   // tabId → { shot, page, url, frames, busy }
const waits = {};  // tabId → timer for the next settled view

async function api(path, body) {
  const s = await get();
  if (!s.port) throw new Error("Pair Hunt Capture with Hunt first.");
  const json = !(body instanceof FormData);
  let r;
  try {
    r = await fetch(`http://127.0.0.1:${s.port}/api/capture/${path}`, {
      method: "POST",
      headers: { ...(s.key ? { "x-hunt-key": s.key } : {}), ...(json ? { "content-type": "application/json" } : {}) },
      body: json ? JSON.stringify(body || {}) : body,
    });
  } catch {
    throw new Error("Hunt isn't reachable. Is `hunt app` running? If it restarted, pair again with its new code.");
  }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `Hunt answered ${r.status}`);
  return data;
}

async function badge() {
  const s = await get();
  for (const t of await chrome.tabs.query({})) {  // tell open pages whether to report views
    if (SITE.test(t.url || "")) chrome.tabs.sendMessage(t.id, { type: "on", on: s.on }).catch(() => {});
  }
  await chrome.action.setBadgeBackgroundColor({ color: "#c62828" });
  await chrome.action.setBadgeText({ text: s.recording ? "●" : s.on ? "REC" : "" });
  await chrome.action.setTitle({ title: s.on ? `Hunt Capture: recording into “${s.caseLabel}”` : "Hunt Capture (off)" });
}

async function problem(error) {
  console.warn("Hunt Capture:", error);
  await chrome.storage.session.set({ lastError: `${new Date().toLocaleTimeString()}: ${error.message || error}` });
}

function blobOf(dataUrl) {  // a data: URL → Blob, without fetch (the CSP allows only 127.0.0.1)
  const [head, body] = dataUrl.split(",");
  const bytes = Uint8Array.from(atob(body), (c) => c.charCodeAt(0));
  return new Blob([bytes], { type: head.slice(5, head.indexOf(";")) });
}

function form(s, tab, when, fields) {
  const f = new FormData();
  f.append("case", s.case);
  f.append("url", tab.url);
  f.append("viewed_at", new Date(when).toISOString());
  for (const [k, v] of Object.entries(fields)) Array.isArray(v) ? f.append(k, ...v) : f.append(k, v);
  return f;
}

async function shot(tab, kind) {
  const s = await get();
  const t = (tabs[tab.id] ||= { shot: 0, page: 0, url: "", frames: 0, busy: false });
  const now = Date.now();
  if (t.url !== tab.url) t.frames = 0;
  if (kind === "view" && now - t.shot < SHOT_GAP) return;
  if (kind === "frame" && (now - t.shot < FRAME_GAP || t.frames >= MAX_FRAMES)) return;
  t.shot = now;
  if (kind === "frame") t.frames += 1;
  const image = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "jpeg", quality: 85 });
  await api("view", form(s, tab, now, { title: tab.title || "", kind, screenshot: [blobOf(image), "screenshot.jpg"] }));
}

async function archive(tab, force) {
  const s = await get();
  const t = (tabs[tab.id] ||= { shot: 0, page: 0, url: "", frames: 0, busy: false });
  const now = Date.now();
  if (t.busy || (!force && t.url === tab.url && now - t.page < PAGE_GAP)) return null;
  t.busy = true;
  try {
    const mhtml = await chrome.pageCapture.saveAsMHTML({ tabId: tab.id });
    const done = await api("page", form(s, tab, now, { archive: [mhtml, "page.mhtml"] }));
    Object.assign(t, { page: now, url: tab.url });
    return done;
  } finally {
    t.busy = false;
  }
}

// A meaningful view of a page you opened: a screenshot, and the page's archive when it's new to Hunt.
async function view(tabId, kind) {
  const s = await get();
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  if (!s.on || !s.case || !tab || !tab.active || !SITE.test(tab.url || "")) return null;
  if (s.mode === "manual" && kind !== "manual") return null;
  await shot(tab, kind);
  return kind === "frame" ? null : archive(tab, kind === "manual");
}

function soon(tabId, kind, wait) {
  clearTimeout(waits[tabId]);
  waits[tabId] = setTimeout(() => view(tabId, kind).catch(problem), wait);
}

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  return tab;
}

// What the popup asks for. Content scripts can only say "settled" or "frame".
async function handle(msg) {
  const s = await get();
  switch (msg.type) {
    case "state": {
      const { lastError } = await chrome.storage.session.get({ lastError: "" });
      const { key, ...shown } = s;
      return { ...shown, paired: Boolean(key), lastError };
    }
    case "pair": {
      const m = CODE.exec((msg.code || "").replace(/\s+/g, ""));
      if (!m) throw new Error("Paste the whole code Hunt shows, like 53211-48271953.");
      await set({ port: Number(m[1]), key: null });
      const { key } = await api("pair", { code: m[2], name: "Hunt Capture" });
      await set({ key, on: false });
      return { paired: true };
    }
    case "hello":
      return api("hello");
    case "checklist":
      return s.case ? api("checklist", { case: s.case }) : { accounts: [] };
    case "case":
      await set({ case: msg.slug, caseLabel: msg.label, on: s.on && msg.slug === s.case });
      return badge();
    case "toggle":
      await set({ on: Boolean(msg.on) && Boolean(s.case) });
      if (msg.on) soon((await activeTab())?.id, "view", 200);
      return badge();
    case "mode":
      return set({ mode: msg.mode === "manual" ? "manual" : "auto" });
    case "capture": {
      const tab = await activeTab();
      if (!s.on) throw new Error("Turn capture on first.");
      return view(tab.id, "manual");
    }
    case "record":
      return record(msg.streamId, await chrome.tabs.get(msg.tabId));
    case "stop":
      return chrome.runtime.sendMessage({ target: "offscreen", type: "stop" });
    case "recorded":
      await set({ recording: null });
      if (msg.error) await problem(new Error(msg.error));
      return badge();
    case "unpair":
      await set({ ...DEFAULTS });
      return badge();
    default:
      throw new Error(`unknown request ${msg.type}`);
  }
}

// Recording a video as you play it: the popup gets a tab-capture stream id (your click is the
// permission), an offscreen page records it and sends the WebM to Hunt.
async function record(streamId, tab) {
  const s = await get();
  if (!s.on) throw new Error("Turn capture on first.");
  if (!SITE.test(tab.url || "")) throw new Error("Hunt Capture records only the supported sites.");
  if (!(await chrome.offscreen.hasDocument())) {
    await chrome.offscreen.createDocument({
      url: "offscreen.html",
      reasons: ["USER_MEDIA"],
      justification: "Record the tab while you play a video, for your Hunt case",
    });
  }
  await set({ recording: tab.id });
  await badge();
  return chrome.runtime.sendMessage({
    target: "offscreen", type: "start", streamId,
    port: s.port, key: s.key, case: s.case, url: tab.url, startedAt: new Date().toISOString(),
  });
}

chrome.runtime.onStartup.addListener(async () => {  // capture is off whenever the browser starts
  await set({ on: false, recording: null });
  await badge();
});
chrome.runtime.onInstalled.addListener(badge);

chrome.tabs.onUpdated.addListener((tabId, info, tab) => {
  if ((info.status === "complete" || info.url) && SITE.test(tab.url || "")) soon(tabId, "view", 2000);
});
chrome.tabs.onActivated.addListener(({ tabId }) => soon(tabId, "view", 1000));

chrome.commands.onCommand.addListener((command, tab) => {
  if (command === "capture-this" && tab) view(tab.id, "manual").catch(problem);
});

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (sender.id !== chrome.runtime.id || msg.target === "offscreen") return false;
  if (sender.tab) {  // a content script: it may only ask whether capture is on, or report a view
    if (msg.type === "on?") { get().then((s) => reply({ on: s.on })); return true; }
    if (msg.type === "settled") soon(sender.tab.id, "view", 300);
    if (msg.type === "frame") view(sender.tab.id, "frame").catch(problem);
    return false;
  }
  handle(msg).then((value) => reply(value ?? {}), (error) => reply({ error: error.message }));
  return true;
});
