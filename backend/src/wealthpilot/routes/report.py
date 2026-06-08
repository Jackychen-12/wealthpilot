"""周报路由 + PDF 导出。"""

import io
from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.services.market_data import fetch_fund_info, fetch_fund_nav
from wealthpilot.services.report import generate_weekly_report
from wealthpilot.storage.db import get_session

router = APIRouter(prefix="/report", tags=["report"])


@router.get("/weekly")
async def get_weekly_report(db: Session = Depends(get_session)):
    """获取/生成最新周报。"""
    holdings = list(db.exec(select(PortfolioHolding)).all())
    if not holdings:
        return {"error": "暂无持仓数据，请先添加持仓"}

    nav_data: dict[str, float] = {}
    nav_history: dict[str, list[dict]] = {}

    for h in holdings:
        info = await fetch_fund_info(h.fund_code)
        if info:
            nav_data[h.fund_code] = info["nav"]
        else:
            nav_data[h.fund_code] = h.cost_price

        hist = await fetch_fund_nav(h.fund_code, 30)
        if hist:
            nav_history[h.fund_code] = hist

    report = generate_weekly_report(holdings, nav_data, nav_history)
    return report


@router.post("/generate")
async def force_generate_report(db: Session = Depends(get_session)):
    """手动触发重新生成周报。"""
    holdings = list(db.exec(select(PortfolioHolding)).all())
    if not holdings:
        return {"error": "暂无持仓数据"}

    nav_data: dict[str, float] = {}
    nav_history: dict[str, list[dict]] = {}

    for h in holdings:
        info = await fetch_fund_info(h.fund_code)
        if info:
            nav_data[h.fund_code] = info["nav"]
        else:
            nav_data[h.fund_code] = h.cost_price

        hist = await fetch_fund_nav(h.fund_code, 30)
        if hist:
            nav_history[h.fund_code] = hist

    report = generate_weekly_report(holdings, nav_data, nav_history)
    return {"status": "generated", "report": report}


@router.get("/pdf")
async def export_pdf(db: Session = Depends(get_session)):
    """导出周报为纯文本 PDF（简易版，无第三方 PDF 库依赖）。"""
    holdings = list(db.exec(select(PortfolioHolding)).all())
    if not holdings:
        return {"error": "暂无持仓数据"}

    nav_data: dict[str, float] = {}
    nav_history: dict[str, list[dict]] = {}
    for h in holdings:
        info = await fetch_fund_info(h.fund_code)
        nav_data[h.fund_code] = info["nav"] if info else h.cost_price
        hist = await fetch_fund_nav(h.fund_code, 30)
        if hist:
            nav_history[h.fund_code] = hist

    report = generate_weekly_report(holdings, nav_data, nav_history)

    # 生成纯文本格式报告（可用 txt 打开，也可直接粘贴）
    lines = []
    lines.append("=" * 50)
    lines.append("WealthPilot AI 周复盘报告")
    lines.append(f"周期: {report.get('week_start', '')} — {report.get('week_end', '')}")
    lines.append("=" * 50)
    lines.append("")
    lines.append(f"【总结】{report.get('summary', '')}")
    lines.append("")

    overview = report.get("overview", {})
    lines.append("【本周数据】")
    lines.append(f"  组合周收益: {overview.get('weekly_return', 0):.0f} 元")
    lines.append(f"  组合涨幅: {overview.get('weekly_growth_pct', 0):.2f}%")
    lines.append(f"  超额收益: {overview.get('excess_return_pct', 0):.2f}%")
    lines.append(f"  Sharpe 比率: {overview.get('sharpe_ratio', 'N/A')}")
    lines.append("")

    lines.append("【关键归因点】")
    for kp in report.get("key_points", []):
        lines.append(f"  • {kp.get('title', '')}: {kp.get('desc', '')}")
    lines.append("")

    lines.append("【下周关注】")
    for f in report.get("next_week_focus", []):
        lines.append(f"  • {f}")
    lines.append("")

    if report.get("risk_alert"):
        lines.append(f"【风险提示】{report['risk_alert']}")
        lines.append("")

    lines.append(f"【AI 洞察】{report.get('ai_insight', '')}")
    lines.append("")
    lines.append("-" * 50)
    lines.append("由 WealthPilot AI Engine 生成")
    lines.append("⚠️ 以上仅为分析视角，不构成投资建议")

    content = "\n".join(lines)
    buf = io.BytesIO(content.encode("utf-8"))
    filename = f"wealthpilot-weekly-{date.today().isoformat()}.txt"

    return StreamingResponse(
        buf,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
