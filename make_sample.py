"""TG-1 · 样例数据生成（合成占位）。

用 edge-tts（微软在线 TTS，多音色轮流模拟多人讨论）合成一段中文「产品例会」，
供本地跑通 pipeline。各音色之间插入 0.5s 静音。

⚠️ 这是**合成占位数据，不是真实会议录音**。M0 验收（≥10min 中文为主、英文术语混用）
仍需用户提供真实会议音频，替换到 `samples/` 下即可（文件名无要求）。

用法:
    python make_sample.py [输出路径]     # 默认 samples/meeting-001.mp3
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# (说话人, 音色, 台词)
SCRIPT = [
    ("主持人", "zh-CN-YunjianNeural",
     "大家好，我们开始今天的周会。主要同步三个事情：版本迭代进度、客户反馈、以及下个迭代的排期。"),
    ("主持人", "zh-CN-YunjianNeural",
     "先请后端同步一下 API 联调的进度，尤其是转写接口和纪要接口的状态。"),
    ("研发A", "zh-CN-YunxiNeural",
     "后端这边，音频上传和转写接口已经联调通过了，延迟在可接受范围内。纪要生成接口还在等 LLM 的 key 到位。"),
    ("研发A", "zh-CN-YunxiNeural",
     "另外数据库 schema 今天会有一次小改动，把 task 的状态机字段补全，影响不大。"),
    ("主持人", "zh-CN-YunjianNeural",
     "好的，那纪要生成这条链路卡在 key 上，会后我找负责人去催一下。产品那边，客户反馈怎么样？"),
    ("产品", "zh-CN-XiaoxiaoNeural",
     "客户反馈主要集中在两点：一是希望纪要能自动提取行动项，二是希望支持导出 PDF。"),
    ("产品", "zh-CN-XiaoxiaoNeural",
     "第一个点我们已经排进下个迭代了，第二个 PDF 导出优先级可以往后放。"),
    ("研发B", "zh-CN-YunyangNeural",
     "前端这边，上传页面和进度条已经跑通，剩下纪要展示页还在调样式。明天应该能出一个可以联调的版本。"),
    ("主持人", "zh-CN-YunjianNeural",
     "那明天前端和后端联调纪要展示。最后确认下个迭代的排期：行动项抽取、纪要模板、还有历史检索，有没有异议？"),
    ("研发A", "zh-CN-YunxiNeural",
     "没有异议，行动项抽取我们可以先做一版基于规则的，再上大模型。"),
    ("产品", "zh-CN-XiaoxiaoNeural",
     "可以，模板我这边会整理三种：标准、精简、详细。"),
    ("主持人", "zh-CN-YunjianNeural",
     "好，那就这么定。今天会议先到这里，大家把今天的行动项认领一下。散会。"),
]


async def _tts(text: str, voice: str, out: Path) -> None:
    import edge_tts
    c = edge_tts.Communicate(text, voice)
    await c.save(str(out))


async def generate(out: Path) -> None:
    import edge_tts  # noqa: F401  (ensure importable before heavy work)

    tmp = out.parent / ".make_sample_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    pieces: list[Path] = []
    try:
        for i, (speaker, voice, text) in enumerate(SCRIPT):
            p = tmp / f"turn_{i:02d}.mp3"
            print(f"  合成 {i + 1}/{len(SCRIPT)}: [{speaker}] {text[:18]}…")
            await _tts(text, voice, p)
            pieces.append(p)

        # 0.5s 静音
        silence = tmp / "silence.mp3"
        from audio import resolve_ffmpeg
        ffmpeg, _ = resolve_ffmpeg()
        import subprocess
        subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                        "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
                        "-t", "0.5", str(silence)], check=True)

        # 用 concat demuxer 拼接（路径相对 concat.txt 所在目录，故用文件名）
        concat_list = tmp / "concat.txt"
        lines = []
        for p in pieces:
            lines.append(f"file '{p.name}'")
            lines.append(f"file '{silence.name}'")
        concat_list.write_text("\n".join(lines), encoding="utf-8")
        subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                        "-f", "concat", "-safe", "0", "-i", str(concat_list),
                        "-c", "copy", str(out)], check=True)
        print(f"✅ 样例已生成: {out}")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("samples/meeting-001.mp3")
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        asyncio.run(generate(out))
    except Exception as e:  # 网络/代理问题
        print(f"❌ 合成失败（可能无网络 / 代理不可用）: {e}", file=sys.stderr)
        print("请改用手动放置真实会议音频到 samples/ 目录。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
