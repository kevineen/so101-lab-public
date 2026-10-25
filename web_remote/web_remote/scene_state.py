"""Shared perception output for the rate router.

Center-camera processing and a future image model both write this type.
The router and the motor experts read it and never see pixels.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Motion = Literal["still", "moving", "fast"]
Proximity = Literal["clear", "near_object", "unknown"]
Workspace = Literal["inside", "near_edge", "unknown"]

MOTIONS: frozenset[str] = frozenset({"still", "moving", "fast"})
PROXIMITIES: frozenset[str] = frozenset({"clear", "near_object", "unknown"})
WORKSPACES: frozenset[str] = frozenset({"inside", "near_edge", "unknown"})


@dataclass
class SceneState:
    """One look at the arm's motion, nearby objects, and visible workspace.

    ``source`` is ``center_cv`` for the lightweight camera watcher. A later
    image model should write the same fields with ``source="image_jev"``.
    """

    motion: Motion = "still"
    proximity: Proximity = "unknown"
    workspace: Workspace = "unknown"
    source: str = "center_cv"
    summary: str = ""
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, str | float]:
        """JSON-ready copy for the status API and the text Jev call."""
        return {
            "motion": self.motion,
            "proximity": self.proximity,
            "workspace": self.workspace,
            "source": self.source,
            "summary": self.summary,
            "updated_at": self.updated_at,
        }


def coerce_motion(value: str) -> Motion:
    """Return a valid motion label; unknown text becomes ``still``."""
    if value == "moving" or value == "fast":
        return value
    return "still"


def describe_scene(motion: Motion, proximity: Proximity, workspace: Workspace) -> str:
    """Short English sentence a text decision model can read."""
    return (
        f"Center camera: motion is {motion}. "
        f"Proximity is {proximity}. "
        f"Workspace is {workspace}."
    )
