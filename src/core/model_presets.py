"""Built-in LLM provider presets for settings UI."""
from __future__ import annotations

from typing import Any

LLM_PROVIDERS: dict[str, dict[str, Any]] = {
    "deepseek": {
        "label": "DeepSeek",
        "api_key_env": "DEEPSEEK_API_KEY",
        "default_base": "https://api.deepseek.com",
        "default_model": "deepseek/deepseek-chat",
        "models": [
            {"id": "deepseek/deepseek-chat", "label": "DeepSeek Chat"},
            {"id": "deepseek/deepseek-reasoner", "label": "DeepSeek Reasoner"},
        ],
    },
    "openai": {
        "label": "OpenAI",
        "api_key_env": "OPENAI_API_KEY",
        "default_base": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "models": [
            {"id": "gpt-4o-mini", "label": "GPT-4o Mini"},
            {"id": "gpt-4o", "label": "GPT-4o"},
            {"id": "gpt-4.1-mini", "label": "GPT-4.1 Mini"},
        ],
    },
    "anthropic": {
        "label": "Anthropic",
        "api_key_env": "ANTHROPIC_API_KEY",
        "default_base": "https://api.anthropic.com",
        "default_model": "claude-sonnet-4-20250514",
        "models": [
            {"id": "claude-sonnet-4-20250514", "label": "Claude Sonnet 4"},
            {"id": "claude-haiku-3-20240307", "label": "Claude Haiku 3"},
        ],
    },
    "zhipu": {
        "label": "智谱 AI",
        "api_key_env": "ZHIPUAI_API_KEY",
        "default_base": "https://open.bigmodel.cn/api/paas/v4",
        "default_model": "zhipu/glm-4-flash",
        "models": [
            {"id": "zhipu/glm-4-flash", "label": "GLM-4 Flash"},
            {"id": "zhipu/glm-4-plus", "label": "GLM-4 Plus"},
        ],
    },
    "moonshot": {
        "label": "Moonshot (Kimi)",
        "api_key_env": "MOONSHOT_API_KEY",
        "default_base": "https://api.moonshot.cn/v1",
        "default_model": "moonshot/moonshot-v1-8k",
        "models": [
            {"id": "moonshot/moonshot-v1-8k", "label": "Moonshot v1 8K"},
            {"id": "moonshot/moonshot-v1-32k", "label": "Moonshot v1 32K"},
            {"id": "moonshot/moonshot-v1-128k", "label": "Moonshot v1 128K"},
        ],
    },
    "ollama": {
        "label": "Ollama (本地)",
        "api_key_env": None,
        "default_base": "http://localhost:11434",
        "default_model": "ollama/qwen2.5:14b",
        "models": [
            {"id": "ollama/qwen2.5:14b", "label": "Qwen 2.5 14B"},
            {"id": "ollama/qwen2.5:7b", "label": "Qwen 2.5 7B"},
            {"id": "ollama/llama3.2", "label": "Llama 3.2"},
        ],
    },
    "custom": {
        "label": "自定义 / 中转",
        "api_key_env": "OPENAI_API_KEY",
        "default_base": "",
        "default_model": "gpt-4o-mini",
        "models": [],
        "hint": "OpenAI 兼容接口：填写 Base URL、模型 ID 和 API Key",
    },
}


def list_providers() -> list[dict[str, Any]]:
    """Return provider list for UI (without secrets)."""
    return [
        {
            "id": pid,
            "label": preset["label"],
            "default_base": preset.get("default_base", ""),
            "default_model": preset.get("default_model", ""),
            "models": preset.get("models", []),
            "hint": preset.get("hint", ""),
        }
        for pid, preset in LLM_PROVIDERS.items()
    ]


def get_provider(provider_id: str) -> dict[str, Any]:
    return LLM_PROVIDERS.get(provider_id, LLM_PROVIDERS["deepseek"])
