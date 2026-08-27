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
