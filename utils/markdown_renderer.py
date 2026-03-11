from __future__ import annotations

import logging
import re
from markdown_it import MarkdownIt
from pygments import highlight
from pygments.lexers import get_lexer_by_name, TextLexer
from pygments.formatters import HtmlFormatter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ARTIFACT STRIPPING
#
# This model uses Private Use Area (PUA) Unicode characters as tool-use
# delimiters. Analysis of real chat files reveals this structure:
#
#   \ue200 TAG \ue202 REFERENCE \ue201   → tool call: STRIP entirely
#       Examples: \ue200cite\ue202turn0search0\ue201
#                 \ue200video\ue202VideoTitle\ue202turn0search5\ue201
#                 \ue200entity\ue202["type","Name","desc"]\ue201
#
#   \ue203 TEXT \ue204                   → annotation wrapping real text: KEEP TEXT
#       (These contain actual readable sentences — preserve them)
#
#   \ue206                              → trailing marker: STRIP
#
#   【...†...】 or 【{...}】            → citation/image fetch brackets: STRIP
#
#   ■ based tokens                     → older format, also STRIP
#
# ---------------------------------------------------------------------------


def _clean_artifacts(text: str) -> str:
    """Remove all tool/citation artifact tokens, preserving readable content."""

    # 1. Unwrap \ue203...\ue204 annotations — keep the inner text, remove only the markers
    text = re.sub(r'\ue203(.*?)\ue204', r'\1', text, flags=re.DOTALL)

    # 2. Strip complete \ue200...\ue201 tool-call blocks (cite, video, entity, etc.)
    text = re.sub(r'\ue200[^\ue201]{0,300}\ue201', '', text, flags=re.DOTALL)

    # 3. Strip any remaining lone PUA characters (\ue200-\ue206, \uf120)
    text = re.sub(r'[\ue200-\ue206\uf120]', '', text)

    # 4. Strip 【...】 bracket forms:
    #    【turn0search0†source】  【28†embed_image】  【{"image_fetch": "..."}】
    text = re.sub(r'【[^】]{0,200}】', '', text)

    # 5. Strip ■-based tokens (older model format):
    #    ■entity☆[...], ■link_title☆..., ■cite☆..., ■cite☆↗
    text = re.sub(r'■[^\n]*', '', text)

    # 6. Strip bare turn0searchN / turn1productN references
    text = re.sub(r'\bturn\d+\w+\d+(?:[†↑→↗]\w*)?', '', text)

    # 7. Clean up lines that are now empty or contain only glyph residue
    text = re.sub(r'(?m)^[ \t]*[↗↕↔↑↓†‡*\-]+[ \t]*$', '', text)

    # 8. Remove ◆ ◇ diamond bullets (entity section markers)
    text = re.sub(r'(?m)^[◆◇▶▷]\s+', '', text)

    # 9. Collapse 3+ blank lines → 2
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


# ---------------------------------------------------------------------------

class MarkdownRenderer:
    def __init__(self):
        self.linkify_enabled = False
        try:
            from linkify_it import LinkifyIt
            self.linkify_enabled = True
        except ImportError:
            logger.warning("linkify-it-py not found, linkify will be disabled")

        self.md = MarkdownIt("gfm-like", {
            "highlight": self._highlight_code,
            "html": True,
            "linkify": self.linkify_enabled,
            "typographer": True,
        })

        if self.linkify_enabled:
            try:
                self.md.enable("linkify")
            except Exception:
                self.linkify_enabled = False
        else:
            self.md.disable("linkify")

    def _highlight_code(self, code: str, lang: str, attrs) -> str:
        try:
            lexer = get_lexer_by_name(lang, stripall=True)
        except Exception:
            lexer = TextLexer(stripall=True)
        formatter = HtmlFormatter(nowrap=True)
        return highlight(code, lexer, formatter)

    def _fix_lists_for_qt(self, html: str) -> str:
        def replace_ol(m):
            items = re.findall(r'<li[^>]*>(.*?)</li>', m.group(1), re.DOTALL)
            rows = ''.join(
                f'<tr>'
                f'<td style="padding:2px 8px 2px 18px;vertical-align:top;'
                f'color:#8b949e;font-size:13px;white-space:nowrap;">{i+1}.</td>'
                f'<td style="padding:2px 0;">{item.strip()}</td>'
                f'</tr>'
                for i, item in enumerate(items)
            )
            return (
                f'<table style="border:none;margin:4px 0 10px 0;'
                f'border-collapse:collapse;width:100%;">{rows}</table>'
            )

        def replace_ul(m):
            items = re.findall(r'<li[^>]*>(.*?)</li>', m.group(1), re.DOTALL)
            rows = ''.join(
                f'<tr>'
                f'<td style="padding:2px 8px 2px 18px;vertical-align:top;'
                f'color:#8b949e;font-size:15px;white-space:nowrap;">•</td>'
                f'<td style="padding:2px 0;">{item.strip()}</td>'
                f'</tr>'
                for item in items
            )
            return (
                f'<table style="border:none;margin:4px 0 10px 0;'
                f'border-collapse:collapse;width:100%;">{rows}</table>'
            )

        for _ in range(4):
            html = re.sub(r'<ol[^>]*>(.*?)</ol>', replace_ol, html, flags=re.DOTALL)
            html = re.sub(r'<ul[^>]*>(.*?)</ul>', replace_ul, html, flags=re.DOTALL)
        return html

    def _wrap_code_blocks(self, html: str) -> str:
        def replace_pre(m):
            content = m.group(1)
            lang_match = re.search(r'class="language-(\w+)"', content)
            lang = lang_match.group(1) if lang_match else 'code'
            return (
                f'<table style="border:none;border-collapse:collapse;'
                f'width:100%;margin:10px 0;">'
                f'<tr><td style="background:#161b22;padding:4px 12px;'
                f'border-radius:8px 8px 0 0;border:1px solid #30363d;'
                f'border-bottom:none;">'
                f'<span style="color:#8b949e;font-family:Consolas,monospace;'
                f'font-size:11px;">{lang}</span>'
                f'</td></tr>'
                f'<tr><td style="padding:0;">'
                f'<pre style="margin:0;border-radius:0 0 8px 8px;">'
                f'{content}</pre>'
                f'</td></tr>'
                f'</table>'
            )
        return re.sub(r'<pre>(.*?)</pre>', replace_pre, html, flags=re.DOTALL)

    def render(self, text: str) -> str:
        try:
            text = _clean_artifacts(text)
            html = self.md.render(text)
            html = self._fix_lists_for_qt(html)
            html = self._wrap_code_blocks(html)
            return html
        except Exception as e:
            logger.error(f"Markdown rendering error: {e}")
            return f'<p>{_clean_artifacts(text)}</p>'

    @staticmethod
    def get_css() -> str:
        return HtmlFormatter(style="monokai").get_style_defs(".highlight")
