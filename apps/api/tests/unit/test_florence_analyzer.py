import sys
from unittest.mock import MagicMock, patch

# Mock third-party libraries not present in the base python environment
mock_torch = MagicMock()
mock_torch.cuda = MagicMock()
mock_torch.cuda.is_available = MagicMock(return_value=False)

mock_transformers = MagicMock()

sys.modules["torch"] = mock_torch
sys.modules["transformers"] = mock_transformers

import pytest

from tools.florence_analyzer import FlorenceResult, get_florence_analyzer, reset_florence_analyzer


@pytest.fixture(autouse=True)
def setup_teardown():
    reset_florence_analyzer()
    yield
    reset_florence_analyzer()


def test_singleton_get_florence_analyzer():
    analyzer1 = get_florence_analyzer()
    analyzer2 = get_florence_analyzer()
    assert analyzer1 is analyzer2


def test_florence_load_success():
    mock_processor = MagicMock()
    mock_transformers.AutoProcessor.from_pretrained = MagicMock(return_value=mock_processor)
    mock_model = MagicMock()
    mock_transformers.AutoModelForCausalLM.from_pretrained = MagicMock(return_value=mock_model)

    analyzer = get_florence_analyzer()
    assert analyzer.available is False

    success = analyzer._load()
    assert success is True
    assert analyzer.available is True
    assert analyzer._device == "cpu"
    # Tolerant of the local_files_only kwarg (set from settings.offline_mode).
    proc_call = mock_transformers.AutoProcessor.from_pretrained.call_args
    assert proc_call.args[0] == "microsoft/Florence-2-base"
    assert proc_call.kwargs["trust_remote_code"] is True
    model_call = mock_transformers.AutoModelForCausalLM.from_pretrained.call_args
    assert model_call.args[0] == "microsoft/Florence-2-base"
    assert model_call.kwargs["trust_remote_code"] is True
    assert model_call.kwargs["attn_implementation"] == "eager"


def test_florence_load_failure():
    mock_transformers.AutoProcessor.from_pretrained = MagicMock(side_effect=Exception("Load error"))
    analyzer = get_florence_analyzer()
    success = analyzer._load()
    assert success is False
    assert analyzer.available is False


@patch("PIL.Image.open")
def test_florence_analyze_without_load(mock_image_open):
    # If load fails, analyze should return not available
    analyzer = get_florence_analyzer()
    with patch.object(analyzer, "_load", return_value=False):
        result = analyzer.analyze("fake_image.png")
        assert result.available is False
        assert "not available" in result.error


@patch("PIL.Image.open")
def test_florence_analyze_success(mock_image_open):
    mock_image = MagicMock()
    mock_converted_image = MagicMock()
    # Real dimensions so cap_image_dimension's width/height comparisons work
    # (it would otherwise compare MagicMocks → "'>' not supported").
    mock_converted_image.width = 800
    mock_converted_image.height = 600
    mock_converted_image.size = (800, 600)
    mock_image.convert.return_value = mock_converted_image
    mock_image_open.return_value = mock_image

    analyzer = get_florence_analyzer()
    mock_processor = MagicMock()
    mock_model = MagicMock()

    # Stub out the attributes directly to simulate load
    analyzer._processor = mock_processor
    analyzer._model = mock_model
    analyzer._device = "cpu"
    analyzer._available = True
    analyzer._loaded = True

    # Mock the internal _run_task method
    with patch.object(analyzer, "_run_task") as mock_run_task:
        mock_run_task.side_effect = lambda task, img: f"result for {task}"

        result = analyzer.analyze("fake_image.png")

        assert result.available is True
        assert result.caption == "result for <DETAILED_CAPTION>"
        assert result.detailed_caption == "result for <DETAILED_CAPTION>"
        assert result.best_description() == "result for <DETAILED_CAPTION>"

        mock_run_task.assert_called_once_with("<DETAILED_CAPTION>", mock_converted_image)


def test_florence_result_best_description():
    res = FlorenceResult(caption="Simple caption", detailed_caption="Detailed caption", available=True)
    assert res.best_description() == "Detailed caption"

    res_no_detailed = FlorenceResult(caption="Simple caption", detailed_caption="", available=True)
    assert res_no_detailed.best_description() == "Simple caption"
