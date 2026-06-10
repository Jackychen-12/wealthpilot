.PHONY: setup dev backend frontend test docker clean

setup:           ## 首次配置：复制 .env、安装依赖
	@test -f backend/.env || cp backend/.env.example backend/.env
	cd backend && uv sync
	npm install
	@echo ""
	@echo "✅ 安装完成！请编辑 backend/.env 填入 ANTHROPIC_API_KEY"
	@echo "   然后运行 make dev 启动开发服务"

dev:             ## 启动后端 + 前端（开发模式）
	@echo "启动后端（:8000）+ 前端（:5173）..."
	cd backend && uv run uvicorn wealthpilot.main:app --reload --port 8000 &
	npm run dev

backend:         ## 仅启动后端
	cd backend && uv run uvicorn wealthpilot.main:app --reload --port 8000

frontend:        ## 仅启动前端
	npm run dev

test:            ## 运行测试
	cd backend && uv run pytest -v

docker:          ## Docker Compose 启动
	@test -f backend/.env || cp backend/.env.example backend/.env
	docker compose up --build

clean:           ## 清理生成文件
	rm -rf backend/data/ node_modules/ backend/.venv/

config:          ## 查看当前配置
	cd backend && uv run python -m wealthpilot config

chat:            ## 终端交互式 AI 对话
	cd backend && uv run python -m wealthpilot chat

help:            ## 显示帮助
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'
