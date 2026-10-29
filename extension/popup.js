// Hunt Capture's popup: pair, choose the case, turn capture on and off, capture or record on demand,
// and see which sections of each confirmed account are still to open.

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
  const pick = $("case");
  pick.replaceChildren(el("option", { value: "" }, "Choose a case…"),
    ...hello.cases.map((c) => el("option", { value: c.slug, selected: c.slug === s.case }, c.label)));
  $("toggle").disabled = !s.case;
  $("toggle").textContent = s.on ? "Stop capturing" : "Start capturing";
  $("capture").disabled = $("record").disabled = !s.on;
  $("record").textContent = s.recording ? "Stop recording" : "Record video";
  for (const r of document.querySelectorAll("input[name=mode]")) r.checked = r.value === s.mode;
  await renderChecklist();
}

async function renderChecklist() {
  const { accounts } = await ask({ type: "checklist" });
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

$("unpair").addEventListener("click", async () => {
  await ask({ type: "unpair" });
  await render();
});

render().catch(showError);
