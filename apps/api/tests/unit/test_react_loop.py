"""
Unit tests for the ReAct loop models and HITL checkpoint system.

Covers:
- ReActStep model validation and field types
- ReActStepType enum values
- HITLCheckpointReason enum completeness
- HITLCheckpointStatus enum values
- HITLCheckpointState model construction
- HumanDecisionType enum values
- HumanDecision model fields
- AgentFinding status values
"""

import os
from datetime import datetime
from uuid import UUID, uuid4

import pytest

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SIGNING_KEY", "test-signing-key-" + "x" * 32)
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("REDIS_PASSWORD", "test")
os.environ.setdefault("NEXT_PUBLIC_DEMO_PASSWORD", "test")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_MODEL", "test-model")

from core.react_loop import (
    AgentFinding,
    HITLCheckpointReason,
    HITLCheckpointState,
    HumanDecision,
    HumanDecisionType,
    ReActStep,
    ReActStepType,
)

# â”€â”€ ReActStepType â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestReActStepType:
    def test_thought_value(self):
        assert ReActStepType.THOUGHT == "THOUGHT"

    def test_action_value(self):
        assert ReActStepType.ACTION == "ACTION"

    def test_observation_value(self):
        assert ReActStepType.OBSERVATION == "OBSERVATION"

    def test_exactly_three_types(self):
        assert len(list(ReActStepType)) == 3


# â”€â”€ ReActStep model â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestReActStep:
    def _thought(self, iteration: int = 1) -> ReActStep:
        return ReActStep(
            step_type="THOUGHT",
            content="Analyzing ELA outputâ€¦",
            iteration=iteration,
        )

    def _action(self) -> ReActStep:
        return ReActStep(
            step_type="ACTION",
            content="Call ela_full_image",
            tool_name="ela_full_image",
            tool_input={"quality": 95},
            iteration=2,
        )

    def _observation(self) -> ReActStep:
        return ReActStep(
            step_type="OBSERVATION",
            content="ELA returned uniform map",
            tool_output={"anomaly_score": 0.05},
            iteration=3,
        )

    def test_thought_step_type(self):
        s = self._thought()
        assert s.step_type == "THOUGHT"

    def test_thought_content_stored(self):
        s = self._thought()
        assert "ELA" in s.content

    def test_thought_tool_name_none(self):
        s = self._thought()
        assert s.tool_name is None

    def test_action_tool_name_stored(self):
        s = self._action()
        assert s.tool_name == "ela_full_image"

    def test_action_tool_input_stored(self):
        s = self._action()
        assert s.tool_input == {"quality": 95}

    def test_observation_tool_output_stored(self):
        s = self._observation()
        assert s.tool_output == {"anomaly_score": 0.05}

    def test_iteration_stored(self):
        s = self._thought(iteration=7)
        assert s.iteration == 7

    def test_timestamp_utc_auto_set(self):
        s = self._thought()
        assert isinstance(s.timestamp_utc, datetime)
        assert s.timestamp_utc.tzinfo is not None

    @pytest.mark.parametrize("step_type", ["THOUGHT", "ACTION", "OBSERVATION"])
    def test_all_step_types_valid(self, step_type):
        s = ReActStep(step_type=step_type, content="test", iteration=1)
        assert s.step_type == step_type


# â”€â”€ HITLCheckpointReason â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestHITLCheckpointReason:
    EXPECTED_REASONS = [
        "ITERATION_CEILING_50PCT",
        "CONTESTED_FINDING",
        "TOOL_UNAVAILABLE",
        "SEVERITY_THRESHOLD_BREACH",
        "TRIBUNAL_ESCALATION",
    ]

    @pytest.mark.parametrize("reason", EXPECTED_REASONS)
    def test_reason_exists(self, reason):
        assert hasattr(HITLCheckpointReason, reason)

    def test_all_reasons_are_strings(self):
        for r in HITLCheckpointReason:
            assert isinstance(r.value, str)


# â”€â”€ HITLCheckpointState â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestHITLCheckpointState:
    def _make(self, **kwargs) -> HITLCheckpointState:
        defaults = {
            "agent_id": "Agent1",
            "session_id": uuid4(),
            "reason": HITLCheckpointReason.CONTESTED_FINDING,
            "paused_at_iteration": 5,
        }
        defaults.update(kwargs)
        return HITLCheckpointState(**defaults)

    def test_checkpoint_id_is_uuid(self):
        s = self._make()
        assert isinstance(s.checkpoint_id, UUID)

    def test_two_checkpoints_different_ids(self):
        a = self._make()
        b = self._make()
        assert a.checkpoint_id != b.checkpoint_id

    def test_default_status_is_paused(self):
        s = self._make()
        assert s.status == "PAUSED"

    def test_agent_id_stored(self):
        s = self._make(agent_id="Agent3")
        assert s.agent_id == "Agent3"

    def test_reason_stored(self):
        s = self._make(reason=HITLCheckpointReason.TRIBUNAL_ESCALATION)
        assert s.reason == HITLCheckpointReason.TRIBUNAL_ESCALATION

    def test_paused_at_iteration_stored(self):
        s = self._make(paused_at_iteration=12)
        assert s.paused_at_iteration == 12

    def test_serialized_state_default_none(self):
        s = self._make()
        assert s.serialized_state is None

    @pytest.mark.parametrize("status", ["PAUSED", "RESUMED", "OVERRIDDEN", "TERMINATED"])
    def test_all_statuses_valid(self, status):
        s = self._make()
        s.status = status
        assert s.status == status


# â”€â”€ HumanDecisionType â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestHumanDecisionType:
    EXPECTED_TYPES = ["APPROVE", "REDIRECT", "OVERRIDE", "TERMINATE", "ESCALATE"]

    @pytest.mark.parametrize("dtype", EXPECTED_TYPES)
    def test_decision_type_exists(self, dtype):
        assert hasattr(HumanDecisionType, dtype)

    def test_exactly_five_decision_types(self):
        assert len(list(HumanDecisionType)) == 5


# â”€â”€ HumanDecision model â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# HumanDecision fields: decision_type (Literal), investigator_id (str), notes (str),
# override_finding (dict|None), redirect_context (str|None)

class TestHumanDecision:
    def test_approve_decision_fields(self):
        d = HumanDecision(
            decision_type="APPROVE",
            investigator_id="REQ-001",
        )
        assert d.decision_type == "APPROVE"

    def test_redirect_with_notes(self):
        d = HumanDecision(
            decision_type="REDIRECT",
            investigator_id="REQ-002",
            notes="Please re-examine timestamp.",
        )
        assert d.notes == "Please re-examine timestamp."

    def test_override_with_finding(self):
        d = HumanDecision(
            decision_type="OVERRIDE",
            investigator_id="REQ-003",
            override_finding={"finding_id": "abc", "status": "CONFIRMED"},
        )
        assert d.override_finding is not None
        assert d.override_finding["status"] == "CONFIRMED"

    def test_redirect_context_stored(self):
        d = HumanDecision(
            decision_type="REDIRECT",
            investigator_id="REQ-004",
            redirect_context="Focus on timestamps only.",
        )
        assert d.redirect_context == "Focus on timestamps only."

    def test_notes_default_empty(self):
        d = HumanDecision(decision_type="APPROVE", investigator_id="REQ-005")
        assert d.notes == ""


# â”€â”€ AgentFinding status â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestAgentFinding:
    EXPECTED_STATUSES = ["CONFIRMED", "CONTESTED", "INCONCLUSIVE", "INCOMPLETE"]

    def test_finding_can_be_constructed(self):
        f = AgentFinding(
            agent_id="Agent1",
            finding_type="ela_analysis",
            status="CONFIRMED",
            confidence_raw=0.9,
            reasoning_summary="ELA uniform.",
            court_statement="No manipulation.",
        )
        assert f.agent_id == "Agent1"

    @pytest.mark.parametrize("status", EXPECTED_STATUSES)
    def test_all_statuses_accepted(self, status):
        f = AgentFinding(
            agent_id="Agent1",
            finding_type="test",
            status=status,
            confidence_raw=0.5,
            reasoning_summary="test",
            court_statement="test",
        )
        assert f.status == status

    def test_finding_id_auto_generated(self):
        f = AgentFinding(
            agent_id="Agent1",
            finding_type="test",
            status="CONFIRMED",
            confidence_raw=0.5,
            reasoning_summary="test",
            court_statement="test",
        )
        assert f.finding_id is not None


