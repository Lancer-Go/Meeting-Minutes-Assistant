"""M4 · llm_registry 模块 — 模型注册表（TG-0）。

模型别名 → `ModelSpec(provider / base_url / model / api_key)` 映射，配置化热切换。

设计（面向可扩展，而非写死 qwen）：
- **供应商目录** `_PROVIDER_CATALOG`：内置 DeepSeek / OpenAI(GPT) / 通义(Qwen) / 智谱(GLM) / 月之暗面(Kimi)
  等 OpenAI 兼容供应商的 base_url 与密钥环境变量。新增供应商 = 目录加一行。
- **内置别名** `_DEFAULT_ALIASES`：常用模型快捷名；新增模型 = 这里登记一行。
- **零改码扩展**：`MMA_LLM_ALIASES`（JSON 环境变量）可在不改代码的情况下增改任意 OpenAI 兼容别名，
  例 `{"gpt-4o-mini": {"provider": "openai", "model": "gpt-4o-mini"}}`（可选 base_url / api_key_env）。
- `MMA_LLM_ALIAS` 指定当前生效别名，改环境变量即可热切换（ASR 维持现状）。

summary 与 extractor 统一经本注册表取 base_url / model / api_key；凡 OpenAI 兼容接口均可复用
`OpenAILikeLLM` / `OpenAILikeExtractor`，无需为每家供应商写新类。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

from app import config

# 供应商目录：provider → OpenAI 兼容 base_url + 密钥环境变量
_PROVIDER_CATALOG: dict[str, dict] = {
    "deepseek": {"base_url": "https://api.deepseek.com", "key_env": "DEEPSEEK_API_KEY"},
    "openai": {"base_url": "https://api.openai.com/v1", "key_env": "OPENAI_API_KEY"},
    "qwen": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
             "key_env": "DASHSCOPE_API_KEY"},
    "zhipu": {"base_url": "https://open.bigmodel.cn/api/paas/v4", "key_env": "ZHIPU_API_KEY"},
    "moonshot": {"base_url": "https://api.moonshot.cn/v1", "key_env": "MOONSHOT_API_KEY"},
}

# 内置别名：alias → provider + 默认 model
_DEFAULT_ALIASES: dict[str, dict] = {
    "v4-pro": {"provider": "deepseek", "model": "deepseek-v4-pro"},
    "v4-flash": {"provider": "deepseek", "model": "deepseek-v4-flash"},
    "qwen-plus": {"provider": "qwen", "model": "qwen-plus"},
    "gpt-4o": {"provider": "openai", "model": "gpt-4o"},
    "glm-4-plus": {"provider": "zhipu", "model": "glm-4-plus"},
    "moonshot-v1-8k": {"provider": "moonshot", "model": "moonshot-v1-8k"},
}

# 旧 provider 名 → 默认别名（向后兼容 M1~M3 的 deepseek / qwen 叫法）
_PROVIDER_DEFAULT_ALIAS = {
    "deepseek": "v4-pro",
    "qwen": "qwen-plus",
    "openai": "gpt-4o",
    "zhipu": "glm-4-plus",
    "moonshot": "moonshot-v1-8k",
}


@dataclass(frozen=True)
class ModelSpec:
    alias: str
    provider: str          # 供应商（deepseek / openai / qwen / zhipu / moonshot / …）
    base_url: str
    model: str
    api_key: str

    def available(self) -> bool:
        return bool(self.api_key)


def _provider_api_key(provider: str) -> str:
    """按供应商取密钥（qwen 兼容 QWEN_API_KEY 或 DASHSCOPE_API_KEY）。"""
    if provider == "deepseek":
        return config.DEEPSEEK_API_KEY
    if provider == "openai":
        return config.OPENAI_API_KEY
    if provider == "qwen":
        return config.QWEN_API_KEY or config.DASHSCOPE_API_KEY
    if provider == "zhipu":
        return config.ZHIPU_API_KEY
    if provider == "moonshot":
        return config.MOONSHOT_API_KEY
    return ""


def _env_aliases() -> dict[str, dict]:
    """解析 `MMA_LLM_ALIASES`（JSON），零改码扩展/覆盖别名。"""
    raw = config.MMA_LLM_ALIASES
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): v for k, v in data.items() if isinstance(v, dict)}


def _resolve_api_key(provider: str, spec: dict) -> str:
    env = spec.get("api_key_env")
    if env:
        return os.getenv(env, "") or ""
    return _provider_api_key(provider)


def build_specs() -> dict[str, ModelSpec]:
    """构建全部别名 → ModelSpec（内置 + 环境变量扩展）。每次调用读取最新 config（支持测试 monkeypatch）。"""
    aliases: dict[str, dict] = dict(_DEFAULT_ALIASES)
    aliases.update(_env_aliases())
    specs: dict[str, ModelSpec] = {}
    for alias, spec in aliases.items():
        provider = spec.get("provider", "openai")
        cat = _PROVIDER_CATALOG.get(provider, {})
        base_url = spec.get("base_url") or cat.get("base_url", "")
        model = spec.get("model", alias)
        if alias == "v4-pro":
            model = config.MMA_LLM_MODEL or config.DEEPSEEK_MODEL
        elif alias == "qwen-plus":
            model = config.MMA_QWEN_MODEL
        specs[alias] = ModelSpec(alias, provider, base_url, model,
                                 _resolve_api_key(provider, spec))
    return specs


def resolve(alias: str) -> ModelSpec:
    """解析模型别名 → ModelSpec。兼容旧 provider 名（deepseek / qwen / openai / zhipu / moonshot）。"""
    specs = build_specs()
    alias = _PROVIDER_DEFAULT_ALIAS.get(alias, alias)
    if alias not in specs:
        raise ValueError(f"未知模型别名: {alias}（可选 {sorted(specs)}）")
    return specs[alias]


def family_of(alias: str) -> str:
    """别名所属供应商（provider），未知返回原名。"""
    try:
        return resolve(alias).provider
    except ValueError:
        return alias


def active_summary_alias(provider_name: str | None = None) -> str:
    """当前纪要生成应使用的模型别名。

    provider_name 为旧 provider 名（deepseek / qwen / extractive）时：
    - extractive → 返回 extractive（本地兜底）
    - 其余 → 优先 `MMA_LLM_ALIAS`（热切换入口），否则用该 provider 的默认别名。
    """
    if provider_name == "extractive":
        return "extractive"
    alias = config.MMA_LLM_ALIAS or ""
    if alias in build_specs():
        return alias
    if provider_name in _PROVIDER_DEFAULT_ALIAS:
        return _PROVIDER_DEFAULT_ALIAS[provider_name]
    return alias or "v4-pro"


def active_extractor_alias(provider_name: str | None = None) -> str:
    """当前抽取器应使用的模型别名（rule 本地兜底除外，其余跟随纪要模型）。"""
    if provider_name == "rule":
        return "rule"
    return active_summary_alias(provider_name)
