.PHONY: setup start install uninstall dev backend workbench demo-build record-demo test docker clean

setup:           ## 首次配置：复制 .env、安装依赖
	@test -f backend/.env || cp backend/.env.example backend/.env
	cd backend && uv sync --extra dev
	npm --prefix workbench install
	npm --prefix workbench run build -- --outDir dist-app --emptyOutDir
	@echo ""
	@echo "✅ 安装完成。下一步："
	@echo "   make start     一条命令：终端 + 网页版（http://localhost:8000）+ 每日盯盘"
	@echo "   make install   把 wealthpilot 装成全局命令，之后在任意目录直接敲 wealthpilot"
	@echo "   模型 Key 可以在网页版左侧「设置」里填"

start:           ## 一条命令启动：终端入口，同时在后台带起网页版和每日盯盘
	cd backend && uv run wealthpilot

install:         ## 把 wealthpilot 装成全局命令（任意目录可用；代码改了不用重装）
	@mkdir -p $(HOME)/.local/bin
	@printf '#!/bin/sh\n# WealthPilot 的入口：转给仓库里那套已经装好的环境，所以代码更新后不用重装\nexec "%s/backend/.venv/bin/wealthpilot" "$$@"\n' "$(CURDIR)" > $(HOME)/.local/bin/wealthpilot
	@chmod +x $(HOME)/.local/bin/wealthpilot
	@echo "✅ 已安装到 ~/.local/bin/wealthpilot，现在可以在任意目录运行：wealthpilot"
	@case ":$$PATH:" in *":$(HOME)/.local/bin:"*) ;; *) echo "   注意：~/.local/bin 不在 PATH 里，需要先加进去";; esac

uninstall:       ## 移除全局命令
	@rm -f $(HOME)/.local/bin/wealthpilot && echo "已移除 ~/.local/bin/wealthpilot"

dev:             ## 启动后端 + 工作台（开发模式）
	@echo "启动后端（:8000）+ 工作台（http://localhost:5180）..."
	cd backend && uv run uvicorn wealthpilot.main:app --reload --port 8000 &
	npm --prefix workbench run dev

workbench:       ## 仅启动工作台（:5180，/api 代理到 :8000）
	npm --prefix workbench run dev

demo-build:      ## 构建在线演示版（无后端，回放录好的真实结果）
	cd workbench && VITE_DEMO=1 WP_BASE=/wealthpilot/ npm run build

record-demo:     ## 重新录制在线演示的数据快照（会调用真实模型）
	cd backend && uv run python scripts/record_demo.py

backend:         ## 仅启动后端
	cd backend && uv run uvicorn wealthpilot.main:app --reload --port 8000

test:            ## 运行测试
	cd backend && uv run pytest -v

docker:          ## Docker Compose 启动
	@test -f backend/.env || cp backend/.env.example backend/.env
	docker compose up --build

clean:           ## 清理生成文件
	rm -rf backend/data/ workbench/node_modules/ workbench/dist/ backend/.venv/

config:          ## 查看当前配置
	cd backend && uv run python -m wealthpilot config

tui:             ## 终端入口：研究、行情、选股、复盘（远程：make tui SERVER=http://host:8000）
	cd backend && uv run wealthpilot $(if $(SERVER),--server $(SERVER),)

chat:            ## 终端交互式 AI 对话
	cd backend && uv run python -m wealthpilot chat

mcp:             ## 启动 MCP Server (stdio, for Claude Code)
	cd backend && uv run python -m wealthpilot mcp

ask:             ## 非交互式 AI 查询（例: make ask Q="查净值"）
	cd backend && uv run python -m wealthpilot ask "$(Q)"

help:            ## 显示帮助
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'
