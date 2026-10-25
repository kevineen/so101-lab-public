#!/usr/bin/env python3
"""mkdocs print-site の出力（site/print_page/index.html）から単一HTMLを書き出す。

ローカルの CSS / JS（Material 本体・print-site 分）を <style>/<script> として
埋め込む。スマホや Google Drive に 1 ファイル置くだけでサーバー無し・圏外でも
読めるようにするための変換（make docs-print から呼ぶ）。

- リモート URL（CDN 等）はそのまま（圏外では単に読み込まれない）
- mermaid 図はクライアント側レンダリングのため、オフラインではコードブロック
  として表示される（全文は読める）
- 検索ボックスはオフラインでは動作しない

使い方:
    python3 scripts/inline_print_page.py site/print_page/index.html print/so101-lab_docs.html
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote

LINK_RE = re.compile(r'<link\s+rel="stylesheet"\s+href="([^"]+)"\s*/?>')
SCRIPT_RE = re.compile(r'<script\s+src="([^"]+)"></script>')

REMOTE = ("http://", "https://", "//")


def _local(page_dir: Path, ref: str) -> Path | None:
    if ref.startswith(REMOTE):
        return None
    path = (page_dir / unquote(ref.split("?", 1)[0].split("#", 1)[0])).resolve()
    return path if path.exists() else None


def inline(html: str, page_dir: Path) -> str:
    missing: list[str] = []

    def css(match: re.Match[str]) -> str:
        path = _local(page_dir, match.group(1))
        if path is None:
            if not match.group(1).startswith(REMOTE):
                missing.append(match.group(1))
            return match.group(0)
        return "<style>\n" + path.read_text(encoding="utf-8") + "\n</style>"

    def js(match: re.Match[str]) -> str:
        path = _local(page_dir, match.group(1))
        if path is None:
            if not match.group(1).startswith(REMOTE):
                missing.append(match.group(1))
            return match.group(0)
        return "<script>\n" + path.read_text(encoding="utf-8") + "\n</script>"

    html = LINK_RE.sub(css, html)
    html = SCRIPT_RE.sub(js, html)
    for ref in missing:
        print(f"warning: asset not found, left as reference: {ref}", file=sys.stderr)
    return html


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("page", type=Path, help="site/print_page/index.html")
    parser.add_argument("out", type=Path, help="output single-file HTML")
    args = parser.parse_args(argv)

    html = inline(args.page.read_text(encoding="utf-8"), args.page.parent)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html, encoding="utf-8")
    size = args.out.stat().st_size
    print(f"wrote {args.out} ({size / 1024:.0f} KiB) — copy to your phone / Google Drive")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
