"""能接哪些模型服务。命令行的配置向导和网页的设置页用的是同一份。

model 一栏是"通常能用的一个模型名"，只在用户没填的时候拿来预填 —— 各家的模型名经常换，以服务商自己的文档为准。
要求只有一条：模型得支持工具调用（function calling），不然 Agent 取不了数。
"""

from __future__ import annotations

PRESETS: list[dict] = [
    {"key": "deepseek", "label": "DeepSeek", "provider": "deepseek", "base_url": "https://api.deepseek.com", "model": "deepseek-chat",
     "needs_key": True, "note": "便宜，中文好", "key_page": "https://platform.deepseek.com/api_keys"},
    {"key": "claude", "label": "Claude（Anthropic）", "provider": "anthropic", "base_url": "", "model": "claude-sonnet-5-5",
     "needs_key": True, "note": "质量好，贵一些", "key_page": "https://console.anthropic.com/"},
    {"key": "siliconflow", "label": "硅基流动", "provider": "openai", "base_url": "https://api.siliconflow.cn/v1", "model": "deepseek-ai/DeepSeek-V3",
     "needs_key": True, "note": "一个 Key 用多家的开源模型", "key_page": "https://cloud.siliconflow.cn/account/ak"},
    {"key": "zhipu", "label": "智谱", "provider": "openai", "base_url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4-flash",
     "needs_key": True, "note": "", "key_page": "https://open.bigmodel.cn/usercenter/apikeys"},
    {"key": "moonshot", "label": "Moonshot（Kimi）", "provider": "openai", "base_url": "https://api.moonshot.cn/v1", "model": "moonshot-v1-32k",
     "needs_key": True, "note": "", "key_page": "https://platform.moonshot.cn/console/api-keys"},
    {"key": "dashscope", "label": "阿里云百炼（通义）", "provider": "openai", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus",
     "needs_key": True, "note": "", "key_page": "https://bailian.console.aliyun.com/"},
    {"key": "ark", "label": "火山方舟（豆包）", "provider": "openai", "base_url": "https://ark.cn-beijing.volces.com/api/v3", "model": "",
     "needs_key": True, "note": "模型名填你在方舟控制台建的接入点 ID", "key_page": "https://console.volcengine.com/ark"},
    {"key": "openrouter", "label": "OpenRouter", "provider": "openai", "base_url": "https://openrouter.ai/api/v1", "model": "deepseek/deepseek-chat",
     "needs_key": True, "note": "", "key_page": "https://openrouter.ai/keys"},
    {"key": "openai", "label": "OpenAI", "provider": "openai", "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini",
     "needs_key": True, "note": "", "key_page": "https://platform.openai.com/api-keys"},
    {"key": "ollama", "label": "本机 Ollama", "provider": "openai", "base_url": "http://localhost:11434/v1", "model": "qwen2.5:14b",
     "needs_key": False, "note": "不花钱；要先装好 Ollama 并拉好模型，小模型效果会差一截", "key_page": ""},
]
BY_KEY = {p["key"]: p for p in PRESETS}
ALIASES = {"anthropic": "claude", "kimi": "moonshot", "qwen": "dashscope", "tongyi": "dashscope", "bailian": "dashscope", "doubao": "ark",
           "volc": "ark", "glm": "zhipu", "local": "ollama", "硅基流动": "siliconflow", "智谱": "zhipu", "通义": "dashscope", "豆包": "ark"}


def custom(base_url: str) -> dict:
    """清单之外的服务：只知道一个接口地址，模型名得用户自己给。Key 可有可无 —— 自己机器上跑的服务通常不要。"""
    return {"key": "custom", "label": "自定义服务", "provider": "openai", "base_url": base_url.strip(), "model": "", "needs_key": False, "note": "", "key_page": ""}


def find(name: str) -> dict | None:
    key = (name or "").strip().lower()
    return BY_KEY.get(ALIASES.get(key, key))


def guess_from_key(api_key: str) -> dict:
    """只给了一个 Key、没说是哪家的：按前缀猜。Anthropic 的 Key 以 sk-ant- 开头，其余当作 DeepSeek。"""
    return BY_KEY["claude"] if api_key.strip().startswith("sk-ant-") else BY_KEY["deepseek"]


def changes_for(preset: dict, api_key: str = "", model: str = "", base_url: str = "") -> dict:
    """选了这家服务，要写哪些配置项。"""
    model = model.strip() or preset["model"]
    if preset["provider"] == "deepseek":
        return {"ai_provider": "deepseek", "deepseek_api_key": api_key, "deepseek_model": model}
    if preset["provider"] == "anthropic":
        return {"ai_provider": "anthropic", "anthropic_api_key": api_key, "anthropic_model": model}
    return {"ai_provider": "openai", "openai_api_key": api_key, "openai_model": model, "openai_base_url": base_url.strip() or preset["base_url"]}
