"""pipeline 模块单元测试（成本估算 / Provider 降级解析）。"""
from app.pipeline import estimate_cost, resolve_asr_name, resolve_llm_name


def test_estimate_cost_cloud():
    asr_cost, llm_cost = estimate_cost("tencent", 60.0, "deepseek", 1000)
    assert asr_cost > 0
    assert llm_cost > 0


def test_estimate_cost_offline():
    asr_cost, llm_cost = estimate_cost("whisper", 60.0, "extractive", 1000)
    assert asr_cost == 0
    assert llm_cost == 0


def test_estimate_cost_zero_chars():
    asr_cost, llm_cost = estimate_cost("tencent", 60.0, "deepseek", 0)
    assert asr_cost > 0
    assert llm_cost == 0


def test_resolve_asr_keeps_whisper():
    assert resolve_asr_name("whisper") == "whisper"


def test_resolve_asr_fallback(monkeypatch):
    monkeypatch.setattr("app.pipeline.asr_has_creds", lambda n: False)
    assert resolve_asr_name("tencent") == "whisper"


def test_resolve_asr_no_fallback(monkeypatch):
    monkeypatch.setattr("app.pipeline.asr_has_creds", lambda n: True)
    assert resolve_asr_name("tencent") == "tencent"


def test_resolve_llm_fallback(monkeypatch):
    monkeypatch.setattr("app.pipeline.llm_has_creds", lambda n: False)
    assert resolve_llm_name("deepseek") == "extractive"


def test_resolve_llm_keeps_extractive():
    assert resolve_llm_name("extractive") == "extractive"
