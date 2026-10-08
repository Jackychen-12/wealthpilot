"""FastAPI 入口。"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from wealthpilot import __version__
from wealthpilot.routes import api_router
from wealthpilot.services import background, logs
from wealthpilot.settings import get_settings
from wealthpilot.storage.db import get_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.ensure_dirs()
    get_engine()  # 初始化数据库表
    logs.setup()
    logging.getLogger("wealthpilot").info("服务启动 v%s 模型=%s·%s", __version__, settings.ai_provider, settings.active_model)
    if not os.environ.get("WEALTHPILOT_QUIET"):   # 终端入口在后台带起服务时不打这两行，免得搅乱界面
        print(f"🚀 WealthPilot Backend v{__version__}")
        print(f"📂 DB: {settings.db_path.resolve()}")
    # 每日盯盘、自动任务、手机渠道：后端开着就自己跑，不需要另配 cron
    task = asyncio.create_task(background.run_all()) if os.environ.get("WATCH_ENABLED", "").lower() != "false" else None
    yield
    if task:
        task.cancel()


app = FastAPI(
    title="WealthPilot API",
    version=__version__,
    description="AI-Powered Investment Advisory Agent Backend",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:5180", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


# 构建好的工作台（make setup 会构建到 workbench/dist-app）。有它的话，后端自己就能把页面发出去，
# 不用再单独起一个前端服务：一个进程、一个端口。开发时仍然可以用 make dev 走 Vite。
WEB_DIR = Path(__file__).resolve().parents[3] / "workbench" / "dist-app"   # 跟着源码仓库走，与数据放在哪无关


@app.get("/")
async def root():
    if (WEB_DIR / "index.html").is_file():
        return FileResponse(WEB_DIR / "index.html")
    return {"name": "wealthpilot", "version": __version__, "docs": "/docs"}


if (WEB_DIR / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=WEB_DIR / "assets"), name="assets")


@app.get("/favicon.svg", include_in_schema=False)
async def favicon():
    if (WEB_DIR / "favicon.svg").is_file():
        return FileResponse(WEB_DIR / "favicon.svg")
    return JSONResponse({"detail": "not found"}, status_code=404)


@app.get("/health")
async def health():
    return {"status": "ok"}
