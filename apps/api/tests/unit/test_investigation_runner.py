"""
Tests for investigation_runner.py — critical path between pipeline and outside world.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta, UTC
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from api.schemas import BriefUpdate
from orchestration.investigation_runner import (
    run_investigation_task,
)


@pytest.fixture
def mock_pipeline():
    mock = MagicMock()
    mock.report_id = uuid4()
    return mock


@pytest.fixture
def mock_report():
    from agents.arbiter import ForensicReport
    
    return ForensicReport(
        report_id=uuid4(),
        case_id="case-123",
        session_id=uuid4(),
        investigator_id="user-123",
        overall_verdict="AUTHENTIC",
        overall_confidence=0.95,
        executive_summary="Test report summary",
        uncertainty_statement="No significant uncertainties detected",
        per_agent_findings={},
        per_agent_metrics={},
        cross_agent_comparisons=[],
        tribunal_resolved=[],
        contested_findings=[],
        created_at=datetime.now(UTC),
    )


class TestRunInvestigationTask:
    @pytest.mark.asyncio
    async def test_successful_run_broadcasts_complete(self, mock_report, tmp_path):
        """Test that successful run broadcasts PIPELINE_COMPLETE."""
        session_id = str(uuid4())
        evidence_file = tmp_path / "test.jpg"
        evidence_file.write_bytes(b"fake image")
        
        mock_pipeline = MagicMock()
        mock_pipeline.run_investigation = AsyncMock(return_value=mock_report)
        mock_pipeline._final_report = mock_report
        
        with patch("orchestration.investigation_runner.get_session_persistence") as mock_persist, \
             patch("orchestration.investigation_runner.broadcast_update") as mock_broadcast, \
             patch("orchestration.investigation_runner.set_final_report") as mock_set, \
             patch("orchestration.investigation_runner.set_active_pipeline_metadata") as mock_set_meta, \
             patch("orchestration.investigation_runner.clear_session_websockets") as mock_clear_ws, \
             patch("orchestration.investigation_runner.remove_active_pipeline") as mock_remove, \
             patch("orchestration.investigation_runner.increment_investigations_completed") as mock_inc_comp, \
             patch("orchestration.investigation_runner._active_tasks", {}):
            
            mock_persist.return_value = MagicMock(
                save_report=AsyncMock(),
                update_session_status=AsyncMock()
            )
            
            await run_investigation_task(
                session_id=session_id,
                pipeline=mock_pipeline,
                evidence_file_path=str(evidence_file),
                case_id="case-123",
                investigator_id="user-123",
            )
            
            # Verify broadcast was called with PIPELINE_COMPLETE
            call_args = mock_broadcast.call_args_list
            assert len(call_args) > 0
            event_type = call_args[0][0][1].type
            assert event_type == "PIPELINE_COMPLETE"

    @pytest.mark.asyncio
    async def test_successful_run_persists_report(self, mock_report, tmp_path):
        """Test that successful run persists report to storage."""
        session_id = str(uuid4())
        evidence_file = tmp_path / "test.jpg"
        evidence_file.write_bytes(b"fake image")
        
        mock_pipeline = MagicMock()
        mock_pipeline.run_investigation = AsyncMock(return_value=mock_report)
        mock_pipeline._final_report = mock_report
        
        with patch("orchestration.investigation_runner.get_session_persistence") as mock_persist, \
             patch("orchestration.investigation_runner.broadcast_update") as mock_broadcast, \
             patch("orchestration.investigation_runner.set_final_report") as mock_set, \
             patch("orchestration.investigation_runner.set_active_pipeline_metadata") as mock_set_meta, \
             patch("orchestration.investigation_runner.clear_session_websockets") as mock_clear_ws, \
             patch("orchestration.investigation_runner.remove_active_pipeline") as mock_remove, \
             patch("orchestration.investigation_runner.increment_investigations_completed") as mock_inc_comp, \
             patch("orchestration.investigation_runner._active_tasks", {}):
            
            mock_persistence = MagicMock(
                save_report=AsyncMock(),
                update_session_status=AsyncMock()
            )
            mock_persist.return_value = mock_persistence
            
            await run_investigation_task(
                session_id=session_id,
                pipeline=mock_pipeline,
                evidence_file_path=str(evidence_file),
                case_id="case-123",
                investigator_id="user-123",
            )
            
            # Verify persistence save was called
            assert mock_persistence.save_report.called

    @pytest.mark.asyncio
    async def test_successful_run_increments_completed_metric(self, mock_report, tmp_path):
        """Test that successful run increments the completed metric."""
        session_id = str(uuid4())
        evidence_file = tmp_path / "test.jpg"
        evidence_file.write_bytes(b"fake image")
        
        mock_pipeline = MagicMock()
        mock_pipeline.run_investigation = AsyncMock(return_value=mock_report)
        mock_pipeline._final_report = mock_report
        
        with patch("orchestration.investigation_runner.get_session_persistence") as mock_persist, \
             patch("orchestration.investigation_runner.broadcast_update") as mock_broadcast, \
             patch("orchestration.investigation_runner.set_final_report") as mock_set, \
             patch("orchestration.investigation_runner.set_active_pipeline_metadata") as mock_set_meta, \
             patch("orchestration.investigation_runner.clear_session_websockets") as mock_clear_ws, \
             patch("orchestration.investigation_runner.remove_active_pipeline") as mock_remove, \
             patch("orchestration.investigation_runner.increment_investigations_completed") as mock_inc_comp, \
             patch("orchestration.investigation_runner._active_tasks", {}):
            
            mock_persist.return_value = MagicMock(
                save_report=AsyncMock(),
                update_session_status=AsyncMock()
            )
            
            await run_investigation_task(
                session_id=session_id,
                pipeline=mock_pipeline,
                evidence_file_path=str(evidence_file),
                case_id="case-123",
                investigator_id="user-123",
            )
            
            # Verify metric was incremented
            assert mock_inc_comp.call_count == 1

    @pytest.mark.asyncio
    async def test_successful_run_deletes_temp_file(self, mock_report, tmp_path):
        """Test that successful run deletes the temp file."""
        session_id = str(uuid4())
        evidence_file = tmp_path / "test.jpg"
        evidence_file.write_bytes(b"fake image")
        
        mock_pipeline = MagicMock()
        mock_pipeline.run_investigation = AsyncMock(return_value=mock_report)
        mock_pipeline._final_report = mock_report
        
        with patch("orchestration.investigation_runner.get_session_persistence") as mock_persist, \
             patch("orchestration.investigation_runner.broadcast_update") as mock_broadcast, \
             patch("orchestration.investigation_runner.set_final_report") as mock_set, \
             patch("orchestration.investigation_runner.set_active_pipeline_metadata") as mock_set_meta, \
             patch("orchestration.investigation_runner.clear_session_websockets") as mock_clear_ws, \
             patch("orchestration.investigation_runner.remove_active_pipeline") as mock_remove, \
             patch("orchestration.investigation_runner.increment_investigations_completed") as mock_inc_comp, \
             patch("orchestration.investigation_runner._active_tasks", {}):
            
            mock_persist.return_value = MagicMock(
                save_report=AsyncMock(),
                update_session_status=AsyncMock()
            )
            
            await run_investigation_task(
                session_id=session_id,
                pipeline=mock_pipeline,
                evidence_file_path=str(evidence_file),
                case_id="case-123",
                investigator_id="user-123",
            )
            
            # File should be deleted on success
            assert not evidence_file.exists()

    @pytest.mark.asyncio
    async def test_pipeline_failure_broadcasts_error(self, tmp_path):
        """Test that pipeline failure broadcasts ERROR."""
        session_id = str(uuid4())
        evidence_file = tmp_path / "test.jpg"
        evidence_file.write_bytes(b"fake image")
        
        mock_pipeline = MagicMock()
        mock_pipeline.run_investigation = AsyncMock(
            side_effect=RuntimeError("Pipeline exploded")
        )
        
        with patch("orchestration.investigation_runner.get_session_persistence") as mock_persist, \
             patch("orchestration.investigation_runner.broadcast_update") as mock_broadcast, \
             patch("orchestration.investigation_runner.set_final_report") as mock_set, \
             patch("orchestration.investigation_runner.set_active_pipeline_metadata") as mock_set_meta, \
             patch("orchestration.investigation_runner.clear_session_websockets") as mock_clear_ws, \
             patch("orchestration.investigation_runner.remove_active_pipeline") as mock_remove, \
             patch("orchestration.investigation_runner.increment_investigations_failed") as mock_inc_fail, \
             patch("orchestration.investigation_runner._active_tasks", {}):
            
            mock_persist.return_value = MagicMock(
                save_report=AsyncMock(),
                update_session_status=AsyncMock()
            )
            
            await run_investigation_task(
                session_id=session_id,
                pipeline=mock_pipeline,
                evidence_file_path=str(evidence_file),
                case_id="case-123",
                investigator_id="user-123",
            )
            
            # Verify broadcast was called with ERROR
            call_args = mock_broadcast.call_args_list
            assert len(call_args) > 0
            event_type = call_args[0][0][1].type
            assert event_type == "ERROR"

    @pytest.mark.asyncio
    async def test_pipeline_failure_increments_failed_metric(self, tmp_path):
        """Test that pipeline failure increments the failed metric."""
        session_id = str(uuid4())
        evidence_file = tmp_path / "test.jpg"
        evidence_file.write_bytes(b"fake image")
        
        mock_pipeline = MagicMock()
        mock_pipeline.run_investigation = AsyncMock(
            side_effect=RuntimeError("Pipeline exploded")
        )
        
        with patch("orchestration.investigation_runner.get_session_persistence") as mock_persist, \
             patch("orchestration.investigation_runner.broadcast_update") as mock_broadcast, \
             patch("orchestration.investigation_runner.set_final_report") as mock_set, \
             patch("orchestration.investigation_runner.set_active_pipeline_metadata") as mock_set_meta, \
             patch("orchestration.investigation_runner.clear_session_websockets") as mock_clear_ws, \
             patch("orchestration.investigation_runner.remove_active_pipeline") as mock_remove, \
             patch("orchestration.investigation_runner.increment_investigations_failed") as mock_inc_fail, \
             patch("orchestration.investigation_runner._active_tasks", {}):
            
            mock_persist.return_value = MagicMock(
                save_report=AsyncMock(),
                update_session_status=AsyncMock()
            )
            
            await run_investigation_task(
                session_id=session_id,
                pipeline=mock_pipeline,
                evidence_file_path=str(evidence_file),
                case_id="case-123",
                investigator_id="user-123",
            )
            
            # Verify failed metric was incremented
            assert mock_inc_fail.call_count == 1

    @pytest.mark.asyncio
    async def test_pipeline_failure_still_cleans_up_file(self, tmp_path):
        """Test that pipeline failure still cleans up the temp file."""
        session_id = str(uuid4())
        evidence_file = tmp_path / "test.jpg"
        evidence_file.write_bytes(b"fake image")
        
        mock_pipeline = MagicMock()
        mock_pipeline.run_investigation = AsyncMock(
            side_effect=RuntimeError("Pipeline exploded")
        )
        
        with patch("orchestration.investigation_runner.get_session_persistence") as mock_persist, \
             patch("orchestration.investigation_runner.broadcast_update") as mock_broadcast, \
             patch("orchestration.investigation_runner.set_final_report") as mock_set, \
             patch("orchestration.investigation_runner.set_active_pipeline_metadata") as mock_set_meta, \
             patch("orchestration.investigation_runner.clear_session_websockets") as mock_clear_ws, \
             patch("orchestration.investigation_runner.remove_active_pipeline") as mock_remove, \
             patch("orchestration.investigation_runner.increment_investigations_failed") as mock_inc_fail, \
             patch("orchestration.investigation_runner._active_tasks", {}):
            
            mock_persist.return_value = MagicMock(
                save_report=AsyncMock(),
                update_session_status=AsyncMock()
            )
            
            await run_investigation_task(
                session_id=session_id,
                pipeline=mock_pipeline,
                evidence_file_path=str(evidence_file),
                case_id="case-123",
                investigator_id="user-123",
            )
            
            # File should be deleted even on failure
            assert not evidence_file.exists()

    @pytest.mark.asyncio
    async def test_temp_file_already_deleted_does_not_raise(self, mock_report, tmp_path):
        """Test that missing temp file on cleanup doesn't raise."""
        session_id = str(uuid4())
        evidence_file = tmp_path / "test.jpg"
        # Don't create the file - it doesn't exist
        
        mock_pipeline = MagicMock()
        mock_pipeline.run_investigation = AsyncMock(return_value=mock_report)
        mock_pipeline._final_report = mock_report
        
        with patch("orchestration.investigation_runner.get_session_persistence") as mock_persist, \
             patch("orchestration.investigation_runner.broadcast_update") as mock_broadcast, \
             patch("orchestration.investigation_runner.set_final_report") as mock_set, \
             patch("orchestration.investigation_runner.set_active_pipeline_metadata") as mock_set_meta, \
             patch("orchestration.investigation_runner.clear_session_websockets") as mock_clear_ws, \
             patch("orchestration.investigation_runner.remove_active_pipeline") as mock_remove, \
             patch("orchestration.investigation_runner.increment_investigations_completed") as mock_inc_comp, \
             patch("orchestration.investigation_runner._active_tasks", {}):
            
            mock_persist.return_value = MagicMock(
                save_report=AsyncMock(),
                update_session_status=AsyncMock()
            )
            
            # Should not raise even if file doesn't exist
            await run_investigation_task(
                session_id=session_id,
                pipeline=mock_pipeline,
                evidence_file_path=str(evidence_file),  # File doesn't exist
                case_id="case-123",
                investigator_id="user-123",
            )

    @pytest.mark.asyncio
    async def test_none_report_raises_runtime_error(self, tmp_path):
        """Test that None report is handled as an error (caught and logged)."""
        session_id = str(uuid4())
        evidence_file = tmp_path / "test.jpg"
        evidence_file.write_bytes(b"fake image")
        
        mock_pipeline = MagicMock()
        mock_pipeline.run_investigation = AsyncMock(return_value=None)
        mock_pipeline._final_report = None  # Both are None
        
        with patch("orchestration.investigation_runner.get_session_persistence") as mock_persist, \
             patch("orchestration.investigation_runner.broadcast_update") as mock_broadcast, \
             patch("orchestration.investigation_runner.set_final_report") as mock_set, \
             patch("orchestration.investigation_runner.set_active_pipeline_metadata") as mock_set_meta, \
             patch("orchestration.investigation_runner.clear_session_websockets") as mock_clear_ws, \
             patch("orchestration.investigation_runner.remove_active_pipeline") as mock_remove, \
             patch("orchestration.investigation_runner.increment_investigations_completed") as mock_inc_comp, \
             patch("orchestration.investigation_runner._active_tasks", {}):
            
            mock_persist.return_value = MagicMock(
                save_report=AsyncMock(),
                update_session_status=AsyncMock()
            )
            
            # Should complete without raising - error is caught and handled
            await run_investigation_task(
                session_id=session_id,
                pipeline=mock_pipeline,
                evidence_file_path=str(evidence_file),
                case_id="case-123",
                investigator_id="user-123",
            )
            
            # Should broadcast ERROR when report is None
            assert mock_broadcast.called

    @pytest.mark.asyncio
    async def test_storage_persistence_failure_does_not_block_completion(self, mock_report, tmp_path):
        """Test that storage persistence failure doesn't block completion."""
        session_id = str(uuid4())
        evidence_file = tmp_path / "test.jpg"
        evidence_file.write_bytes(b"fake image")
        
        mock_pipeline = MagicMock()
        mock_pipeline.run_investigation = AsyncMock(return_value=mock_report)
        mock_pipeline._final_report = mock_report
        
        with patch("orchestration.investigation_runner.get_session_persistence") as mock_persist, \
             patch("orchestration.investigation_runner.broadcast_update") as mock_broadcast, \
             patch("orchestration.investigation_runner.set_final_report") as mock_set, \
             patch("orchestration.investigation_runner.set_active_pipeline_metadata") as mock_set_meta, \
             patch("orchestration.investigation_runner.clear_session_websockets") as mock_clear_ws, \
             patch("orchestration.investigation_runner.remove_active_pipeline") as mock_remove, \
             patch("orchestration.investigation_runner.increment_investigations_completed") as mock_inc_comp, \
             patch("orchestration.investigation_runner._active_tasks", {}):
            
            # Persistence fails but should continue
            mock_persist.return_value = MagicMock(
                save_report=AsyncMock(side_effect=RuntimeError("DB down"))
            )
            
            # Should complete without raising
            await run_investigation_task(
                session_id=session_id,
                pipeline=mock_pipeline,
                evidence_file_path=str(evidence_file),
                case_id="case-123",
                investigator_id="user-123",
            )
            
            # Broadcast should still have been called
            assert mock_broadcast.called