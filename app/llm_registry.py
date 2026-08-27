"""M4 · llm_registry 模块 — 模型注册表（TG-0）。

模型别名 → `ModelSpec(provider / base_url / model / api_key)` 映射，配置化热切换。
summary 与 extractor 统一经本注册表取 base_url / model / api_key，去掉类内硬编码。
`MMA_LLM_ALIAS`（默认 v4-pro）指定当前生效的云端 LLM 模型：改环境变量即可切换，无需改代码。
"""
from __future__ import annotations

from dataclasses import dataclass

from app import config

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# 别名 → 家族（provider）
_FAMILY = {
    "v4-pro": "deepseek",
    "v4-flash": "deepseek",
    "qwen-plus": "qwen",
}

# 旧 provider 名 → 默认别名（向后兼容 M1~M3 的 deepseek / qwen 叫法）
_PROVIDER_DEFAULT_ALIAS = {
    "deepseek": "v4-pro",
    "qwen": "qwen-plus",
}


@dataclass(frozen=True)
class ModelSpec:
    alias: str
    provider: str          # deepseek | qwen（OpenAI 兼容家族）
    base_url: str
    model: str
    api_key: str

    def available(self) -> bool:
        return bool(self.api_key)


def _qwen_key() -> str:
    return config.QWEN_API_KEY or config.DASHSCOPE_API_KEY


def build_specs() -> dict[str, ModelSpec]:
    """按当前配置构建全部别名 → ModelSpec。每次调用读取最新 config（支持测试 monkeypatch）。"""
    return {
        "v4-pro": ModelSpec("v4-pro", "deepseek", DEEPSEEK_BASE_URL,
                            config.MMA_LLM_MODEL or config.DEEPSEEK_MODEL,
                            config.DEEPSEEK_API_KEY),
        "v4-flash": ModelSpec("v4-flash", "deepseek", DEEPSEEK_BASE_URL,
                              "deepseek-v4-flash", config.DEEPSEEK_API_KEY),
        "qwen-plus": ModelSpec("qwen-plus", "qwen", QWEN_BASE_URL,
                               config.MMA_QWEN_MODEL, _qwen_key()),
    }


def resolve(alias: str) -> ModelSpec:
    """解析模型别名 → ModelSpec。兼容旧 provider 名（deepseek / qwen）。"""
    specs = build_specs()
    alias = _PROVIDER_DEFAULT_ALIAS.get(alias, alias)
    if alias not in specs:
        raise ValueError(f"未知模型别名: {alias}（可选 {sorted(specs)}）")
    return specs[alias]


def family_of(alias: str) -> str:
    """别名所属家族（deepseek / qwen），未知返回原名。"""
    return _FAMILY.get(alias, alias)


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
