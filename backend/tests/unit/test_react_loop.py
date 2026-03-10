"""
Unit tests for core/react_loop.py
"""

import pytest
from typing import Any
from core.react_loop import (
    ReActStep,
    ReActStepType,
    AgentFinding,
    HITLCheckpointState,
    HITLCheckpointReason,
)


class TestReActStep:
    """Test cases for ReActStep model."""

    def test_create_thought_step(self):
        """Test creating a THOUGHT step."""
        step = ReActStep(
            step_type=ReActStepType.THOUGHT,
            content="Analyzing the image",
            iteration=1,
        )
        
        assert step.step_type == ReActStepType.THOUGHT
        assert step.content == "Analyzing the image"
        assert step.iteration == 1

    def test_create_action_step(self):
        """Test creating an ACTION step."""
        step = ReActStep(
            step_type=ReActStepType.ACTION,
            content="Running ELA analysis",
            tool_name="ela_full_image",
            tool_input={"file_path": "/tmp/test.jpg"},
            iteration=1,
        )
        
        assert step.step_type == ReActStepType.ACTION
        assert step.tool_name == "ela_full_image"
        assert step.tool_input == {"file_path": "/tmp/test.jpg"}

    def test_create_observation_step(self):
        """Test creating an OBSERVATION step."""
        step = ReActStep(
            step_type=ReActStepType.OBSERVATION,
            content="Analysis complete",
            tool_output={"anomaly_score": 0.8},
            iteration=1,
        )
        
        assert step.step_type == ReActStepType.OBSERVATION
        assert step.tool_output == {"anomaly_score": 0.8}


class TestAgentFinding:
    """Test cases for AgentFinding model."""

    def test_create_finding(self):
        """Test creating an agent finding."""
        finding = AgentFinding(
            agent_id="Agent1",
            agent_name="Image Forensics",
            confidence=0.85,
            finding_type="manipulation_detected",
            court_statement="Image shows signs of manipulation",
        )
        
        assert finding.agent_id == "Agent1"
        assert finding.confidence == 0.85

    def test_confidence_validation(self):
        """Test confidence score validation."""
        # Valid confidence
        finding = AgentFinding(
            agent_id="Agent1",
            agent_name="Image Forensics",
            confidence=0.5,
            finding_type="test",
        )
        assert finding.confidence == 0.5

    def test_finding_metadata(self):
        """Test finding metadata."""
        finding = AgentFinding(
            agent_id="Agent1",
            agent_name="Image Forensics",
            confidence=0.85,
            finding_type="test",
            metadata={"tool_name": "ela_full_image"},
        )
        
        assert finding.metadata["tool_name"] == "ela_full_image"


class TestHITLCheckpoint:
    """Test cases for HITL checkpoint."""

    def test_create_checkpoint(self):
        """Test creating a checkpoint."""
        checkpoint = HITLCheckpointState(
            agent_id="Agent1",
            session_id="session-123",
            reason=HITLCheckpointReason.SEVERITY_THRESHOLD_BREACH,
            paused_at_iteration=5,
        )
        
        assert checkpoint.agent_id == "Agent1"
        assert checkpoint.status == "PAUSED"

    def test_checkpoint_reason_types(self):
        """Test all checkpoint reason types."""
        reasons = [
            HITLCheckpointReason.ITERATION_CEILING_50PCT,
            HITLCheckpointReason.CONTESTED_FINDING,
            HITLCheckpointReason.TOOL_UNAVAILABLE,
            HITLCheckpointReason.SEVERITY_THRESHOLD_BREACH,
            HITLCheckpointReason.TRIBUNAL_ESCALATION,
        ]
        
        for reason in reasons:
            checkpoint = HITLCheckpointState(
                agent_id="Agent1",
                session_id="session-123",
                reason=reason,
                paused_at_iteration=1,
            )
            assert checkpoint.reason == reason
