"""Locust 压测脚本（M3 TG-5）。

验证吞吐 ≥ 实时 5 倍、并发无丢失/错乱。压测以 mock ASR（快进）为主控费（mission §5 利润 0）。

用法（Linux / 有 Docker 的目标环境）：
    # 1) 启动服务（生产模式，mock ASR）
    # 2) 准备账号与样例音频
    export MMA_BASE_URL=http://localhost:8000
    export MMA_USERNAME=loadtest
    export MMA_PASSWORD=loadtest123
    export MMA_SAMPLE_AUDIO=/path/to/meeting.wav   # 2h 大文件或短样例
    locust -f locustfile.py --host=$MMA_BASE_URL --headless \
        -u 10 -r 2 -t 5m --csv=report/perf --html=report/perf.html

注：本机（Windows + gevent/ssl 冲突）locust 导入有已知环境问题，建议在 Linux / Docker 内运行。
"""
from __future__ import annotations

import os
from pathlib import Path

from locust import HttpUser, between, task

BASE_URL = os.getenv("MMA_BASE_URL", "http://localhost:8000")
USERNAME = os.getenv("MMA_USERNAME", "loadtest")
PASSWORD = os.getenv("MMA_PASSWORD", "loadtest123")
SAMPLE_AUDIO = os.getenv("MMA_SAMPLE_AUDIO", "")


class MeetingUser(HttpUser):
    wait_time = between(1, 3)
    token: str = ""
    sample: bytes | None = None

    def on_start(self):
        """注册/登录拿 token；加载样例音频。"""
        self.sample = self._load_sample()
        r = self.client.post("/api/auth/login",
                             json={"username": USERNAME, "password": PASSWORD})
        if r.status_code != 200:
            self.client.post("/api/auth/register",
                             json={"username": USERNAME, "password": PASSWORD})
            r = self.client.post("/api/auth/login",
                                 json={"username": USERNAME, "password": PASSWORD})
        self.token = r.json().get("token", "")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def _load_sample(self) -> bytes | None:
        if SAMPLE_AUDIO and Path(SAMPLE_AUDIO).exists():
            return Path(SAMPLE_AUDIO).read_bytes()
        # 兜底：合成 1s 静音 WAV（16kHz 单声道）
        import struct
        import tempfile
        import wave as _wave
        p = Path(tempfile.gettempdir()) / "mma_sample.wav"
        if not p.exists():
            with _wave.open(str(p), "w") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(16000)
                w.writeframes(struct.pack("<h", 0) * 16000)
        return p.read_bytes()

    @task(3)
    def health(self):
        self.client.get("/health")

    @task(2)
    def list_tasks(self):
        self.client.get("/api/tasks", headers=self.headers)

    @task(2)
    def search_minutes(self):
        self.client.get("/api/minutes", headers=self.headers)

    @task(1)
    def upload_task(self):
        """上传任务（大文件/长会议边界场景）。"""
        if not self.sample:
            return
        self.client.post(
            "/api/tasks",
            headers=self.headers,
            files={"file": ("meeting.wav", self.sample, "audio/wav")},
        )

    @task(1)
    def cost_and_metrics(self):
        self.client.get("/api/costs", headers=self.headers)
