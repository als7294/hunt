// Hunt Capture's service worker (docs/capture.md).
//
// A passive recorder. While capture is on, it records the pages you open yourself on Facebook, Instagram, TikTok,
// X, YouTube and Reddit (never LinkedIn, Strava or Snapchat, whose terms name extensions): a screenshot of what's
// on screen when a view settles, and an MHTML archive of the page (chrome.pageCapture: the page and the pictures
// your browser already loaded). Everything goes only to Hunt on this computer (127.0.0.1; the extension's CSP
// allows nothing else). It sends no request to any platform.
//
// Every request a platform receives is caused by one deliberate input of yours. The extension itself never
// navigates, clicks, scrolls, types, searches, likes, follows or messages, with one exception you drive: in guided
// mode, each press of Next (Alt+Shift+N, or the popup's button) does exactly one step, either one scroll of the
// grid by a screen (guidedScroll, in content.js) or one navigation to the next item on Hunt's "open these" list
// (guidedOpen, below). Nothing repeats, nothing runs on a timer, and the next press is locked until this step's
// capture is recorded.
//
// In the Hunt Browser it pairs itself from pairing.json, which Hunt writes beside it, and it tells Hunt which
// platforms you're signed in to: from whether each sign-in cookie exists. It never reads, keeps or sends a
// cookie's value. It watches the addresses you're sent to for checkpoints, challenges and suspensions, and stops
// recording that platform if it sees one (Hunt also checks each archive's text).

const SITE = /^https:\/\/([a-z0-9-]+\.)*(facebook|instagram|tiktok|x|twitter|youtube|reddit)\.com\//i;  // the switch's "on" sites
const NAMES = { facebook: "Facebook", instagram: "Instagram", tiktok: "TikTok", x: "X", twitter: "X", youtube: "YouTube",
  reddit: "Reddit", linkedin: "LinkedIn" };
const REVOKED = {  // the revocation watcher: where a platform sends an account it checked, challenged or blocked
  Facebook: /\/checkpoint(\/|$)/, Instagram: /\/challenge(\/|$)|\/accounts\/(suspended|disabled)/,
  X: /\/account\/(access|suspended|locked)/, TikTok: /\/captcha/, Reddit: /\/account-suspended/,
};
const SHOT_GAP = 2500;   // ms between automatic screenshots of one tab (Chrome allows 2 a second)
const FRAME_GAP = 2000;  // ms between screenshots while a video plays
const MAX_FRAMES = 90;   // per page, so a long video doesn't flood the case
const PAGE_GAP = 20000;  // ms before the same page is archived again
const RETRY_MS = 6000;   // a page that gave no posts is archived once more after this, for apps that draw late
const GUIDE_MAX = 20000; // ms after which a guided step's lock is released even if its capture never came back
const CODE = /^(\d{2,5})-(\d{8})$/;
const SIGN_IN = {  // platform → [site, the cookie that exists only while signed in]
  facebook: ["https://www.facebook.com/", "c_user"],
  instagram: ["https://www.instagram.com/", "sessionid"],
  tiktok: ["https://www.tiktok.com/", "sessionid"],
  linkedin: ["https://www.linkedin.com/", "li_at"],
  x: ["https://x.com/", "auth_token"],
};

const DEFAULTS = { port: null, key: null, case: null, caseLabel: "", on: false, mode: "auto", recording: null, stopped: {} };
chrome.storage.local.setAccessLevel?.({ accessLevel: "TRUSTED_CONTEXTS" }).catch(() => {});  // the key: never to content scripts
const get = () => chrome.storage.local.get(DEFAULTS);
const set = (values) => chrome.storage.local.set(values);
const session = () => chrome.storage.session.get({ lastError: "", paused: [], visited: [] });
const tabs = {};     // tabId → { shot, page, url, frames, busy, scrolled, retried, guided }
const waits = {};    // tabId → timer for the next settled view
const guiding = {};  // tabId → the lock on guided mode until the last step's capture is recorded
const tabState = (id) => (tabs[id] ||= { shot: 0, page: 0, url: "", frames: 0, busy: false });

function siteOf(url) {  // "facebook", "x"... for any page, or null
  const m = /^https:\/\/(?:[a-z0-9-]+\.)*(facebook|instagram|tiktok|x|twitter|youtube|reddit|linkedin)\.com\//i.exec(url || "");
  return m ? m[1].toLowerCase().replace("twitter", "x") : null;
}
const nameOf = (url) => NAMES[siteOf(url)] || null;

async function api(path, body, again = true) {
  const s = await get();
  if (!s.port && !(again && await autopair())) throw new Error("Pair Hunt Capture with Hunt first.");
  return call(path, body, again);
}

async function call(path, body, again) {
  const s = await get();
  const json = !(body instanceof FormData);
  let r;
  try {
    r = await fetch(`http://127.0.0.1:${s.port}/api/capture/${path}`, {
      method: "POST",
      headers: { ...(s.key ? { "x-hunt-key": s.key } : {}), ...(json ? { "content-type": "application/json" } : {}) },
      body: json ? JSON.stringify(body || {}) : body,
    });
  } catch (error) {
    if (again && await autopair()) return call(path, body, false);  // Hunt restarted on a new port
    throw new Error(`Hunt isn't reachable (${error.message}). Is \`hunt app\` running? If it restarted, pair again with its new code.`);
  }
  if (r.status === 403 && again && await autopair()) return call(path, body, false);  // Hunt issued a new key
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `Hunt answered ${r.status}`);
  return data;
}

// The Hunt Browser: Hunt wrote pairing.json beside this extension, so there's no code to type.
async function autopair() {
  try {
    const r = await fetch(chrome.runtime.getURL("pairing.json"), { cache: "no-store" });
    const { port, key } = await r.json();
    const s = await get();
    if (s.port === port && s.key === key) return false;
    await set({ port, key, huntBrowser: true });
    return true;
  } catch {
    return false;  // an everyday browser: paired by code instead
  }
}

// Which platforms you're signed in to, from the presence of each sign-in cookie. Only the yes/no leaves here.
async function signIns() {
  const out = {};
  for (const [platform, [url, name]] of Object.entries(SIGN_IN)) {
    try {
      out[platform] = (await chrome.cookies.get({ url, name })) ? "signed_in" : "signed_out";
    } catch {
      out[platform] = "unknown";
    }
  }
  return out;
}

let signInTimer;
function reportSignIns(wait = 2000) {
  clearTimeout(signInTimer);
  signInTimer = setTimeout(async () => {
    const s = await get();
    const { isOnToolbar } = await chrome.action.getUserSettings();  // the REC badge only shows when pinned
    if (s.key || s.port) await api("signins", { ...(await signIns()), pinned: isOnToolbar }).catch(problem);
  }, wait);
}

// Capture can be turned on or off from Hunt's own screens too, and Hunt keeps the hard stops: follow Hunt.
async function follow() {
  const { capture, stopped } = await api("hello");
  const s = await get();
  const changes = {};
  if (capture && (capture.on !== s.on || (capture.case && capture.case !== s.case))) {
    Object.assign(changes, { on: capture.on }, capture.case ? { case: capture.case, caseLabel: capture.label || capture.case } : {});
  }
  if (stopped && JSON.stringify(stopped) !== JSON.stringify(s.stopped)) changes.stopped = stopped;
  if (Object.keys(changes).length) {
    await set(changes);
    await badge();
  }
}

async function badge() {
  const s = await get();
  const { paused } = await session();
  const text = s.recording ? "●" : s.on ? "REC" : "";
  await chrome.action.setBadgeBackgroundColor({ color: "#c62828" });
  await chrome.action.setBadgeText({ text });
  await chrome.action.setTitle({ title: s.on ? `Hunt Capture: recording into “${s.caseLabel}”` : "Hunt Capture (off)" });
  const signedIn = await signIns();
  for (const t of await chrome.tabs.query({})) {
    const stopped = s.stopped[nameOf(t.url)];
    const tabText = stopped ? "STOP" : paused.includes(t.id) && s.on ? "II" : text;
    chrome.action.setBadgeText({ tabId: t.id, text: tabText }).catch(() => {});
    // tell open pages whether to report views, and where she's signed in (for the Story warning)
    if (SITE.test(t.url || "")) chrome.tabs.sendMessage(t.id, { type: "on", on: s.on, signedIn }).catch(() => {});
  }
}

async function problem(error) {
  console.warn("Hunt Capture:", error);
  const message = String(error && error.message || error).slice(0, 300);
  await chrome.storage.session.set({ lastError: `${new Date().toLocaleTimeString()}: ${message}` });
  call("problem", { message }, false).catch(() => {});  // so Hunt can show that capture is failing, and why
}

function blobOf(dataUrl) {  // a data: URL → Blob, without fetch (the CSP allows only 127.0.0.1)
  const [head, body] = dataUrl.split(",");
  const bytes = Uint8Array.from(atob(body), (c) => c.charCodeAt(0));
  return new Blob([bytes], { type: head.slice(5, head.indexOf(";")) });
}

// Every upload carries its capture record's browser-side fields: the extension's version, and whether you were
// signed in to that platform (Hunt adds the rest; docs/capture.md "Capture record").
async function form(s, tab, when, fields) {
  const f = new FormData();
  const signedIn = await signIns();
  f.append("case", s.case);
  f.append("url", tab.url);
  f.append("viewed_at", new Date(when).toISOString());
  f.append("capture_version", chrome.runtime.getManifest().version);
  if (signedIn[siteOf(tab.url)]) f.append("session", signedIn[siteOf(tab.url)]);
  for (const [k, v] of Object.entries(fields)) Array.isArray(v) ? f.append(k, ...v) : f.append(k, v);
  return f;
}

async function shot(tab, kind) {
  const s = await get();
  const t = tabState(tab.id);
  const now = Date.now();
  if (t.url !== tab.url) t.frames = 0;
  if (kind === "view" && now - t.shot < SHOT_GAP) return;
  if (kind === "frame" && (now - t.shot < FRAME_GAP || t.frames >= MAX_FRAMES)) return;
  t.shot = now;
  if (kind === "frame") t.frames += 1;
  const image = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "jpeg", quality: 85 });
  await api("view", await form(s, tab, now, { title: tab.title || "", kind, screenshot: [blobOf(image), "screenshot.jpg"] }));
}

async function archive(tab, force) {
  const s = await get();
  const t = tabState(tab.id);
  const now = Date.now();
  // the same page again only after you scrolled (new posts loaded) and PAGE_GAP passed; a new page, or a guided
  // step, at once
  if (t.busy || (!force && !t.guided && t.url === tab.url && (!t.scrolled || now - t.page < PAGE_GAP))) return null;
  t.busy = true;
  try {
    const mhtml = await chrome.pageCapture.saveAsMHTML({ tabId: tab.id });
    const done = await api("page", await form(s, tab, now, { archive: [mhtml, "page.mhtml"] }));
    Object.assign(t, { page: now, url: tab.url, scrolled: false });
    if (done.stopped) await stopped(nameOf(tab.url), done.stopped);
    if (done.posts === 0 && t.retried !== tab.url) {  // an app still drawing its posts (X, live QA): archive once more
      t.retried = tab.url;
      setTimeout(async () => {
        const again = await chrome.tabs.get(tab.id).catch(() => null);
        if (again && again.url === tab.url && (await get()).on) archive(again, true).catch(problem);
      }, RETRY_MS);
    }
    return done;
  } finally {
    t.busy = false;
    if (t.guided) {  // the guided step's capture is recorded (or failed): the next press may go
      t.guided = false;
      unlock(tab.id);
    }
  }
}

// A meaningful view of a page you opened: a screenshot, and the page's archive when it's new to Hunt.
// Screenshots need Chrome's activeTab grant (your click on Hunt Capture, or Alt+Shift+H, in that tab) unless you
// allowed "Screenshots on every view" in the popup; the archive needs neither, so it's taken either way.
const warned = new Set();  // tabs already told about the missing screenshot permission
async function view(tabId, kind) {
  const s = await get();
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  if (!s.on || !s.case || !tab || !tab.active || !SITE.test(tab.url || "")) return null;
  if (s.stopped[nameOf(tab.url)] || (await session()).paused.includes(tabId)) return null;
  if (s.mode === "manual" && kind !== "manual") return null;
  try {
    await shot(tab, kind);
  } catch (error) {
    if (!/activeTab|all_urls/.test(error.message)) throw error;
    if (kind === "frame") return null;
    if (!warned.has(tabId)) {
      warned.add(tabId);
      await problem(new Error("No screenshot: click Hunt Capture once in this tab (or allow screenshots on every view in its popup). The page archive is still saved."));
    }
  }
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

// The revocation watcher's hard stop: that platform isn't recorded again until you resume it in Hunt.
async function stopped(platform, entry) {
  const s = await get();
  await set({ stopped: { ...s.stopped, [platform]: entry } });
  await problem(new Error(entry.message));
  await badge();
}

async function watch(url) {
  const platform = nameOf(url);
  if (!platform || !REVOKED[platform] || !REVOKED[platform].test(new URL(url).pathname) || (await get()).stopped[platform]) return;
  await stopped(platform, await api("revoked", { url }));
}

// --- guided mode: one press of Next, one step -------------------------------------------------------------------

function lock(tabId) {
  guiding[tabId] = setTimeout(() => unlock(tabId), GUIDE_MAX);  // this timer only releases the lock; it moves nothing
}
function unlock(tabId) {
  clearTimeout(guiding[tabId]);
  delete guiding[tabId];
}

const norm = (url) => (url || "").toLowerCase().replace(/^https:\/\/(www\.|m\.)?/, "").replace(/twitter\.com/, "x.com").replace(/[?#].*$/, "").replace(/\/$/, "");

async function account(s, tab) {  // the confirmed account this tab belongs to (its profile, or an item on its list)
  const { accounts } = await api("checklist", { case: s.case });
  const here = norm(tab.url);
  return accounts.find((a) => here === norm(a.account) || here.startsWith(norm(a.account) + "/")
    || (a.todo || []).some((t) => norm(t.url) === here)) || null;
}

async function guidedBlock(s, tab) {  // why Next can't step right now, or null
  if (!s.on || !s.case) return "Turn capture on first.";
  if (!tab || !SITE.test(tab.url || "")) return "Guided mode runs only on the sites Hunt Capture records.";
  if (s.stopped[nameOf(tab.url)]) return s.stopped[nameOf(tab.url)].message;
  if ((await session()).paused.includes(tab.id)) return "This tab is paused.";
  if (guiding[tab.id]) return "Wait: the last step is still being recorded.";
  if (tab.status !== "complete") return "Wait: the page is still loading.";
  return null;
}

async function guidedNext() {
  const s = await get();
  const tab = await activeTab();
  const why = await guidedBlock(s, tab);
  if (why) throw new Error(why);
  const mine = await account(s, tab);
  if (!mine) throw new Error("Guided mode works on the subject's confirmed accounts and their \"open these\" list.");
  const onProfile = norm(tab.url) === norm(mine.account) || norm(tab.url).startsWith(norm(mine.account) + "/");
  const place = await chrome.tabs.sendMessage(tab.id, { type: "guided-where" }).catch(() => null);
  if (!place) throw new Error("Wait: the page is still loading.");
  lock(tab.id);
  if (onProfile && !place.atBottom) {  // the grid isn't all seen yet: one screen further
    tabState(tab.id).guided = true;
    await chrome.tabs.sendMessage(tab.id, { type: "guided-scroll" });
    api("guided", { case: s.case, action: "scroll", url: tab.url }).catch(problem);
    return { did: "scroll", progress: mine.progress };
  }
  const { visited } = await session();
  const next = (mine.todo || []).find((t) => norm(t.url) !== norm(tab.url) && !visited.includes(t.url));
  if (!next) {
    unlock(tab.id);
    return { did: "nothing", why: "Everything on this account's \"open these\" list has been opened.", progress: mine.progress };
  }
  await chrome.storage.session.set({ visited: [...visited, next.url] });
  await guidedOpen(tab.id, next.url);
  api("guided", { case: s.case, action: "open", url: tab.url, to: next.url }).catch(problem);
  return { did: "open", to: next.url, progress: mine.progress };
}

async function guidedOpen(tabId, url) {  // the one navigation a press of Next may make
  tabState(tabId).guided = true;
  await chrome.tabs.update(tabId, { url });
}

// --- what the popup asks for -------------------------------------------------------------------------------------

async function handle(msg) {
  const s = await get();
  switch (msg.type) {
    case "state": {
      const { lastError, paused } = await session();
      const tab = await activeTab();
      const { key, ...shown } = s;
      return { ...shown, paired: Boolean(key), lastError, tabUrl: tab?.url || "", tabPaused: paused.includes(tab?.id),
        guidedBusy: Boolean(tab && guiding[tab.id]) };
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
      reportSignIns(0);
      return api("hello");
    case "checklist":
      return s.case ? api("checklist", { case: s.case }) : { accounts: [] };
    case "case":
      await set({ case: msg.slug, caseLabel: msg.label, on: s.on && msg.slug === s.case });
      await api("state", { case: msg.slug, on: s.on && msg.slug === s.case }).catch(problem);  // keep Hunt in step
      return badge();
    case "toggle":
      await set({ on: Boolean(msg.on) && Boolean(s.case) });
      await api("state", { case: s.case, on: Boolean(msg.on) && Boolean(s.case) }).catch(problem);
      if (msg.on) soon((await activeTab())?.id, "view", 200);
      return badge();
    case "pause": {  // pause or resume recording in the current tab only
      const tab = await activeTab();
      const { paused } = await session();
      await chrome.storage.session.set({ paused: msg.paused ? [...new Set([...paused, tab.id])] : paused.filter((id) => id !== tab.id) });
      return badge();
    }
    case "mode":
      return set({ mode: msg.mode === "manual" ? "manual" : "auto" });
    case "capture": {
      const tab = await activeTab();
      if (!s.on) throw new Error("Turn capture on first.");
      return view(tab.id, "manual");
    }
    case "next":
      return guidedNext();
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
  if (s.stopped[nameOf(tab.url)]) throw new Error(s.stopped[nameOf(tab.url)].message);
  if (!(await chrome.offscreen.hasDocument())) {
    await chrome.offscreen.createDocument({
      url: "offscreen.html",
      reasons: ["USER_MEDIA"],
      justification: "Record the tab while you play a video, for your Hunt case",
    });
  }
  await set({ recording: tab.id });
  await badge();
  const signedIn = await signIns();
  return chrome.runtime.sendMessage({
    target: "offscreen", type: "start", streamId, port: s.port, key: s.key, case: s.case, url: tab.url,
    startedAt: new Date().toISOString(), captureVersion: chrome.runtime.getManifest().version,
    session: signedIn[siteOf(tab.url)] || "",
  });
}

chrome.runtime.onStartup.addListener(async () => {  // capture is off whenever the browser starts
  await set({ on: false, recording: null });
  await autopair();
  await badge();
  reportSignIns(0);
});
chrome.runtime.onInstalled.addListener(async () => {
  await autopair();
  await badge();
  reportSignIns(0);
});
// Also whenever this worker starts: when Hunt replaces the worker with new code, neither event above fires.
autopair().then(badge).then(() => reportSignIns(), problem);
const WATCHED = new Set(Object.values(SIGN_IN).map(([, name]) => name));
chrome.cookies.onChanged.addListener(({ cookie }) => { if (WATCHED.has(cookie.name)) reportSignIns(); });

chrome.tabs.onUpdated.addListener((tabId, info, tab) => {
  if (info.url) watch(info.url).catch(problem);
  if ((info.status === "complete" || info.url) && SITE.test(tab.url || "")) {
    follow().catch(() => {}).finally(() => soon(tabId, "view", 2000));
  }
});
chrome.tabs.onActivated.addListener(({ tabId }) => soon(tabId, "view", 1000));
chrome.tabs.onRemoved.addListener((tabId) => unlock(tabId));

chrome.commands.onCommand.addListener((command, tab) => {
  if (command === "capture-this" && tab) view(tab.id, "manual").catch(problem);
  if (command === "guided-next") guidedNext().catch(problem);
});

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (sender.id !== chrome.runtime.id || msg.target === "offscreen") return false;
  if (sender.tab) {  // a content script: it may only ask whether capture is on, or report a view
    if (msg.type === "on?") {
      Promise.all([get(), signIns()]).then(([s, signedIn]) => reply({ on: s.on, signedIn }));
      return true;
    }
    if (msg.type === "settled") {
      tabState(sender.tab.id).scrolled = true;
      soon(sender.tab.id, "view", 300);
    }
    if (msg.type === "frame") view(sender.tab.id, "frame").catch(problem);
    return false;
  }
  handle(msg).then((value) => reply(value ?? {}), (error) => reply({ error: error.message }));
  return true;
});
