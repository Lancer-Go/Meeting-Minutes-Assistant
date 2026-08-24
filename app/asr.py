"""M1 · asr 模块 — 语音转写（可插拔 Provider）。

抽象 `ASRProvider` 接口，主用腾讯云 16k_zh（M0 锁定），本地 faster-whisper 作离线兜底。
腾讯云长音频走**切片法**（base64 ≤5MB ≈2min），逐段识别后按时间偏移合并，支持单场 ≤ 2h。
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app import audio, config


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


# --------------------------------------------------------------------------- 本地离线兜底
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


# --------------------------------------------------------------------------- 云 ASR
class TencentASR(ASRProvider):
    """腾讯云录音文件识别（16k_zh，M0 锁定）。

    单段音频走 base64（SourceType=1，≤5MB）；长音频自动切片逐段识别再合并。
    """

    name = "tencent"

    def __init__(self, secret_id: str = "", secret_key: str = "",
                 engine: str = "16k_zh", chunk_seconds: float | None = None):
        self.secret_id = secret_id or config.TENCENT_SECRET_ID
        self.secret_key = secret_key or config.TENCENT_SECRET_KEY
        self.engine = engine
        self.model = engine
        self.chunk_seconds = chunk_seconds or config.ASR_CHUNK_SECONDS
        if not (self.secret_id and self.secret_key):
            raise RuntimeError("缺少 TENCENT_SECRET_ID / TENCENT_SECRET_KEY（腾讯云）。请在 .env 配置后重试。")

    def _recognize_chunk(self, wav: Path) -> list[Segment]:
        """识别单段音频（base64 ≤5MB），返回段内相对时间的 segments。"""
        import base64

        from tencentcloud.asr.v20190614 import asr_client, models
        from tencentcloud.common import credential
        from tencentcloud.common.profile.client_profile import ClientProfile

        raw = Path(wav).read_bytes()
        if len(raw) > 3_750_000:  # base64 后约 5MB（接口上限）
            raise RuntimeError(
                f"腾讯云单段音频上限 base64 ≤5MB，当前 {len(raw) / 1e6:.1f}MB 超限。"
                f"请减小切片时长（当前 {self.chunk_seconds}s）。"
            )

        cred = credential.Credential(self.secret_id, self.secret_key)
        cp = ClientProfile()
        client = asr_client.AsrClient(cred, "ap-guangzhou", cp)

        req = models.CreateRecTaskRequest()
        req.EngineModelType = self.engine
        req.ChannelNum = 1
        req.ResTextFormat = 3     # 含标点 + 分句时间戳（ResultDetail.FinalSentence/StartMs/EndMs）
        req.SourceType = 1        # 音频数据（base64）
        req.Data = base64.b64encode(raw).decode()
        req.DataLen = len(raw)

        resp = client.CreateRecTask(req)
        task_id = resp.Data.TaskId

        deadline = time.time() + 600
        sresp = None
        while time.time() < deadline:
            st = models.DescribeTaskStatusRequest()
            st.TaskId = task_id
            sresp = client.DescribeTaskStatus(st)
            status = sresp.Data.Status  # 0 等待 / 1 执行中 / 2 成功 / 3 失败
            if status == 2:
                break
            if status == 3:
                raise RuntimeError(f"腾讯云转写失败: {sresp.Data.ErrorMsg}")
            time.sleep(2)
        else:
            raise TimeoutError("腾讯云转写超时（>10min）")

        segs = []
        for r in sresp.Data.ResultDetail or []:
            segs.append(Segment(float(r.StartMs) / 1000.0, float(r.EndMs) / 1000.0,
                                r.FinalSentence or ""))
        return segs

    def transcribe(self, wav: Path) -> Transcript:
        t0 = time.time()
        wav = Path(wav)
        # 超切片时长或超 base64 上限 → 切片逐段识别
        if (audio.get_duration(wav) > self.chunk_seconds + 5
                or wav.stat().st_size > 3_750_000):
            chunks = audio.split_wav(wav, self.chunk_seconds, wav.parent / "chunks")
            all_segs: list[Segment] = []
            for i, c in enumerate(chunks):
                offset = i * self.chunk_seconds
                for s in self._recognize_chunk(c):
                    s.start += offset
                    s.end += offset
                    all_segs.append(s)
            text = "".join(s.text for s in all_segs)
        else:
            all_segs = self._recognize_chunk(wav)
            text = "".join(s.text for s in all_segs)
        return Transcript(segments=all_segs, text=text, provider=self.name,
                          model=self.engine, elapsed_s=time.time() - t0,
                          cost_rmb=0.0)  # 成本估算见 pipeline.estimate_cost


class AliyunNLSRealtimeASR(ASRProvider):
    """阿里云智能语音交互（NLS）实时语音转写（无需 OSS）。

    走 websocket 流式识别本地音频（NlsSpeechTranscriber），返回带时间戳的分句。
    ⚠️ 实时接口按实时节奏处理，长音频耗时接近音频时长；批量场景建议「录音文件识别」。
    """

    name = "aliyun"

    def __init__(self, app_key: str = "", access_key_id: str = "",
                 access_key_secret: str = "", region: str = "cn-shanghai"):
        self.app_key = app_key or config.ALIYUN_APP_KEY
        self.ak_id = access_key_id or config.ALIYUN_ACCESS_KEY_ID
        self.ak_secret = access_key_secret or config.ALIYUN_ACCESS_KEY_SECRET
        self.region = region
        self.model = "nls-realtime"
        if not (self.app_key and self.ak_id and self.ak_secret):
            raise RuntimeError(
                "缺少 ALIYUN_APP_KEY / ALIYUN_ACCESS_KEY_ID / ALIYUN_ACCESS_KEY_SECRET。"
                "（阿里云智能语音交互的 AppKey 是 NLS 体系，需配套 AccessKey。）"
            )

    def transcribe(self, wav: Path) -> Transcript:
        import json as _json
        import time as _t
        import wave as _wave
        from nls.token import getToken
        from nls.speech_transcriber import NlsSpeechTranscriber

        token = getToken(self.ak_id, self.ak_secret)
        segs: list[Segment] = []
        begin_map: dict[int, float] = {}
        errors: list[str] = []

        def on_sentence_begin(message, *args):
            m = _json.loads(message)
            p = m.get("payload", {})
            begin_map[p.get("index", 0)] = float(p.get("time", 0))

        def on_sentence_end(message, *args):
            m = _json.loads(message)
            p = m.get("payload", {})
            text = (p.get("result") or "").strip()
            if text:
                segs.append(Segment(begin_map.get(p.get("index", 0), 0.0) / 1000.0,
                                    float(p.get("time", 0)) / 1000.0, text))

        def on_error(message, *args):
            errors.append(message)

        sr = NlsSpeechTranscriber(token=token, appkey=self.app_key,
                                  on_sentence_begin=on_sentence_begin,
                                  on_sentence_end=on_sentence_end,
                                  on_error=on_error)
        t0 = _t.time()
        sr.start(aformat="pcm", sample_rate=16000, ch=1,
                 enable_punctuation_prediction=True,
                 enable_intermediate_result=False)

        with _wave.open(str(wav), "rb") as w:
            if w.getframerate() != 16000 or w.getnchannels() != 1:
                raise RuntimeError("阿里云实时识别需 16kHz 单声道 WAV")
            while True:
                data = w.readframes(320)  # 20ms 一帧
                if not data:
                    break
                sr.send_audio(data)

        duration_s = segs[-1].end if segs else 0.0
        sr.stop(timeout=max(int(duration_s) + 60, 30))
        if errors:
            raise RuntimeError(f"阿里云转写错误: {errors[-1]}")
        text = "".join(s.text for s in segs)
        return Transcript(segments=segs, text=text, provider=self.name,
                          model=self.model, elapsed_s=_t.time() - t0,
                          cost_rmb=0.0)


class IFlytekASR(ASRProvider):
    """讯飞开放平台（需 XFYUN_APP_ID / XFYUN_API_KEY / XFYUN_API_SECRET）。

    ⚠️ 未实现：讯飞「录音文件识别」（LFASR）需自研 HMAC 签名并上传音频，流程较长。
    接入留待提供密钥后按官方文档补齐。
    """

    name = "iflytek"

    def __init__(self, app_id: str = "", api_key: str = "", api_secret: str = ""):
        self.app_id = app_id or config.XFYUN_APP_ID
        self.api_key = api_key or config.XFYUN_API_KEY
        self.api_secret = api_secret or config.XFYUN_API_SECRET
        self.model = "iflytek-lfasr"
        if not (self.app_id and self.api_key and self.api_secret):
            raise RuntimeError("缺少讯飞 XFYUN_APP_ID / XFYUN_API_KEY / XFYUN_API_SECRET。")

    def transcribe(self, wav: Path) -> Transcript:
        raise NotImplementedError(
            "讯飞录音文件识别（LFASR）尚未实现：需 HMAC-SHA256 签名 + 音频上传 + 轮询结果。"
        )


PROVIDERS = {
    "whisper": WhisperLocalASR,
    "aliyun": AliyunNLSRealtimeASR,
    "tencent": TencentASR,
    "iflytek": IFlytekASR,
}


def get_asr_provider(name: str, **kwargs) -> ASRProvider:
    """按名称构造 ASR Provider。"""
    if name not in PROVIDERS:
        raise ValueError(f"未知 ASR provider: {name}（可选 {list(PROVIDERS)}）")
    return PROVIDERS[name](**kwargs)


def has_cloud_credentials(name: str) -> bool:
    """判断指定云端 ASR 是否已配置密钥（供降级判断）。"""
    if name == "tencent":
        return bool(config.TENCENT_SECRET_ID and config.TENCENT_SECRET_KEY)
    if name == "aliyun":
        return bool(config.ALIYUN_APP_KEY and config.ALIYUN_ACCESS_KEY_ID
                    and config.ALIYUN_ACCESS_KEY_SECRET)
    if name == "iflytek":
        return bool(config.XFYUN_APP_ID and config.XFYUN_API_KEY and config.XFYUN_API_SECRET)
    return True  # whisper 本地无需密钥
