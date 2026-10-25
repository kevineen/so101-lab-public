"""Entry point: phone buttons, then the normal ``lerobot-record`` CLI."""

from __future__ import annotations

import sys


def main() -> None:
    # Help text should name the shell entry, not this module file.
    sys.argv[0] = "record_with_buttons.sh"
    try:
        from record_buttons.hook import install_phone_buttons
        from record_buttons.offload import install_dataset_offload

        install_dataset_offload()
        install_phone_buttons()
    except ImportError as exc:
        print(
            "lerobot が見つかりません。scripts/record_with_buttons.sh から起動してください。",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    from lerobot.scripts.lerobot_record import main as record_main

    record_main()


if __name__ == "__main__":
    main()
