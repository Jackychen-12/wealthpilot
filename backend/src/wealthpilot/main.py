"""FastAPI 入口。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from wealthpilot import __version__
from wealthpilot.routes import api_router
from wealthpilot.settings import get_settings
from wealthpilot.storage.db import get_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.ensure_dirs()
    get_engine()  # 初始化数据库表
    print(f"🚀 WealthPilot Backend v{__version__}")
    print(f"📂 DB: {settings.db_path.resolve()}")
    yield


app = FastAPI(
    title="WealthPilot API",
    version=__version__,
    description="AI-Powered Investment Advisory Agent Backend",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/")
async def root():
    return {"name": "wealthpilot", "version": __version__, "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "ok"}
