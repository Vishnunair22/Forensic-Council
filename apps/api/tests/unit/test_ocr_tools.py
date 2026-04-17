import pytest
from unittest.mock import MagicMock, patch, mock_open
import os
from core.evidence import EvidenceArtifact
from tools.ocr_tools import (
    _is_pdf,
    _get_easyocr_reader,
    _extract_text_pymupdf_sync,
    extract_text_from_pdf,
    _extract_text_easyocr_sync,
    extract_text_easyocr,
    extract_evidence_text,
    _build_summary
)

@pytest.fixture
def mock_artifact():
    artifact = MagicMock(spec=EvidenceArtifact)
    artifact.file_path = "test_file.pdf"
    artifact.artifact_id = "test_id"
    return artifact

class TestOCRTools:
    
    def test_is_pdf_valid(self):
        with patch("builtins.open", mock_open(read_data=b"%PDF-1.5")):
            assert _is_pdf("dummy.pdf") is True

    def test_is_pdf_invalid(self):
        with patch("builtins.open", mock_open(read_data=b"not a pdf")):
            assert _is_pdf("dummy.txt") is False

    def test_get_easyocr_reader_caching(self):
        with patch("easyocr.Reader") as mock_reader:
            reader1 = _get_easyocr_reader()
            reader2 = _get_easyocr_reader()
            assert reader1 is reader2
            # Reader should only be called once if successful
            mock_reader.assert_called_once()

    @patch("fitz.open")
    def test_extract_text_pymupdf_sync(self, mock_fitz_open):
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Extracted Text"
        mock_page.get_images.return_value = [1, 2] # 2 images
        mock_doc.__iter__.return_value = [mock_page]
        mock_doc.page_count = 1
        mock_doc.metadata = {"title": "Test PDF"}
        mock_fitz_open.return_value = mock_doc
        
        result = _extract_text_pymupdf_sync("test.pdf")
        
        assert result["pymupdf_available"] is True
        assert result["full_text"] == "Extracted Text"
        assert result["embedded_image_count"] == 2
        assert result["doc_metadata"]["title"] == "Test PDF"
        mock_doc.close.assert_called_once()

    @patch("tools.ocr_tools._is_pdf", return_value=True)
    @patch("os.path.exists", return_value=True)
    @pytest.mark.asyncio
    async def test_extract_text_from_pdf_async(self, mock_exists, mock_is_pdf, mock_artifact):
        # We need to mock the loop to return an asyncio.Future
        import asyncio
        async_future = asyncio.Future()
        async_future.set_result({"pymupdf_available": True, "full_text": "Async Text"})
        
        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.run_in_executor.return_value = async_future
            result = await extract_text_from_pdf(mock_artifact)
            
        assert result["method"] == "pymupdf"
        assert result["full_text"] == "Async Text"

    @patch("tools.ocr_tools._get_easyocr_reader")
    def test_extract_text_easyocr_sync(self, mock_get_reader):
        mock_reader = MagicMock()
        # format: [([x1,y1], [x2,y1], [x2,y2], [x1,y2]), text, confidence]
        mock_reader.readtext.return_value = [
            ([[0, 0], [10, 0], [10, 10], [0, 10]], "Hello", 0.95),
            ([[20, 0], [30, 0], [30, 10], [20, 10]], "World", 0.85)
        ]
        mock_get_reader.return_value = mock_reader
        
        result = _extract_text_easyocr_sync("image.jpg", detail=True)
        
        assert result["easyocr_available"] is True
        assert result["full_text"] == "Hello World"
        assert result["avg_confidence"] == 0.9
        assert len(result["bboxes"]) == 2
        assert result["bboxes"][0]["text"] == "Hello"

    @patch("os.path.exists", return_value=True)
    @pytest.mark.asyncio
    async def test_extract_evidence_text_routing(self, mock_exists, mock_artifact):
        # Test PDF routing
        mock_artifact.file_path = "test.pdf"
        with patch("tools.ocr_tools.extract_text_from_pdf") as mock_pdf:
            mock_pdf.return_value = {"method": "pymupdf", "has_text": True}
            result = await extract_evidence_text(mock_artifact)
            assert result["file_type_hint"] == "pdf_document"
            
        # Test Image routing
        mock_artifact.file_path = "test.jpg"
        with patch("tools.ocr_tools.extract_text_easyocr") as mock_img:
            mock_img.return_value = {"method": "easyocr", "has_text": True}
            result = await extract_evidence_text(mock_artifact)
            assert result["file_type_hint"] == "image"

        # Test AV routing (skipped)
        mock_artifact.file_path = "test.mp4"
        result = await extract_evidence_text(mock_artifact)
        assert result["file_type_hint"] == "audio_video"
        assert result["method"] == "skipped"

    def test_build_summary_pdf(self):
        result = {
            "has_text": True,
            "word_count": 100,
            "method": "pymupdf",
            "page_count": 5
        }
        summary = _build_summary(result, "pdf_document")
        assert "PDF document: 100 words" in summary
        assert "5 page(s)" in summary

    def test_build_summary_image(self):
        result = {
            "has_text": True,
            "word_count": 10,
            "method": "easyocr",
            "avg_confidence": 0.92,
            "lines": ["Line 1", "Line 2", "Line 3", "Line 4"]
        }
        summary = _build_summary(result, "image")
        assert "Image text: 10 words" in summary
        assert "92%" in summary
        assert "Line 1 | Line 2 | Line 3 ..." in summary

    @patch("os.path.exists", return_value=False)
    @pytest.mark.asyncio
    async def test_extract_text_from_pdf_file_not_found(self, mock_exists, mock_artifact):
        from core.exceptions import ToolUnavailableError
        with pytest.raises(ToolUnavailableError, match="File not found"):
            await extract_text_from_pdf(mock_artifact)

    @patch("tools.ocr_tools._is_pdf", return_value=False)
    @patch("os.path.exists", return_value=True)
    @pytest.mark.asyncio
    async def test_extract_text_from_pdf_not_a_pdf(self, mock_exists, mock_is_pdf, mock_artifact):
        result = await extract_text_from_pdf(mock_artifact)
        assert result["has_text"] is False
        assert "File is not a PDF" in result["note"]

    @patch("tools.ocr_tools._get_easyocr_reader", return_value=None)
    @patch("os.path.exists", return_value=True)
    @pytest.mark.asyncio
    async def test_extract_text_easyocr_unavailable_fallback(self, mock_exists, mock_get_reader, mock_artifact):
        with patch("tools.ocr_tools._extract_text_tesseract_fallback") as mock_fallback:
            mock_fallback.return_value = {"method": "tesseract_fallback", "has_text": True}
            result = await extract_text_easyocr(mock_artifact)
            assert result["method"] == "tesseract_fallback"

    @patch("os.path.exists", return_value=True)
    @pytest.mark.asyncio
    async def test_extract_evidence_text_scanned_pdf(self, mock_exists, mock_artifact):
        mock_artifact.file_path = "scanned.pdf"
        with patch("tools.ocr_tools.extract_text_from_pdf") as mock_pdf:
            mock_pdf.return_value = {"method": "pymupdf", "has_text": False}
            result = await extract_evidence_text(mock_artifact)
            assert "scanned_pdf_note" in result
            assert "rasterise pages" in result["scanned_pdf_note"]
