# -*- coding: utf-8 -*-
"""Write investigation report as both Markdown and PDF."""

from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    HRFlowable, Paragraph, Preformatted,
    SimpleDocTemplate, Spacer, Table, TableStyle,
)

import re
import markdown

# ---------------------------------------------------------------------------
# Font setup (built-in CID fonts — no external font files needed)
# ---------------------------------------------------------------------------
pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
pdfmetrics.registerFont(UnicodeCIDFont("HeiseiMin-W3"))

FONT = "HeiseiKakuGo-W5"
FONT_MONO = "HeiseiKakuGo-W5"


def _style(name, **kw) -> ParagraphStyle:
    s = ParagraphStyle(name)
    s.fontName = FONT
    for k, v in kw.items():
        setattr(s, k, v)
    return s


S_NORMAL = _style("N",  fontSize=10, leading=17, spaceAfter=3)
S_H1     = _style("H1", fontSize=17, leading=22, spaceAfter=6, spaceBefore=14,
                  textColor=colors.HexColor("#1a3a5c"))
S_H2     = _style("H2", fontSize=13, leading=18, spaceAfter=5, spaceBefore=10,
                  textColor=colors.HexColor("#2e6da4"))
S_H3     = _style("H3", fontSize=11, leading=16, spaceAfter=4, spaceBefore=7,
                  textColor=colors.HexColor("#444444"))
S_H4     = _style("H4", fontSize=10, leading=15, spaceAfter=3, spaceBefore=5,
                  textColor=colors.HexColor("#666666"))
S_BULLET = _style("B",  fontSize=10, leading=15, leftIndent=14, spaceAfter=2)
S_CODE   = _style("C",  fontSize=8,  leading=12, leftIndent=8, rightIndent=8,
                  fontName=FONT_MONO,
                  backColor=colors.HexColor("#f5f5f5"),
                  spaceAfter=5, spaceBefore=4)
S_BQ     = _style("BQ", fontSize=9,  leading=14, leftIndent=12,
                  textColor=colors.HexColor("#555555"))


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _md_to_story(md_text: str) -> list:
    story = []
    lines = md_text.split("\n")
    i = 0
    para_buf: list[str] = []

    def flush(style=S_NORMAL):
        text = " ".join(para_buf).strip()
        if text:
            story.append(Paragraph(_esc(text), style))
        para_buf.clear()

    while i < len(lines):
        line = lines[i]

        # Fenced code block
        if line.startswith("```"):
            flush()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            story.append(Preformatted("\n".join(code_lines), S_CODE))
            i += 1
            continue

        # Horizontal rule
        if re.match(r"^-{3,}$", line.strip()):
            flush()
            story.append(HRFlowable(width="100%", thickness=1,
                                    color=colors.HexColor("#cccccc"), spaceAfter=5))
            i += 1
            continue

        # Headings
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            flush()
            level = len(m.group(1))
            text  = m.group(2).strip()
            st    = {1: S_H1, 2: S_H2, 3: S_H3, 4: S_H4}.get(level, S_NORMAL)
            story.append(Paragraph(_esc(text), st))
            if level == 1:
                story.append(HRFlowable(width="100%", thickness=2,
                                        color=colors.HexColor("#1a3a5c"), spaceAfter=3))
            elif level == 2:
                story.append(HRFlowable(width="100%", thickness=1,
                                        color=colors.HexColor("#b0c8e8"), spaceAfter=2))
            i += 1
            continue

        # Table
        if line.startswith("|"):
            flush()
            tbl_lines = []
            while i < len(lines) and lines[i].startswith("|"):
                tbl_lines.append(lines[i])
                i += 1
            data = []
            for tl in tbl_lines:
                if re.match(r"^\|[-| :]+\|$", tl.strip()):
                    continue
                cells = [c.strip() for c in tl.strip().strip("|").split("|")]
                data.append(cells)
            if data:
                col_count = max(len(r) for r in data)
                for r in data:
                    while len(r) < col_count:
                        r.append("")
                col_w = [16.5 * cm / col_count] * col_count
                tbl = Table(data, colWidths=col_w, repeatRows=1)
                tbl.setStyle(TableStyle([
                    ("FONTNAME",        (0, 0), (-1, -1), FONT),
                    ("FONTSIZE",        (0, 0), (-1, -1), 9),
                    ("BACKGROUND",      (0, 0), (-1, 0),  colors.HexColor("#dce6f0")),
                    ("GRID",            (0, 0), (-1, -1), 0.5, colors.HexColor("#bbbbbb")),
                    ("VALIGN",          (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING",      (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING",   (0, 0), (-1, -1), 4),
                    ("LEFTPADDING",     (0, 0), (-1, -1), 6),
                ]))
                story.append(tbl)
                story.append(Spacer(1, 5))
            continue

        # Blockquote
        if line.startswith(">"):
            flush()
            story.append(Paragraph(_esc(line[1:].strip()), S_BQ))
            i += 1
            continue

        # Bullet list
        m = re.match(r"^(\s*)[-*]\s+(.*)", line)
        if m:
            flush()
            story.append(Paragraph(f"• {_esc(m.group(2))}", S_BULLET))
            i += 1
            continue

        # Numbered list
        m = re.match(r"^\d+\.\s+(.*)", line)
        if m:
            flush()
            story.append(Paragraph(f"  {_esc(m.group(1))}", S_BULLET))
            i += 1
            continue

        # Empty line
        if line.strip() == "":
            flush()
            story.append(Spacer(1, 4))
            i += 1
            continue

        # Normal text
        para_buf.append(line.strip())
        i += 1

    flush()
    return story


def _write_html(md_content: str, html_path: Path) -> None:
    html_body = markdown.markdown(
        md_content,
        extensions=["tables", "fenced_code"]
    )
    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>Investigation Report</title>
<style>
body {{ font-family: "Segoe UI", Arial, sans-serif; margin: 2rem; line-height: 1.6; color: #111; background: #fff; }}
pre {{ background: #f7f7f7; padding: 1rem; overflow-x: auto; border-radius: 4px; }}
code {{ background: #f5f5f5; padding: .15rem .3rem; border-radius: .3rem; font-family: Consolas, Menlo, Monaco, monospace; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 1rem; }}
th, td {{ border: 1px solid #ccc; padding: .5rem .75rem; text-align: left; }}
th {{ background: #f0f0f0; }}
blockquote {{ border-left: 4px solid #ccc; margin: 1rem 0; padding-left: 1rem; color: #555; background: #f9f9f9; }}
a {{ color: #0366d6; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
{html_body}
</body>
</html>"""
    html_path.write_text(html, encoding="utf-8")


def write_report(md_content: str) -> tuple[str, str, str]:
    today = date.today().strftime("%Y%m%d")
    reports_dir = Path(__file__).parent / "reports"
    reports_dir.mkdir(exist_ok=True)

    md_path  = reports_dir / f"report_{today}.md"
    pdf_path = reports_dir / f"report_{today}.pdf"

    # Save Markdown
    md_path.write_text(md_content, encoding="utf-8")

    # Build PDF
    story = _md_to_story(md_content)
    doc = SimpleDocTemplate(
        str(pdf_path), pagesize=A4,
        leftMargin=2.5 * cm, rightMargin=2.5 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
    )
    doc.build(story)

    html_path = reports_dir / f"report_{today}.html"
    _write_html(md_content, html_path)

    return str(md_path), str(pdf_path), str(html_path)
