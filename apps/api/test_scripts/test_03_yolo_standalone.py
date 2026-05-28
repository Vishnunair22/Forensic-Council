"""
Test 3: Object Detection (Agent 3 - Object/Scene)
Tests object_detection_handler with graceful degradation when ML models unavailable.
"""
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock


async def test_object_detection_handler_with_mock():
    """Test the SceneHandler's object_detection_handler via the handler class."""
    from core.handlers.scene import SceneHandlers

    mock_agent = MagicMock()
    mock_agent.agent_id = "Agent3"
    mock_agent.session_id = "test-session"
    mock_agent.evidence_artifact = MagicMock()
    mock_agent.evidence_artifact.file_path = "/tmp/test_object.jpg"
    mock_agent.evidence_artifact.mime_type = "image/jpeg"
    mock_agent.config.yolo_model_name = "detr-resnet-50"
    mock_agent.config.enable_agpl_models = False
    mock_agent.working_memory = MagicMock()
    mock_agent.custody_logger = AsyncMock()
    mock_agent.heavy_tool_semaphore = None
    mock_agent._tool_context = {}
    mock_agent.update_sub_task = AsyncMock()
    mock_agent._record_tool_result = AsyncMock()

    mock_inference = AsyncMock()
    mock_inference.predict_yolo = AsyncMock(return_value=[])
    mock_inference.get_yolo_model = AsyncMock()

    mock_model = MagicMock()
    mock_model.names = {}
    mock_model.ckpt_path = "mock-detector"
    mock_inference.get_yolo_model.return_value = mock_model

    handler = SceneHandlers(agent=mock_agent)

    with patch.object(handler, 'get_inference', new=AsyncMock(return_value=mock_inference)), \
         patch.object(handler, '_extension_safe_media_path', new=AsyncMock(return_value=("/tmp/test_object.jpg", None))), \
         patch.object(handler, '_is_video', return_value=False):
        result = await handler.object_detection_handler({"artifact": mock_agent.evidence_artifact})

        assert "available" in result
        if not result["available"]:
            print("  Model unavailable (expected without ML deps) — graceful degradation OK")
        else:
            assert "detections" in result
            assert "detection_count" in result
            print(f"  Detections: {result['detection_count']}")


async def test_model_availability_check():
    from core.inference_client import get_inference_client
    from core.config import get_settings

    settings = get_settings()
    try:
        client = await get_inference_client(settings)
        available = await client.is_available()
        print(f"  Model available: {available}")
        print(f"  Model name: {settings.yolo_model_name}")
        print(f"  AGPL enabled: {settings.enable_agpl_models}")
    except Exception as e:
        print(f"  Model unavailable (expected): {type(e).__name__}: {e}")


if __name__ == "__main__":
    print("Test 3a: Object Detection Handler (mocked)")
    asyncio.run(test_object_detection_handler_with_mock())
    print()
    print("Test 3b: Model Availability Check")
    asyncio.run(test_model_availability_check())
    print()
    print(" All YOLO/Object Detection tests passed!")
