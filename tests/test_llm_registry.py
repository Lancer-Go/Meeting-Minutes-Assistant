"""M4 · llm_registry 模型注册表单元测试（TG-0）。"""
import pytest

from app import llm_registry as registry
from app.llm_registry import ModelSpec


def test_resolve_aliases():
    s = registry.resolve("v4-pro")
    assert s.provider == "deepseek"
    assert s.model == "deepseek-v4-pro"
    assert s.base_url == "https://api.deepseek.com"
    assert registry.resolve("v4-flash").model == "deepseek-v4-flash"
    assert registry.resolve("qwen-plus").provider == "qwen"


def test_resolve_legacy_provider_names():
    assert registry.resolve("deepseek").alias == "v4-pro"
    assert registry.resolve("qwen").alias == "qwen-plus"


def test_resolve_unknown():
    with pytest.raises(ValueError):
        registry.resolve("nope")


def test_model_spec_available():
    assert ModelSpec("a", "deepseek", "http://x", "m", "key").available() is True
    assert ModelSpec("a", "deepseek", "http://x", "m", "").available() is False


def test_active_summary_alias_default():
    assert registry.active_summary_alias("deepseek") == "v4-pro"
    assert registry.active_summary_alias("extractive") == "extractive"


def test_active_summary_alias_hot_switch(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "MMA_LLM_ALIAS", "v4-flash")
    assert registry.active_summary_alias("deepseek") == "v4-flash"
    monkeypatch.setattr(config, "MMA_LLM_ALIAS", "qwen-plus")
    assert registry.active_summary_alias("deepseek") == "qwen-plus"


def test_active_extractor_alias():
    assert registry.active_extractor_alias("rule") == "rule"
    assert registry.active_extractor_alias("deepseek") == "v4-pro"


def test_family_of():
    assert registry.family_of("v4-pro") == "deepseek"
    assert registry.family_of("qwen-plus") == "qwen"
    assert registry.family_of("unknown") == "unknown"


def test_summary_alias_factory(monkeypatch):
    """v4-flash 别名经 get_llm_provider 构造出 flash 模型（去硬编码）。"""
    from app import config
    from app.summary import get_llm_provider
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "fake-key")
    llm = get_llm_provider("v4-flash")
    assert llm.model == "deepseek-v4-flash"
    assert llm.base_url == "https://api.deepseek.com"


def test_extractor_alias_factory(monkeypatch):
    """v4-flash 别名经 get_extractor_provider 构造出 flash 抽取器。"""
    from app import config
    from app.extractor import get_extractor_provider
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "fake-key")
    e = get_extractor_provider("v4-flash")
    assert e.model == "deepseek-v4-flash"
    assert e.base_url == "https://api.deepseek.com"


def test_resolve_new_providers():
    """内置供应商目录覆盖 GPT / GLM / Kimi（不止 qwen）。"""
    assert registry.resolve("gpt-4o").provider == "openai"
    assert registry.resolve("gpt-4o").base_url == "https://api.openai.com/v1"
    assert registry.resolve("glm-4-plus").provider == "zhipu"
    assert registry.resolve("moonshot-v1-8k").provider == "moonshot"


def test_resolve_provider_name_to_alias():
    assert registry.resolve("openai").alias == "gpt-4o"
    assert registry.resolve("zhipu").alias == "glm-4-plus"
    assert registry.resolve("moonshot").alias == "moonshot-v1-8k"


def test_env_aliases_extension(monkeypatch):
    """MMA_LLM_ALIASES 零改码扩展新模型别名。"""
    from app import config
    monkeypatch.setattr(config, "MMA_LLM_ALIASES",
                        '{"gpt-4o-mini": {"provider": "openai", "model": "gpt-4o-mini"}}')
    s = registry.resolve("gpt-4o-mini")
    assert s.provider == "openai"
    assert s.model == "gpt-4o-mini"
    assert s.base_url == "https://api.openai.com/v1"


def test_env_aliases_custom_base_url_and_key(monkeypatch):
    """自定义供应商：显式 base_url + api_key_env，不依赖内置目录。"""
    from app import config
    monkeypatch.setattr(config, "MMA_LLM_ALIASES",
                        '{"my-llm": {"provider": "custom", "base_url": "https://x/v1",'
                        ' "model": "m", "api_key_env": "OPENAI_API_KEY"}}')
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    s = registry.resolve("my-llm")
    assert s.base_url == "https://x/v1"
    assert s.model == "m"
    assert s.api_key == "sk-x"
    assert s.available() is True


def test_get_llm_provider_new_alias(monkeypatch):
    """get_llm_provider 对未登记别名回退到注册表（GPT 可用）。"""
    from app import config
    from app.summary import get_llm_provider
    monkeypatch.setattr(config, "OPENAI_API_KEY", "fake-key")
    llm = get_llm_provider("gpt-4o")
    assert llm.model == "gpt-4o"
    assert llm.base_url == "https://api.openai.com/v1"


def test_get_extractor_provider_new_alias(monkeypatch):
    """get_extractor_provider 对未登记别名回退到注册表（GLM 可用）。"""
    from app import config
    from app.extractor import get_extractor_provider
    monkeypatch.setattr(config, "ZHIPU_API_KEY", "fake-key")
    e = get_extractor_provider("glm-4-plus")
    assert e.model == "glm-4-plus"
    assert e.base_url == "https://open.bigmodel.cn/api/paas/v4"
