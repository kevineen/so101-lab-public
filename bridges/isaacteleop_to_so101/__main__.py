"""python -m bridges.isaacteleop_to_so101 は使わず、receiver / sender を直接指定する。"""

from __future__ import annotations

import sys


def main() -> None:
    print(
        "Usage:\n"
        "  python -m bridges.isaacteleop_to_so101.receiver --dry-run\n"
        "  python -m bridges.isaacteleop_to_so101.sender --host <PiIP> --demo-bimanual\n",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
