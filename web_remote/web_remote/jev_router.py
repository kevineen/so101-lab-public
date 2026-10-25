"""Optional text Jev call for the gray zone between cruise and approach.

Jev does not see pixels and does not emit joint targets. The motor loop never
waits on this client. A later image model should fill :class:`SceneState`
upstream; the questions here can stay the same.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Callable

from .scene_state import SceneState

logger = logging.getLogger(__name__)

JEV_MODEL = "jev-1.13.0"
CONFIDENCE_MIN = 0.6
_TIMEOUT_S = 0.8

Poster = Callable[[dict[str, Any]], dict[str, Any]]


def interpret_answers(payload: dict[str, Any]) -> tuple[str, str] | None:
    """Map a System One response to ``(mode, reason)``, or None when unsure."""
    answers = payload.get("answers")
    if not isinstance(answers, dict):
        return None
    near = answers.get("near_object")
    noul = near.get("noul") if isinstance(near, dict) else None
    if isinstance(noul, (int, float)) and float(noul) >= CONFIDENCE_MIN:
        return "approach", "jev_near"
    mode = answers.get("mode")
    if not isinstance(mode, dict):
        return None
    choice = mode.get("choice")
    confidence = mode.get("confidence")
    if choice in {"cruise", "approach"} and isinstance(confidence, (int, float)):
        if float(confidence) >= CONFIDENCE_MIN:
            return str(choice), "jev"
    return None


def _questions() -> dict[str, Any]:
    return {
        "mode": {
            "type": "choice",
            "instructions": (
                "Choose the motor-loop mode from perception. "
                "approach means move carefully. cruise means the faster loop is appropriate."
            ),
            "criteria": {
                "cruise": "Nothing nearby is confirmed, and a faster move is acceptable.",
                "approach": "The arm is near an object or the edge of the workspace.",
            },
        },
        "near_object": {
            "type": "noul",
            "instructions": "The arm is close enough to a physical object that it should slow down.",
            "criteria": {
                "true": "perception.proximity is near_object, or the summary says an object is close",
                "false": "perception.proximity is clear or unknown",
            },
        },
    }


class JevRouter:
    """Ask Jev which expert to use. Disabled when ``TYPESAFE_API_KEY`` is unset."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        poster: Poster | None = None,
    ) -> None:
        if api_key is None:
            api_key = os.environ.get("TYPESAFE_API_KEY", "")
        self._api_key = api_key.strip()
        self._model = model or os.environ.get("TYPESAFE_MODEL", JEV_MODEL)
        root = (base_url or os.environ.get("TYPESAFE_BASE_URL", "https://api.typesafe.ai")).rstrip("/")
        self._url = f"{root}/v1/systemone"
        self._poster = poster
        self.enabled = bool(self._api_key) or poster is not None

    def choose_mode(
        self,
        scene: SceneState,
        *,
        command_motion: str,
        joint_near_edge: bool,
    ) -> tuple[str, str] | None:
        """Return cruise or approach when Jev is confident enough."""
        if not self.enabled:
            return None
        payload = {
            "model": self._model,
            "state": {
                "perception": {
                    "motion": scene.motion,
                    "proximity": scene.proximity,
                    "workspace": scene.workspace,
                    "summary": scene.summary,
                    "command": command_motion,
                    "joint_near_calibrated_edge": joint_near_edge,
                }
            },
            "questions": _questions(),
        }
        try:
            body = self._post(payload)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
            logger.warning("Jev mode query failed", exc_info=True)
            return None
        return interpret_answers(body)

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._poster is not None:
            return self._poster(payload)
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self._url,
            data=data,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
            parsed = json.loads(response.read().decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("Jev response was not an object")
        return parsed
