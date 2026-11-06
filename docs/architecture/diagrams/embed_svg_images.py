"""Inline PNG node-icons into generated SVGs as base64 data URIs.

Graphviz emits <image xlink:href="/abs/local/path.png"> — which breaks when the
SVG is served elsewhere (GitHub) and leaks the local path. This rewrites every
local href to a data URI. Idempotent; run as the last step of rendering.
"""
import base64
import glob
import os
import re

IMG_DIR = os.path.join(os.path.dirname(__file__), "..", "img")
HREF = re.compile(r'xlink:href="([^"]+\.png)"')


def main() -> None:
    for svg in sorted(glob.glob(os.path.join(IMG_DIR, "*.svg"))):
        with open(svg, encoding="utf-8") as f:
            text = f.read()

        def repl(m: "re.Match[str]") -> str:
            href = m.group(1)
            if href.startswith("data:"):
                return m.group(0)
            path = href if os.path.isabs(href) else os.path.join(os.path.dirname(svg), href)
            if not os.path.exists(path):
                return m.group(0)
            with open(path, "rb") as img:
                b64 = base64.b64encode(img.read()).decode("ascii")
            return f'xlink:href="data:image/png;base64,{b64}"'

        with open(svg, "w", encoding="utf-8") as f:
            f.write(HREF.sub(repl, text))
        print("embedded", os.path.basename(svg))


if __name__ == "__main__":
    main()
