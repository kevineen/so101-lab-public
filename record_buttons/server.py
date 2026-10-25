"""LAN page that starts, stops, reviews, and keeps a lerobot-record episode.

The page shares the recording ``events`` dict with the keyboard:

* ready — Start or ``n`` begins the take. Nest toggle holds both arms at nest.
* record — Stop ends the take and opens review. ``r`` discards immediately.
* review — 残す keeps it and goes to the next ready. 捨てる discards as failure, then ready.
* reset — kept for API compatibility; the phone flow skips this phase after review.
* stop — Esc / ``q`` ends the session. An open take is discarded.

Nothing here opens a robot serial port. Keeping a take does not add a
success column. Discard skips ``save_episode`` the same way ``r`` does.
Transfer runs only after a take is kept.
"""

from __future__ import annotations

import json
import logging
import socket
import struct
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

logger = logging.getLogger("record_buttons")

# Linux SIOCGIFADDR. Absent on other platforms; interface listing falls back.
_SIOCGIFADDR = 0x8915

CONTROLS = ("start", "halt", "pause", "keep", "discard", "success", "failure", "nest", "stop")

_MESSAGES = {
    "start": "ブラウザの記録開始。録画を始めます。",
    "halt": "ブラウザの記録終了。確認に入ります。",
    "pause": "ブラウザの一時停止。",
    "keep": "ブラウザで残します。次の開始待ちへ進み、開始前に転送します。",
    "discard": "ブラウザで捨てます（失敗）。次の開始待ちへ。",
    "success": "ブラウザの成功。リセットを終えます。",
    "failure": "ブラウザの失敗。残す前の本を捨てます。",
    "nest": "ブラウザの nest トグル。",
    "stop": "ブラウザの中止。録画を止めます。",
}

# Which button is valid in which phone phase. The record thread is the
# only writer of ``phase``; a press for another phase is rejected.
_PHASE_CONTROLS = {
    "homing": {"nest", "start", "stop"},
    "ready": {"nest", "start", "stop"},
    "record": {"halt", "pause", "discard", "stop"},
    "review": {"keep", "discard", "stop"},
    "reset": {"success", "failure", "pause", "stop"},
    "upload": {"stop"},
    "idle": {"stop"},
}

PAGE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#111111">
<title>録画</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  html, body { height: auto; min-height: 100%; }
  body {
    margin: 0;
    min-height: 100dvh;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    background: #111;
    color: #f3f3f3;
    font-family: system-ui, sans-serif;
  }
  header { padding: 16px 16px 0; }
  h1 { margin: 0; font-size: 1.5rem; }
  #hint { margin: 8px 0 0; color: #c8c8c8; line-height: 1.45; min-height: 3.2em; }
  main { flex: 1; display: flex; flex-direction: column; gap: 12px; padding: 12px; }
  button { border: 0; border-radius: 18px; font: inherit; touch-action: manipulation; }
  button[hidden] { display: none !important; }
  button.choice {
    flex: 1;
    min-height: 18vh;
    font-size: clamp(2rem, 9vw, 3.2rem);
    font-weight: 800;
  }
  button.choice small {
    display: block;
    margin-top: 8px;
    font-size: 1rem;
    font-weight: 600;
  }
  button.go { background: #3ddc84; color: #06210f; }
  button.halt { background: #f0c14a; color: #241c04; }
  button.danger { background: #e23b3b; color: #fff; }
  button.nest { background: #6ec6ff; color: #071226; }
  button.nest.on { background: #3d8fd6; color: #fff; }
  button.quiet { min-height: 64px; font-size: 1.2rem; background: #2a2a2a; color: #ddd; }
  button.stop { margin: 0 12px 12px; height: 48px; background: #2a2a2a; color: #ddd; }
  button:disabled { opacity: 0.4; }
  #progress { margin: 8px 0 0; color: #d5d5d5; font-size: 1.05rem; }
  #clock {
    margin: 4px 0 0;
    font-size: 2rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    letter-spacing: 0.03em;
  }
  #preview { display: flex; flex-direction: column; gap: 8px; }
  #preview[hidden] { display: none; }
  .cams { display: flex; gap: 8px; }
  .cams figure { margin: 0; flex: 1; }
  .cams img { width: 100%; background: #000; border-radius: 8px; }
  .cams figcaption { font-size: 0.8rem; color: #aaa; }
  input[type=range] { width: 100%; }
  input[type=range][hidden] { display: none; }
  footer { padding: 0 16px 16px; color: #8d8d8d; font-size: 0.85rem; line-height: 1.4; }
  button.choice { min-height: 14vh; }
  button.pause { background: #8eb4ff; color: #071226; }
</style>
</head>
<body>
<header>
  <h1 id="title">待機</h1>
  <p id="progress">エピソード —</p>
  <p id="clock">0:00.0</p>
  <p id="hint">録画プロセスを待っています。</p>
</header>
<main>
  <div id="preview" hidden>
    <div class="cams" id="cams"></div>
    <input id="scrub" type="range" min="0" max="0" value="0">
  </div>
  <button class="choice nest" type="button" id="nest"><span id="nest-label">両方 nest へ</span><small id="nest-sub">まず手首(ID4)を nest 角度へ、そのあと全身を保持</small></button>
  <button class="choice go" type="button" id="start">記録開始<small>録画を始める</small></button>
  <button class="choice halt" type="button" id="halt">記録終了<small>止めて確認する</small></button>
  <button class="choice pause" type="button" id="pause"><span id="pause-label">一時停止</span><small id="pause-sub">時間とフレームを止める</small></button>
  <button class="choice go" type="button" id="keep">残す<small>保存して開始待ちへ。転送は次の開始前</small></button>
  <button class="choice danger" type="button" id="discard">捨てる<small>失敗として捨て、すぐ開始待ちへ</small></button>
  <button class="choice go" type="button" id="success">成功<small id="success-sub">戻し終わった</small></button>
  <button class="choice danger" type="button" id="failure">失敗<small id="failure-sub">さっきの本を捨てる</small></button>
</main>
<button class="stop" type="button" id="stop">中止</button>
<footer>非常停止は手元の ESTOP です。この画面はトルクを切りません。「両方 nest へ」は手首(ID4)を先に nest 角度へ戻し、揃ったら他の関節を戻して保持します。OFF で leader 追従に戻ります。一時停止中も follower はリーダーに追従し、記録時間とフレームだけ止まります。</footer>
<script>
const copy = {
  homing: ["nest へ移動中", "両腕が nest へゆっくり動いています。到着後はその姿勢を保持します。"],
  ready: ["開始待ち", "nest 保持中は両腕が nest に留まります。トグル OFF で leader 追従。揃ったら記録開始。"],
  record: ["録画中", "記録終了で止めて、映像を見てから残すか捨てるかを決めます。一時停止は時間とフレームだけ止めます。"],
  review: ["確認", "残すと保存し、すぐ次の開始待ちへ進みます。捨てた本は送りません。物の戻しは開始待ちで行います。"],
  reset: ["リセット中", "物と腕を戻したら成功。残したくなくなったら失敗。"],
  upload: ["転送中", "残した本を PC へ送っています。"],
  idle: ["待機", "次の開始待ちを準備しています。"]
};
const buttons = ["nest", "start", "halt", "pause", "keep", "discard", "success", "failure"];
const visible = {
  homing: ["nest", "start"],
  ready: ["nest", "start"],
  record: ["halt", "pause", "discard"],
  review: ["keep", "discard"],
  reset: ["success", "failure", "pause"],
  upload: [],
  idle: []
};
let shownKey = "";
let liveKey = "";
let liveSeq = -1;
let lastData = null;

function fmt(seconds) {
  const n = Math.max(0, Number(seconds) || 0);
  const m = Math.floor(n / 60);
  const rest = (n - m * 60).toFixed(1).padStart(4, "0");
  return m + ":" + rest;
}

function fillFigures(names, srcFor) {
  const cams = document.getElementById("cams");
  cams.textContent = "";
  names.forEach((name) => {
    const fig = document.createElement("figure");
    const img = document.createElement("img");
    img.alt = name;
    img.dataset.cam = name;
    img.src = srcFor(name);
    const cap = document.createElement("figcaption");
    cap.textContent = name;
    fig.appendChild(img);
    fig.appendChild(cap);
    cams.appendChild(fig);
  });
}

function renderReview(data, samples) {
  const box = document.getElementById("preview");
  const scrub = document.getElementById("scrub");
  liveKey = "";
  liveSeq = -1;
  if (samples < 1) {
    box.hidden = true;
    shownKey = "";
    return;
  }
  box.hidden = false;
  scrub.hidden = false;
  scrub.max = String(samples - 1);
  let index = Number(scrub.value);
  if (!Number.isFinite(index) || index < 0 || index >= samples) {
    index = samples - 1;
    scrub.value = String(index);
  }
  const names = Array.isArray(data.cameras) && data.cameras.length ? data.cameras : ["front", "wrist"];
  const key = index + ":" + names.join(",");
  if (key === shownKey) return;
  shownKey = key;
  fillFigures(names, (name) => "/preview/" + encodeURIComponent(name) + "/" + index + ".jpg");
}

function renderLive(data) {
  const box = document.getElementById("preview");
  const scrub = document.getElementById("scrub");
  shownKey = "";
  scrub.hidden = true;
  const names = Array.isArray(data.cameras) ? data.cameras : [];
  const seq = Number(data.live_seq || 0);
  if (!names.length || seq < 1) {
    box.hidden = true;
    liveKey = "";
    return;
  }
  box.hidden = false;
  const key = names.join(",");
  const cams = document.getElementById("cams");
  if (key !== liveKey) {
    liveKey = key;
    fillFigures(names, (name) => "/live/" + encodeURIComponent(name) + ".jpg?v=" + seq);
    liveSeq = seq;
    return;
  }
  if (seq === liveSeq) return;
  liveSeq = seq;
  names.forEach((name) => {
    const img = cams.querySelector('img[data-cam="' + name + '"]');
    if (img) img.src = "/live/" + encodeURIComponent(name) + ".jpg?v=" + seq;
  });
}

function renderPreview(data) {
  const samples = Number(data.samples || 0);
  const livePhase = data.phase === "ready" || data.phase === "record" || data.phase === "reset" || data.phase === "homing";
  if (data.phase === "review") {
    renderReview(data, samples);
    return;
  }
  if (livePhase) {
    renderLive(data);
    return;
  }
  document.getElementById("preview").hidden = true;
  document.getElementById("scrub").hidden = true;
  shownKey = "";
  liveKey = "";
}

function render(data) {
  const known = Object.prototype.hasOwnProperty.call(copy, data.phase);
  const phase = known ? data.phase : "idle";
  const row = copy[phase];
  const paused = Boolean(data.paused);
  const holdNest = Boolean(data.hold_nest);
  const nestHolding = Boolean(data.nest_holding);
  let title = row[0];
  if (data.stop) title = "停止中";
  else if (paused) title = "一時停止";
  else if (holdNest && nestHolding) title = "nest 保持中";
  else if (holdNest && phase === "homing") title = "nest へ移動中";
  document.getElementById("title").textContent = title;
  const total = Number(data.total) || 0;
  const episode = Number(data.episode) || 0;
  const saved = Number(data.saved) || 0;
  let progress = "保存 " + saved;
  if (total) progress += " / " + total;
  if (episode) progress = "エピソード " + episode + (total ? " / " + total : "") + " · " + progress;
  if (data.frames) progress += " · " + data.frames + " フレーム";
  document.getElementById("progress").textContent = progress;
  let clockLabel = "時間 ";
  if (phase === "ready" || phase === "record" || phase === "review" || phase === "homing") clockLabel = "記録 ";
  else if (phase === "reset") clockLabel = "リセット ";
  let clock = fmt(data.elapsed_s);
  if (data.limit_s) clock += " / " + fmt(data.limit_s);
  document.getElementById("clock").textContent = clockLabel + clock;
  const pauseLabel = document.getElementById("pause-label");
  const pauseSub = document.getElementById("pause-sub");
  pauseLabel.textContent = paused ? "再開" : "一時停止";
  pauseSub.textContent = paused ? "記録時間を進める" : "時間とフレームを止める";
  const nestLabel = document.getElementById("nest-label");
  const nestSub = document.getElementById("nest-sub");
  const nestBtn = document.getElementById("nest");
  if (holdNest) {
    nestLabel.textContent = "nest 解除";
    nestSub.textContent = nestHolding ? "保持中。押すと leader 追従に戻る" : "移動中。押すと追従に戻る";
    nestBtn.classList.add("on");
  } else {
    nestLabel.textContent = "両方 nest へ";
    nestSub.textContent = "まず手首(ID4)を nest 角度へ、そのあと全身を保持";
    nestBtn.classList.remove("on");
  }
  let hint = row[1];
  if (data.stop) hint = "録画を止めています。";
  else if (data.pending) hint = "送りました。次の制御周期で反映されます。";
  else if (holdNest && nestHolding) hint = "両腕が nest を保持しています。この姿勢のまま記録開始できます。";
  else if (holdNest && phase === "homing") hint = "両腕を nest へゆっくり移動中です。";
  else if (!holdNest && (phase === "ready" || phase === "homing")) hint = "leader 追従中。「両方 nest へ」で両腕を nest に戻せます。";
  else if (paused && phase === "record") hint = "一時停止中です。時間とフレームは止まり、follower はリーダーに追従します。";
  else if (paused && phase === "reset") hint = "一時停止中です。リセット時間は止まります。腕はリーダーに追従します。";
  else if ((phase === "ready" || phase === "record" || phase === "reset" || phase === "homing") && !data.live_seq) hint = "カメラ映像を待っています。" + hint;
  else if (phase === "review" && data.frames) hint = data.frames + " フレーム。" + hint;
  else if (phase === "reset" && data.rerecord) hint = "失敗を受け付け済みです。リセット後、この本は保存されません。";
  else if (data.error === "pending") hint = "すでに受け付け済みです。";
  else if (data.error === "phase") hint = "いまの画面では押せません。";
  else if (data.ok === false) hint = "送れませんでした。";
  document.getElementById("hint").textContent = hint;
  const show = visible[phase] || [];
  // nest トグルは exit_early 待ち中でも押せる（記録開始の pending とは独立）。
  const locked = Boolean(data.pending || data.stop);
  buttons.forEach((name) => {
    const el = document.getElementById(name);
    const on = show.indexOf(name) !== -1;
    el.hidden = !on;
    el.disabled = !on || (name !== "nest" && locked);
    el.style.order = on ? String(show.indexOf(name) + 1) : "0";
  });
  document.getElementById("stop").disabled = Boolean(data.stop);
  lastData = data;
  renderPreview(data);
}

async function send(name) {
  if (name === "stop") {
    const duringReset = lastData && lastData.phase === "reset";
    const text = duringReset
      ? "セッションを止めますか？残すと決めた本は保存して転送します。"
      : "録画セッションを止めますか？まだ残していない本は残りません。";
    if (!window.confirm(text)) return;
  }
  try {
    const res = await fetch("/api/" + name, {method: "POST"});
    render(await res.json());
  } catch (err) {
    document.getElementById("hint").textContent = "録画プロセスとつながっていません。";
  }
}

buttons.forEach((name) => {
  document.getElementById(name).addEventListener("click", () => send(name));
});
document.getElementById("stop").addEventListener("click", () => send("stop"));
document.getElementById("scrub").addEventListener("input", () => {
  shownKey = "";
  if (lastData) renderPreview(lastData);
});

async function poll() {
  try {
    const res = await fetch("/api/state", {cache: "no-store"});
    render(await res.json());
  } catch (err) {
    document.getElementById("hint").textContent = "録画プロセスとつながっていません。";
  }
}
poll();
setInterval(poll, 400);
</script>
</body>
</html>
"""


def fresh_events() -> dict:
    """Flags shared with ``init_keyboard_listener``."""
    return {
        "exit_early": False,
        "rerecord_episode": False,
        "stop_recording": False,
        "phase": "idle",
        "paused": False,
        "hold_nest": False,
        "nest_holding": False,
        "start_episode": False,
    }


def apply_phone_control(name: str, events: dict) -> None:
    """Write the keyboard-equivalent flags for one phone button.

    Start, Stop, keep, and discard are phase-gated. ``n`` is ``exit_early``
    (start while waiting, end the take while recording, keep while reviewing,
    end the reset while resetting). ``r`` is discard. ``q`` ends the session
    and drops an open take. During reset, ``q`` does not drop a take already kept.
    ``nest`` toggles both-arm nest hold without ending the ready loop.
    """
    phase = events.get("phase", "idle")
    if phase not in _PHASE_CONTROLS or name not in _PHASE_CONTROLS[phase]:
        raise ValueError("phase")
    if name == "pause":
        # Does not end the loop. The record clock and add_frame both read this flag.
        events["paused"] = not bool(events.get("paused"))
    elif name == "nest":
        events["hold_nest"] = not bool(events.get("hold_nest"))
        if not events["hold_nest"]:
            events["nest_holding"] = False
    elif name == "start":
        events["exit_early"] = True
        events["start_episode"] = True
    elif name in ("halt", "keep", "success"):
        events["exit_early"] = True
    elif name in ("discard", "failure"):
        events["rerecord_episode"] = True
        events["exit_early"] = True
    elif name == "stop":
        events["stop_recording"] = True
        events["exit_early"] = True
        # Reset means the take was already accepted. Ending the session there
        # still saves it. Anywhere else, stop must not fall through to save.
        if phase != "reset":
            events["rerecord_episode"] = True
    else:
        raise ValueError(name)


def _live_jpeg(board: ButtonBoard, path: str) -> bytes | None:
    """JPEG for ``/live/<camera>.jpg``. None when the path is something else."""
    prefix = "/live/"
    if not path.startswith(prefix) or not path.endswith(".jpg"):
        return None
    camera = path[len(prefix) : -4]
    if not camera or "/" in camera:
        return b""
    preview = board.preview
    if preview is None or not hasattr(preview, "live_jpeg"):
        return b""
    blob = preview.live_jpeg(camera)
    return blob or b""


def _preview_jpeg(board: ButtonBoard, path: str) -> bytes | None:
    """JPEG for ``/preview/<camera>/<index>.jpg``. None when the path is something else."""
    prefix = "/preview/"
    if not path.startswith(prefix) or not path.endswith(".jpg"):
        return None
    body = path[len(prefix) : -4]
    camera, sep, index_text = body.partition("/")
    if not sep or "/" in index_text or not index_text.isdigit():
        return b""
    preview = board.preview
    if preview is None:
        return b""
    blob = preview.jpeg(camera, int(index_text))
    return blob or b""


def origin_allowed(origin: str | None, host: str | None) -> bool:
    """Allow curl (no Origin) and the page itself. Reject other sites."""
    if not origin:
        return True
    if not host:
        return False
    parsed = urlparse(origin)
    return parsed.netloc == host


class ButtonBoard:
    """Thread-safe view of the recording ``events`` dict and the frame preview."""

    def __init__(self, events: dict, preview: object | None = None, session: object | None = None) -> None:
        self.events = events
        self.preview = preview
        self.session = session
        self.last: str | None = None
        self._lock = threading.Lock()

    def snapshot(self) -> dict:
        with self._lock:
            return self._snapshot_locked()

    def _snapshot_locked(self) -> dict:
        phase = self.events.get("phase", "idle")
        if phase not in ("homing", "ready", "record", "review", "reset", "upload", "idle"):
            phase = "idle"
        pending = bool(self.events.get("exit_early") or self.events.get("stop_recording"))
        payload = {
            "ok": True,
            "phase": phase,
            "pending": pending,
            "stop": bool(self.events.get("stop_recording")),
            "rerecord": bool(self.events.get("rerecord_episode")),
            "last": self.last,
            "frames": 0,
            "samples": 0,
            "cameras": [],
            "live_seq": 0,
            "episode": 0,
            "saved": 0,
            "total": 0,
            "elapsed_s": 0.0,
            "limit_s": 0.0,
            "paused": bool(self.events.get("paused")),
            "hold_nest": bool(self.events.get("hold_nest")),
            "nest_holding": bool(self.events.get("nest_holding")),
        }
        if self.preview is not None:
            info = self.preview.info()
            if phase == "review":
                review = info.get("review_cameras") or []
                if review:
                    info = dict(info)
                    info["cameras"] = review
            payload.update(info)
        if self.session is not None:
            payload.update(self.session.public())
        payload["paused"] = bool(self.events.get("paused"))
        payload["hold_nest"] = bool(self.events.get("hold_nest"))
        payload["nest_holding"] = bool(self.events.get("nest_holding"))
        return payload

    def submit(self, name: str) -> tuple[int, dict]:
        """Accept one button, or 409 while a previous press is still pending.

        The record loop clears ``exit_early`` when it notices the press. Until
        then a second tap must not replace 残す with 捨てる. A button that does
        not belong to the current phase is also 409. ``nest`` is exempt from the
        pending lock so the hold toggle stays responsive.
        """
        if name not in CONTROLS:
            return 400, {"ok": False, "error": "unknown", **self.snapshot()}
        with self._lock:
            if name != "nest" and (self.events.get("exit_early") or self.events.get("stop_recording")):
                payload = self._snapshot_locked()
                payload["ok"] = False
                payload["error"] = "pending"
                return 409, payload
            try:
                apply_phone_control(name, self.events)
            except ValueError:
                payload = self._snapshot_locked()
                payload["ok"] = False
                payload["error"] = "phase"
                return 409, payload
            self.last = name
            message = _MESSAGES[name]
            if name == "pause":
                message = (
                    "ブラウザの一時停止。記録時間とフレームを止めます。腕は追従します。"
                    if self.events.get("paused")
                    else "ブラウザの再開。記録時間を進めます。"
                )
            elif name == "nest":
                message = (
                    "ブラウザ: 両腕を nest へ移動／保持します（まず手首 ID4、そのあと他の関節）。"
                    if self.events.get("hold_nest")
                    else "ブラウザ: nest 保持を解除。leader 追従に戻します。"
                )
            print(message, flush=True)
            logger.info(message)
            return 200, self._snapshot_locked()


class _HTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], board: ButtonBoard) -> None:
        self.board = board
        super().__init__(address, _Handler)


class _Handler(BaseHTTPRequestHandler):
    server: _HTTPServer

    def log_message(self, fmt: str, *args) -> None:
        # Polls are frequent. Accepted buttons are printed in ButtonBoard.submit.
        return

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            body = PAGE.encode()
            self._bytes(200, "text/html; charset=utf-8", body)
            return
        if path == "/api/state":
            self._json(200, self.server.board.snapshot())
            return
        live = _live_jpeg(self.server.board, path)
        if live is not None:
            if live:
                self._bytes(200, "image/jpeg", live)
            else:
                self._json(404, {"ok": False, "error": "live"})
            return
        preview = _preview_jpeg(self.server.board, path)
        if preview is not None:
            if preview:
                self._bytes(200, "image/jpeg", preview)
            else:
                self._json(404, {"ok": False, "error": "preview"})
            return
        self._json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        name = path.removeprefix("/api/")
        if name not in CONTROLS:
            self._json(404, {"ok": False, "error": "not_found"})
            return
        if not origin_allowed(self.headers.get("Origin"), self.headers.get("Host")):
            self._json(403, {"ok": False, "error": "origin"})
            return
        if not self._discard_body():
            return
        code, payload = self.server.board.submit(name)
        self._json(code, payload)

    def _discard_body(self) -> bool:
        raw = self.headers.get("Content-Length", "0") or "0"
        try:
            length = int(raw)
        except ValueError:
            self._json(400, {"ok": False, "error": "length"})
            return False
        if length < 0 or length > 4096:
            self._json(413, {"ok": False, "error": "body"})
            return False
        if length:
            self.rfile.read(length)
        return True

    def _json(self, code: int, payload: dict) -> None:
        self._bytes(code, "application/json; charset=utf-8", json.dumps(payload).encode())

    def _bytes(self, code: int, content_type: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


class ButtonServer:
    """Serve the phone page until ``stop`` (called from the record ``finally``)."""

    def __init__(self, board: ButtonBoard, host: str, port: int) -> None:
        self._httpd = _HTTPServer((host, port), board)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="record-buttons",
            daemon=True,
        )
        self._stopped = False

    @property
    def port(self) -> int:
        return int(self._httpd.server_address[1])

    @property
    def host(self) -> str:
        return str(self._httpd.server_address[0])

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=2.0)
        preview = self._httpd.board.preview
        if preview is not None and hasattr(preview, "close"):
            preview.close()

    def listen_lines(self) -> list[str]:
        """URLs a phone on this LAN can open."""
        host, port = self.host, self.port
        if host not in ("0.0.0.0", "::", ""):
            return [f"http://{host}:{port}/"]
        pairs = interface_ipv4()
        if not pairs:
            return [f"http://127.0.0.1:{port}/"]
        return [f"http://{ip}:{port}/  ({name})" for name, ip in pairs]


def start_button_server(
    events: dict,
    host: str,
    port: int,
    preview: object | None = None,
    session: object | None = None,
) -> ButtonServer | None:
    """Bind the phone page. Return None when the port is already taken.

    Recording continues on the keyboard either way.
    """
    try:
        server = ButtonServer(ButtonBoard(events, preview, session), host, port)
    except OSError as exc:
        logger.error("ブラウザボタンは起動できませんでした (%s)。キーボードの n / r / q で続けます。", exc)
        print(
            f"ブラウザボタンは起動できませんでした ({exc})。キーボードの n / r / q で続けます。",
            flush=True,
        )
        return None
    server.start()
    return server


# Printed URLs stay on Wi-Fi / Ethernet. Virtual nets still accept a connection
# because the socket is 0.0.0.0, but they are the wrong address to type on a phone.
_HIDDEN_IFACE_PREFIXES = (
    "docker",
    "br-",
    "veth",
    "tailscale",
    "zt",
    "virbr",
    "cni",
    "flannel",
    "tun",
    "tap",
    "wg",
)


def hidden_iface(name: str) -> bool:
    """True for loopback and virtual interfaces a phone should not open."""
    lowered = name.lower()
    return lowered == "lo" or lowered.startswith(_HIDDEN_IFACE_PREFIXES)


def preferred_interfaces(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Wi-Fi first, then Ethernet. Drop virtual interfaces."""
    visible = [(name, ip) for name, ip in pairs if not hidden_iface(name)]
    visible.sort(key=lambda item: (_iface_rank(item[0]), item[0]))
    return visible


def interface_ipv4() -> list[tuple[str, str]]:
    """LAN IPv4 addresses a phone on the same Wi-Fi can open."""
    try:
        names = [name for _index, name in socket.if_nameindex()]
    except OSError:
        names = []
    pairs: list[tuple[str, str]] = []
    for name in names:
        if hidden_iface(name):
            continue
        ip = _ipv4_of(name)
        if not ip or ip.startswith("127.") or ip.startswith("169.254."):
            continue
        pairs.append((name, ip))
    ordered = preferred_interfaces(pairs)
    if ordered:
        return ordered
    fallback = _udp_default_ipv4()
    if fallback:
        return [("default", fallback)]
    return []


def _iface_rank(name: str) -> int:
    lowered = name.lower()
    if lowered.startswith(("wl", "wlan", "wifi")):
        return 0
    if lowered.startswith(("en", "eth", "end")):
        return 1
    return 2


def _ipv4_of(name: str) -> str | None:
    try:
        import fcntl
    except ImportError:
        return None
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        packed = struct.pack("256s", name[:15].encode())
        try:
            res = fcntl.ioctl(sock.fileno(), _SIOCGIFADDR, packed)
        except OSError:
            return None
    finally:
        sock.close()
    return socket.inet_ntoa(res[20:24])


def _udp_default_ipv4() -> str | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        try:
            sock.connect(("8.8.8.8", 80))
        except OSError:
            return None
        ip = sock.getsockname()[0]
    finally:
        sock.close()
    if not ip or ip.startswith("127."):
        return None
    return ip
