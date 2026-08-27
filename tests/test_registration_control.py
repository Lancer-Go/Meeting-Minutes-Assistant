"""需求变更 · 账号注册管控（禁自助注册 + 管理员/数据库加用户）测试。

覆盖 validation.md V1~V8：公开注册关闭、管理员创建用户与鉴权隔离、is_admin 迁移无损、
管理员初始化幂等、CLI 加用户、审计留痕。
"""
from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from app import auth, config, db
from app.cli import main as cli_main
from app.main import app


def _enable_auth(monkeypatch):
    monkeypatch.setattr(config, "AUTH_ENABLED", True)


def _seed_user(username, password="secret123", is_admin=False):
    db.create_user(username, auth.hash_password(password), is_admin=is_admin)


def _login(client, username, password="secret123"):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"]


# --------------------------------------------------------------------------- V1 · 公开注册关闭
def test_public_register_gone(tmp_data_dir):
    with TestClient(app) as client:
        r = client.post("/api/auth/register",
                        json={"username": "x", "password": "secret123"})
        assert r.status_code == 404  # 路由已移除


def test_register_page_gone(tmp_data_dir):
    with TestClient(app) as client:
        assert client.get("/register.html").status_code == 404


# --------------------------------------------------------------------------- V2/V3 · 管理员创建用户与鉴权隔离
def test_admin_create_user_requires_auth(tmp_data_dir, monkeypatch):
    _enable_auth(monkeypatch)
    with TestClient(app) as client:
        # 未登录 → 401
        r = client.post("/api/admin/users",
                        json={"username": "alice", "password": "secret123"})
        assert r.status_code == 401
        # 非管理员 → 403
        _seed_user("bob")
        tok = _login(client, "bob")
        r = client.post("/api/admin/users",
                        json={"username": "alice", "password": "secret123"},
                        headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 403


def test_admin_create_user_ok_and_login(tmp_data_dir, monkeypatch):
    _enable_auth(monkeypatch)
    with TestClient(app) as client:
        _seed_user("root", is_admin=True)
        tok = _login(client, "root")
        r = client.post("/api/admin/users",
                        json={"username": "alice", "password": "secret123",
                              "is_admin": False},
                        headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 201, r.text
        body = r.json()["user"]
        assert body["username"] == "alice"
        assert body["is_admin"] is False
        # 新建用户可正常登录
        assert _login(client, "alice")


def test_admin_can_create_admin(tmp_data_dir, monkeypatch):
    _enable_auth(monkeypatch)
    with TestClient(app) as client:
        _seed_user("root", is_admin=True)
        tok = _login(client, "root")
        r = client.post("/api/admin/users",
                        json={"username": "admin2", "password": "secret123",
                              "is_admin": True},
                        headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 201
        assert r.json()["user"]["is_admin"] is True


def test_admin_create_user_duplicate_and_weak(tmp_data_dir, monkeypatch):
    _enable_auth(monkeypatch)
    with TestClient(app) as client:
        _seed_user("root", is_admin=True)
        tok = _login(client, "root")
        h = {"Authorization": f"Bearer {tok}"}
        # 弱密码
        assert client.post("/api/admin/users",
                           json={"username": "a", "password": "123"},
                           headers=h).status_code == 400
        # 重复用户名
        _seed_user("dup")
        assert client.post("/api/admin/users",
                           json={"username": "dup", "password": "secret123"},
                           headers=h).status_code == 400


# --------------------------------------------------------------------------- V8 · 审计留痕
def test_admin_create_user_audit(tmp_data_dir, monkeypatch):
    _enable_auth(monkeypatch)
    with TestClient(app) as client:
        _seed_user("root", is_admin=True)
        tok = _login(client, "root")
        client.post("/api/admin/users",
                    json={"username": "alice", "password": "secret123"},
                    headers={"Authorization": f"Bearer {tok}"})
        logs = db.list_audit_logs(action="admin_create_user")
        assert len(logs) == 1
        assert logs[0]["target"] == "alice"


# --------------------------------------------------------------------------- V4 · is_admin 迁移无损
def test_is_admin_migration_adds_column(tmp_data_dir):
    """旧库 users 表缺 is_admin 列 → init_db 迁移补列，历史用户登录不受影响。"""
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(config.DB_PATH))
    conn.execute("CREATE TABLE users (id VARCHAR PRIMARY KEY, username VARCHAR NOT NULL, "
                 "password_hash VARCHAR NOT NULL, created_at VARCHAR)")
    conn.execute("INSERT INTO users (id, username, password_hash, created_at) "
                 "VALUES ('u1', 'legacy', ?, '2026-01-01T00:00:00')",
                 (auth.hash_password("secret123"),))
    conn.commit()
    conn.close()

    db.init_db(db_path=config.DB_PATH)

    from sqlalchemy import inspect
    cols = {c["name"] for c in inspect(db._engine()).get_columns("users")}
    assert "is_admin" in cols
    u = db.get_user_by_username("legacy", db_path=config.DB_PATH)
    assert u["id"] == "u1"
    assert not u.get("is_admin")  # 历史用户 is_admin 空/False，登录不受影响


# --------------------------------------------------------------------------- V5 · 管理员初始化幂等
def test_ensure_admin_exists_idempotent(tmp_data_dir, monkeypatch):
    monkeypatch.setattr(config, "MMA_ADMIN_USERNAME", "boss")
    monkeypatch.setattr(config, "MMA_ADMIN_PASSWORD", "secret123")
    db.init_db()
    assert auth.ensure_admin_exists() is True
    u = db.get_user_by_username("boss")
    assert u["is_admin"] is True
    # 重复启动不重复建、不覆盖密码
    assert auth.ensure_admin_exists() is False
    assert db.get_user_by_username("boss")["password_hash"] == u["password_hash"]


def test_ensure_admin_exists_not_configured(tmp_data_dir, monkeypatch):
    monkeypatch.setattr(config, "MMA_ADMIN_USERNAME", "")
    monkeypatch.setattr(config, "MMA_ADMIN_PASSWORD", "")
    db.init_db()
    assert auth.ensure_admin_exists() is False


def test_ensure_admin_promotes_existing_non_admin(tmp_data_dir, monkeypatch):
    monkeypatch.setattr(config, "MMA_ADMIN_USERNAME", "boss")
    monkeypatch.setattr(config, "MMA_ADMIN_PASSWORD", "secret123")
    db.init_db()
    db.create_user("boss", auth.hash_password("secret123"), is_admin=False)
    assert auth.ensure_admin_exists() is False  # 不重复建
    assert db.get_user_by_username("boss")["is_admin"] is True  # 但被置 True


# --------------------------------------------------------------------------- V6 · CLI 加用户
def test_cli_create_user_success(tmp_data_dir):
    db.init_db()
    assert cli_main(["create-user", "--username", "cli1", "--password", "secret123"]) == 0
    u = db.get_user_by_username("cli1")
    assert u is not None and u["is_admin"] is False


def test_cli_create_user_admin(tmp_data_dir):
    db.init_db()
    assert cli_main(["create-user", "--username", "cliadmin", "--password", "secret123",
                     "--admin"]) == 0
    assert db.get_user_by_username("cliadmin")["is_admin"] is True


def test_cli_create_user_duplicate_and_weak(tmp_data_dir):
    db.init_db()
    db.create_user("dup2", auth.hash_password("secret123"))
    assert cli_main(["create-user", "--username", "dup2", "--password", "secret123"]) == 1
    assert cli_main(["create-user", "--username", "weak", "--password", "123"]) == 1
