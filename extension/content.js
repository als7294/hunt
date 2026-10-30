// Hunt Capture's content script. It tells the extension when your view of the page settles (you stopped scrolling)
// and when a video is playing on screen, so it can take a screenshot. It reads no page data, adds nothing to the
// page, and never clicks, types or navigates.
//
// Two things here act, each only on your input:
// - The Story warning: when you're signed in and click a Story, it asks first, because Story viewers can see
//   your account. Cancel stops that click; OK lets the same click through. Nothing is re-sent.
// - Guided mode: each press of Next asks for one step, and guidedScroll moves the page down exactly one screen. It
//   never repeats and runs on no timer.

let on = false;      // asked of the extension, which also says when it changes (this script can't read its storage)
let signedIn = {};   // platform → signed_in / signed_out, from the presence of each sign-in cookie
chrome.runtime.sendMessage({ type: "on?" }).then((r) => { on = Boolean(r && r.on); signedIn = (r && r.signedIn) || {}; }).catch(() => {});

const send = (type) => { if (on) chrome.runtime.sendMessage({ type }).catch(() => {}); };

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (msg.type === "on") {
    on = msg.on;
    signedIn = msg.signedIn || signedIn;
  }
  if (msg.type === "guided-where") {  // has the page finished loading, and is there more grid below?
    const scroller = document.scrollingElement || document.documentElement;
    reply({ loaded: document.readyState === "complete",
      atBottom: scroller.scrollTop + innerHeight >= scroller.scrollHeight - 4 });
  }
  if (msg.type === "guided-scroll") {
    guidedScroll();
    reply({ ok: true });
  }
  return false;
});

// The one scroll a press of Next makes: one screen down.
function guidedScroll() {
  (document.scrollingElement || document.documentElement).scrollBy({ top: Math.round(innerHeight * 0.9), behavior: "instant" });
}

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

// The Story warning, before a Story opens while you're signed in to Instagram or Facebook.
const STORY = 'a[href*="/stories/"], [role="button"][aria-label*="story" i], [role="link"][aria-label*="story" i]';
document.addEventListener("click", (e) => {
  const platform = /(^|\.)instagram\.com$/.test(location.hostname) ? "instagram"
    : /(^|\.)facebook\.com$/.test(location.hostname) ? "facebook" : null;
  if (!platform || signedIn[platform] !== "signed_in" || !e.target.closest || !e.target.closest(STORY)) return;
  if (!confirm("Story viewers can see your account. Open this Story anyway?")) {
    e.preventDefault();
    e.stopImmediatePropagation();
  }
}, true);
