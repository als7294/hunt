// Hunt Capture's content script: tells the extension when your view of the page settles (you stopped
// scrolling) and when a video is playing on screen, so it can take a screenshot. It reads no page data,
// changes nothing, and never clicks, scrolls, types or navigates.

let on = false;  // asked of the extension, which also says when it changes (this script can't read its storage)
chrome.runtime.sendMessage({ type: "on?" }).then((r) => { on = Boolean(r && r.on); }).catch(() => {});
chrome.runtime.onMessage.addListener((msg) => { if (msg.type === "on") on = msg.on; });

const send = (type) => { if (on) chrome.runtime.sendMessage({ type }).catch(() => {}); };

let quiet;
document.addEventListener("scroll", () => {  // capture phase: also feeds that scroll inside a panel
  clearTimeout(quiet);
  quiet = setTimeout(() => send("settled"), 1200);
}, { passive: true, capture: true });

const onScreen = (el) => {
  const r = el.getBoundingClientRect();
  return r.width > 120 && r.height > 90 && r.bottom > 0 && r.top < innerHeight;
};
setInterval(() => {
  if (!on || document.visibilityState !== "visible") return;
  const playing = [...document.querySelectorAll("video")].some((v) => !v.paused && !v.ended && v.readyState > 2 && onScreen(v));
  if (playing) send("frame");
}, 2000);
