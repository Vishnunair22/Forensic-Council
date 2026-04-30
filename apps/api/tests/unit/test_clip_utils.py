from tools.clip_utils import CLIPAnalysisResult, CLIPImageAnalyzer


def test_generate_fingerprint_uses_embedding_without_model_load(monkeypatch):
    analyzer = CLIPImageAnalyzer()

    embedding = [0.25, -0.5, 0.0, 1.234, -2.5, 0.01, -0.02, 0.03]

    def fake_analyze_image(image_path, categories=None, check_concerns=False):
        return CLIPAnalysisResult(
            top_match="forensic evidence photograph",
            top_confidence=0.91,
            all_scores=[],
            concern_flag=False,
            available=True,
            embedding=embedding,
        )

    monkeypatch.setattr(analyzer, "analyze_image", fake_analyze_image)

    fingerprint = analyzer.generate_fingerprint("sample.jpg")

    assert fingerprint["available"] is True
    assert fingerprint["method"] == "clip_embedding_projection"
    assert fingerprint["dimensions"] == len(embedding)
    assert fingerprint["projection_dimensions"] == len(embedding)
    assert fingerprint["projection"] == [250, -500, 0, 1234, -2500, 10, -20, 30]
    assert fingerprint["bit_fingerprint"] == "10110101"
    assert len(fingerprint["sha256"]) == 64
    assert fingerprint["top_match"] == "forensic evidence photograph"


def test_generate_fingerprint_reports_unavailable_when_embedding_missing(monkeypatch):
    analyzer = CLIPImageAnalyzer()

    def fake_analyze_image(image_path, categories=None, check_concerns=False):
        return CLIPAnalysisResult(
            top_match="unknown",
            top_confidence=0.0,
            all_scores=[],
            concern_flag=False,
            available=False,
            embedding=None,
            error="model unavailable",
        )

    monkeypatch.setattr(analyzer, "analyze_image", fake_analyze_image)

    fingerprint = analyzer.generate_fingerprint("sample.jpg")

    assert fingerprint == {
        "available": False,
        "error": "model unavailable",
        "method": "clip_embedding_projection",
    }
