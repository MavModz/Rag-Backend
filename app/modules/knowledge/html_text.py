"""Convert KB HTML bodies to plain text for chunking."""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from urllib.parse import urlparse


def _attr(attrs: list[tuple[str, str | None]], name: str) -> str:
    for key, value in attrs:
        if key.lower() == name:
            return (value or "").strip()
    return ""


def _image_kind(url: str) -> str:
    path = urlparse(url).path.lower()
    if path.endswith(".gif"):
        return "animated GIF"
    if path.endswith(".png"):
        return "PNG"
    if path.endswith((".jpg", ".jpeg")):
        return "JPEG"
    if path.endswith(".webp"):
        return "WebP"
    if path.endswith(".svg"):
        return "SVG"
    return "image"


def format_image_reference(src: str, alt: str = "") -> str:
    """Turn an <img> tag into searchable plain text with URL preserved."""
    src = html.unescape(src.strip())
    alt = html.unescape(alt.strip())
    if not src:
        return ""
    kind = _image_kind(src)
    if alt:
        return f"[Image ({kind}): {alt} — {src}]"
    return f"[Image ({kind}): {src}]"


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style"}:
            self._skip_depth += 1
            return
        if tag == "img":
            line = format_image_reference(_attr(attrs, "src"), _attr(attrs, "alt"))
            if line:
                self._parts.append(f"\n{line}\n")
            return
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._skip_depth:
            self._skip_depth -= 1
        if tag in {"p", "div", "li", "h1", "h2", "h3", "h4", "ul", "ol", "table"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self._parts.append(text + " ")

    def get_text(self) -> str:
        raw = "".join(self._parts)
        raw = html.unescape(raw)
        raw = re.sub(r"[ \t]+\n", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def html_to_plain_text(fragment: str | None) -> str:
    if not fragment:
        return ""
    parser = _HTMLTextExtractor()
    parser.feed(fragment)
    parser.close()
    return parser.get_text()
