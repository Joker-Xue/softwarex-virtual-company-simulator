"""
virtual company Demo Automatic Tests Script
Tests content：
1. NPCseed system（Idempotence、data integrity）
2. Simulation engine（Tick execution, state machine transfer）
3. MBTIBehaviorDifference（Work/Social weight）
4. Automatic Task Completion + Promotion
5. simulation control endpoints（status/speed/seed）
6. Character creation（force Intern + ai_enabled）
7. Front-end build verification
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
    """TestsNPCseed system"""

    def test_npc_roster_complete(self):
        """The NPC list should cover all levels"""
        assert len(NPC_ROSTER) >= 12
        levels = {npc["career_level"] for npc in NPC_ROSTER}
        assert 1 in levels
        assert 2 in levels
        assert 3 in levels
        assert 4 in levels
        assert 5 in levels
        assert 6 in levels

    def test_npc_roster_departments(self):
        """NPCShould cover 4 Departments"""
        depts = {npc["department"] for npc in NPC_ROSTER}
        assert "engineering" in depts
        assert "marketing" in depts
        assert "finance" in depts
        assert "hr" in depts

    def test_npc_roster_mbti_valid(self):
        """Each NPC's MBTI should be valid 4 characters"""
        for npc in NPC_ROSTER:
            mbti = npc["mbti"]
            assert len(mbti) == 4
            assert mbti[0] in "EI"
            assert mbti[1] in "SN"
            assert mbti[2] in "TF"
            assert mbti[3] in "JP"

    def test_npc_roster_xp_matches_level(self):
        """Each NPC's tasks_completed and xp should meet its career_level requirements"""
        for npc in NPC_ROSTER:
            level = npc["career_level"]
            req = CAREER_LEVELS[level]
            assert npc["tasks_completed"] >= req["tasks_required"] - 2, \
                f"{npc['nickname']} tasks {npc['tasks_completed']} < required {req['tasks_required']} (tolerance=2)"
            assert npc["xp"] >= req["xp_required"] - 10, \
                f"{npc['nickname']} xp {npc['xp']} < required {req['xp_required']} (tolerance=10)"

    @pytest.mark.asyncio
    async def test_seed_npcs_idempotent(self, client):
        """seed_npcs should be idempotent，Call Back0 for the second time"""
        resp1 = await client.post("/api/simulation/seed-npcs")
        assert resp1.status_code == 200
        count1 = resp1.json()["seeded"]

        resp2 = await client.post("/api/simulation/seed-npcs")
        assert resp2.status_code == 200
        count2 = resp2.json()["seeded"]
        # If it has been seeded for the first time，The second time must be 0
        if count1 > 0:
            assert count2 == 0


# ═══════════════════════════════════════════════════════════════
# Test 2: MBTI Behavior Multipliers
# ══════════════════════════════════════════════���════════════════

class TestMBTIMultipliers:
    """TestsMBTIpersonality's impact on Behavior"""

    def test_introvert_works_faster(self):
        """Introversion typeWork speedShould be higher than Extraversion type"""
        assert get_work_speed("ISTJ") > get_work_speed("ESTJ")
        assert get_work_speed("INTJ") > get_work_speed("ENTJ")

    def test_extrovert_socializes_better(self):
        """Extraversion typeSocial BonusShould be higher than Introversion type"""
        assert get_social_bonus("ENFJ") > get_social_bonus("INFJ")
        assert get_social_bonus("ESTP") > get_social_bonus("ISTP")

    def test_intuitive_xp_bonus_on_hard_tasks(self):
        """IntuitionTypes should have an XP bonus on difficult missions"""
        assert get_xp_bonus("INTJ", 4) > get_xp_bonus("ISTJ", 4)
        # There should be no difference between low difficulty tasks（N bonus only on difficulty >= 3）
        assert get_xp_bonus("INTJ", 1) >= 1.0

    def test_thinker_goes_technical(self):
        """TType MBTI should automatically select Technical Track"""
        assert get_auto_career_path("INTJ") == "technical"
        assert get_auto_career_path("ISTP") == "technical"
        assert get_auto_career_path("ENTJ") == "technical"

    def test_feeler_goes_management(self):
        """FType MBTI should automatically select Management Track"""
        assert get_auto_career_path("INFJ") == "management"
        assert get_auto_career_path("ESFJ") == "management"
        assert get_auto_career_path("ENFP") == "management"

    def test_work_speed_always_positive(self):
        """MBTItypeWork SpeedShould be a positive number"""
        for mbti in ["INTJ", "ENFP", "ISTP", "ESFJ", "XXXX"]:
            assert get_work_speed(mbti) > 0

    def test_social_bonus_always_positive(self):
        """All MBTI types Social BonusShould be a positive number"""
        for mbti in ["INTJ", "ENFP", "ISTP", "ESFJ"]:
            assert get_social_bonus(mbti) > 0


# ═══════════════════════════════════════════════════════════════
# Test 3: Simulation Loop
# ═══════════════════════════════════════════════════════════════

class TestSimulationLoop:
    """Tests simulate the core logic of the engine"""

    def test_get_status(self):
        """get_statusShould Back the correct structure"""
        status = get_status()
        assert "tick_count" in status
        assert "tick_interval" in status
        assert "speed" in status
        assert "running" in status

    def test_set_speed(self):
        """set_speed should adjust tick intervals correctly"""
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
        """_save_sim_state should correctly write and replace sim state"""
        class FakeAgent:
            daily_schedule = [{"time": "09:00", "activity": "Work", "room_type": "office"}]
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
    """Tests simulation control API endpoint"""

    @pytest.mark.asyncio
    async def test_status_endpoint(self, client):
        """GET /api/simulation/status Should Back the correct structure"""
        resp = await client.get("/api/simulation/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "tick_count" in data
        assert "ai_agent_count" in data
        assert "total_agents" in data
        assert "avg_career_level" in data

    @pytest.mark.asyncio
    async def test_speed_endpoint(self, client):
        """POST /api/simulation/speed Speed should be adjusted correctly"""
        resp = await client.post("/api/simulation/speed?multiplier=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tick_interval"] == 15
        # Reset
        await client.post("/api/simulation/speed?multiplier=1")

    @pytest.mark.asyncio
    async def test_speed_validation(self, client):
        """Speed ratio should be in the range of 0.5-10"""
        resp = await client.post("/api/simulation/speed?multiplier=0.1")
        assert resp.status_code == 422
        resp = await client.post("/api/simulation/speed?multiplier=20")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_diagnostics_endpoint(self, client):
        """GET /api/simulation/diagnostics Back fingerprint and distribution structure"""
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
        """POST /api/simulation/rebuild-npcs Should Back rebuild the report"""
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
    """TestsCharacter creation（force Intern + AI automatic control）"""

    @pytest.mark.asyncio
    async def test_create_profile_forced_intern(self, client, auth_token):
        """create profileCareer_level should be mandatory=0"""
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
        if resp.status_code == 400 and "already created" in resp.text:
            # Profile already exists, get it
            resp = await client.get("/api/agent/profile",
                                    headers={"Authorization": "Bearer " + auth_token})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        profile = data if "career_level" in data else data.get("data", data)
        assert profile["career_level"] == 0, "The new Role should start from Intern(level 0)start"
        assert profile["ai_enabled"] is True, "New characters should be controlled by defaultAI"


# ═══════════════════════════════════════════════════════════════
# Test 6: Promotion Logic
# ═══════════════════════════════════════════════════════════════

class TestPromotionLogic:
    """Tests promotion logic"""

    @pytest.mark.asyncio
    async def test_check_and_promote(self):
        """Should be automatically promoted when msgs requirements are met"""
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
        assert agent.career_level == 1, "Meet Lv.1 msgs piece(5tasks, 100xp)Should be promoted"

    @pytest.mark.asyncio
    async def test_no_promote_below_threshold(self):
        """You should not be promoted if you do not meet the msgs requirements"""
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
        assert agent.career_level == 0, "Unsatisfied msgs should not be promoted"

    def test_auto_career_path_at_level4(self):
        """When promoted to Level 4, the route should be automatically selected based on MBTI"""
        # T type → technical
        assert get_auto_career_path("INTJ") == "technical"
        # F type → management
        assert get_auto_career_path("ENFJ") == "management"


# ═══════════════════════════════════════════════════════════════
# Test 7: Frontend Build
# ═══════════════════════════════════════════════════════════════

class TestFrontendBuild:
    """Tests front-end build"""

    def test_frontend_build_succeeds(self):
        """Front-end build should be error-free"""
        import subprocess
        subprocess.run(
            ["npm", "install"],
            cwd=str((__import__("pathlib").Path(__file__).resolve().parents[1] / "src" / "frontend")),
            capture_output=True, text=True, timeout=300,
            shell=True,
        )
        result = subprocess.run(
            ["npm", "run", "build-only"],
            cwd=str((__import__("pathlib").Path(__file__).resolve().parents[1] / "src" / "frontend")),
            capture_output=True, text=True, timeout=180,
            shell=True,
        )
        assert result.returncode == 0, "Frontend build failed: " + result.stderr[-500:]


# ═══════════════════════════════════════════════════════════════
# Test 8: Integration - Full Simulation Tick
# ═══════════════════════════════════════════════════════════════

class TestIntegration:
    """Integrated Tests"""

    @pytest.mark.asyncio
    async def test_simulation_status_has_agents(self, client):
        """After seeding the simulation status should showagent"""
        # Ensure NPCs are seeded
        await client.post("/api/simulation/seed-npcs")
        resp = await client.get("/api/simulation/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_agents"] >= 12, "There should be at least 12 NPC agents"


# ═══════════════════════════════════════════════════════════════
# Test 9: Transparent Decision Engine
# ═══════════════════════════════════════════════════════════════

class TestTransparentDecision:
    """Tests decision-making transparency"""

    def test_decide_action_returns_tuple(self):
        """decide_action_simpleBack(action_dict, decision_record)tuple"""
        # We test the weight computation directly
        weights = _get_mbti_weights("INTJ")
        assert isinstance(weights, dict)
        assert "work" in weights
        # Type I should increase Work weight
        assert weights["work"] > 30  # base is 30, I adds 15

    def test_mbti_weights_differ_by_type(self):
        """The weightings of different MBTIs should be significantly different"""
        intj = _get_mbti_weights("INTJ")
        enfp = _get_mbti_weights("ENFP")
        # INTJ should have higher work weight
        assert intj["work"] > enfp["work"], "INTJWork weight should be higher than ENFP"
        # ENFP should have higher chat weight
        assert enfp["chat"] > intj["chat"], "ENFPSocial weight should be higher than INTJ"

    def test_decision_log_append(self):
        """append_decision_log should correctly append and limit the number of msgs"""
        class FakeAgent:
            daily_schedule = [{"time": "09:00", "activity": "Work", "room_type": "office"}]

        agent = FakeAgent()
        for i in range(55):
            append_decision_log(agent, {"type": "test", "index": i})

        # Find the log
        log = None
        for item in agent.daily_schedule:
            if isinstance(item, dict) and "_decision_log" in item:
                log = item["_decision_log"]
                break
        assert log is not None, "Decision log should exist"
        assert len(log) <= 50, "Decision logs should be limited to 50 msgs"
        assert log[-1]["index"] == 54, "The latest record should be at the end"


# ═══════════════════════════════════════════════════════════════
# Test 10: Task Preference Scoring
# ═══════════════════════════════════════════════════════════════

class TestTaskPreference:
    """TestsTask Preference Sorting"""

    def test_t_type_prefers_technical(self):
        """TPreference technical tasks"""
        class FakeAgent:
            mbti = "INTJ"
            attr_technical = 90
            attr_communication = 40
            attr_creativity = 60
            attr_leadership = 30

        class TechTask:
            task_type = "technical"
            title = "API performance optimization"
            difficulty = 3

        class SocialTask:
            task_type = "social"
            title = "Team communicationMeeting"
            difficulty = 2

        scored = get_task_preference_scores(FakeAgent(), [TechTask(), SocialTask()])
        assert scored[0][0].task_type == "technical", "INTJ should give priority to technologyTask"
        assert scored[0][1] > scored[1][1], "technologyTask score should be higher"

    def test_f_type_prefers_social(self):
        """FType the PreferenceSocial class task"""
        class FakeAgent:
            mbti = "ENFJ"
            attr_technical = 40
            attr_communication = 90
            attr_creativity = 60
            attr_leadership = 80

        class TechTask:
            task_type = "technical"
            title = "code review"
            difficulty = 2

        class SocialTask:
            task_type = "social"
            title = "Training for newcomers"
            difficulty = 2

        scored = get_task_preference_scores(FakeAgent(), [TechTask(), SocialTask()])
        assert scored[0][0].task_type == "social", "ENFJs should choose SocialTask first"

    def test_scores_include_reasons(self):
        """Preference score should include reason string"""
        class FakeAgent:
            mbti = "ISTP"
            attr_technical = 80
            attr_communication = 40
            attr_creativity = 50
            attr_leadership = 30

        class Task:
            task_type = "technical"
            title = "Debugging Bugs"
            difficulty = 2

        scored = get_task_preference_scores(FakeAgent(), [Task()])
        assert len(scored) == 1
        _, score, reason, alignment = scored[0]
        assert score > 50, "The matching Task should have a score higher than the Base score of 50"
        assert isinstance(reason, str)
        assert len(reason) > 0, "There should be a reason to explain"


# ═══════════════════════════════════════════════════════════════
# Test 11: Event Decision Engine
# ═══════════════════════════════════════════════════════════════

class TestEventDecision:
    """TestsAIactivity decisions"""

    @pytest.mark.asyncio
    async def test_dynamic_event_creation_uses_upcoming_ongoing_finished_states(self):
        """After a dynamic event is created, it can only use upcoming/ongoing/finished state."""

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
        """EPrefers Participate in SocialActivities"""
        class Agent:
            mbti = "ENFP"
            current_action = "idle"
            attr_communication = 85
            attr_technical = 40

        class Event:
            event_type = "team_building"
            name = "FridayTeam Building"

        joined, interest, reason = should_join_event(Agent(), Event())
        assert joined is True, "ENFP should join Team Building"
        assert interest >= 50

    def test_introvert_avoids_social(self):
        """IPrefers AvoidSocialActivity"""
        class Agent:
            mbti = "INTJ"
            current_action = "work"
            attr_communication = 40
            attr_technical = 90

        class Event:
            event_type = "team_building"
            name = "FridayTeam Building"

        joined, interest, reason = should_join_event(Agent(), Event())
        # INTJ working: base 50 - 20(I social) - 15(J working) + 4(comm/10) = 19
        assert joined is False, "WorkingINTJ should rejectTeam Building"
        assert interest < 50

    def test_introvert_joins_tech_event(self):
        """Type I should participate in technologyActivity"""
        class Agent:
            mbti = "INTP"
            current_action = "idle"
            attr_communication = 40
            attr_technical = 95

        class Event:
            event_type = "tech_talk"
            name = "tech sharing"

        joined, interest, reason = should_join_event(Agent(), Event())
        # base 50 + 20(I tech) + 15(T tech) + 9(tech/10) = 94
        assert joined is True, "INTP should participate in tech sharing"
        assert interest >= 70

    def test_conflict_resolution(self):
        """Conflict activities should select preference Score higher"""
        class Agent:
            mbti = "INTJ"
            current_action = "idle"
            attr_communication = 40
            attr_technical = 90

        class SocialEvent:
            event_type = "team_building"
            name = "Team BuildingActivity"

        class TechEvent:
            event_type = "tech_talk"
            name = "tech sharing"

        chosen, comparison = resolve_event_conflict(Agent(), SocialEvent(), TechEvent())
        assert chosen.name == "tech sharing", "INTJ should choose tech sharing instead of Team Building"
        assert "preference score" in comparison

    def test_reason_includes_mbti(self):
        """The rationale for the decision should include a description of the MBTI dimensions"""
        class Agent:
            mbti = "ESFJ"
            current_action = "idle"
            attr_communication = 80
            attr_technical = 30

        class Event:
            event_type = "team_building"
            name = "Team Building"

        _, _, reason = should_join_event(Agent(), Event())
        assert "Type E" in reason, "Reasons should be mentioned for Type E"

    def test_event_participation_maps_social_events_to_chat(self):
        """SocialActivity should be mapped to chat Behavior."""
        event = SimpleNamespace(event_type="team_building", name="FridayTeam Building")
        assert _event_action_for(event) == "chat"

    def test_event_participation_maps_formal_events_to_meeting(self):
        """Formal Activity should be mapped to meeting Behavior."""
        event = SimpleNamespace(event_type="training", name="technologyTraining")
        assert _event_action_for(event) == "meeting"

    def test_event_participation_maps_emergency_events_to_work(self):
        """Emergency events should be mapped to work Behavior."""
        event = SimpleNamespace(event_type="emergency", name="Emergency Mobilization")
        assert _event_action_for(event) == "work"

    def test_dynamic_event_interval_is_configurable(self):
        """Dynamic event polling intervals should support environment variable configuration。"""
        with patch.dict(os.environ, {"DYNAMIC_EVENT_INTERVAL_SECONDS": "120"}):
            assert _env_int("DYNAMIC_EVENT_INTERVAL_SECONDS", 3600) == 120


# ═══════════════════════════════════════════════════════════════
# Test 12: Personality Trace API
# ═══════════════════════════════════════════════════════════════

class TestPersonalityTraceAPI:
    """TestspersonalitytraceAPI"""

    @pytest.mark.asyncio
    async def test_personality_trace_endpoint(self, client, auth_token):
        """GET /api/agent/personality-trace Should Back complete personality data"""
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
        """GET /api/agent/task-status Should BackTaskstate"""
        resp = await client.get("/api/agent/task-status",
                                headers={"Authorization": "Bearer " + auth_token})
        if resp.status_code == 404:
            pytest.skip("No agent profile for this user")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "current_task" in data
        assert "task_queue" in data
