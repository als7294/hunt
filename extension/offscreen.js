// Records the tab while you play a video (chrome.tabCapture stream → MediaRecorder → WebM), keeps its
// sound playing for you, and sends the recording only to Hunt on this computer.

const MAX_MS = 10 * 60 * 1000;  // a recording stops itself after 10 minutes
let recorder = null;
let limit = null;

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.target !== "offscreen") return;
  if (msg.type === "start") start(msg).catch((e) => done(e.message));
  if (msg.type === "stop" && recorder) recorder.stop();
});

async function start({ streamId, port, key, case: slug, url, startedAt }) {
  if (recorder) throw new Error("Already recording.");
  const media = await navigator.mediaDevices.getUserMedia({
    audio: { mandatory: { chromeMediaSource: "tab", chromeMediaSourceId: streamId } },
    video: { mandatory: { chromeMediaSource: "tab", chromeMediaSourceId: streamId } },
  });
  const sound = new AudioContext();  // capturing a tab mutes it; play it back so you still hear it
  sound.createMediaStreamSource(media).connect(sound.destination);
  const chunks = [];
  recorder = new MediaRecorder(media, { mimeType: "video/webm" });
  recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
  recorder.onstop = async () => {
    clearTimeout(limit);
    media.getTracks().forEach((t) => t.stop());
    await sound.close();
    recorder = null;
    try {
      const f = new FormData();
      f.append("case", slug);
      f.append("url", url);
      f.append("started_at", startedAt);
      f.append("video", new Blob(chunks, { type: "video/webm" }), "recording.webm");
      const r = await fetch(`http://127.0.0.1:${port}/api/capture/recording`, { method: "POST", headers: { "x-hunt-key": key }, body: f });
      const data = await r.json().catch(() => ({}));
      done(r.ok ? null : data.error || `Hunt answered ${r.status}`);
    } catch {
      done("Hunt isn't reachable; the recording wasn't saved.");
    }
  };
  recorder.start(1000);
  limit = setTimeout(() => recorder && recorder.stop(), MAX_MS);
}

function done(error) {
  chrome.runtime.sendMessage({ type: "recorded", error });
}
