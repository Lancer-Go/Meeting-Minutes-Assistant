"""pytest 配置：确保项目根在 sys.path，提供隔离数据目录 fixture。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture()
def tmp_data_dir(tmp_path, monkeypatch):
    """把 config 数据目录指向临时目录，隔离测试数据；默认关闭鉴权（M3 前向兼容）。"""
    from app import config
    data = tmp_path / "data"
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "UPLOAD_DIR", data / "uploads")
    monkeypatch.setattr(config, "TASK_DIR", data / "tasks")
    monkeypatch.setattr(config, "DB_PATH", data / "mma.db")
    monkeypatch.setattr(config, "AUTH_ENABLED", False)
    monkeypatch.setattr(config, "S3_ENDPOINT", "")
    return data
