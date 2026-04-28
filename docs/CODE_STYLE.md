# Code Style Guide

## Python Docstrings

All functions, classes, and modules must have docstrings.

### Format: Google Style

```python
def process_image(image_path: str, threshold: float = 0.5) -> Dict[str, Any]:
    """
    Process an image for forensic analysis.

    This function reads an image file, applies forensic ML tools,
    and returns analysis results with confidence scores.

    Args:
        image_path: Path to image file on disk
        threshold: Confidence threshold (0.0-1.0) for flagging anomalies

    Returns:
        Dictionary with keys:
            - "status": "success" or "error"
            - "findings": List of forensic findings
            - "confidence": Overall confidence 0-1
            - "error": Error message if status="error"

    Raises:
        FileNotFoundError: If image_path doesn't exist
        ValueError: If threshold not in range 0.0-1.0
        ProcessingError: If ML analysis fails

    Example:
        >>> result = process_image("/path/to/image.jpg", threshold=0.75)
        >>> if result["status"] == "success":
        ...     print(f"Found {len(result['findings'])} anomalies")
    """
```

## Python Type Hints

All functions and methods require explicit type annotations:

```python
# Correct
def get_session(session_id: str) -> Optional[Session]:
    pass

# Correct
async def run_analysis(file: Path, config: Config) -> AnalysisResult:
    pass

# Correct
def validate_input(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    pass
```

## Linting Rules

- Ruff: All rules enabled except explicitly disabled (linting + formatting via `ruff-format`)
- Mypy: Strict type checking enabled
- No unused imports or variables
- No print statements in production code (use logger instead)

## Commit Messages

Follow Conventional Commits format:

```
type(scope): subject

body

footer
```

Types: feat, fix, docs, style, refactor, test, chore
