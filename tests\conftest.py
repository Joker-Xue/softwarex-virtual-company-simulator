"""
pytest 配置文件 - 测试夹具和公共工具

使用 httpx.AsyncClient 进行异步API集成测试。
测试数据库使用主数据库，每次测试后清理数据。

兼容 pytest-asyncio >=1.0 (session-scoped loop via pytest.ini)
"""
import os
from typing import AsyncGenerator, Dict
from datetime import datetime, timedelta, timezone

import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import text

# 设置测试环境变量（在导入app之前）
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/career_planner")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_BASE_URL", "https://www.aiping.cn/api/v1")
os.environ.setdefault("LLM_MODEL", "deepseek-chat")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
os.environ.setdefault("ENCRYPTION_KEY_V1", "jvurkchh5gXqh0MLRewhx8eBHrOFJexqrlWv9HKF4/c=")
os.environ.setdefault("TIANAPI_KEY", "test-tianapi-key")
os.environ["TESTING"] = "1"

from app.main import app
from app.database import Base

# 独立的测试引擎（NullPool 避免连接池跨事件循环问题）
_TEST_DB_URL = os.environ["DATABASE_URL"]
_test_engine = create_async_engine(_TEST_DB_URL, poolclass=NullPool)
_TestSessionLocal = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)

# 测试用户凭据
TEST_USER = {
    "username": "testuser_pytest",
    "email": "testuser_pytest@test.com",
    "password": "testpass123",
    "full_name": "测试用户",
}

TEST_USER_2 = {
    "username": "testuser2_pytest",
    "email": "testuser2_pytest@test.com",
    "password": "testpass456",
    "full_name": "测试用户2",
}


@pytest_asyncio.fixture(scope="session")
async def setup_db():
    """会话级别：确保数据库表存在"""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await _test_engine.dispose()


@pytest_asyncio.fixture
async def db_session(setup_db) -> AsyncGenerator[AsyncSession, None]:
    """每个测试获取一个独立的数据库会话"""
    async with _TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(setup_db) -> AsyncGenerator[AsyncClient, None]:
    """异步HTTP客户端"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _cleanup_user(db: AsyncSession, username: str):
    """清理单个用户及关联数据"""
    tables = [
        "chat_history", "career_reports", "match_results",
        "student_portraits", "resumes",
    ]
    for table in tables:
        try:
            await db.execute(
                text(f"DELETE FROM {table} WHERE user_id IN (SELECT id FROM users WHERE username = :u)"),
                {"u": username},
            )
        except Exception:
            pass
    # agent 相关
    agent_tables = [
        "user_achievements", "agent_memories", "agent_action_logs",
        "agent_messages", "agent_tasks", "meeting_bookings", "agent_salary_logs",
    ]
    for table in agent_tables:
        try:
            await db.execute(
                text(f"DELETE FROM {table} WHERE agent_id IN "
                     f"(SELECT id FROM agent_profiles WHERE user_id IN "
                     f"(SELECT id FROM users WHERE username = :u))"),
                {"u": username},
            )
        except Exception:
            pass
    try:
        await db.execute(
            text("DELETE FROM agent_friendships WHERE from_id IN "
                 "(SELECT id FROM agent_profiles WHERE user_id IN "
                 "(SELECT id FROM users WHERE username = :u)) "
                 "OR to_id IN "
                 "(SELECT id FROM agent_profiles WHERE user_id IN "
                 "(SELECT id FROM users WHERE username = :u))"),
            {"u": username},
        )
    except Exception:
        pass
    try:
        await db.execute(
            text("DELETE FROM agent_profiles WHERE user_id IN (SELECT id FROM users WHERE username = :u)"),
            {"u": username},
        )
    except Exception:
        pass
    try:
        await db.execute(text("DELETE FROM users WHERE username = :u"), {"u": username})
    except Exception:
        pass


@pytest_asyncio.fixture
async def clean_test_users(db_session: AsyncSession):
    """清理测试用户数据（测试前后）"""
    for user in [TEST_USER, TEST_USER_2]:
        await _cleanup_user(db_session, user["username"])
    # 清理测试邮箱验证码
    for user in [TEST_USER, TEST_USER_2]:
        try:
            await db_session.execute(
                text("DELETE FROM email_verification_tokens WHERE email = :e"),
                {"e": user["email"]},
            )
        except Exception:
            pass
    await db_session.commit()
    yield
    for user in [TEST_USER, TEST_USER_2]:
        await _cleanup_user(db_session, user["username"])
    for user in [TEST_USER, TEST_USER_2]:
        try:
            await db_session.execute(
                text("DELETE FROM email_verification_tokens WHERE email = :e"),
                {"e": user["email"]},
            )
        except Exception:
            pass
    await db_session.commit()


async def inject_verification_code(client: AsyncClient, email: str, code: str = "123456") -> str:
    """向数据库注入邮箱验证码，返回验证码值（绕过邮件发送）"""
    from app.database import get_db
    from app.models.email_verification import EmailVerificationToken

    # 直接通过 engine 写入
    async with _TestSessionLocal() as session:
        token = EmailVerificationToken(
            email=email,
            token=code,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            used=False,
        )
        session.add(token)
        await session.commit()
    return code


async def register_and_login(client: AsyncClient, user: dict = None) -> Dict[str, str]:
    """注册并登录，返回 {"token": "...", "user_id": ..., "headers": {...}}"""
    user = user or TEST_USER

    # 注入邮箱验证码
    vcode = await inject_verification_code(client, user["email"])

    # 注册（可能已存在，忽略错误）
    reg_data = {**user, "verification_code": vcode}
    await client.post("/api/auth/register", json=reg_data)

    # 注入测试验证码
    from app.utils.captcha import _store as captcha_store
    import time as _time
    _cid = f"test_{user['username']}_{_time.time()}"
    captcha_store[_cid] = ("AAAA", _time.time() + 300)

    # 登录
    login_resp = await client.post(
        f"/api/auth/login?captcha_id={_cid}&captcha_code=AAAA",
        data={"username": user["username"], "password": user["password"]},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    data = login_resp.json()
    return {
        "token": data["access_token"],
        "user_id": data["user"]["id"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
    }


def auth_headers(token: str) -> dict:
    """生成认证请求头"""
    return {"Authorization": f"Bearer {token}"}


def inject_test_captcha(suffix: str = "") -> tuple[str, str]:
    """注入测试验证码，返回 (captcha_id, captcha_code)"""
    import time as _time
    from app.utils.captcha import _store as captcha_store
    cid = f"test_cap_{suffix}_{_time.time()}"
    code = "AAAA"
    captcha_store[cid] = (code, _time.time() + 300)
    return cid, code
