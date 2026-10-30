// Hunt Capture's content script. It tells the extension when your view of the page settles (you stopped scrolling)
// and when a video is playing on screen, so it can take a screenshot. It reads no page data, adds nothing to the
// page, and never clicks, types or navigates.
//
// Three things here act, each only on your input:
// - The Story warning: unless you're known to be signed out, a click on a Story asks first, because Story viewers
//   can see your account. Cancel stops that click; OK lets the same click through. Nothing is re-sent.
// - The contact warning: likewise before your own follow, add-friend, connect, like, comment or message click. An
//   OK is reported to Hunt, which audits it.
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

// Is she possibly signed in here? Only a known "signed_out" says no: a failed or missing check warns anyway.
const PLATFORM = (/(?:^|\.)(facebook|instagram|tiktok|x|twitter|youtube|reddit)\.com$/.exec(location.hostname) || [])[1];
const maybeSignedIn = () => signedIn[PLATFORM === "twitter" ? "x" : PLATFORM] !== "signed_out";

// The Story warning, before a Story opens on Instagram or Facebook (a click or a middle-click).
const STORY = 'a[href*="/stories/"], [role="button"][aria-label*="story" i], [role="link"][aria-label*="story" i]';
function storyGuard(e) {
  const story = (PLATFORM === "instagram" || PLATFORM === "facebook") && e.target.closest && e.target.closest(STORY);
  if (!story || !maybeSignedIn()) return;
  if (confirm("Story viewers can see your account. Instagram and Facebook then move on to other people's Stories by "
    + "themselves; they can see you too. Open this Story anyway?")) {
    chrome.runtime.sendMessage({ type: "story-ok", href: story.href || "" }).catch(() => {});
  } else {
    e.preventDefault();
    e.stopImmediatePropagation();
  }
}
document.addEventListener("click", storyGuard, true);
document.addEventListener("auxclick", storyGuard, true);

// The contact warning: your own follow, friend, connect, like, comment or message click, from your account.
const CONTACT = /^(?:follow|follow back|add friend|connect|like|love|react|comment|leave a comment|message|send message|subscribe|join|join group)$/i;
function contactGuard(e) {
  const control = e.target.closest && e.target.closest('button, [role="button"], a');
  const label = control && (control.getAttribute("aria-label") || control.querySelector("[aria-label]")?.getAttribute("aria-label")
    || control.textContent || "").trim();
  if (!label || !CONTACT.test(label) || !maybeSignedIn()) return;
  if (confirm(`"${label}" acts from your account, and the person may be told. Hunt's rules say no contact with the `
    + "subject or the people around them. Do it anyway?")) {
    chrome.runtime.sendMessage({ type: "contact-ok", what: label }).catch(() => {});
  } else {
    e.preventDefault();
    e.stopImmediatePropagation();
  }
}
document.addEventListener("click", contactGuard, true);
document.addEventListener("auxclick", contactGuard, true);
