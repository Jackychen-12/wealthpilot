"""周报路由 + PDF 导出。"""

from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlmodel import Session

from wealthpilot.services.context import load_market_context
from wealthpilot.services.deps import current_user_id, user_holdings
from wealthpilot.services.report import generate_weekly_report
from wealthpilot.storage.db import get_session

router = APIRouter(prefix="/report", tags=["report"])


@router.get("/weekly")
async def get_weekly_report(db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    """获取/生成最新周报。"""
    holdings = user_holdings(db, user_id)
    if not holdings:
        return {"error": "暂无持仓数据，请先添加持仓"}

    nav_data, nav_history = await load_market_context(holdings, 30)

    report = generate_weekly_report(holdings, nav_data, nav_history)
    return report


@router.post("/generate")
async def force_generate_report(db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    """手动触发重新生成周报。"""
    holdings = user_holdings(db, user_id)
    if not holdings:
        return {"error": "暂无持仓数据"}

    nav_data, nav_history = await load_market_context(holdings, 30)

    report = generate_weekly_report(holdings, nav_data, nav_history)
    return {"status": "generated", "report": report}


@router.get("/pdf")
async def export_pdf(
    db: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
):
    """导出周报 PDF。

    原实现输出的是纯文本 .txt，只是端点叫 /pdf —— 这次换成真实 PDF。
    中文用 reportlab 内置的 CID 字体 STSong-Light，不依赖宿主机字体文件，
    Docker 容器里同样可用。
    """
    from wealthpilot.services.analysis import calculate_overview
    from wealthpilot.services.pdf_report import build_weekly_pdf

    holdings = user_holdings(db, user_id)
    if not holdings:
        return Response(
            content="暂无持仓数据，请先添加持仓".encode(),
            status_code=400,
            media_type="text/plain; charset=utf-8",
        )

    nav_data, nav_history = await load_market_context(holdings, 30)

    report = generate_weekly_report(holdings, nav_data, nav_history)

    # 归一化成 pdf_report 期望的键名
    payload = {
        "week_start": report.get("week_start", ""),
        "week_end": report.get("week_end", ""),
        "summary": report.get("summary", ""),
        "key_points": [
            f"{kp.get('title', '')}：{kp.get('desc', '')}"
            for kp in report.get("key_points", [])
        ],
        "next_week_focus": report.get("next_week_focus", []),
        "risks": [report["risk_alert"]] if report.get("risk_alert") else [],
        "ai_insights": report.get("ai_insight", ""),
    }

    try:
        summary = calculate_overview(holdings, nav_data, nav_history)
    except Exception:
        summary = None

    pdf = build_weekly_pdf(payload, summary)
    filename = f"wealthpilot-weekly-{date.today().isoformat()}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


