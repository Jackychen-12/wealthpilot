#!/usr/bin/env bash
# WealthPilot 一键安装。
#
#   curl -fsSL https://raw.githubusercontent.com/Jackychen-12/wealthpilot/main/scripts/install.sh | bash
#
# 它做这几件事，做完告诉你下一步：
#   1. 没有 uv 就先装 uv（Python 的包管理器，用它装依赖，不动你系统里的 Python）
#   2. 把代码放到 ~/.wealthpilot/app（已经有就更新）
#   3. 装依赖；机器上有 Node.js 就顺手把网页版构建出来，没有也不影响终端使用
#   4. 在 ~/.local/bin 放一个 wealthpilot 命令
# 你的数据（配置、数据库、研究方法）都在 ~/.wealthpilot，和代码分开，升级、重装都不会动它。
#
# 可以用环境变量改默认行为：
#   WEALTHPILOT_KEY=sk-xxx        装完直接把模型 Key 配好（自动认出是 DeepSeek 还是 Claude），真正一条命令就能用
#   WEALTHPILOT_HOME=目录         数据放哪（默认 ~/.wealthpilot）
#   WEALTHPILOT_DIR=目录          代码放哪（默认 $WEALTHPILOT_HOME/app）
#   WEALTHPILOT_BIN_DIR=目录      命令放哪（默认 ~/.local/bin）
#   WEALTHPILOT_REPO / WEALTHPILOT_BRANCH   从哪个仓库、哪个分支装
#   WEALTHPILOT_SKIP_WEB=1        不构建网页版
# 卸载：bash install.sh --uninstall（只删代码和命令，数据留着）

set -euo pipefail

REPO="${WEALTHPILOT_REPO:-https://github.com/Jackychen-12/wealthpilot.git}"
BRANCH="${WEALTHPILOT_BRANCH:-main}"
DATA="${WEALTHPILOT_HOME:-$HOME/.wealthpilot}"
APP="${WEALTHPILOT_DIR:-$DATA/app}"
BIN="${WEALTHPILOT_BIN_DIR:-$HOME/.local/bin}"

say()  { printf '%s\n' "$*"; }
step() { printf '\n\033[1m%s\033[0m\n' "$*"; }
fail() { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

if [ "${1:-}" = "--uninstall" ]; then
  rm -f "$BIN/wealthpilot"
  rm -rf "$APP"
  say "已卸载：命令和代码都删了。"
  say "你的数据还在 $DATA（配置、数据库、研究方法）。确定不要了再自己删：rm -rf \"$DATA\""
  exit 0
fi

command -v git >/dev/null 2>&1 || fail "需要先装 git。macOS：xcode-select --install；Ubuntu：sudo apt install git"
command -v curl >/dev/null 2>&1 || fail "需要先装 curl"

step "1/4 准备 uv"
if ! command -v uv >/dev/null 2>&1; then
  say "没有找到 uv，用它官方的安装脚本装一个（装在你的用户目录下，不需要管理员权限）…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  command -v uv >/dev/null 2>&1 || fail "uv 装完了但找不到命令。新开一个终端窗口再运行一次这个脚本。"
fi
say "✓ $(uv --version)"

step "2/4 获取代码 → $APP"
mkdir -p "$DATA"
if [ -d "$APP/.git" ]; then
  git -C "$APP" fetch --quiet origin "$BRANCH"
  git -C "$APP" checkout --quiet "$BRANCH"
  git -C "$APP" pull --quiet --ff-only origin "$BRANCH" || fail "代码目录里有本地改动，没法直接更新：$APP"
  say "✓ 已更新到最新"
else
  [ -e "$APP" ] && fail "$APP 已经存在但不是 WealthPilot 的代码目录。换个位置：WEALTHPILOT_DIR=别的目录"
  git clone --quiet --depth 1 --branch "$BRANCH" "$REPO" "$APP"
  say "✓ 已下载"
fi

step "3/4 安装依赖"
(cd "$APP/backend" && uv sync --quiet --extra feishu) || fail "依赖没装上。多半是网络问题，稍后重新运行这个脚本即可（会接着装）。"
say "✓ 依赖装好了"
if [ "${WEALTHPILOT_SKIP_WEB:-}" = "1" ]; then
  say "· 按你的要求跳过了网页版"
elif command -v npm >/dev/null 2>&1; then
  say "构建网页版（一两分钟）…"
  # npm ci 照锁文件装，不会改动仓库里的文件 —— 代码目录保持干净，以后 wealthpilot update 才能直接拉取
  if (cd "$APP/workbench" && npm ci --no-audit --no-fund --silent && npm run build --silent -- --outDir dist-app --emptyOutDir) >/dev/null 2>&1; then
    say "✓ 网页版构建好了"
  else
    say "! 网页版没构建成，终端照样能用。之后想补：重新运行这个脚本。"
  fi
else
  say "! 没有找到 Node.js，先不构建网页版 —— 终端里什么都能做。想要网页版：装好 Node.js 后重新运行这个脚本。"
fi

step "4/4 放好 wealthpilot 命令 → $BIN"
mkdir -p "$BIN" "$DATA/skills"
# 自带的两个示例方法放进数据目录（已有的不覆盖）
for f in "$APP"/backend/skills/*.md; do [ -e "$DATA/skills/$(basename "$f")" ] || cp "$f" "$DATA/skills/"; done
cat > "$BIN/wealthpilot" <<SHIM
#!/bin/sh
# WealthPilot 的入口：数据在 $DATA，代码在 $APP。
export WEALTHPILOT_HOME="\${WEALTHPILOT_HOME:-$DATA}"
if [ ! -x "$APP/backend/.venv/bin/wealthpilot" ]; then
  echo "找不到 WealthPilot 的安装（$APP）。重新运行安装脚本即可，数据不会丢。" >&2
  exit 127
fi
exec "$APP/backend/.venv/bin/wealthpilot" "\$@"
SHIM
chmod +x "$BIN/wealthpilot"
say "✓ 命令放好了"

if [ -n "${WEALTHPILOT_KEY:-}" ]; then
  step "配置模型"
  "$BIN/wealthpilot" setup --key "$WEALTHPILOT_KEY" --no-test || say "! 模型没配上，稍后运行：wealthpilot setup"
fi

printf '\n\033[1m装好了。\033[0m\n'
case ":$PATH:" in
  *":$BIN:"*) ;;
  *) say "注意：$BIN 不在 PATH 里。把这一行加进 ~/.zshrc 或 ~/.bashrc，然后新开一个终端：
  export PATH=\"$BIN:\$PATH\"" ;;
esac
if "$BIN/wealthpilot" status >/dev/null 2>&1; then   # status 在模型配好时返回 0
  say "下一步：  wealthpilot          模型已经配好，直接开始用"
else
  say "下一步：  wealthpilot setup    选一家模型、贴一个 Key（一分钟）
          wealthpilot          开始用"
fi
say "以后升级：wealthpilot update    哪里不通：wealthpilot doctor"
