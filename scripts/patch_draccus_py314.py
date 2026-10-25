#!/usr/bin/env python3
"""Let draccus 0.8 register Union fields on Python 3.14.

Python 3.14's argparse rejects a non-callable ``type=``. draccus passes
``dict[...] | None`` through, so ``ACTConfig`` fails to load on Thor's
3.14 venv. Run this with that venv's interpreter, then restart
``policy_server``. Idempotent.
"""

from __future__ import annotations

import inspect
from pathlib import Path

OLD = """        else:
            _arg_options["type"] = tpe
            try:
                _arg_options["type"].__name__ = self.type.__repr__().replace("typing.", "")
            except Exception:
                # Only to prettify printing, if fails just continue
                pass
"""

NEW = """        else:
            # Python 3.14 argparse rejects Union annotations (they are not callable).
            if callable(tpe):
                _arg_options["type"] = tpe
                try:
                    _arg_options["type"].__name__ = self.type.__repr__().replace("typing.", "")
                except Exception:
                    # Only to prettify printing, if fails just continue
                    pass
"""


def main() -> None:
    import draccus

    path = Path(inspect.getfile(draccus)).parent / "wrappers" / "field_wrapper.py"
    text = path.read_text()
    if NEW in text:
        print(f"already patched: {path}")
        return
    if OLD not in text:
        raise SystemExit(f"draccus layout changed, not patched: {path}")
    path.write_text(text.replace(OLD, NEW, 1))
    print(f"patched: {path}")


if __name__ == "__main__":
    main()
