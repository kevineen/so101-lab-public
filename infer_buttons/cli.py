"""Entry point: phone buttons, then the normal ``robot_client`` CLI."""

from __future__ import annotations

import sys


def main() -> None:
    sys.argv[0] = "infer_with_buttons.sh"
    try:
        from infer_buttons.hook import install_phone_infer

        install_phone_infer()
    except ImportError as exc:
        print(
            "lerobot が見つかりません。scripts/infer_with_buttons.sh から起動してください。",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    from lerobot.utils.import_utils import register_third_party_plugins
    from lerobot.async_inference.robot_client import async_client

    register_third_party_plugins()
    async_client()


if __name__ == "__main__":
    main()
