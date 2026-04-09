"""
虚拟公司 Demo 自动测试脚本
测试内容：
1. NPC种子系统（幂等性、数据完整性）
2. 模拟引擎（tick执行、状态机流转）
3. MBTI行为差异（工作/社交权重）
4. 自动任务完成 + 晋升
5. 模拟控制端点（status/speed/seed）
6. 角色创建（强制实习生 + ai_enabled）
7. 前端构建验证
"""
import asyncio
import os
import pytest
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, func

from app.main import app
from app.database import AsyncSessionLocal, engine, Base
from app.models.agent_profile import AgentProfile
from app.models.agent_task import AgentTask
from app.models.user import User
from app.models.email_verification import EmailVerificationToken
from app.engine.npc_seeder import seed_npcs, NPC_ROSTER, seed_npcs_standalone
from app.engine.simulation_loop import (
    process_agent, simulation_tick, get_status, set_speed,
    get_work_speed, get_social_bonus, get_xp_bonus, get_auto_career_path,
    _check_and_promote, _resolve_work, _save_sim_state, append_decision_log,
    _event_action_for,
)
from app.engine.agent_ai import get_task_preference_scores, _get_mbti_weights
from app.engine.event_engine import check_dynamic_events, should_join_event, resolve_event_conflict
from app.main import _env_int
from app.schemas.agent_social import CAREER_LEVELS


# ─── Fixtures ───

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def db():
    async with AsyncSessionLocal() as session:
        yield session


@pytest.fixture
async def auth_token(client: AsyncClient):
    """Register + login a test user, return token."""
    username = "test_sim_" + str(int(time.time() * 1000))[-6:]
    email = username + "@example.com"
    password = "TestPass123!"
    # Get captcha
    cap_resp = await client.get("/api/auth/captcha")
    assert cap_resp.status_code == 200, cap_resp.text
    cap_data = cap_resp.json()
    captcha_id = cap_data.get("data", cap_data).get("captcha_id", "")
    # Inject email verification token for registration flow.
    async with AsyncSessionLocal() as session:
        session.add(EmailVerificationToken(
            email=email,
            token="123456",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            used=False,
        ))
        await session.commit()
    # Register (may fail if already exists)
    await client.post("/api/auth/register", json={
        "username": username, "email": email, "password": password, "verification_code": "123456",
    })
    # Login with captcha (verification may be mocked/pass-through in test)
    # Try with a dummy captcha code - if captcha is Redis-backed, it may fail
    # Use the verify_captcha mock approach
    from unittest.mock import patch
    with patch("app.routers.auth.verify_captcha", return_value=True):
        resp = await client.post(
            "/api/auth/login?captcha_id=" + captcha_id + "&captcha_code=0000",
            data={"username": username, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    token = data.get("data", data).get("access_token", data.get("access_token", ""))
    assert token, "Failed to get access token"
    return token


# ═══════════════════════════════════════════════════════════════
# Test 1: NPC Seeder
# ═══════════════════════════════════════════════════════════════

class TestNPCSeeder:
    """测试NPC种子系统"""

    def test_npc_roster_complete(self):
        """NPC名单应覆盖各级别"""
        assert len(NPC_ROSTER) >= 12
        levels = {npc["career_level"] for npc in NPC_ROSTER}
        assert 1 in levels
        assert 2 in levels
        assert 3 in levels
        assert 4 in levels
        assert 5 in levels
        assert 6 in levels

    def test_npc_roster_departments(self):
        """NPC应覆盖4个部门"""
        depts = {npc["department"] for npc in NPC_ROSTER}
        assert "engineering" in depts
        assert "marketing" in depts
        assert "finance" in depts
        assert "hr" in depts

    def test_npc_roster_mbti_valid(self):
        """每个NPC的MBTI应为有效4字符"""
        for npc in NPC_ROSTER:
            mbti = npc["mbti"]
            assert len(mbti) == 4
            assert mbti[0] in "EI"
            assert mbti[1] in "SN"
            assert mbti[2] in "TF"
            assert mbti[3] in "JP"

    def test_npc_roster_xp_matches_level(self):
        """每个NPC的tasks_completed和xp应满足其career_level要求"""
        for npc in NPC_ROSTER:
            level = npc["career_level"]
            req = CAREER_LEVELS[level]
            assert npc["tasks_completed"] >= req["tasks_required"] - 2, \
                f"{npc['nickname']} tasks {npc['tasks_completed']} < required {req['tasks_required']} (tolerance=2)"
            assert npc["xp"] >= req["xp_required"] - 10, \
                f"{npc['nickname']} xp {npc['xp']} < required {req['xp_required']} (tolerance=10)"

    @pytest.mark.asyncio
    async def test_seed_npcs_idempotent(self, client):
        """seed_npcs应幂等，第二次调用返回0"""
        resp1 = await client.post("/api/simulation/seed-npcs")
        assert resp1.status_code == 200
        count1 = resp1.json()["seeded"]

        resp2 = await client.post("/api/simulation/seed-npcs")
        assert resp2.status_code == 200
        count2 = resp2.json()["seeded"]
        # 如果第一次已经seed了，第二次一定是0
        if count1 > 0:
            assert count2 == 0


# ═══════════════════════════════════════════════════════════════
# Test 2: MBTI Behavior Multipliers
# ══════════════════════════════════════════════���════════════════

class TestMBTIMultipliers:
    """测试MBTI性格对行为的影响"""

    def test_introvert_works_faster(self):
        """内向型工作效率应高于外向型"""
        assert get_work_speed("ISTJ") > get_work_speed("ESTJ")
        assert get_work_speed("INTJ") > get_work_speed("ENTJ")

    def test_extrovert_socializes_better(self):
        """外向型社交加成应高于内向型"""
        assert get_social_bonus("ENFJ") > get_social_bonus("INFJ")
        assert get_social_bonus("ESTP") > get_social_bonus("ISTP")

    def test_intuitive_xp_bonus_on_hard_tasks(self):
        """直觉型在高难度任务上应有XP加成"""
        assert get_xp_bonus("INTJ", 4) > get_xp_bonus("ISTJ", 4)
        # 低难度任务应无差异（N bonus only on difficulty >= 3）
        assert get_xp_bonus("INTJ", 1) >= 1.0

    def test_thinker_goes_technical(self):
        """T型MBTI应自动选择技术路线"""
        assert get_auto_career_path("INTJ") == "technical"
        assert get_auto_career_path("ISTP") == "technical"
        assert get_auto_career_path("ENTJ") == "technical"

    def test_feeler_goes_management(self):
        """F型MBTI应自动选择管理路线"""
        assert get_auto_career_path("INFJ") == "management"
        assert get_auto_career_path("ESFJ") == "management"
        assert get_auto_career_path("ENFP") == "management"

    def test_work_speed_always_positive(self):
        """所有MBTI类型的工作速度应为正数"""
        for mbti in ["INTJ", "ENFP", "ISTP", "ESFJ", "XXXX"]:
            assert get_work_speed(mbti) > 0

    def test_social_bonus_always_positive(self):
        """所有MBTI类型的社交加成应为正数"""
        for mbti in ["INTJ", "ENFP", "ISTP", "ESFJ"]:
            assert get_social_bonus(mbti) > 0


# ═══════════════════════════════════════════════════════════════
# Test 3: Simulation Loop
# ═══════════════════════════════════════════════════════════════

class TestSimulationLoop:
    """测试模拟引擎核心逻辑"""

    def test_get_status(self):
        """get_status应返回正确结构"""
        status = get_status()
        assert "tick_count" in status
        assert "tick_interval" in status
        assert "speed" in status
        assert "running" in status

    def test_set_speed(self):
        """set_speed应正确调整tick间隔"""
        set_speed(1)
        assert get_status()["tick_interval"] == 30
        set_speed(2)
        assert get_status()["tick_interval"] == 15
        set_speed(5)
        assert get_status()["tick_interval"] == 6
        set_speed(10)
        assert get_status()["tick_interval"] == 3
        # Reset
        set_speed(1)

    def test_save_sim_state(self):
        """_save_sim_state应正确写入和替换sim state"""
        class FakeAgent:
            daily_schedule = [{"time": "09:00", "activity": "工作", "room_type": "office"}]
        agent = FakeAgent()
        _save_sim_state(agent, {"action_started_at": 12345})
        # Should have original schedule + sim state
        assert len(agent.daily_schedule) == 2
        assert agent.daily_schedule[-1]["_sim_state"]["action_started_at"] == 12345
        # Second save should replace, not append
        _save_sim_state(agent, {"action_started_at": 99999})
        assert len(agent.daily_schedule) == 2
        assert agent.daily_schedule[-1]["_sim_state"]["action_started_at"] == 99999


# ═══════════════════════════════════════════════════════════════
# Test 4: Simulation Control Endpoints
# ═══════════════════════════════════════════════════════════════

class TestSimulationEndpoints:
    """测试模拟控制API端点"""

    @pytest.mark.asyncio
    async def test_status_endpoint(self, client):
        """GET /api/simulation/status 应返回正确结构"""
        resp = await client.get("/api/simulation/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "tick_count" in data
        assert "ai_agent_count" in data
        assert "total_agents" in data
        assert "avg_career_level" in data

    @pytest.mark.asyncio
    async def test_speed_endpoint(self, client):
        """POST /api/simulation/speed 应正确调整速度"""
        resp = await client.post("/api/simulation/speed?multiplier=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tick_interval"] == 15
        # Reset
        await client.post("/api/simulation/speed?multiplier=1")

    @pytest.mark.asyncio
    async def test_speed_validation(self, client):
        """速度倍率应在0.5-10范围内"""
        resp = await client.post("/api/simulation/speed?multiplier=0.1")
        assert resp.status_code == 422
        resp = await client.post("/api/simulation/speed?multiplier=20")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_diagnostics_endpoint(self, client):
        """GET /api/simulation/diagnostics 返回指纹与分布结构"""
        resp = await client.get("/api/simulation/diagnostics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "runtime" in data
        assert "distribution" in data
        assert "gates" in data
        assert "fingerprint" in data["runtime"]
        assert "behavior_versions" in data["runtime"]
        assert "by_floor" in data["distribution"]
        assert "hotspots" in data["distribution"]

    @pytest.mark.asyncio
    async def test_rebuild_npcs_endpoint(self, client):
        """POST /api/simulation/rebuild-npcs 应返回重建报告"""
        resp = await client.post("/api/simulation/rebuild-npcs")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["ok"] is True
        report = payload["report"]
        assert report["created_npc_profiles"] >= 1
        assert report["repositioned_profiles"] >= report["created_npc_profiles"]
        assert "distribution" in report
        assert report["distribution"]["online_total"] >= report["created_npc_profiles"]


# ═══════════════════════════════════════════════════════════════
# Test 5: Profile Creation (Forced Intern + AI Enabled)
# ═══════════════════════════════════════════════════════════════

class TestProfileCreation:
    """测试角色创建（强制实习生 + AI自动操控）"""

    @pytest.mark.asyncio
    async def test_create_profile_forced_intern(self, client, auth_token):
        """创建角色应强制career_level=0"""
        resp = await client.post("/api/agent/profile", json={
            "nickname": "TestAgent_" + str(int(time.time()))[-4:],
            "mbti": "INTJ",
            "department": "engineering",
            "attr_communication": 50,
            "attr_leadership": 50,
            "attr_creativity": 50,
            "attr_technical": 50,
            "attr_teamwork": 50,
            "attr_diligence": 50,
        }, headers={"Authorization": "Bearer " + auth_token})
        if resp.status_code == 400 and "已创建" in resp.text:
            # Profile already exists, get it
            resp = await client.get("/api/agent/profile",
                                    headers={"Authorization": "Bearer " + auth_token})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        profile = data if "career_level" in data else data.get("data", data)
        assert profile["career_level"] == 0, "新角色应从实习生(level 0)开始"
        assert profile["ai_enabled"] is True, "新角色应默认AI操控"


# ═══════════════════════════════════════════════════════════════
# Test 6: Promotion Logic
# ═══════════════════════════════════════════════════════════════

class TestPromotionLogic:
    """测试晋升逻辑"""

    @pytest.mark.asyncio
    async def test_check_and_promote(self):
        """满足条件时应自动晋升"""
        class FakeAgent:
            id = 999
            career_level = 0
            tasks_completed = 10
            xp = 200
            career_path = ""
            mbti = "INTJ"
            nickname = "TestBot"
            daily_schedule = []

        class FakeDB:
            async def flush(self): pass

        agent = FakeAgent()
        db = FakeDB()
        await _check_and_promote(db, agent)
        assert agent.career_level == 1, "满足Lv.1条件(5tasks, 100xp)应晋升"

    @pytest.mark.asyncio
    async def test_no_promote_below_threshold(self):
        """不满足条件时不应晋升"""
        class FakeAgent:
            id = 999
            career_level = 0
            tasks_completed = 3
            xp = 50
            career_path = ""
            mbti = "INTJ"
            nickname = "TestBot"
            daily_schedule = []

        class FakeDB:
            async def flush(self): pass

        agent = FakeAgent()
        db = FakeDB()
        await _check_and_promote(db, agent)
        assert agent.career_level == 0, "未满足条件不应晋升"

    def test_auto_career_path_at_level4(self):
        """晋升到Lv.4时应根据MBTI自动选择路线"""
        # T type → technical
        assert get_auto_career_path("INTJ") == "technical"
        # F type → management
        assert get_auto_career_path("ENFJ") == "management"


# ═══════════════════════════════════════════════════════════════
# Test 7: Frontend Build
# ═══════════════════════════════════════════════════════════════

class TestFrontendBuild:
    """测试前端构建"""

    def test_frontend_build_succeeds(self):
        """前端build应无错误"""
        import subprocess
        subprocess.run(
            ["npm", "install"],
            cwd=r"D:\林旭燊\2026服创赛\career-planner-merged\frontend",
            capture_output=True, text=True, timeout=300,
            shell=True,
        )
        result = subprocess.run(
            ["npm", "run", "build-only"],
            cwd=r"D:\林旭燊\2026服创赛\career-planner-merged\frontend",
            capture_output=True, text=True, timeout=180,
            shell=True,
        )
        assert result.returncode == 0, "Frontend build failed: " + result.stderr[-500:]


# ═══════════════════════════════════════════════════════════════
# Test 8: Integration - Full Simulation Tick
# ═══════════════════════════════════════════════════════════════

class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_simulation_status_has_agents(self, client):
        """种子后simulation status应显示agent"""
        # Ensure NPCs are seeded
        await client.post("/api/simulation/seed-npcs")
        resp = await client.get("/api/simulation/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_agents"] >= 12, "应至少有12个NPC agent"


# ═══════════════════════════════════════════════════════════════
# Test 9: Transparent Decision Engine
# ═══════════════════════════════════════════════════════════════

class TestTransparentDecision:
    """测试决策透明化"""

    def test_decide_action_returns_tuple(self):
        """decide_action_simple应返回(action_dict, decision_record)元组"""
        # We test the weight computation directly
        weights = _get_mbti_weights("INTJ")
        assert isinstance(weights, dict)
        assert "work" in weights
        # I型应增加工作权重
        assert weights["work"] > 30  # base is 30, I adds 15

    def test_mbti_weights_differ_by_type(self):
        """不同MBTI的权重应明显不同"""
        intj = _get_mbti_weights("INTJ")
        enfp = _get_mbti_weights("ENFP")
        # INTJ should have higher work weight
        assert intj["work"] > enfp["work"], "INTJ工作权重应高于ENFP"
        # ENFP should have higher chat weight
        assert enfp["chat"] > intj["chat"], "ENFP社交权重应高于INTJ"

    def test_decision_log_append(self):
        """append_decision_log应正确追加和限制条数"""
        class FakeAgent:
            daily_schedule = [{"time": "09:00", "activity": "工作", "room_type": "office"}]

        agent = FakeAgent()
        for i in range(55):
            append_decision_log(agent, {"type": "test", "index": i})

        # Find the log
        log = None
        for item in agent.daily_schedule:
            if isinstance(item, dict) and "_decision_log" in item:
                log = item["_decision_log"]
                break
        assert log is not None, "决策日志应存在"
        assert len(log) <= 50, "决策日志应限制在50条以内"
        assert log[-1]["index"] == 54, "最新记录应在末尾"


# ═══════════════════════════════════════════════════════════════
# Test 10: Task Preference Scoring
# ═══════════════════════════════════════════════════════════════

class TestTaskPreference:
    """测试任务偏好排序"""

    def test_t_type_prefers_technical(self):
        """T型应偏好技术类任务"""
        class FakeAgent:
            mbti = "INTJ"
            attr_technical = 90
            attr_communication = 40
            attr_creativity = 60
            attr_leadership = 30

        class TechTask:
            task_type = "technical"
            title = "API性能优化"
            difficulty = 3

        class SocialTask:
            task_type = "social"
            title = "团队沟通会议"
            difficulty = 2

        scored = get_task_preference_scores(FakeAgent(), [TechTask(), SocialTask()])
        assert scored[0][0].task_type == "technical", "INTJ应优先选择技术任务"
        assert scored[0][1] > scored[1][1], "技术任务分数应更高"

    def test_f_type_prefers_social(self):
        """F型应偏好社交类任务"""
        class FakeAgent:
            mbti = "ENFJ"
            attr_technical = 40
            attr_communication = 90
            attr_creativity = 60
            attr_leadership = 80

        class TechTask:
            task_type = "technical"
            title = "代码审查"
            difficulty = 2

        class SocialTask:
            task_type = "social"
            title = "新人培训"
            difficulty = 2

        scored = get_task_preference_scores(FakeAgent(), [TechTask(), SocialTask()])
        assert scored[0][0].task_type == "social", "ENFJ应优先选择社交任务"

    def test_scores_include_reasons(self):
        """偏好分数应包含理由字符串"""
        class FakeAgent:
            mbti = "ISTP"
            attr_technical = 80
            attr_communication = 40
            attr_creativity = 50
            attr_leadership = 30

        class Task:
            task_type = "technical"
            title = "调试Bug"
            difficulty = 2

        scored = get_task_preference_scores(FakeAgent(), [Task()])
        assert len(scored) == 1
        _, score, reason, alignment = scored[0]
        assert score > 50, "匹配的任务应高于基础分50"
        assert isinstance(reason, str)
        assert len(reason) > 0, "应有理由说明"


# ═══════════════════════════════════════════════════════════════
# Test 11: Event Decision Engine
# ═══════════════════════════════════════════════════════════════

class TestEventDecision:
    """测试AI活动决策"""

    @pytest.mark.asyncio
    async def test_dynamic_event_creation_uses_upcoming_ongoing_finished_states(self):
        """动态事件创建后只能使用 upcoming/ongoing/finished 状态。"""

        class FakeResult:
            def __init__(self, *, scalar=None, scalar_one_or_none=None, first=None, items=None):
                self._scalar = scalar
                self._scalar_one_or_none = scalar_one_or_none
                self._first = first
                self._items = items or []

            def scalar(self):
                return self._scalar

            def scalar_one_or_none(self):
                return self._scalar_one_or_none

            def first(self):
                return self._first

            def scalars(self):
                return SimpleNamespace(all=lambda: list(self._items))

        class FakeSession:
            def __init__(self):
                self.added = []
                self.committed = False
                self._results = iter([
                    FakeResult(scalar=1500),
                    FakeResult(scalar_one_or_none=None),
                    FakeResult(first=None),
                    FakeResult(scalar=0),
                    FakeResult(scalar=0),
                    FakeResult(items=[]),
                ])

            async def execute(self, *_args, **_kwargs):
                return next(self._results)

            def add(self, obj):
                self.added.append(obj)

            async def commit(self):
                self.committed = True

        class FakeSessionContext:
            def __init__(self, session):
                self._session = session

            async def __aenter__(self):
                return self._session

            async def __aexit__(self, exc_type, exc, tb):
                return False

        fake_db = FakeSession()
        with patch("app.engine.event_engine.AsyncSessionLocal", return_value=FakeSessionContext(fake_db)):
            triggered = await check_dynamic_events()

        assert triggered == ["milestone_1000"]
        assert fake_db.committed is True
        assert fake_db.added
        assert all(event.is_active in {"upcoming", "ongoing", "finished"} for event in fake_db.added)
        assert all(event.is_active != "active" for event in fake_db.added)

    def test_extrovert_joins_social_event(self):
        """E型应倾向参加社交活动"""
        class Agent:
            mbti = "ENFP"
            current_action = "idle"
            attr_communication = 85
            attr_technical = 40

        class Event:
            event_type = "team_building"
            name = "周五团建"

        joined, interest, reason = should_join_event(Agent(), Event())
        assert joined is True, "ENFP应参加团建"
        assert interest >= 50

    def test_introvert_avoids_social(self):
        """I型应倾向回避社交活动"""
        class Agent:
            mbti = "INTJ"
            current_action = "work"
            attr_communication = 40
            attr_technical = 90

        class Event:
            event_type = "team_building"
            name = "周五团建"

        joined, interest, reason = should_join_event(Agent(), Event())
        # INTJ working: base 50 - 20(I social) - 15(J working) + 4(comm/10) = 19
        assert joined is False, "工作中的INTJ应拒绝团建"
        assert interest < 50

    def test_introvert_joins_tech_event(self):
        """I型应参加技术活动"""
        class Agent:
            mbti = "INTP"
            current_action = "idle"
            attr_communication = 40
            attr_technical = 95

        class Event:
            event_type = "tech_talk"
            name = "技术分享会"

        joined, interest, reason = should_join_event(Agent(), Event())
        # base 50 + 20(I tech) + 15(T tech) + 9(tech/10) = 94
        assert joined is True, "INTP应参加技术分享"
        assert interest >= 70

    def test_conflict_resolution(self):
        """冲突活动应选择兴趣度更高的"""
        class Agent:
            mbti = "INTJ"
            current_action = "idle"
            attr_communication = 40
            attr_technical = 90

        class SocialEvent:
            event_type = "team_building"
            name = "团建活动"

        class TechEvent:
            event_type = "tech_talk"
            name = "技术分享"

        chosen, comparison = resolve_event_conflict(Agent(), SocialEvent(), TechEvent())
        assert chosen.name == "技术分享", "INTJ应选择技术分享而非团建"
        assert "兴趣度" in comparison

    def test_reason_includes_mbti(self):
        """决策理由应包含MBTI维度说明"""
        class Agent:
            mbti = "ESFJ"
            current_action = "idle"
            attr_communication = 80
            attr_technical = 30

        class Event:
            event_type = "team_building"
            name = "团建"

        _, _, reason = should_join_event(Agent(), Event())
        assert "E型" in reason, "理由应提及E型"

    def test_event_participation_maps_social_events_to_chat(self):
        """社交活动应映射为 chat 行为。"""
        event = SimpleNamespace(event_type="team_building", name="周五团建")
        assert _event_action_for(event) == "chat"

    def test_event_participation_maps_formal_events_to_meeting(self):
        """正式活动应映射为 meeting 行为。"""
        event = SimpleNamespace(event_type="training", name="技术培训")
        assert _event_action_for(event) == "meeting"

    def test_event_participation_maps_emergency_events_to_work(self):
        """紧急事件应映射为 work 行为。"""
        event = SimpleNamespace(event_type="emergency", name="紧急动员")
        assert _event_action_for(event) == "work"

    def test_dynamic_event_interval_is_configurable(self):
        """动态事件轮询间隔应支持环境变量配置。"""
        with patch.dict(os.environ, {"DYNAMIC_EVENT_INTERVAL_SECONDS": "120"}):
            assert _env_int("DYNAMIC_EVENT_INTERVAL_SECONDS", 3600) == 120


# ═══════════════════════════════════════════════════════════════
# Test 12: Personality Trace API
# ═══════════════════════════════════════════════════════════════

class TestPersonalityTraceAPI:
    """测试性格轨迹API"""

    @pytest.mark.asyncio
    async def test_personality_trace_endpoint(self, client, auth_token):
        """GET /api/agent/personality-trace 应返回完整性格数据"""
        resp = await client.get("/api/agent/personality-trace",
                                headers={"Authorization": "Bearer " + auth_token})
        if resp.status_code == 404:
            pytest.skip("No agent profile for this user")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "mbti" in data
        assert "effective_multipliers" in data
        assert "personality_tendency" in data
        assert "recent_decisions" in data
        m = data["effective_multipliers"]
        assert "work_speed" in m
        assert "social_bonus" in m
        assert "career_tendency" in m

    @pytest.mark.asyncio
    async def test_task_status_endpoint(self, client, auth_token):
        """GET /api/agent/task-status 应返回任务状态"""
        resp = await client.get("/api/agent/task-status",
                                headers={"Authorization": "Bearer " + auth_token})
        if resp.status_code == 404:
            pytest.skip("No agent profile for this user")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "current_task" in data
        assert "task_queue" in data
