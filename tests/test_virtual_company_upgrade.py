"""
虚拟公司升级功能 - 综合测试

Part A: 纯单元测试（18个）— 不依赖数据库
Part B: 集成测试（12个）— 使用conftest的client fixture
"""
import pytest
import time
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
from app.database import AsyncSessionLocal
from app.models.email_verification import EmailVerificationToken


# ══════════════════════════════════════
# Part A: 纯单元测试（无数据库依赖）
# ══════════════════════════════════════

class TestSanitizeUtils:
    async def test_sanitize_text_escapes_html(self):
        from app.utils.sanitize import sanitize_text
        assert "&lt;" in sanitize_text("<script>")
        assert sanitize_text("正常文字") == "正常文字"

    async def test_validate_mbti_valid(self):
        from app.utils.sanitize import validate_mbti
        assert validate_mbti("INTJ") == "INTJ"
        assert validate_mbti("enfp") == "ENFP"

    async def test_validate_mbti_invalid(self):
        from app.utils.sanitize import validate_mbti
        with pytest.raises(ValueError):
            validate_mbti("XXXX")
        with pytest.raises(ValueError):
            validate_mbti("IN")

    async def test_clamp_affinity(self):
        from app.utils.sanitize import clamp_affinity
        assert clamp_affinity(50) == 50
        assert clamp_affinity(-10) == 0
        assert clamp_affinity(150) == 100


class TestAffinityEngine:
    async def test_clamp_affinity(self):
        from app.engine.affinity_engine import clamp_affinity
        assert clamp_affinity(0) == 0
        assert clamp_affinity(100) == 100
        assert clamp_affinity(-5) == 0
        assert clamp_affinity(200) == 100

    async def test_affinity_rewards_defined(self):
        from app.engine.affinity_engine import AFFINITY_REWARDS
        assert "chat" in AFFINITY_REWARDS
        assert "task_collaborate" in AFFINITY_REWARDS


class TestCareerPathSchema:
    async def test_career_levels_defined(self):
        from app.schemas.agent_social import CAREER_LEVELS
        assert CAREER_LEVELS[0]["title"] == "实习生"
        assert CAREER_LEVELS[6]["title"] == "CEO"

    async def test_career_paths_both_tracks(self):
        from app.schemas.agent_social import CAREER_PATHS
        assert CAREER_PATHS["management"][6]["title"] == "CEO"
        assert CAREER_PATHS["technical"][6]["title"] == "CTO"
        assert CAREER_PATHS["technical"][4]["title"] == "技术专家"

    async def test_get_career_title_all_levels(self):
        from app.schemas.agent_social import get_career_title
        assert get_career_title(0) == "实习生"
        assert get_career_title(3) == "高级员工"
        assert get_career_title(4, "management") == "经理"
        assert get_career_title(4, "technical") == "技术专家"
        assert get_career_title(6, "management") == "CEO"
        assert get_career_title(6, "technical") == "CTO"


class TestSalaryEngine:
    async def test_salary_no_penalty(self):
        from app.engine.salary_engine import calculate_daily_salary
        from unittest.mock import MagicMock
        agent = MagicMock(); agent.career_level = 2; agent.tasks_completed = 10
        result = calculate_daily_salary(agent, expired_count=0)
        assert result["base_salary"] == 200
        assert result["penalty_applied"] is False

    async def test_salary_with_penalty(self):
        from app.engine.salary_engine import calculate_daily_salary
        from unittest.mock import MagicMock
        agent = MagicMock(); agent.career_level = 2; agent.tasks_completed = 5
        r1 = calculate_daily_salary(agent, expired_count=0)
        r2 = calculate_daily_salary(agent, expired_count=10)
        assert r2["penalty_applied"] is True
        assert r2["total"] < r1["total"]

    async def test_salary_all_levels(self):
        from app.engine.salary_engine import calculate_daily_salary, SALARY_TABLE
        from unittest.mock import MagicMock
        for level in range(7):
            agent = MagicMock(); agent.career_level = level; agent.tasks_completed = 0
            assert calculate_daily_salary(agent)["base_salary"] == SALARY_TABLE[level]


class TestPromptTemplates:
    async def test_v2_prompts_exist(self):
        from app.prompts.agent_prompt import (
            AGENT_DECISION_PROMPT_V2, NPC_CHAT_PROMPT, TASK_GENERATION_PROMPT_V2, MBTI_HINTS,
        )
        assert "{nickname}" in AGENT_DECISION_PROMPT_V2
        assert "{recent_memories}" in AGENT_DECISION_PROMPT_V2
        assert "{speaker_nickname}" in NPC_CHAT_PROMPT
        assert len(MBTI_HINTS) == 8

    async def test_mbti_hints_all_letters(self):
        from app.prompts.agent_prompt import MBTI_HINTS
        for letter in "EISNTFJP":
            assert letter in MBTI_HINTS


class TestTaskTemplates:
    async def test_15_per_department(self):
        from app.engine.task_generator import TASK_TEMPLATES
        for dept in ["engineering", "marketing", "finance", "hr"]:
            assert len(TASK_TEMPLATES[dept]) >= 15

    async def test_template_fields_valid(self):
        from app.engine.task_generator import TASK_TEMPLATES
        for dept, templates in TASK_TEMPLATES.items():
            for t in templates:
                assert all(k in t for k in ("title", "description", "difficulty", "xp_reward", "tag"))
                assert 1 <= t["difficulty"] <= 5
                assert t["xp_reward"] > 0


class TestAchievementDefs:
    async def test_at_least_20_achievements(self):
        from app.engine.achievement_engine import ACHIEVEMENT_DEFS
        assert len(ACHIEVEMENT_DEFS) >= 20
        categories = {a["category"] for a in ACHIEVEMENT_DEFS}
        for cat in ("task", "social", "career", "economy"):
            assert cat in categories

    async def test_achievement_fields_valid(self):
        from app.engine.achievement_engine import ACHIEVEMENT_DEFS
        for a in ACHIEVEMENT_DEFS:
            assert all(k in a for k in ("key", "name", "category", "condition_type", "condition_value"))


# ══════════════════════════════════════
# Part B: 集成测试（使用conftest fixtures）
# ══════════════════════════════════════

_TS = str(int(time.time()))[-6:]


async def _auth(client, suffix=""):
    user = {
        "username": f"vc_{_TS}{suffix}",
        "email": f"vc_{_TS}{suffix}@t.com",
        "password": "testpass123",
        "full_name": "测试",
    }
    async with AsyncSessionLocal() as session:
        session.add(EmailVerificationToken(
            email=user["email"],
            token="123456",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            used=False,
        ))
        await session.commit()

    await client.post("/api/auth/register", json={**user, "verification_code": "123456"})

    # 获取验证码并注入正确答案以绕过验证
    from app.utils.captcha import _store as captcha_store
    test_captcha_id = f"test_captcha_{suffix}"
    captcha_store[test_captcha_id] = ("AAAA", time.time() + 300)

    r = await client.post(
        f"/api/auth/login?captcha_id={test_captcha_id}&captcha_code=AAAA",
        data={"username": user["username"], "password": user["password"]},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    d = r.json()
    if "access_token" not in d:
        raise RuntimeError(f"Login failed ({r.status_code}): {d}")
    return {"Authorization": f"Bearer {d['access_token']}"}


class TestHealthRegression:
    async def test_root(self, client: AsyncClient):
        assert (await client.get("/")).status_code == 200

    async def test_health(self, client: AsyncClient):
        r = await client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] in ("healthy", "degraded")

    async def test_docs(self, client: AsyncClient):
        assert (await client.get("/docs")).status_code == 200

    async def test_redoc(self, client: AsyncClient):
        assert (await client.get("/redoc")).status_code == 200


class TestDashboardAPI:
    async def test_dashboard_no_auth(self, client: AsyncClient):
        r = await client.get("/api/agent/analytics/dashboard")
        assert r.status_code == 200
        d = r.json()
        for field in ("kpi", "dept_trend", "level_distribution", "top_agents", "department_stats", "online_agents", "active_rooms"):
            assert field in d

    async def test_dashboard_kpi_types(self, client: AsyncClient):
        d = (await client.get("/api/agent/analytics/dashboard")).json()["kpi"]
        for k in ("online_count", "total_agents", "today_tasks", "total_xp"):
            assert isinstance(d[k], int) and d[k] >= 0


class TestFloorEncodingContract:
    async def test_ws_floor_detection_uses_encoded_y(self):
        from app.routers.agent_ws import _detect_floor
        # Same canvas position but encoded on 3F should resolve floor 3.
        floor = _detect_floor(50, 1500)
        assert floor == 3

    async def test_analytics_position_decode(self):
        from app.routers.agent_analytics import _decode_floor, _decode_canvas_y
        assert _decode_floor(50) == 1
        assert _decode_floor(750) == 2
        assert _decode_floor(1450) == 3
        assert _decode_canvas_y(1450) == 50

    async def test_world_map_meeting_room_name_canonicalized(self, client: AsyncClient):
        r = await client.get("/api/world/map")
        assert r.status_code == 200
        names = {room["name"] for room in r.json()}
        assert "会议室" in names
        assert "会议室A" not in names


class TestNamedSpotMovementContract:
    async def test_snap_to_nearest_spot_respects_floor(self):
        from app.engine.named_spots import snap_to_nearest_spot
        # 接近 2F 工程工位区域，应吸附到工程部工位
        spot = snap_to_nearest_spot(x=54, encoded_y=873, career_level=1)
        assert spot.startswith("eng_desk_")

    async def test_non_executive_cannot_snap_to_anchor_spot(self):
        from app.engine.named_spots import snap_to_nearest_spot
        # 普通员工点击 CEO 办公桌附近，也不应停在 ceo_desk 锚点
        spot = snap_to_nearest_spot(x=450, encoded_y=1790, career_level=2)
        assert spot != "ceo_desk"

    async def test_non_management_level6_not_forced_to_ceo_anchor(self):
        from app.engine.named_spots import get_anchor_spot
        assert get_anchor_spot(6, "engineering", "technical") is None
        assert get_anchor_spot(6, "management", "management") == "ceo_desk"

    async def test_online_agents_endpoint_includes_npc_residents(self, client: AsyncClient):
        r = await client.get("/api/world/agents/online")
        assert r.status_code == 200
        agents = r.json()
        npc_count = sum(1 for a in agents if str(a.get("avatar_key", "")).startswith("npc_"))
        assert npc_count >= 1

    async def test_world_move_always_returns_named_spot_position(self, client: AsyncClient):
        from app.engine.named_spots import SPOTS

        h = await _auth(client, "_snap")
        r = await client.post("/api/agent/profile", json={
            "nickname": "吸附测试", "mbti": "ISTJ", "department": "engineering",
            "attr_communication": 50, "attr_leadership": 50, "attr_creativity": 50,
            "attr_technical": 50, "attr_teamwork": 50, "attr_diligence": 50,
        }, headers=h)
        assert r.status_code == 200

        moved = await client.post("/api/world/move", json={"x": 333, "y": 1666}, headers=h)
        assert moved.status_code == 200
        data = moved.json()
        valid_positions = {(s["x"], s["encoded_y"]) for s in SPOTS.values()}
        assert (data["pos_x"], data["pos_y"]) in valid_positions

    async def test_after_work_spot_is_distributed(self):
        from app.engine.named_spots import get_after_work_spot
        # 连续多个agent不应都落在同一个下班点
        spots = [
            get_after_work_spot(agent_id=i, department="engineering", career_level=2)
            for i in range(12)
        ]
        assert len(set(spots)) >= 4

    async def test_rebuild_then_diagnostics_has_floor2_population(self, client: AsyncClient):
        rb = await client.post("/api/simulation/rebuild-npcs")
        assert rb.status_code == 200
        dg = await client.get("/api/simulation/diagnostics")
        assert dg.status_code == 200
        data = dg.json()
        assert data["ok"] is True
        assert data["gates"]["floor2_online_gt_0"] is True

    async def test_room_interactions_contract_and_move_inside(self, client: AsyncClient):
        h = await _auth(client, "_inside_move")
        create = await client.post("/api/agent/profile", json={
            "nickname": "室内移动测试", "mbti": "ISTJ", "department": "engineering",
            "attr_communication": 50, "attr_leadership": 50, "attr_creativity": 50,
            "attr_technical": 50, "attr_teamwork": 50, "attr_diligence": 50,
        }, headers=h)
        assert create.status_code == 200

        rooms = (await client.get("/api/world/map")).json()
        room = next(r for r in rooms if r["name"] == "工程部")

        interactions = await client.get(f"/api/world/rooms/{room['id']}/interactions", headers=h)
        assert interactions.status_code == 200
        payload = interactions.json()
        assert payload["room_id"] == room["id"]
        assert len(payload["interaction_spots"]) >= 1
        assert len(payload["object_actions"]) >= 1
        assert "metrics" in payload

        moved = await client.post(
            f"/api/world/rooms/{room['id']}/move-inside",
            json={"x": 9999, "y": 9999},
            headers=h,
        )
        assert moved.status_code == 200
        move_data = moved.json()
        assert move_data["room_id"] == room["id"]
        assert move_data["pos_x"] == room["x"] + move_data["spot"]["x"]
        assert (move_data["pos_y"] % 700) == room["y"] + move_data["spot"]["y"]
        assert move_data["spot"]["floor"] == room["floor"]

    async def test_room_interact_can_drive_task_progress(self, client: AsyncClient):
        h = await _auth(client, "_inside_interact")
        create = await client.post("/api/agent/profile", json={
            "nickname": "室内交互测试", "mbti": "INTJ", "department": "engineering",
            "attr_communication": 50, "attr_leadership": 50, "attr_creativity": 50,
            "attr_technical": 50, "attr_teamwork": 50, "attr_diligence": 50,
        }, headers=h)
        assert create.status_code == 200

        await client.post("/api/task/generate", headers=h)
        rooms = (await client.get("/api/world/map")).json()
        room = next(r for r in rooms if r["name"] == "工程部")
        interactions = (await client.get(f"/api/world/rooms/{room['id']}/interactions", headers=h)).json()
        assert interactions["object_actions"], "工程部应至少有一个可交互动作"
        obj_key = interactions["object_actions"][0]["object_key"]

        moved = await client.post(
            f"/api/world/rooms/{room['id']}/move-inside",
            json={"x": 20, "y": 20},
            headers=h,
        )
        assert moved.status_code == 200

        interacted = await client.post(
            f"/api/world/rooms/{room['id']}/interact",
            json={"object_key": obj_key},
            headers=h,
        )
        assert interacted.status_code == 200
        data = interacted.json()
        assert data["success"] is True
        assert "task_delta" in data
        assert "xp_delta" in data


class TestFullAgentFlow:
    """端到端：注册→角色→任务→分析→成就→会议"""

    async def test_complete_flow(self, client: AsyncClient):
        h = await _auth(client, "_flow")

        # 创建角色
        r = await client.post("/api/agent/profile", json={
            "nickname": "流程测试", "mbti": "INTJ", "department": "engineering",
            "attr_communication": 50, "attr_leadership": 50, "attr_creativity": 50,
            "attr_technical": 50, "attr_teamwork": 50, "attr_diligence": 50,
        }, headers=h)
        assert r.status_code == 200
        assert r.json()["career_level"] == 0

        # 生成+完成任务
        tasks = (await client.post("/api/task/generate", headers=h)).json()
        assert len(tasks) == 3
        comp = await client.post(f"/api/task/{tasks[0]['id']}/complete", headers=h)
        assert comp.status_code == 200
        assert comp.json()["xp_earned"] > 0

        # 排行榜
        assert (await client.get("/api/task/leaderboard", headers=h)).status_code == 200

        # 个人分析
        pa = (await client.get("/api/agent/analytics/personal", headers=h)).json()
        assert "xp_history" in pa and "task_stats" in pa

        # 公司分析
        ca = (await client.get("/api/agent/analytics/company", headers=h)).json()
        assert "department_stats" in ca

        # 行为分析 [5.1]
        ba = (await client.get("/api/agent/analytics/behavior", headers=h)).json()
        assert "insights" in ba

        # 职业预测 [5.2]
        pred = (await client.get("/api/agent/analytics/prediction", headers=h)).json()
        assert "predictions" in pred and "percentile_rank" in pred

        # 成就 [2.1]
        ach = (await client.get("/api/achievement/list", headers=h)).json()
        assert len(ach) >= 10
        assert (await client.get("/api/achievement/my", headers=h)).status_code == 200
        assert (await client.get("/api/achievement/progress", headers=h)).status_code == 200

        # 会议 [4.1]
        assert isinstance((await client.get("/api/meeting/list", headers=h)).json(), list)

        # 职业路径选择（等级不够应失败）[3.2]
        assert (await client.post("/api/agent/career-path?path=technical", headers=h)).status_code == 400


class TestInputValidation:
    async def test_xss_nickname(self, client: AsyncClient):
        h = await _auth(client, "_xss")
        r = await client.post("/api/agent/profile", json={
            "nickname": "<script>alert(1)</script>", "mbti": "INTJ", "department": "engineering",
        }, headers=h)
        assert r.status_code == 422

    async def test_invalid_mbti(self, client: AsyncClient):
        h = await _auth(client, "_mbti")
        r = await client.post("/api/agent/profile", json={
            "nickname": "正常名字", "mbti": "XXXX", "department": "engineering",
        }, headers=h)
        assert r.status_code in (400, 422)

    async def test_attribute_over_300(self, client: AsyncClient):
        h = await _auth(client, "_attr")
        r = await client.post("/api/agent/profile", json={
            "nickname": "超标角色", "mbti": "INTJ", "department": "engineering",
            "attr_communication": 100, "attr_leadership": 100, "attr_creativity": 100,
            "attr_technical": 100, "attr_teamwork": 50, "attr_diligence": 50,
        }, headers=h)
        assert r.status_code == 400

    async def test_duplicate_profile(self, client: AsyncClient):
        h = await _auth(client, "_dup")
        r1 = await client.post("/api/agent/profile", json={
            "nickname": "角色1", "mbti": "ENFP", "department": "hr",
        }, headers=h)
        assert r1.status_code == 200
        r2 = await client.post("/api/agent/profile", json={
            "nickname": "角色2", "mbti": "ENFP", "department": "hr",
        }, headers=h)
        assert r2.status_code == 400

    async def test_meeting_404(self, client: AsyncClient):
        h = await _auth(client, "_m404")
        await client.post("/api/agent/profile", json={
            "nickname": "会议测试", "mbti": "ESTJ", "department": "finance",
        }, headers=h)
        assert (await client.post("/api/meeting/99999/cancel", headers=h)).status_code == 404
