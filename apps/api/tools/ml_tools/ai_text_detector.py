"""Statistical AI-generated-text detector (CALIBRATION_PLAN §5, Agent 5).

A self-contained, offline, deterministic detector that scores how machine-like a
passage reads on 0-1 (higher = more likely AI-generated). It exploits interpretable
distributional regularities that separate LLM output from human writing — it is NOT
a trained neural model, and it cannot perceive a synthesis method that leaves no
statistical trace.

By design the RAW score is INDICATIVE / screening-tier. It becomes an honest
probability only after Platt calibration on a labelled benchmark (RAID / HC3) via
the calibration pipeline — which is the whole point of wiring it into
`collect_calibration_scores.py`. Until a calibrated model is adopted, the report /
capability manifest must disclose this as an uncalibrated screening signal.

Signals (each ~0-1, higher = more AI-like), combined into a logistic score:
  • low_burstiness        — humans vary sentence length far more; LLMs are uniform
  • repetition            — repeated bigrams / over-used tokens
  • low_lexical_diversity — flattened type-token ratio
  • punctuation_regularity— even clause / punctuation rhythm
  • connective_density    — LLMs over-use discourse connectives ("however", "moreover")
"""

from __future__ import annotations

import math
import re
from statistics import mean, pstdev
from typing import Any

_SENT_SPLIT = re.compile(r"[.!?]+(?:\s+|$)")
_WORD = re.compile(r"[A-Za-z']+")

# Discourse connectives LLMs lean on disproportionately.
_CONNECTIVES = frozenset({
    "however", "moreover", "furthermore", "additionally", "consequently",
    "therefore", "thus", "hence", "nevertheless", "nonetheless", "overall",
    "importantly", "notably", "specifically", "ultimately", "essentially",
    "indeed", "accordingly", "subsequently", "conversely",
})


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def detect(text_or_path: str, *, is_path: bool = False) -> dict[str, Any]:
    """Return an AI-generated-text screening result.

    ``ai_text_probability`` is the 0-1 raw score the calibration collector reads.
    Pass ``is_path=True`` to read the text from a file first (txt/md direct,
    pdf/docx best-effort).
    """
    text = _read(text_or_path) if is_path else (text_or_path or "")
    text = text.strip()
    words = _WORD.findall(text.lower())
    if len(words) < 40:
        # Too little signal to score honestly — abstain rather than guess.
        return {
            "available": False,
            "ai_text_probability": None,
            "reason": "insufficient text (need >=40 words for a stable score)",
            "word_count": len(words),
            "backend": "statistical-screening",
        }

    sentences = [s for s in _SENT_SPLIT.split(text) if s.strip()]
    sent_lens = [len(_WORD.findall(s)) for s in sentences if _WORD.findall(s)]

    # 1. Burstiness — coefficient of variation of sentence length. Human prose
    #    swings between short and long sentences (high CV); LLM prose is even.
    if len(sent_lens) >= 3 and mean(sent_lens) > 0:
        cv = pstdev(sent_lens) / mean(sent_lens)
        low_burstiness = _clamp01(1.0 - cv / 0.75)  # cv>=0.75 -> human-like (0)
    else:
        low_burstiness = 0.5

    # 2. Repetition — share of bigrams that recur.
    bigrams = list(zip(words, words[1:]))
    uniq_bi = len(set(bigrams))
    repetition = _clamp01(1.0 - (uniq_bi / len(bigrams))) if bigrams else 0.0
    repetition = _clamp01((repetition - 0.15) / 0.35)  # only count above human baseline

    # 3. Lexical diversity — type-token ratio, length-normalised. A flattened
    #    (mid, very uniform) TTR reads AI-like; extreme values are human-ish.
    ttr = len(set(words)) / len(words)
    low_lexical_diversity = _clamp01(1.0 - abs(ttr - 0.45) / 0.45)

    # 4. Punctuation regularity — variance of clause lengths between commas.
    clause_lens = [len(_WORD.findall(c)) for c in re.split(r"[,;:]", text) if _WORD.findall(c)]
    if len(clause_lens) >= 3 and mean(clause_lens) > 0:
        clause_cv = pstdev(clause_lens) / mean(clause_lens)
        punctuation_regularity = _clamp01(1.0 - clause_cv / 0.9)
    else:
        punctuation_regularity = 0.4

    # 5. Connective density — discourse markers per 100 words.
    conn = sum(1 for w in words if w in _CONNECTIVES)
    connective_density = _clamp01((conn / len(words)) / 0.02)  # >=2% -> saturated

    # Logistic combination (uncalibrated priors; calibration replaces these).
    z = (
        -1.6
        + 1.8 * low_burstiness
        + 1.4 * repetition
        + 1.0 * low_lexical_diversity
        + 0.9 * punctuation_regularity
        + 1.2 * connective_density
    )
    prob = 1.0 / (1.0 + math.exp(-z))

    return {
        "available": True,
        "ai_text_probability": round(float(prob), 4),
        "is_ai_suspected": prob >= 0.5,
        "word_count": len(words),
        "signals": {
            "low_burstiness": round(low_burstiness, 3),
            "repetition": round(repetition, 3),
            "low_lexical_diversity": round(low_lexical_diversity, 3),
            "punctuation_regularity": round(punctuation_regularity, 3),
            "connective_density": round(connective_density, 3),
        },
        "court_defensible": False,
        "forensic_caveat": (
            "Statistical AI-text screening (uncalibrated). A score is INDICATIVE only "
            "until calibrated on a labelled benchmark; a clean score does not exclude "
            "machine-authored text, and a high score is not proof of it."
        ),
        "backend": "statistical-screening",
    }


def _read(path: str) -> str:
    """Best-effort text extraction: txt/md direct; pdf via pypdf; docx via python-docx."""
    from pathlib import Path

    p = Path(path)
    suf = p.suffix.lower()
    try:
        if suf in (".txt", ".md", ".text", ".csv", ""):
            return p.read_text(encoding="utf-8", errors="ignore")
        if suf == ".pdf":
            try:
                import pypdf  # type: ignore[import-not-found]

                reader = pypdf.PdfReader(str(p))
                return "\n".join((pg.extract_text() or "") for pg in reader.pages)
            except Exception:
                return ""
        if suf in (".docx",):
            try:
                import docx  # type: ignore[import-not-found]

                return "\n".join(par.text for par in docx.Document(str(p)).paragraphs)
            except Exception:
                return ""
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
