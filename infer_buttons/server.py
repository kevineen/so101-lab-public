"""LAN page that starts, pauses, and scores robot_client inference trials.

Nothing here opens a robot serial port. Torque stays with the client process.
ESTOP remains a physical switch.
"""

from __future__ import annotations

import json
import logging
import socket
import struct
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

logger = logging.getLogger("infer_buttons")

_SIOCGIFADDR = 0x8915

CONTROLS = (
    "start",
    "halt",
    "pause",
    "success",
    "fail_no_reach",
    "fail_no_grasp",
    "fail_no_place",
    "fail_disturb",
    "undo",
    "nest",
    "bus_release",
    "model_prev",
    "model_next",
    "stop",
)

_MESSAGES = {
    "start": "ブラウザ: 試行を開始します。",
    "halt": "ブラウザ: 試行を終了し、結果入力へ。",
    "pause": "ブラウザ: 一時停止トグル。",
    "success": "ブラウザ: 成功として記録。",
    "fail_no_reach": "ブラウザ: 失敗 no_reach。",
    "fail_no_grasp": "ブラウザ: 失敗 no_grasp。",
    "fail_no_place": "ブラウザ: 失敗 no_place。",
    "fail_disturb": "ブラウザ: 失敗 disturb。",
    "undo": "ブラウザ: 直前の成功／失敗を取消。",
    "nest": "ブラウザ: nest トグル。",
    "bus_release": "ブラウザ: モータバス復旧（Port is in use 解除）。",
    "model_prev": "ブラウザ: 前のモデルへ。",
    "model_next": "ブラウザ: 次のモデルへ。",
    "stop": "ブラウザ: セッションを終了します。",
}

_PHASE_CONTROLS = {
    "ready": {"nest", "start", "bus_release", "model_prev", "model_next", "undo", "stop"},
    "running": {"halt", "pause", "bus_release", "stop"},
    "result": {
        "success",
        "fail_no_reach",
        "fail_no_grasp",
        "fail_no_place",
        "fail_disturb",
        "bus_release",
        "stop",
    },
    "idle": {"bus_release", "stop"},
}

PAGE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#111111">
<title>推論</title>
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
  #model { margin: 6px 0 0; color: #9ecbff; font-size: 0.95rem; word-break: break-all; }
  #hint { margin: 8px 0 0; color: #c8c8c8; line-height: 1.45; min-height: 3.2em; }
  main { flex: 1; display: flex; flex-direction: column; gap: 10px; padding: 12px; }
  button { border: 0; border-radius: 18px; font: inherit; touch-action: manipulation; }
  button[hidden] { display: none !important; }
  button.choice {
    flex: 1;
    min-height: 12vh;
    font-size: clamp(1.4rem, 6vw, 2.4rem);
    font-weight: 800;
  }
  button.choice small {
    display: block;
    margin-top: 6px;
    font-size: 0.9rem;
    font-weight: 600;
  }
  button.go { background: #3ddc84; color: #06210f; }
  button.halt { background: #f0c14a; color: #241c04; }
  button.danger { background: #e23b3b; color: #fff; }
  button.undo { background: #4a4a4a; color: #eee; min-height: 9vh; font-size: clamp(1.1rem, 4.5vw, 1.5rem); }
  button.nest { background: #6ec6ff; color: #071226; }
  button.nest.on { background: #3d8fd6; color: #fff; }
  button.pause { background: #8eb4ff; color: #071226; }
  button.fail {
    min-height: 9vh;
    font-size: clamp(1.1rem, 4.5vw, 1.6rem);
    background: #5a2a2a;
    color: #ffd7d7;
  }
  button.model { background: #3a3a3a; color: #eee; min-height: 9vh; font-size: clamp(1.1rem, 4.5vw, 1.5rem); }
  button.bus {
    min-height: 8vh;
    font-size: clamp(1.05rem, 4vw, 1.4rem);
    background: #4a3a1a;
    color: #ffe9b0;
  }
  #model-row { display: flex; gap: 8px; }
  #model-row[hidden] { display: none !important; }
  button.stop { margin: 0 12px 12px; height: 48px; background: #2a2a2a; color: #ddd; }
  button:disabled { opacity: 0.4; }
  #progress { margin: 8px 0 0; color: #d5d5d5; font-size: 1.05rem; }
  #score { margin: 4px 0 0; color: #b8b8b8; font-size: 0.95rem; }
  #clock {
    margin: 4px 0 0;
    font-size: 2rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    letter-spacing: 0.03em;
  }
  #load-panel {
    margin: 10px 0 0;
    padding: 12px;
    border-radius: 12px;
    background: #1c2838;
    border: 1px solid #3a5a7a;
  }
  #load-panel[hidden] { display: none !important; }
  #load-target { margin: 0 0 6px; color: #9ecbff; font-size: 0.95rem; word-break: break-all; }
  #load-msg { margin: 0 0 8px; color: #e8e8e8; font-size: 1.05rem; line-height: 1.35; }
  #load-bar {
    height: 14px;
    border-radius: 7px;
    background: #0d1520;
    overflow: hidden;
  }
  #load-fill {
    height: 100%;
    width: 0%;
    background: linear-gradient(90deg, #3d8fd6, #6ec6ff);
    transition: width 0.35s ease;
  }
  #load-meta {
    margin: 8px 0 0;
    color: #a8b8c8;
    font-size: 0.95rem;
    font-variant-numeric: tabular-nums;
  }
  #preview { display: flex; flex-direction: column; gap: 8px; }
  #preview[hidden] { display: none; }
  .cams { display: flex; gap: 8px; }
  .cams figure { margin: 0; flex: 1; }
  .cams img { width: 100%; background: #000; border-radius: 8px; }
  .cams figcaption { font-size: 0.8rem; color: #aaa; }
  #fails { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  #fails[hidden] { display: none !important; }
  footer { padding: 0 16px 16px; color: #8d8d8d; font-size: 0.85rem; line-height: 1.4; }
</style>
</head>
<body>
<header>
  <h1 id="title">待機</h1>
  <p id="model">—</p>
  <p id="progress">試行 —</p>
  <p id="score">成功 0</p>
  <p id="clock">0:00.0</p>
  <div id="load-panel" hidden>
    <p id="load-target">—</p>
    <p id="load-msg">読み込み中…</p>
    <div id="load-bar"><div id="load-fill"></div></div>
    <p id="load-meta">経過 0:00.0 · 0%</p>
  </div>
  <p id="hint">推論プロセスを待っています。</p>
</header>
<main>
  <div id="preview" hidden>
    <div class="cams" id="cams"></div>
  </div>
  <div id="model-row" hidden>
    <button class="choice model" type="button" id="model_prev">◀ 前のモデル<small id="model-prev-sub">一覧の前へ</small></button>
    <button class="choice model" type="button" id="model_next">次のモデル ▶<small id="model-next-sub">サーバで重みを読み直す</small></button>
  </div>
  <button class="choice nest" type="button" id="nest"><span id="nest-label">nest へ</span><small id="nest-sub">先に肩を上げてから nest へ</small></button>
  <button class="choice go" type="button" id="start">試行開始<small>ポリシーで腕を動かす</small></button>
  <button class="choice undo" type="button" id="undo">直前を取消<small>誤った成功／失敗を戻す</small></button>
  <button class="choice halt" type="button" id="halt">試行終了<small>結果を記録する</small></button>
  <button class="choice pause" type="button" id="pause"><span id="pause-label">一時停止</span><small id="pause-sub">行動だけ止める</small></button>
  <button class="choice go" type="button" id="success">成功<small>タスク完了</small></button>
  <div id="fails" hidden>
    <button class="choice fail" type="button" id="fail_no_reach">届かない<small>no_reach</small></button>
    <button class="choice fail" type="button" id="fail_no_grasp">把持失敗<small>no_grasp</small></button>
    <button class="choice fail" type="button" id="fail_no_place">置けない<small>no_place</small></button>
    <button class="choice fail" type="button" id="fail_disturb">暴走・停止<small>disturb</small></button>
  </div>
  <button class="choice bus" type="button" id="bus_release">バス復旧<small>Port is in use を解除</small></button>
</main>
<button class="stop" type="button" id="stop">セッション終了</button>
<footer>非常停止は手元の ESTOP です。この画面はトルクを切りません。一時停止中は行動キューを捨て、腕は現姿勢を保ちます。nest は先に shoulder_lift（2番）を上げてから他関節。誤記録は開始待ちの「直前を取消」。モデル切替中は進捗バーが出ます。「バス復旧」は Feetech の is_using 固まり（Port is in use）をクリアします。</footer>
<script>
const copy = {
  ready: ["開始待ち", "物を定位置に置き、必要なら nest。揃ったら試行開始。モデル切替もここ。"],
  running: ["推論中", "試行終了で結果入力へ。一時停止は行動だけ止めます。"],
  result: ["結果", "成功か失敗種別を押すと、次の開始待ちへ進みます。"],
  idle: ["待機", "次の試行を準備しています。"]
};
const buttons = ["nest", "start", "halt", "pause", "success", "undo", "bus_release"];
const visible = {
  ready: ["nest", "start", "bus_release"],
  running: ["halt", "pause", "bus_release"],
  result: ["success", "bus_release"],
  idle: ["bus_release"]
};
let liveKey = "";
let liveSeq = -1;

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

function renderLive(data) {
  const box = document.getElementById("preview");
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

function render(data) {
  const known = Object.prototype.hasOwnProperty.call(copy, data.phase);
  const phase = known ? data.phase : "idle";
  const row = copy[phase];
  const paused = Boolean(data.paused);
  const holdNest = Boolean(data.hold_nest);
  const switching = Boolean(data.switching);
  const loading = Boolean(data.loading) || switching || Boolean(data.load_phase);
  let title = row[0];
  if (data.stop) title = "停止中";
  else if (switching || data.load_phase === "wait_server" || data.load_phase === "send") title = "モデル読込中";
  else if (data.load_phase === "done") title = "読込完了";
  else if (data.load_phase === "error") title = "読込失敗";
  else if (paused) title = "一時停止";
  else if (data.serial_ok === false) title = "USB切断";
  else if (holdNest && phase === "ready") {
    title = data.nest_phase === "lift" ? "nest 肩上げ中" : "nest 保持中";
  }
  document.getElementById("title").textContent = title;
  const modelBits = [];
  if (data.model_id) modelBits.push(data.model_id);
  if (data.model_label) modelBits.push(data.model_label);
  else if (data.policy_type) modelBits.push(data.policy_type);
  if (data.model) modelBits.push(data.model);
  if (data.model_count) {
    const idx = Number(data.model_index) || 0;
    modelBits.push("(" + (idx + 1) + "/" + data.model_count + ")");
  }
  document.getElementById("model").textContent = modelBits.length ? modelBits.join(" · ") : "—";
  const loadPanel = document.getElementById("load-panel");
  loadPanel.hidden = !loading;
  if (loading) {
    document.getElementById("load-target").textContent = data.load_target || modelBits.join(" · ") || "—";
    document.getElementById("load-msg").textContent = data.load_message || "読み込み中…";
    const pct = Math.max(0, Math.min(100, Number(data.load_pct) || 0));
    document.getElementById("load-fill").style.width = pct + "%";
    document.getElementById("load-meta").textContent =
      "経過 " + fmt(data.load_elapsed_s) + " · " + pct + "%";
    document.getElementById("hint").textContent =
      data.load_message || "サーバが重みを読み込んでいます。数十秒かかることがあります。";
  }
  const total = Number(data.total) || 0;
  const trial = Number(data.trial) || 0;
  let progress = "試行 " + trial;
  if (total) progress += " / " + total;
  if (data.last_result) progress += " · 直前 " + data.last_result;
  document.getElementById("progress").textContent = progress;
  const fails = data.failures || {};
  const failSum = Object.keys(fails).reduce((n, k) => n + (Number(fails[k]) || 0), 0);
  document.getElementById("score").textContent =
    "成功 " + (Number(data.successes) || 0) + " · 失敗 " + failSum;
  let clock = fmt(data.elapsed_s);
  if (data.limit_s) clock += " / " + fmt(data.limit_s);
  document.getElementById("clock").textContent = "経過 " + clock;
  if (!loading) {
    if (data.serial_ok === false) {
      document.getElementById("hint").textContent =
        data.serial_message || "モータUSBが切れました。推論クライアントを再起動してください。";
    } else if (data.bus_message) {
      document.getElementById("hint").textContent = data.bus_message;
    } else if (holdNest && data.nest_message) {
      document.getElementById("hint").textContent =
        (data.nest_ok === false ? "⚠ " : "") + data.nest_message;
    } else {
      document.getElementById("hint").textContent = data.task || row[1];
    }
  }
  document.getElementById("pause-label").textContent = paused ? "再開" : "一時停止";
  document.getElementById("pause-sub").textContent = paused ? "行動を再開する" : "行動だけ止める";
  document.getElementById("nest-label").textContent = holdNest ? "nest 解除" : "nest へ";
  document.getElementById("nest-sub").textContent = holdNest
    ? (data.nest_message || "保持をやめて開始待ちのままにする")
    : "先に肩（2番）を上げてから nest へ";
  document.getElementById("nest").classList.toggle("on", holdNest);
  const show = visible[phase] || [];
  buttons.forEach((id) => {
    if (id === "undo") {
      document.getElementById(id).hidden =
        phase !== "ready" || switching || loading || !data.can_undo;
      return;
    }
    document.getElementById(id).hidden = show.indexOf(id) < 0 || switching || (loading && data.load_phase !== "done" && data.load_phase !== "error");
  });
  const canSwitch = phase === "ready" && !switching && !loading && Number(data.model_count || 0) > 1;
  document.getElementById("model-row").hidden = !canSwitch;
  document.getElementById("fails").hidden = phase !== "result" || switching;
  renderLive(data);
  document.getElementById("stop").disabled = Boolean(data.stop) || switching;
}

async function refresh() {
  try {
    const res = await fetch("/api/state", { cache: "no-store" });
    if (!res.ok) return;
    render(await res.json());
  } catch (err) {}
}

async function press(name) {
  try {
    const res = await fetch("/api/" + name, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    const data = await res.json();
    if (data && data.ok !== false) render(data);
    else await refresh();
  } catch (err) {
    await refresh();
  }
}

["nest", "start", "halt", "pause", "success", "undo", "bus_release", "fail_no_reach", "fail_no_grasp", "fail_no_place", "fail_disturb", "model_prev", "model_next", "stop"].forEach((id) => {
  document.getElementById(id).addEventListener("click", () => press(id));
});
setInterval(refresh, 400);
refresh();
</script>
</body>
</html>
"""


def apply_phone_control(name: str, events: dict) -> None:
    """Map one phone button onto the shared ``events`` dict."""
    phase = events.get("phase", "idle")
    if phase not in _PHASE_CONTROLS or name not in _PHASE_CONTROLS[phase]:
        raise ValueError("phase")
    if name == "pause":
        events["paused"] = not bool(events.get("paused"))
        events["pause_changed"] = True
    elif name == "nest":
        turning_on = not bool(events.get("hold_nest"))
        events["hold_nest"] = turning_on
        if turning_on:
            # Lift shoulder_lift first; control loop resets StagedNest.
            events["nest_reset"] = True
    elif name == "bus_release":
        events["release_bus"] = True
    elif name == "start":
        if events.get("switching"):
            raise ValueError("phase")
        events["start_trial"] = True
    elif name == "halt":
        events["end_trial"] = True
    elif name == "success":
        events["mark_success"] = True
    elif name.startswith("fail_"):
        events["mark_failure"] = name.removeprefix("fail_")
    elif name == "undo":
        if events.get("switching"):
            raise ValueError("phase")
        events["undo_last"] = True
    elif name == "model_prev":
        if events.get("switching"):
            raise ValueError("phase")
        events["model_delta"] = -1
    elif name == "model_next":
        if events.get("switching"):
            raise ValueError("phase")
        events["model_delta"] = 1
    elif name == "stop":
        events["stop_session"] = True
    else:
        raise ValueError(name)


def _live_jpeg(board: "ButtonBoard", path: str) -> bytes | None:
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


def origin_allowed(origin: str | None, host: str | None) -> bool:
    if not origin:
        return True
    if not host:
        return False
    return urlparse(origin).netloc == host


class ButtonBoard:
    """Thread-safe view of infer ``events`` plus preview and scoreboard."""

    def __init__(self, events: dict, preview: object | None = None, status: object | None = None) -> None:
        self.events = events
        self.preview = preview
        self.status = status
        self.last: str | None = None
        self._lock = threading.Lock()

    def snapshot(self) -> dict:
        with self._lock:
            return self._snapshot_locked()

    def _snapshot_locked(self) -> dict:
        phase = self.events.get("phase", "idle")
        if phase not in ("ready", "running", "result", "idle"):
            phase = "idle"
        pending = bool(
            self.events.get("start_trial")
            or self.events.get("end_trial")
            or self.events.get("mark_success")
            or self.events.get("mark_failure")
            or self.events.get("undo_last")
            or self.events.get("model_delta")
            or self.events.get("stop_session")
            or self.events.get("switching")
        )
        payload = {
            "ok": True,
            "phase": phase,
            "pending": pending,
            "stop": bool(self.events.get("stop_session")),
            "last": self.last,
            "cameras": [],
            "live_seq": 0,
            "paused": bool(self.events.get("paused")),
            "hold_nest": bool(self.events.get("hold_nest")),
            "switching": bool(self.events.get("switching")),
            "loading": False,
            "load_phase": "",
            "load_message": "",
            "load_target": "",
            "load_pct": 0,
            "load_elapsed_s": 0.0,
            "model": "",
            "policy_type": "",
            "task": "",
            "model_id": "",
            "model_label": "",
            "model_index": 0,
            "model_count": 0,
            "trial": 0,
            "total": 0,
            "successes": 0,
            "failures": {},
            "last_result": "",
            "can_undo": False,
            "nest_phase": "",
            "nest_message": "",
            "nest_ok": True,
            "serial_ok": True,
            "serial_message": "",
            "bus_message": "",
            "elapsed_s": 0.0,
            "limit_s": 0.0,
        }
        if self.preview is not None:
            info = self.preview.info()
            payload["cameras"] = info.get("cameras") or []
            payload["live_seq"] = int(info.get("live_seq") or 0)
        if self.status is not None:
            payload.update(self.status.public())
        payload["paused"] = bool(self.events.get("paused"))
        payload["hold_nest"] = bool(self.events.get("hold_nest"))
        return payload

    def submit(self, name: str) -> tuple[int, dict]:
        if name not in CONTROLS:
            return 400, {"ok": False, "error": "unknown", **self.snapshot()}
        with self._lock:
            pending = (
                self.events.get("start_trial")
                or self.events.get("end_trial")
                or self.events.get("mark_success")
                or self.events.get("mark_failure")
                or self.events.get("undo_last")
                or self.events.get("model_delta")
                or self.events.get("stop_session")
                or self.events.get("switching")
            )
            # nest / pause / bus_release stay clickable while another action is pending.
            if name not in ("nest", "pause", "bus_release") and pending:
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
                    "ブラウザ: 一時停止。行動を止めます。"
                    if self.events.get("paused")
                    else "ブラウザ: 再開。行動を進めます。"
                )
            elif name == "nest":
                message = (
                    "ブラウザ: nest へ移動／保持します。"
                    if self.events.get("hold_nest")
                    else "ブラウザ: nest 保持を解除します。"
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
        return

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._bytes(200, "text/html; charset=utf-8", PAGE.encode())
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
    def __init__(self, board: ButtonBoard, host: str, port: int) -> None:
        self._httpd = _HTTPServer((host, port), board)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="infer-buttons",
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
        self._thread.join(timeout=2.0)


def list_lan_urls(port: int) -> list[str]:
    """Best-effort LAN URLs for the phone (same Wi-Fi as the Pi)."""
    urls: list[str] = []
    seen: set[str] = set()
    try:
        import fcntl
    except ImportError:
        fcntl = None  # type: ignore[assignment]
    if fcntl is not None:
        for iface in ("wlan0", "eth0", "en0", "enp0s3"):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                packed = struct.pack("256s", iface.encode("utf-8")[:15])
                res = fcntl.ioctl(sock.fileno(), _SIOCGIFADDR, packed)
                addr = socket.inet_ntoa(res[20:24])
                sock.close()
            except OSError:
                continue
            if addr.startswith("127."):
                continue
            url = f"http://{addr}:{port}/"
            if url not in seen:
                seen.add(url)
                urls.append(url)
    if not urls:
        try:
            hostname = socket.gethostname()
            for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
                addr = info[4][0]
                if addr.startswith("127."):
                    continue
                url = f"http://{addr}:{port}/"
                if url not in seen:
                    seen.add(url)
                    urls.append(url)
        except OSError:
            pass
    return urls


def start_button_server(
    events: dict,
    *,
    preview: object | None = None,
    status: object | None = None,
    host: str | None = None,
    port: int | None = None,
) -> ButtonServer:
    import os

    bind_host = host or os.environ.get("SO101_INFER_BUTTONS_HOST", "0.0.0.0")
    bind_port = int(port if port is not None else os.environ.get("SO101_INFER_BUTTONS_PORT", "8771"))
    board = ButtonBoard(events, preview=preview, status=status)
    server = ButtonServer(board, bind_host, bind_port)
    server.start()
    urls = list_lan_urls(server.port)
    print(f"Infer phone UI on port {server.port}", flush=True)
    for url in urls:
        print(f"  open on phone: {url}", flush=True)
    if not urls:
        print(f"  open on phone: http://<pi-ip>:{server.port}/", flush=True)
    return server
