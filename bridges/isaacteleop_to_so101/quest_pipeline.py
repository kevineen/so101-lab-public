"""Shared CloudXR / isaaccapture retarget pipeline for record + live bridge."""

from __future__ import annotations


def require_isaaccapture() -> None:
    try:
        import isaaccapture  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "isaaccapture is required. Activate ~/robot/isaac-teleop-env/.venv "
            "or use scripts/start_quest_bridge_live.sh / record_quest_teleop_jsonl.sh"
        ) from exc


def build_controller_pipeline(arms: list[str], *, include_gripper_retargeter: bool = True):
    """SE3 abs (+ optional GripperRetargeter) and raw controller tensors.

    Live teleop with YAML axis maps uses raw ``controller_<arm>`` outputs and can
    set ``include_gripper_retargeter=False``.
    """
    from isaaccapture.retargeters import (
        GripperRetargeter,
        GripperRetargeterConfig,
        Se3AbsRetargeter,
        Se3RetargeterConfig,
    )
    from isaaccapture.retargeting_engine.deviceio_source_nodes import (
        ControllersSource,
        HandsSource,
    )
    from isaaccapture.retargeting_engine.interface import OutputCombiner

    controllers = ControllersSource(name="controllers")
    hands = HandsSource(name="hands")
    outputs: dict = {}

    for arm in arms:
        side = ControllersSource.LEFT if arm == "left" else ControllersSource.RIGHT
        se3 = Se3AbsRetargeter(
            Se3RetargeterConfig(input_device=side),
            name=f"se3_{arm}",
        )
        outputs[f"pose_{arm}"] = se3.connect({side: controllers.output(side)}).output(
            "ee_pose"
        )
        outputs[f"controller_{arm}"] = controllers.output(side)

        if include_gripper_retargeter:
            hand_side = "left" if arm == "left" else "right"
            grip = GripperRetargeter(
                GripperRetargeterConfig(hand_side=hand_side),
                name=f"gripper_{arm}",
            )
            if hand_side == "left":
                grip_in = {
                    ControllersSource.LEFT: controllers.output(ControllersSource.LEFT),
                    HandsSource.LEFT: hands.output(HandsSource.LEFT),
                }
            else:
                grip_in = {
                    ControllersSource.RIGHT: controllers.output(ControllersSource.RIGHT),
                    HandsSource.RIGHT: hands.output(HandsSource.RIGHT),
                }
            outputs[f"gripper_{arm}"] = grip.connect(grip_in).output("gripper_command")

    return OutputCombiner(outputs)
