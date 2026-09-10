"""周报 PDF 导出。

中文 PDF 的常见坑是字体：嵌入 TTF 需要随包分发字体文件，或依赖宿主机上
恰好存在某个字体 —— 两者在 Docker 里都不可靠。这里用 reportlab 内置的
CID 字体 STSong-Light，无需任何外部字体文件，Linux 容器里同样可用。
"""

from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_CJK_FONT = "STSong-Light"
_registered = False

ACCENT = colors.HexColor("#135A87")
INK = colors.HexColor("#171B21")
MUTED = colors.HexColor("#7E8794")
RULE = colors.HexColor("#D9DEE3")


def _ensure_font() -> None:
    """注册内置中文字体。重复调用是安全的。"""
    global _registered
    if not _registered:
        pdfmetrics.registerFont(UnicodeCIDFont(_CJK_FONT))
        _registered = True


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "wpTitle", parent=base["Title"], fontName=_CJK_FONT,
            fontSize=20, leading=26, textColor=INK, alignment=TA_LEFT, spaceAfter=2,
        ),
        "meta": ParagraphStyle(
            "wpMeta", parent=base["Normal"], fontName=_CJK_FONT,
            fontSize=8.5, leading=12, textColor=MUTED,
        ),
        "h2": ParagraphStyle(
            "wpH2", parent=base["Heading2"], fontName=_CJK_FONT,
            fontSize=12.5, leading=17, textColor=ACCENT, spaceBefore=14, spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "wpBody", parent=base["Normal"], fontName=_CJK_FONT,
            fontSize=10, leading=16, textColor=INK,
        ),
        "small": ParagraphStyle(
            "wpSmall", parent=base["Normal"], fontName=_CJK_FONT,
            fontSize=8.5, leading=13, textColor=MUTED,
        ),
    }


def _kv_table(rows: list[tuple[str, str]]) -> Table:
    table = Table([[k, v] for k, v in rows], colWidths=[38 * mm, 128 * mm])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _CJK_FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("TEXTCOLOR", (1, 0), (1, -1), INK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def _bullet_list(items: list, styles: dict) -> list:
    out = []
    for item in items:
        text = item if isinstance(item, str) else str(item)
        out.append(Paragraph(f"• {text}", styles["body"]))
    return out


def build_weekly_pdf(report: dict, portfolio_summary: dict | None = None) -> bytes:
    """把周报数据渲染成 PDF 字节流。

    Args:
        report: /api/report/weekly 的返回结构。
        portfolio_summary: 可选的持仓总览，用于补一张概览表。
    """
    _ensure_font()
    styles = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title="WealthPilot 周报", author="WealthPilot",
    )

    flow: list = []
    flow.append(Paragraph("WealthPilot 投资周报", styles["title"]))

    period = f"{report.get('week_start', '')} 至 {report.get('week_end', '')}"
    flow.append(Paragraph(
        f"报告期间 {period}　·　生成时间 {datetime.now():%Y-%m-%d %H:%M}",
        styles["meta"],
    ))
    flow.append(Spacer(1, 6))
    flow.append(HRFlowable(width="100%", thickness=1.2, color=ACCENT, spaceAfter=4))

    if report.get("summary"):
        flow.append(Paragraph("本周概要", styles["h2"]))
        flow.append(Paragraph(str(report["summary"]), styles["body"]))

    if portfolio_summary:
        flow.append(Paragraph("持仓总览", styles["h2"]))
        rows = []
        for key, label in (
            ("total_market_value", "总市值"),
            ("total_cost", "总成本"),
            ("total_return", "累计收益"),
            ("return_pct", "累计收益率"),
            ("weekly_return", "本周收益"),
            ("volatility_status", "波动状态"),
        ):
            if key in portfolio_summary and portfolio_summary[key] is not None:
                value = portfolio_summary[key]
                suffix = "%" if key.endswith("_pct") else ""
                rows.append((label, f"{value}{suffix}"))
        if rows:
            flow.append(_kv_table(rows))

    for key, heading in (
        ("key_points", "关键要点"),
        ("next_week_focus", "下周关注"),
        ("risks", "风险提示"),
        ("ai_insights", "AI 洞察"),
    ):
        items = report.get(key)
        if not items:
            continue
        flow.append(Paragraph(heading, styles["h2"]))
        if isinstance(items, str):
            flow.append(Paragraph(items, styles["body"]))
        else:
            flow.extend(_bullet_list(list(items), styles))

    flow.append(Spacer(1, 14))
    flow.append(HRFlowable(width="100%", thickness=0.5, color=RULE, spaceAfter=6))
    flow.append(Paragraph(
        "本报告由 WealthPilot 自动生成，数据来源为公开行情接口，"
        "内容仅供研究参考，不构成投资建议。",
        styles["small"],
    ))

    doc.build(flow)
    return buf.getvalue()
