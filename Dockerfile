# WealthPilot：一个镜像、一个端口。先构建网页版，再由后端把页面和接口一起发出去。
# 用法见 docker-compose.yml（docker compose up --build -d，然后打开 http://localhost:8000）

FROM node:22-alpine AS web
WORKDIR /web
COPY workbench/package.json workbench/package-lock.json ./
RUN npm ci
COPY workbench/ .
RUN npm run build -- --outDir dist-app --emptyOutDir

FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 目录结构和仓库保持一致：后端按源码位置去找 ../workbench/dist-app
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock* ./
RUN uv sync --no-dev --extra feishu --extra dingtalk --frozen --no-install-project 2>/dev/null || uv sync --no-dev --extra feishu --extra dingtalk --no-install-project
COPY backend/src/ src/
COPY backend/skills/ skills/
COPY backend/skills-gallery/ skills-gallery/
RUN uv sync --no-dev --extra feishu --extra dingtalk --frozen 2>/dev/null || uv sync --no-dev --extra feishu --extra dingtalk
COPY --from=web /web/dist-app /app/workbench/dist-app

# 数据（数据库、技能、缓存）都放在 /data，挂一个卷就能持久化
ENV WEALTHPILOT_HOME=/data \
    DB_PATH=/data/wealthpilot.db \
    SKILLS_DIR=/data/skills \
    HOST=0.0.0.0 PORT=8000
EXPOSE 8000

# 第一次启动时把自带的示例技能放进数据卷（已有的不覆盖），然后启动服务
CMD ["sh", "-c", "mkdir -p /data/skills && cp -n /app/backend/skills/*.md /data/skills/ 2>/dev/null; exec uv run --no-sync uvicorn wealthpilot.main:app --host 0.0.0.0 --port 8000"]
