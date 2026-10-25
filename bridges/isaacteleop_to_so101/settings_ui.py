"""Touch-friendly teleop settings UI for Meta Quest Browser (and desktop).

Edits ``configs/quest_teleop.local.overrides.yaml`` which the Pi receiver
hot-reloads. Open while CloudXR is paused (Quest menu → Browser).

  python -m bridges.isaacteleop_to_so101.settings_ui --port 8766
"""

from __future__ import annotations

import argparse
import json
import logging
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .controls import (
    load_raw_teleop_dict,
    load_teleop_config,
    overrides_path_for,
    save_teleop_overrides,
)

logger = logging.getLogger(__name__)

_HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1"/>
<title>Quest Teleop 設定</title>
<style>
  :root { color-scheme: dark; }
  body { font-family: system-ui, sans-serif; margin: 0; padding: 1rem;
         background: #111; color: #eee; font-size: 18px; }
  h1 { font-size: 1.4rem; margin: 0 0 .5rem; }
  .hint { color: #aaa; font-size: .95rem; margin-bottom: 1rem; }
  section { background: #1c1c1c; border-radius: 12px; padding: 1rem;
            margin-bottom: 1rem; }
  label { display: block; margin: .6rem 0 .25rem; color: #ccc; }
  input[type=number], select { font-size: 1.2rem; padding: .55rem .7rem;
    width: 100%; max-width: 280px; border-radius: 8px; border: 1px solid #444;
    background: #222; color: #fff; box-sizing: border-box; }
  .row { display: flex; flex-wrap: wrap; gap: .6rem; align-items: center; }
  button, .btn { font-size: 1.15rem; padding: .75rem 1rem; border-radius: 10px;
    border: none; background: #3a7afe; color: #fff; min-height: 48px;
    min-width: 7rem; cursor: pointer; }
  button.secondary { background: #444; }
  button.danger { background: #a33; }
  .status { margin-top: 1rem; padding: .75rem; border-radius: 8px;
            background: #243; white-space: pre-wrap; }
  .axis-grid { display: grid; grid-template-columns: 4rem 1fr; gap: .5rem;
               align-items: center; max-width: 360px; }
</style>
</head>
<body>
  <h1>Quest Teleop 設定</h1>
  <p class="hint">CloudXR を一旦メニューに戻し、このページで変更 → 保存。
     Pi が数秒以内にホットリロードします（receiver 再起動不要）。</p>

  <section>
    <h2>感度</h2>
    <label>pos_scale（動きの大きさ）</label>
    <input id="pos_scale" type="number" step="0.05" min="0.05" max="2" value="1"/>
    <div class="row" style="margin-top:.6rem">
      <button type="button" class="secondary" onclick="bumpScale(-0.1)">−0.1</button>
      <button type="button" class="secondary" onclick="bumpScale(0.1)">+0.1</button>
    </div>
  </section>

  <section>
    <h2>軸マップ（奥手前・左右・上下）</h2>
    <p class="hint">robot 軸 ← Quest 軸。符号で向き反転。</p>
    <div class="axis-grid">
      <div>前後 x</div><select id="map_x"></select>
      <div>左右 y</div><select id="map_y"></select>
      <div>上下 z</div><select id="map_z"></select>
    </div>
    <div class="row" style="margin-top:.6rem">
      <button type="button" class="secondary" onclick="flip('x')">前後 反転</button>
      <button type="button" class="secondary" onclick="flip('y')">左右 反転</button>
      <button type="button" class="secondary" onclick="flip('z')">上下 反転</button>
    </div>
  </section>

  <section>
    <h2>ソフト可動範囲</h2>
    <label><input id="safety_enabled" type="checkbox"/> safety.enabled</label>
    <p class="hint">詳細な関節 min/max は YAML の safety を編集。ここでは ON/OFF と
       先端 Z の床だけ素早く触れます。</p>
    <label>tip Z 下限 (m)</label>
    <input id="tip_z_lo" type="number" step="0.01" value="0.04"/>
    <label>tip Z 上限 (m)</label>
    <input id="tip_z_hi" type="number" step="0.01" value="0.38"/>
  </section>

  <div class="row">
    <button type="button" onclick="save()">保存して反映</button>
    <button type="button" class="secondary" onclick="reload()">再読込</button>
    <button type="button" class="danger" onclick="clearOverrides()">上書き削除</button>
  </div>
  <div id="status" class="status">読み込み中…</div>

<script>
const AXIS_OPTS = ["x","-x","y","-y","z","-z"];
function fillSelect(id, cur) {
  const el = document.getElementById(id);
  el.innerHTML = "";
  for (const o of AXIS_OPTS) {
    const opt = document.createElement("option");
    opt.value = o; opt.textContent = o;
    if (o === cur) opt.selected = true;
    el.appendChild(opt);
  }
}
function flip(axis) {
  const el = document.getElementById("map_" + axis);
  const v = el.value;
  el.value = v.startsWith("-") ? v.slice(1) : ("-" + v);
}
function bumpScale(d) {
  const el = document.getElementById("pos_scale");
  el.value = Math.max(0.05, Math.min(2, Number(el.value) + d)).toFixed(2);
}
async function reload() {
  const r = await fetch("/api/config");
  const j = await r.json();
  document.getElementById("pos_scale").value = j.motion.pos_scale;
  fillSelect("map_x", j.motion.axis_map.x);
  fillSelect("map_y", j.motion.axis_map.y);
  fillSelect("map_z", j.motion.axis_map.z);
  document.getElementById("safety_enabled").checked = !!j.safety.enabled;
  const tip = (j.safety.tip_bounds_m && j.safety.tip_bounds_m["*"]) || {};
  if (tip.z) {
    document.getElementById("tip_z_lo").value = tip.z[0];
    document.getElementById("tip_z_hi").value = tip.z[1];
  }
  document.getElementById("status").textContent =
    "読込OK\\noverrides: " + (j.overrides_path || "(なし)");
}
async function save() {
  const body = {
    motion: {
      pos_scale: Number(document.getElementById("pos_scale").value),
      axis_map: {
        x: document.getElementById("map_x").value,
        y: document.getElementById("map_y").value,
        z: document.getElementById("map_z").value,
      },
    },
    safety: {
      enabled: document.getElementById("safety_enabled").checked,
      tip_bounds_m: {
        "*": {
          z: [
            Number(document.getElementById("tip_z_lo").value),
            Number(document.getElementById("tip_z_hi").value),
          ],
        },
      },
    },
  };
  const r = await fetch("/api/config", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body),
  });
  const j = await r.json();
  document.getElementById("status").textContent =
    j.ok ? ("保存しました\\n" + j.overrides_path) : ("失敗: " + JSON.stringify(j));
}
async function clearOverrides() {
  if (!confirm("ローカル上書きを削除しますか？")) return;
  const r = await fetch("/api/overrides", {method: "DELETE"});
  const j = await r.json();
  document.getElementById("status").textContent = JSON.stringify(j);
  await reload();
}
reload();
</script>
</body>
</html>
"""


def _lan_ip() -> str:
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "127.0.0.1"


def _push_patch_to_pi(bridge_host: str, bridge_port: int, overlay: dict[str, Any]) -> dict[str, Any]:
    """One-shot WebSocket teleop_config_patch to the Pi receiver."""
    import asyncio

    import websockets

    async def _run() -> dict[str, Any]:
        uri = f"ws://{bridge_host}:{bridge_port}/teleop"
        async with websockets.connect(uri, open_timeout=5, max_size=2**20) as ws:
            hello = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            if not hello.get("ok"):
                return {"ok": False, "error": "bad_hello", "hello": hello}
            await ws.send(
                json.dumps(
                    {"type": "teleop_config_patch", "overlay": overlay},
                    separators=(",", ":"),
                )
            )
            ack = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            return ack if isinstance(ack, dict) else {"ok": False, "error": "bad_ack"}

    return asyncio.run(_run())


def make_handler(
    config_path: Path,
    *,
    bridge_host: str | None = None,
    bridge_port: int = 8870,
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            logger.info("%s - " + fmt, self.address_string(), *args)

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, payload: dict[str, Any]) -> None:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send(code, raw, "application/json; charset=utf-8")

        def do_GET(self) -> None:  # noqa: N802
            if self.path in {"/", "/index.html"}:
                self._send(200, _HTML.encode("utf-8"), "text/html; charset=utf-8")
                return
            if self.path.startswith("/api/config"):
                data, base, ov = load_raw_teleop_dict(config_path)
                motion = data.get("motion") or {}
                safety = data.get("safety") or {}
                self._json(
                    200,
                    {
                        "ok": True,
                        "config_path": str(base),
                        "overrides_path": str(ov) if ov.is_file() else None,
                        "bridge_host": bridge_host,
                        "motion": {
                            "pos_scale": float(motion.get("pos_scale", 1.0)),
                            "axis_map": dict(motion.get("axis_map") or {}),
                            "mode": motion.get("mode"),
                        },
                        "safety": safety,
                    },
                )
                return
            self._json(404, {"ok": False, "error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/api/config":
                self._json(404, {"ok": False, "error": "not_found"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                self._json(400, {"ok": False, "error": "bad_json"})
                return
            if not isinstance(payload, dict):
                self._json(400, {"ok": False, "error": "need_object"})
                return
            # Validate by merging+loading locally, then push to Pi if configured.
            try:
                ov = save_teleop_overrides(payload, config_path=config_path)
                load_teleop_config(config_path)
            except Exception as exc:  # noqa: BLE001
                self._json(400, {"ok": False, "error": str(exc)})
                return
            pi_ack: dict[str, Any] | None = None
            if bridge_host:
                try:
                    pi_ack = _push_patch_to_pi(bridge_host, bridge_port, payload)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("push to Pi failed")
                    pi_ack = {"ok": False, "error": str(exc)}
            self._json(
                200,
                {
                    "ok": True,
                    "overrides_path": str(ov),
                    "pi": pi_ack,
                },
            )

        def do_DELETE(self) -> None:  # noqa: N802
            if self.path != "/api/overrides":
                self._json(404, {"ok": False, "error": "not_found"})
                return
            ov = overrides_path_for(config_path)
            if ov.is_file():
                ov.unlink()
            self._json(200, {"ok": True, "deleted": str(ov)})

    return Handler


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[2]
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, default=root / "configs" / "quest_teleop.yaml")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8766)
    p.add_argument(
        "--bridge-host",
        default=None,
        help="Pi IP — push patches over ws://PI:8870/teleop (recommended)",
    )
    p.add_argument("--bridge-port", type=int, default=8870)
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    lan = _lan_ip()
    handler = make_handler(
        args.config,
        bridge_host=args.bridge_host,
        bridge_port=args.bridge_port,
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Quest settings UI: http://{lan}:{args.port}/")
    print(f"Config base: {args.config}")
    print(f"Overrides:   {overrides_path_for(args.config)}")
    if args.bridge_host:
        print(f"Pi sync:     ws://{args.bridge_host}:{args.bridge_port}/teleop")
    else:
        print("Pi sync:     (none — pass --bridge-host <PiIP> so Save reaches the Pi)")
    print("Open in Meta Quest Browser (exit CloudXR immersive first). Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
