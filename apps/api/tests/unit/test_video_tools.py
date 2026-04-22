from unittest.mock import MagicMock, mock_open, patch

import numpy as np
import pytest

from core.evidence import EvidenceArtifact
from tools.video_tools import (
    face_swap_detect,
    face_swap_detect_deepface,
    frame_consistency_analyze,
    frame_window_extract,
    optical_flow_analyze,
    video_metadata_extract,
)


@pytest.fixture
def mock_artifact():
    artifact = MagicMock(spec=EvidenceArtifact)
    artifact.file_path = "test_video.mp4"
    artifact.artifact_id = "test_id"
    # mock to_dict if needed
    artifact.to_dict.return_value = {"id": "test_id"}
    return artifact

class TestVideoTools:

    @patch("cv2.VideoCapture")
    @patch("os.path.exists", return_value=True)
    @patch("os.path.getsize", return_value=1024*1024)
    @pytest.mark.asyncio
    async def test_video_metadata_extract(self, mock_getsize, mock_exists, mock_vc, mock_artifact):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: {
            0: 30.0, # FPS (CAP_PROP_FPS is usually 5) - wait check values
        }.get(prop, 0)
        # Simplified side effect for testing
        mock_cap.get.side_effect = lambda prop: 30.0 if prop == 5 else 100.0 if prop == 7 else 1920 # FPS=30, Count=100
        mock_cap.getBackendName.return_value = "FFMPEG"
        mock_vc.return_value = mock_cap

        result = await video_metadata_extract(mock_artifact)

        assert "metadata" in result
        assert result["metadata"]["fps"] == 30.0
        assert result["metadata"]["frame_count"] == 100
        assert result["metadata"]["duration"] == pytest.approx(3.333, 0.01)

    @patch("cv2.VideoCapture")
    @patch("cv2.imwrite")
    @patch("os.path.exists", return_value=True)
    @patch("os.makedirs")
    @patch("core.evidence.EvidenceArtifact.create_derivative")
    @pytest.mark.asyncio
    async def test_frame_window_extract(self, mock_create_deriv, mock_makedirs, mock_exists, mock_imwrite, mock_vc, mock_artifact):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.return_value = 100 # Total frames
        mock_cap.read.return_value = (True, np.zeros((10, 10, 3), dtype=np.uint8))
        mock_vc.return_value = mock_cap

        # Mock derivative artifact
        mock_deriv = MagicMock()
        mock_deriv.to_dict.return_value = {"id": "deriv_id"}
        mock_create_deriv.return_value = mock_deriv

        result = await frame_window_extract(mock_artifact, start_frame=0, end_frame=5)

        assert result["frame_count"] == 5
        assert mock_imwrite.call_count == 5
        assert result["frames_artifact"]["id"] == "deriv_id"

    @patch("cv2.VideoCapture")
    @patch("cv2.calcOpticalFlowFarneback")
    @patch("cv2.imwrite")
    @patch("os.path.exists", return_value=True)
    @patch("core.evidence.EvidenceArtifact.create_derivative")
    @pytest.mark.asyncio
    async def test_optical_flow_analyze(self, mock_create_deriv, mock_exists, mock_imwrite, mock_flow, mock_vc, mock_artifact):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        # CV2 props: 3=width, 4=height, 5=fps, 7=frame_count
        mock_cap.get.side_effect = lambda prop: {
            3: 100, 4: 100, 5: 30.0, 7: 10
        }.get(prop, 0)
        mock_cap.read.side_effect = [(True, np.zeros((100, 100, 3), dtype=np.uint8))] * 11 + [(False, None)]
        mock_vc.return_value = mock_cap

        # Mock optical flow (returns flow field)
        mock_flow.return_value = np.zeros((100, 100, 2), dtype=np.float32)

        mock_deriv = MagicMock()
        mock_deriv.to_dict.return_value = {"id": "heatmap_id"}
        mock_create_deriv.return_value = mock_deriv

        with patch("builtins.open", mock_open(read_data=b"fake image data")):
            result = await optical_flow_analyze(mock_artifact, flow_threshold=3.0)

        assert "motion_stats" in result
        assert result["anomaly_heatmap_artifact"]["id"] == "heatmap_id"

    @patch("cv2.imread")
    @patch("os.path.isdir", return_value=True)
    @patch("os.listdir")
    @pytest.mark.asyncio
    async def test_frame_consistency_analyze(self, mock_listdir, mock_isdir, mock_imread, mock_artifact):
        mock_listdir.return_value = ["frame_001.png", "frame_002.png", "frame_003.png"]

        # Create different frames to trigger inconsistency
        frame1 = np.zeros((100, 100, 3), dtype=np.uint8)
        frame2 = np.ones((100, 100, 3), dtype=np.uint8) * 255 # Very different
        mock_imread.side_effect = [frame1, frame2, frame1]

        # We need a dummy artifact that points to a directory
        dir_artifact = MagicMock(spec=EvidenceArtifact)
        dir_artifact.file_path = "frames_dir"

        result = await frame_consistency_analyze(dir_artifact, histogram_threshold=0.1)

        assert len(result["inconsistencies"]) > 0
        assert result["classification_hint"] != "natural"

    @patch("cv2.CascadeClassifier")
    @patch("cv2.imread")
    @patch("os.path.isdir", return_value=True)
    @patch("os.listdir")
    @pytest.mark.asyncio
    async def test_face_swap_detect_heuristic(self, mock_listdir, mock_isdir, mock_imread, mock_cascade_cls, mock_artifact):
        mock_listdir.return_value = ["frame_001.png"]
        mock_imread.return_value = np.zeros((200, 200, 3), dtype=np.uint8)

        mock_cascade = MagicMock()
        # Mock detection: [[x, y, w, h]]
        mock_cascade.detectMultiScale.return_value = [[50, 50, 64, 64]]
        mock_cascade_cls.return_value = mock_cascade

        dir_artifact = MagicMock(spec=EvidenceArtifact)
        dir_artifact.file_path = "frames_dir"

        result = await face_swap_detect(dir_artifact)

        assert "deepfake_suspected" in result
        assert result["face_count"] == 1

    @patch("cv2.VideoCapture")
    @patch("os.path.exists", return_value=True)
    @pytest.mark.asyncio
    async def test_face_swap_detect_deepface_fallback(self, mock_exists, mock_vc, mock_artifact):
        # Test fallback when deepface is not installed
        with patch.dict("sys.modules", {"deepface": None}):
             # Reloading or re-importing might be tricky, but face_swap_detect_deepface
             # has a try-except ImportError inside.
             result = await face_swap_detect_deepface(mock_artifact)
             assert result["available"] is False
             assert "DeepFace library not installed" in result["forensic_caveat"]

    @patch("os.path.exists", return_value=False)
    @pytest.mark.asyncio
    async def test_optical_flow_file_not_found(self, mock_exists, mock_artifact):
        from core.exceptions import ToolUnavailableError
        with pytest.raises(ToolUnavailableError, match="File not found"):
            await optical_flow_analyze(mock_artifact)

    @patch("cv2.VideoCapture")
    @patch("os.path.exists", return_value=True)
    @pytest.mark.asyncio
    async def test_optical_flow_cannot_open(self, mock_exists, mock_vc, mock_artifact):
        from core.exceptions import ToolUnavailableError
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_vc.return_value = mock_cap
        with pytest.raises(ToolUnavailableError, match="Cannot open video"):
            await optical_flow_analyze(mock_artifact)

    @patch("os.path.exists", return_value=True)
    @pytest.mark.asyncio
    async def test_frame_window_extract_invalid_range(self, mock_exists, mock_artifact):
        from core.exceptions import ToolUnavailableError
        with patch("cv2.VideoCapture") as mock_vc:
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = True
            mock_cap.get.return_value = 100
            mock_vc.return_value = mock_cap
            with pytest.raises(ToolUnavailableError, match="Invalid frame range"):
                await frame_window_extract(mock_artifact, start_frame=50, end_frame=40)

    @patch("os.path.isdir", return_value=False)
    @pytest.mark.asyncio
    async def test_frame_consistency_not_a_dir(self, mock_isdir, mock_artifact):
        from core.exceptions import ToolUnavailableError
        with pytest.raises(ToolUnavailableError, match="not a directory"):
            await frame_consistency_analyze(mock_artifact)

    @patch("os.path.isdir", return_value=True)
    @patch("os.listdir", return_value=[])
    @pytest.mark.asyncio
    async def test_face_swap_detect_no_frames(self, mock_listdir, mock_isdir, mock_artifact):
        result = await face_swap_detect(mock_artifact)
        assert "No frames found" in result["message"]

    @patch("cv2.VideoCapture")
    @patch("os.path.exists", return_value=True)
    @pytest.mark.asyncio
    async def test_optical_flow_with_outliers(self, mock_exists, mock_vc, mock_artifact):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        # 10 frames, mean flow will vary to trigger Z-score > threshold
        mock_cap.get.side_effect = lambda prop: {3: 100, 4: 100, 5: 10, 7: 10}.get(prop, 0.0)

        # 5 normal frames, 1 outlier, 4 normal
        frame_data = np.ones((100, 100, 3), dtype=np.uint8)
        # side_effect needs to be a list of returns
        mock_cap.read.side_effect = [(True, frame_data)] * 11 + [(False, None)]
        mock_vc.return_value = mock_cap

        # Mock flow to return high magnitude for a specific call
        flow_results = [np.full((100, 100, 2), 1.0)] * 10
        flow_results[5] = np.full((100, 100, 2), 100.0) # outlier

        with patch("cv2.calcOpticalFlowFarneback", side_effect=flow_results), \
             patch("cv2.imwrite"), \
             patch("builtins.open", mock_open(read_data=b"data")), \
             patch("core.evidence.EvidenceArtifact.create_derivative", return_value=MagicMock()):
            result = await optical_flow_analyze(mock_artifact, flow_threshold=1.0)
            assert len(result["flagged_frames"]) > 0

    @patch("cv2.VideoCapture")
    @patch("os.path.exists", return_value=True)
    @patch("os.path.getsize", return_value=1234)
    @pytest.mark.asyncio
    async def test_video_metadata_zero_fps(self, mock_getsize, mock_exists, mock_vc, mock_artifact):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: 0.0 if prop == 5 else 100 # FPS=0
        mock_vc.return_value = mock_cap

        result = await video_metadata_extract(mock_artifact)
        assert result["metadata"]["duration"] == 0

    @patch("cv2.VideoCapture")
    @patch("os.path.exists", return_value=True)
    @pytest.mark.asyncio
    async def test_face_swap_detect_deepface_success(self, mock_exists, mock_vc, mock_artifact):
        # Mock deepface module and its attributes
        mock_deepface = MagicMock()
        with patch.dict("sys.modules", {"deepface": mock_deepface}):
            from deepface import DeepFace

            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = True
            mock_cap.get.return_value = 2.0 # FPS=2, so sample rate = 1 (every frame)
            # 5 frames to ensure we get > 3 detections
            mock_frames = [(True, np.zeros((10, 10, 3)))] * 5
            mock_cap.read.side_effect = mock_frames + [(False, None)]
            mock_vc.return_value = mock_cap

            # 5 embeddings
            DeepFace.represent.side_effect = [
                [{"embedding": [1.0] * 128}],
                [{"embedding": [-1.0] * 128}],
                [{"embedding": [1.0] * 128}],
                [{"embedding": [-1.0] * 128}],
                [{"embedding": [1.0] * 128}]
            ]

            result = await face_swap_detect_deepface(mock_artifact, confidence_threshold=0.1)
            assert result["face_swap_detected"] is True
            assert result["discontinuity_count"] > 0
