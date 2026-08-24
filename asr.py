"""TG-3 · 语音转写。

抽象 `ASRProvider` 接口，接入本地离线（faster-whisper）与云端 ASR。
默认本地 whisper（无需密钥即可跑通）；云端厂商填入密钥后即可对比 CER/耗时/成本。

用法:
    python asr.py <wav> [--provider whisper|aliyun|tencent|iflytek] [--out out.json]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class Transcript:
    segments: list[Segment] = field(default_factory=list)
    text: str = ""
    provider: str = ""
    model: str = ""
    elapsed_s: float = 0.0
    cost_rmb: float = 0.0  # 估算成本（元），实际以账单为准

    @property
    def char_count(self) -> int:
        return len(self.text)

    def to_timestamped_text(self) -> str:
        lines = []
        for s in self.segments:
            mm = int(s.start // 60)
            ss = s.start % 60
            lines.append(f"[{mm:02d}:{ss:05.2f}] {s.text.strip()}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "provider": self.provider, "model": self.model,
            "elapsed_s": round(self.elapsed_s, 2), "cost_rmb": round(self.cost_rmb, 4),
            "char_count": self.char_count,
            "segments": [asdict(s) for s in self.segments],
            "text": self.text,
        }


class ASRProvider(ABC):
    """ASR 供应商统一接口（M4 可插拔的基础）。"""
    name = "base"
    model = ""

    @abstractmethod
    def transcribe(self, wav: Path) -> Transcript:
        ...


# ------------------------------------------------------------------ 本地离线
class WhisperLocalASR(ASRProvider):
    """faster-whisper 本地转写（离线、免费、无需密钥）。首次运行会联网下载模型。"""

    name = "whisper"

    def __init__(self, model: str = "base", language: str = "zh",
                 device: str = "auto", compute_type: str = "auto"):
        self.model_name = model
        self.model = model
        self.language = language
        self.device = device
        self.compute_type = compute_type
        self._m = None

    def _load(self):
        if self._m is None:
            from faster_whisper import WhisperModel  # lazy import
            self._m = WhisperModel(self.model_name, device=self.device,
                                   compute_type=self.compute_type)
        return self._m

    def transcribe(self, wav: Path) -> Transcript:
        t0 = time.time()
        m = self._load()
        seg_iter, _info = m.transcribe(str(wav), language=self.language,
                                       vad_filter=True, beam_size=5)
        segs = [Segment(float(s.start), float(s.end), s.text) for s in seg_iter]
        text = "".join(s.text for s in segs)
        return Transcript(segments=segs, text=text, provider=self.name,
                          model=self.model_name, elapsed_s=time.time() - t0,
                          cost_rmb=0.0)


# ------------------------------------------------------------------ 云 ASR
class AliyunDashScopeASR(ASRProvider):
    """阿里云 DashScope Paraformer 录音文件识别。

    说明（⚠️ 未在本环境实测，需密钥 + 可访问的音频 URL）：
    录音文件识别需要音频位于可公网访问的 URL（先传到 OSS）。此处走
    `Transcription.async_call(file_urls=[...])` 提交后轮询结果。
    """

    name = "aliyun"

    def __init__(self, api_key: str = "", model: str = "paraformer-v2"):
        import config
        self.api_key = api_key or config.DASHSCOPE_API_KEY
        self.model = model
        if not self.api_key:
            raise RuntimeError("缺少 DASHSCOPE_API_KEY（阿里云 DashScope）。请在 .env 配置后重试。")

    def transcribe(self, wav: Path) -> Transcript:
        raise NotImplementedError(
            "阿里云录音文件识别需先将音频上传至 OSS 并传入 file_urls；"
            "接入步骤见 docs/decisions/选型决策记录.md 或联系维护者补齐 OSS 上传流程。"
        )


class TencentASR(ASRProvider):
    """腾讯云录音文件识别（需 TENCENT_SECRET_ID / TENCENT_SECRET_KEY）。

    ⚠️ 未在本环境实测：CreateRecTask(Data=base64) -> 轮询 DescribeTaskStatus。
    """

    name = "tencent"

    def __init__(self, secret_id: str = "", secret_key: str = "", engine: str = "16k_zh"):
        import config
        self.secret_id = secret_id or config.TENCENT_SECRET_ID
        self.secret_key = secret_key or config.TENCENT_SECRET_KEY
        self.engine = engine
        self.model = engine
        if not (self.secret_id and self.secret_key):
            raise RuntimeError("缺少 TENCENT_SECRET_ID / TENCENT_SECRET_KEY（腾讯云）。请在 .env 配置后重试。")

    def transcribe(self, wav: Path) -> Transcript:
        import base64
        import time as _t
        from tencentcloud.asr.v20190614 import asr_client, models
        from tencentcloud.common import credential
        from tencentcloud.common.profile.client_profile import ClientProfile
        from tencentcloud.common.profile.http_profile import HttpProfile

        cred = credential.Credential(self.secret_id, self.secret_key)
        hp = HttpProfile()
        cp = ClientProfile()
        cp.httpProfile = hp
        client = asr_client.AsrClient(cred, "ap-guangzhou", cp)

        data = base64.b64encode(Path(wav).read_bytes()).decode()
        req = models.CreateRecTaskRequest()
        req.EngineModelType = self.engine
        req.ChannelNum = 1
        req.ResTextFormat = 3  # 含时间戳
        req.SourceType = 1     # 音频数据
        req.Data = data

        t0 = _t.time()
        resp = client.CreateRecTask(req)
        task_id = resp.Data.TaskId

        deadline = t0 + 600
        while _t.time() < deadline:
            st = models.DescribeTaskStatusRequest()
            st.TaskId = task_id
            sresp = client.DescribeTaskStatus(st)
            status = sresp.Data.StatusStr
            if status in ("success", "2"):
                break
            if status in ("failed", "3"):
                raise RuntimeError(f"腾讯云转写失败: {sresp.Data.ErrorMsg}")
            _t.sleep(2)
        else:
            raise TimeoutError("腾讯云转写超时")

        segs = []
        for r in sresp.Data.ResultDetail or []:
            segs.append(Segment(float(r.StartMs) / 1000, float(r.EndMs) / 1000, r.FinalSentence or ""))
        text = "".join(s.text for s in segs)
        return Transcript(segments=segs, text=text, provider=self.name,
                          model=self.engine, elapsed_s=_t.time() - t0,
                          cost_rmb=0.0)  # 成本估算见 pipeline.estimate_cost


class IFlytekASR(ASRProvider):
    """讯飞开放平台（需 XFYUN_APP_ID / XFYUN_API_KEY / XFYUN_API_SECRET）。

    ⚠️ 未实现：讯飞「录音文件识别」（LFASR）需自研 HMAC 签名并上传音频，流程较长；
    「实时语音听写」适合流式短音频。M0 暂以阿里云 / 腾讯云 / 本地 whisper 为主，
    讯飞接入留待提供密钥后按官方文档补齐。
    """

    name = "iflytek"

    def __init__(self, app_id: str = "", api_key: str = "", api_secret: str = ""):
        import config
        self.app_id = app_id or config.XFYUN_APP_ID
        self.api_key = api_key or config.XFYUN_API_KEY
        self.api_secret = api_secret or config.XFYUN_API_SECRET
        self.model = "iflytek-lfasr"
        if not (self.app_id and self.api_key and self.api_secret):
            raise RuntimeError("缺少讯飞 XFYUN_APP_ID / XFYUN_API_KEY / XFYUN_API_SECRET。")

    def transcribe(self, wav: Path) -> Transcript:
        raise NotImplementedError(
            "讯飞录音文件识别（LFASR）尚未实现：需 HMAC-SHA256 签名 + 音频上传 + 轮询结果。"
            "详见 https://www.xfyun.cn/doc/asr/lfasr/API.html"
        )


PROVIDERS = {
    "whisper": WhisperLocalASR,
    "aliyun": AliyunDashScopeASR,
    "tencent": TencentASR,
    "iflytek": IFlytekASR,
}


def get_asr_provider(name: str, **kwargs) -> ASRProvider:
    """按名称构造 ASR Provider。"""
    if name not in PROVIDERS:
        raise ValueError(f"未知 ASR provider: {name}（可选 {list(PROVIDERS)}）")
    return PROVIDERS[name](**kwargs)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TG-3 语音转写")
    ap.add_argument("wav", help="16kHz 单声道 WAV（可由 audio.py 生成）")
    ap.add_argument("--provider", default="whisper", choices=list(PROVIDERS))
    ap.add_argument("--model", default="", help="覆盖模型名（whisper: base/small/...）")
    ap.add_argument("--out", default="", help="输出 JSON 路径（默认打印到 stdout）")
    args = ap.parse_args(argv)

    wav = Path(args.wav)
    if not wav.exists():
        print(f"错误: 文件不存在 {wav}", file=sys.stderr)
        return 1

    kwargs = {}
    if args.model:
        kwargs["model"] = args.model
    provider = get_asr_provider(args.provider, **kwargs)
    try:
        t = provider.transcribe(wav)
    except RuntimeError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1

    payload = t.to_dict()
    if args.out:
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写入: {args.out}")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"[{t.provider}/{t.model}] 耗时 {t.elapsed_s:.1f}s，字符 {t.char_count}，成本 ¥{t.cost_rmb:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
