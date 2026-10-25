"""FastAPI app: MJPEG streams + dual-arm joint teleop for SO-101."""

from __future__ import annotations

import argparse
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import (
    ARM_FOLLOWER,
    DEFAULT_CONFIG_PATH,
    JOINT_KEYS,
    JOINT_LIMITS,
    build_web_remote_config,
)
from .session import CameraOnlySession, RobotSession

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

# Polled by the browser. Repeating 200s hide overload and ESTOP lines.
_QUIET_GET_PATHS = frozenset({"/api/state", "/api/calibration"})


class QuietPollAccessFilter(logging.Filter):
    """Show poll access lines only when the HTTP status changes."""

    def __init__(self) -> None:
        super().__init__()
        self._last_status: dict[str, int] = {}

    def filter(self, record: logging.LogRecord) -> bool:
        parsed = _parse_access_args(record.args)
        if parsed is None:
            return True
        method, path, status = parsed
        if method != "GET" or path not in _QUIET_GET_PATHS:
            return True
        previous = self._last_status.get(path)
        self._last_status[path] = status
        return previous != status


def _parse_access_args(args: object) -> tuple[str, str, int] | None:
    """Return method, path, and status from a uvicorn access log record."""
    if not isinstance(args, tuple) or len(args) < 5:
        return None
    method, full_path, status = args[1], args[2], args[4]
    if not isinstance(method, str) or not isinstance(full_path, str):
        return None
    try:
        code = int(status)
    except (TypeError, ValueError):
        return None
    return method, full_path.split("?", 1)[0], code


def _install_access_filter() -> None:
    """Attach the poll filter after uvicorn has configured its access logger."""
    access = logging.getLogger("uvicorn.access")
    if any(isinstance(existing, QuietPollAccessFilter) for existing in access.filters):
        return
    access.addFilter(QuietPollAccessFilter())

_session: RobotSession | CameraOnlySession | None = None


class ActionBody(BaseModel):
    """Joint targets for one arm (motor names without .pos suffix)."""

    arm: str = ARM_FOLLOWER
    joints: dict[str, float] = Field(default_factory=dict)


class CalibArmBody(BaseModel):
    """Select which arm enters / is shown for calibration."""

    arm: str = ARM_FOLLOWER


class CalibMotorsBody(BaseModel):
    """Motor name list for midpoint / range recording / capture."""

    motors: list[str] = Field(default_factory=list)


class CalibCaptureBody(BaseModel):
    """Capture current encoder as range min or max for selected motors."""

    motors: list[str] = Field(default_factory=list)
    endpoint: str = "min"  # min | max


class CalibUpdateBody(BaseModel):
    """Manual draft edits: motor → {homing_offset, range_min, range_max}."""

    motors: dict[str, dict[str, int]] = Field(default_factory=dict)


class CalibDriveBody(BaseModel):
    """Toggle powered browser jog during calibration (torque on / off)."""

    enabled: bool = False


class CalibJogBody(BaseModel):
    """Raw encoder deltas per motor while calib drive is enabled."""

    deltas: dict[str, int] = Field(default_factory=dict)


class TeleopBody(BaseModel):
    """Enable or disable browser teleop for one arm (others stay soft)."""

    enabled: bool = True
    arm: str | None = None


class ControlModeBody(BaseModel):
    """browser = slider drive; leader_follow = physical leader → follower."""

    mode: str = "browser"


class HomeBody(BaseModel):
    """Optional arm for nest save / go-home (omit = all configured arms)."""

    arm: str | None = None


def get_session() -> RobotSession | CameraOnlySession:
    if _session is None:
        raise HTTPException(status_code=503, detail="robot_not_ready")
    return _session


def _require_arms() -> RobotSession:
    session = get_session()
    if getattr(session, "cameras_only", False):
        raise HTTPException(
            status_code=503,
            detail="cameras_only_mode — arm APIs disabled; use bridge for teleop",
        )
    assert isinstance(session, RobotSession)
    return session


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Connect hardware on startup; disconnect on shutdown."""
    _install_access_filter()
    global _session
    cfg_path = Path(app.state.config_path)
    enable_leader = bool(getattr(app.state, "enable_leader", True))
    cameras_only = bool(getattr(app.state, "cameras_only", False))
    bundle = build_web_remote_config(
        cfg_path,
        follower_id=str(app.state.robot_id),
        leader_id=str(getattr(app.state, "leader_id", "my_leader_drive")),
        enable_leader=enable_leader,
    )
    if cameras_only:
        session: RobotSession | CameraOnlySession = CameraOnlySession(bundle)
        session.connect()
        _session = session
        logger.info("Web Remote cameras-only ready (cams=%s)", session.camera_names)
    else:
        session = RobotSession(bundle, control_hz=float(app.state.control_hz))
        session.connect()
        _session = session
        logger.info("Web Remote ready (arms=%s)", session.arm_names)
    try:
        yield
    finally:
        session.disconnect()
        _session = None
        logger.info("Web Remote stopped")


app = FastAPI(title="SO-101 Web Remote", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    index_path = STATIC_DIR / "index.html"
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.get("/api/info")
def api_info() -> dict[str, Any]:
    session = get_session()
    profiles = {name: session.drive_profile(name).to_public_dict() for name in session.arm_names}
    return {
        "ok": True,
        "arms": session.arm_names,
        "joints": JOINT_KEYS,
        "limits": {k: {"min": lo, "max": hi} for k, (lo, hi) in JOINT_LIMITS.items()},
        "cameras": session.camera_names,
        "cameras_only": bool(getattr(session, "cameras_only", False)),
        "drive_profiles": profiles,
        "hand_teleop_available": bool(getattr(session, "hand_teleop_available", False)),
        "control_mode": getattr(session, "control_mode", "browser"),
        "control_modes": ["browser", "leader_follow"],
    }


@app.get("/api/state")
def api_state() -> dict[str, Any]:
    return get_session().get_state()


@app.post("/api/action")
def api_action(
    body: ActionBody,
    x_client_token: str | None = Header(default=None, alias="X-Client-Token"),
) -> JSONResponse:
    token = x_client_token or "anonymous"
    result = _require_arms().set_action(body.joints, arm=body.arm, token=token)
    status = 200 if result.get("ok") else 409
    return JSONResponse(result, status_code=status)


@app.post("/api/estop")
def api_estop() -> JSONResponse:
    result = _require_arms().trigger_estop()
    status = 200 if result.get("ok") else 409
    return JSONResponse(result, status_code=status)


@app.post("/api/estop/clear")
def api_estop_clear() -> JSONResponse:
    result = _require_arms().clear_estop()
    status = 200 if result.get("ok") else 409
    return JSONResponse(result, status_code=status)


@app.post("/api/teleop")
def api_teleop(
    body: TeleopBody,
    x_client_token: str | None = Header(default=None, alias="X-Client-Token"),
) -> JSONResponse:
    token = x_client_token or "anonymous"
    result = _require_arms().set_teleop(body.enabled, token, arm=body.arm)
    status = 200 if result.get("ok") else 409
    return JSONResponse(result, status_code=status)


@app.post("/api/control_mode")
def api_control_mode(
    body: ControlModeBody,
    x_client_token: str | None = Header(default=None, alias="X-Client-Token"),
) -> JSONResponse:
    """Switch browser drive ↔ classic leader→follower hand teleop."""
    token = x_client_token or "anonymous"
    result = _require_arms().set_control_mode(body.mode, token)
    status = 200 if result.get("ok") else 409
    return JSONResponse(result, status_code=status)


@app.post("/api/release")
def api_release(x_client_token: str | None = Header(default=None, alias="X-Client-Token")) -> dict[str, Any]:
    token = x_client_token or "anonymous"
    _require_arms().release_client(token)
    return {"ok": True}


@app.get("/api/home")
def api_home_get() -> dict[str, Any]:
    """Saved nest poses (per arm) used by H / 初期位置へ戻る / post-inference go-home."""
    return _require_arms().get_home()


@app.post("/api/home/save")
def api_home_save(
    body: HomeBody,
    x_client_token: str | None = Header(default=None, alias="X-Client-Token"),
) -> JSONResponse:
    token = x_client_token or "anonymous"
    result = _require_arms().save_home(arm=body.arm, token=token)
    status = 200 if result.get("ok") else 409
    return JSONResponse(result, status_code=status)


@app.post("/api/home/go")
def api_home_go(
    body: HomeBody,
    x_client_token: str | None = Header(default=None, alias="X-Client-Token"),
) -> JSONResponse:
    token = x_client_token or "anonymous"
    result = _require_arms().go_home(arm=body.arm, token=token)
    status = 200 if result.get("ok") else 409
    return JSONResponse(result, status_code=status)


def _calib_status(result: dict[str, Any]) -> JSONResponse:
    """Return 200 for ok, 409 for recoverable client/calib errors."""
    status = 200 if result.get("ok") else 409
    return JSONResponse(result, status_code=status)


@app.get("/api/calibration")
def api_calibration_get(arm: str = ARM_FOLLOWER) -> JSONResponse:
    return _calib_status(_require_arms().get_calibration(arm))


@app.post("/api/calibration/enter")
def api_calibration_enter(
    body: CalibArmBody,
    x_client_token: str | None = Header(default=None, alias="X-Client-Token"),
) -> JSONResponse:
    token = x_client_token or "anonymous"
    return _calib_status(_require_arms().enter_calibration(body.arm, token))


@app.post("/api/calibration/mid")
def api_calibration_mid(
    body: CalibMotorsBody,
    x_client_token: str | None = Header(default=None, alias="X-Client-Token"),
) -> JSONResponse:
    token = x_client_token or "anonymous"
    return _calib_status(_require_arms().calib_set_midpoint(body.motors, token))


@app.post("/api/calibration/range/start")
def api_calibration_range_start(
    body: CalibMotorsBody,
    x_client_token: str | None = Header(default=None, alias="X-Client-Token"),
) -> JSONResponse:
    token = x_client_token or "anonymous"
    return _calib_status(_require_arms().calib_start_range(body.motors, token))


@app.post("/api/calibration/range/stop")
def api_calibration_range_stop(
    x_client_token: str | None = Header(default=None, alias="X-Client-Token"),
) -> JSONResponse:
    token = x_client_token or "anonymous"
    return _calib_status(_require_arms().calib_stop_range(token))


@app.post("/api/calibration/capture")
def api_calibration_capture(
    body: CalibCaptureBody,
    x_client_token: str | None = Header(default=None, alias="X-Client-Token"),
) -> JSONResponse:
    token = x_client_token or "anonymous"
    return _calib_status(_require_arms().calib_capture_endpoint(body.motors, body.endpoint, token))


@app.post("/api/calibration/update")
def api_calibration_update(
    body: CalibUpdateBody,
    x_client_token: str | None = Header(default=None, alias="X-Client-Token"),
) -> JSONResponse:
    token = x_client_token or "anonymous"
    return _calib_status(_require_arms().calib_update_draft(body.motors, token))


@app.post("/api/calibration/drive")
def api_calibration_drive(
    body: CalibDriveBody,
    x_client_token: str | None = Header(default=None, alias="X-Client-Token"),
) -> JSONResponse:
    token = x_client_token or "anonymous"
    return _calib_status(_require_arms().calib_set_drive(body.enabled, token))


@app.post("/api/calibration/jog")
def api_calibration_jog(
    body: CalibJogBody,
    x_client_token: str | None = Header(default=None, alias="X-Client-Token"),
) -> JSONResponse:
    token = x_client_token or "anonymous"
    return _calib_status(_require_arms().calib_jog(body.deltas, token))


@app.post("/api/calibration/save")
def api_calibration_save(
    x_client_token: str | None = Header(default=None, alias="X-Client-Token"),
) -> JSONResponse:
    token = x_client_token or "anonymous"
    return _calib_status(_require_arms().save_calibration(token))


@app.post("/api/calibration/cancel")
def api_calibration_cancel(
    x_client_token: str | None = Header(default=None, alias="X-Client-Token"),
) -> JSONResponse:
    token = x_client_token or "anonymous"
    return _calib_status(_require_arms().cancel_calibration(token))


@app.get("/api/stream/{cam_name}")
def api_stream(cam_name: str, request: Request) -> StreamingResponse:
    session = get_session()
    if cam_name not in session.camera_names:
        raise HTTPException(status_code=404, detail=f"unknown_camera:{cam_name}")

    def generate() -> Any:
        boundary = b"--frame"
        while True:
            jpeg = session.get_jpeg(cam_name)
            if jpeg is None:
                time.sleep(0.05)
                continue
            yield (
                boundary
                + b"\r\nContent-Type: image/jpeg\r\nContent-Length: "
                + str(len(jpeg)).encode()
                + b"\r\n\r\n"
                + jpeg
                + b"\r\n"
            )
            time.sleep(1.0 / 15.0)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"},
    )


@app.get("/api/client-token")
def api_client_token() -> dict[str, str]:
    return {"token": str(uuid.uuid4())}


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="SO-101 browser teleop (1–2 arms) + camera MJPEG")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to so101_dual_cam.yaml (or compatible)",
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--robot-id", default="my_follower", help="Calibration id for follower arm")
    parser.add_argument("--leader-id", default="my_leader_drive", help="Calibration id for leader port (driven as follower)")
    parser.add_argument("--no-leader", action="store_true", help="Connect follower arm only")
    parser.add_argument("--control-hz", type=float, default=40.0)
    parser.add_argument("--dry-run", action="store_true", help="Start HTTP only (skip robot connect)")
    parser.add_argument(
        "--cameras-only",
        action="store_true",
        help="Open cameras + MJPEG only (no serial). Safe alongside bridge receiver.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(asctime)s %(name)s: %(message)s")

    import uvicorn

    if args.dry_run and args.cameras_only:
        raise SystemExit("Use either --dry-run or --cameras-only, not both")

    if args.dry_run:

        @asynccontextmanager
        async def dry_lifespan(_app: FastAPI) -> AsyncIterator[None]:
            _install_access_filter()
            yield

        app.router.lifespan_context = dry_lifespan

    app.state.config_path = str(args.config)
    app.state.robot_id = args.robot_id
    app.state.leader_id = args.leader_id
    app.state.enable_leader = not args.no_leader
    app.state.control_hz = args.control_hz
    app.state.cameras_only = bool(args.cameras_only)

    lan = ""
    try:
        import socket

        lan = socket.gethostbyname(socket.gethostname())
    except Exception:
        pass

    logger.info("Listening on http://%s:%s/", args.host, args.port)
    if args.cameras_only:
        logger.info("Mode: cameras-only (no arm serial)")
    if lan:
        logger.info("Open from another PC: http://%s:%s/", lan, args.port)

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
