// Hunt Capture's popup: pair, choose the case, turn capture on and off, capture or record on demand, pause a tab,
// step through guided mode with Next, and see which sections of each confirmed account are still to open.

const $ = (id) => document.getElementById(id);

async function ask(msg) {
  const r = await chrome.runtime.sendMessage(msg);
  if (r && r.error) throw new Error(r.error);
  return r;
}

function showError(e) {
  $("error").textContent = e ? e.message || String(e) : "";
  $("error").hidden = !e;
}

function el(tag, attrs = {}, text = "") {
  const node = Object.assign(document.createElement(tag), attrs);
  if (text) node.textContent = text;
  return node;
}

async function render() {
  const s = await ask({ type: "state" });
  $("pairing").hidden = s.paired;
  $("main").hidden = !s.paired;
  $("state").textContent = s.recording ? "Recording video…" : s.on ? `Capturing into “${s.caseLabel}”` : "Off";
  $("state").classList.toggle("on", s.on);
  if (s.lastError) showError(new Error(s.lastError));
  if (!s.paired) return;

  const hello = await ask({ type: "hello" });
  if (!s.case && hello.active_case) {  // the Hunt Browser was opened from this case
    await ask({ type: "case", slug: hello.active_case.slug, label: hello.active_case.label });
    return render();
  }
  $("unpair").hidden = Boolean(s.huntBrowser);  // the Hunt Browser pairs itself
  const pick = $("case");
  pick.replaceChildren(el("option", { value: "" }, "Choose a case…"),
    ...hello.cases.map((c) => el("option", { value: c.slug, selected: c.slug === s.case }, c.label)));
  $("toggle").disabled = !s.case;
  $("toggle").textContent = s.on ? "Stop capturing" : "Start capturing";
  $("capture").disabled = $("record").disabled = !s.on;
  $("record").textContent = s.recording ? "Stop recording" : "Record video";
  for (const r of document.querySelectorAll("input[name=mode]")) r.checked = r.value === s.mode;
  $("everyview").checked = await chrome.permissions.contains({ origins: ["<all_urls>"] });
  $("pause").checked = s.tabPaused;
  $("pause").disabled = !s.on;
  const site = (/^https:\/\/(?:[a-z0-9-]+\.)*(linkedin|strava|snapchat)\.com\//i.exec(s.tabUrl) || [])[1];
  const stop = Object.entries(s.stopped || {}).find(([name]) => new RegExp(`${name === "X" ? "(x|twitter)" : name}\\.com`, "i").test(s.tabUrl));
  $("banner").hidden = !(site || stop);
  $("banner").textContent = stop ? stop[1].message
    : site && site.toLowerCase() === "linkedin" ? "Hunt Capture is off on LinkedIn: its terms name browser plugins. Save pages with Save Page As and import them. Consider browsing logged out, or set LinkedIn's profile viewing to private first."
    : site ? `Hunt Capture is off on ${site[0].toUpperCase()}${site.slice(1)}: its terms name extensions. Save pages with Save Page As and import them.` : "";
  $("next").disabled = !s.on || s.guidedBusy || Boolean(site || stop);
  $("next").textContent = s.guidedBusy ? "Recording…" : "Next";
  await renderChecklist(s.tabUrl);
}

function counter(p) {  // "grid 212/212 · flagged 9 · opened 6 of 9 · videos 14, played 6"
  if (!p) return "";
  const grid = p.grid_total ? `${p.grid_seen}/${p.grid_total}` : `${p.grid_seen}`;
  return `grid ${grid} · flagged ${p.flagged} · opened ${p.opened} of ${p.flagged} · videos ${p.videos}, played ${p.played}`;
}

async function renderChecklist(tabUrl = "") {
  const { accounts } = await ask({ type: "checklist" });
  const here = accounts.find((a) => tabUrl.toLowerCase().replace("://m.", "://www.").startsWith(a.account.toLowerCase().replace(/\/$/, "")));
  $("coverage").textContent = here ? `${here.platform} · ${counter(here.progress)}` : "";
  if (!accounts.length) return;
  const lists = accounts.map((a) => {
    const name = a.account.replace(/\/$/, "").split("/").pop();
    const items = a.sections.map((s) => {
      const li = el("li", { className: s.seen ? "seen" : "" });
      li.append(el("span", { className: "tick", ariaHidden: "true" }, s.seen ? "✓" : "○"));
      li.append(s.seen ? el("span", {}, s.label) : el("a", { href: s.url, target: "_blank", rel: "noopener" }, s.label));
      if (!s.seen) li.append(el("span", { className: "visually-hidden" }, " (not opened yet)"));
      return li;
    });
    const box = el("div", { className: "account" });
    const ul = el("ul");
    ul.append(...items);
    box.append(el("h3", {}, `${a.platform} · ${name}`), ul);
    return box;
  });
  $("checklist").replaceChildren(...lists);
}

$("pair-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await ask({ type: "pair", code: $("code").value });
    showError(null);
    await render();
  } catch (err) { showError(err); }
});

$("case").addEventListener("change", async (e) => {
  const option = e.target.selectedOptions[0];
  await ask({ type: "case", slug: e.target.value || null, label: option ? option.textContent : "" });
  await render();
});

$("toggle").addEventListener("click", async () => {
  const s = await ask({ type: "state" });
  await ask({ type: "toggle", on: !s.on });
  await render();
});

for (const r of document.querySelectorAll("input[name=mode]")) {
  r.addEventListener("change", () => ask({ type: "mode", mode: r.value }));
}

$("capture").addEventListener("click", async () => {
  try {
    const done = await ask({ type: "capture" });
    showError(null);
    $("state").textContent = done && done.posts !== undefined ? `Captured: ${done.posts} posts read, ${done.added} new` : "Captured";
    await renderChecklist();
  } catch (err) { showError(err); }
});

$("record").addEventListener("click", async () => {
  try {
    const s = await ask({ type: "state" });
    if (s.recording) {
      await ask({ type: "stop" });
    } else {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      const streamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: tab.id });  // your click allows it
      await ask({ type: "record", streamId, tabId: tab.id });
    }
    await render();
  } catch (err) { showError(err); }
});

$("next").addEventListener("click", async () => {
  try {
    $("next").disabled = true;
    const done = await ask({ type: "next" });
    showError(null);
    $("coverage").textContent = done.did === "nothing" ? done.why : done.did === "open" ? `Opening ${done.to}` : $("coverage").textContent;
  } catch (err) { showError(err); }
  setTimeout(() => render().catch(showError), 1500);  // redraws the popup only; it moves nothing on the page
});

$("pause").addEventListener("change", async (e) => {
  await ask({ type: "pause", paused: e.target.checked });
  await render();
});

$("everyview").addEventListener("change", async (e) => {  // Chrome asks her; nothing is granted without that prompt
  const origins = { origins: ["<all_urls>"] };
  e.target.checked = e.target.checked ? await chrome.permissions.request(origins) : !(await chrome.permissions.remove(origins));
});

$("unpair").addEventListener("click", async () => {
  await ask({ type: "unpair" });
  await render();
});

render().catch(showError);
