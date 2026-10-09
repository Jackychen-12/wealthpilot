"""给在线演示补录不调用模型的那几块：大盘复盘、宏观、反向 DCF、名词解释、现成的数据服务。

和 record_demo.py 的区别：那个会调用真实模型（要花钱），这个只取公开行情和财务数据，不花钱。
它只往 fixtures.json 的 get 里加这几个接口，不动已经录好的研究过程。

    uv run python scripts/record_demo_static.py            # 收盘后运行：录当天的复盘
    uv run python scripts/record_demo_static.py 2026-10-08 # 用本机缓存里那一天的复盘（当天收盘后打开过今日页才有）
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "workbench" / "src" / "demo" / "fixtures.json"
STOCK = "600519"


async def main(day: str = "") -> None:
    from wealthpilot.services import cache, glossary, macro, recap
    from wealthpilot.services.agents.depth_tools import reverse_dcf_for
    from wealthpilot.services.connector_presets import PRESETS, STATUS_LABEL

    fixtures = json.loads(OUT.read_text(encoding="utf-8"))
    get = fixtures["get"]
    report = cache.read(f"recap:{day}", 365 * cache.DAY) if day else await recap.build()
    if not report:
        raise SystemExit("没有拿到大盘复盘：休市、还没收盘，或者本机缓存里没有那一天的。")
    get["/api/market/recap"] = report
    snapshot = await macro.snapshot()
    if snapshot.get("indicators"):
        get["/api/market/macro"] = snapshot
    dcf = await reverse_dcf_for(STOCK)
    if dcf and dcf.get("ok"):
        get[f"/api/market/stock/{STOCK}/reverse-dcf"] = dcf
    get["/api/settings/glossary"] = glossary.as_list()
    get["/api/connectors/presets"] = [{k: p[k] for k in ("key", "label", "official", "status", "provides", "needs", "links", "caveat")}
                                      | {"status_label": STATUS_LABEL[p["status"]]} for p in PRESETS]
    fixtures["static_recorded_at"] = datetime.now().strftime("%Y-%m-%d")
    OUT.write_text(json.dumps(fixtures, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"已补录：大盘复盘（{report['day']}）、宏观 {len(snapshot.get('indicators', []))} 项、{STOCK} 的反向 DCF、名词解释 {len(glossary.TERMS)} 条、现成的数据服务 {len(PRESETS)} 个")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else ""))
