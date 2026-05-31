from __future__ import annotations
import json
from typing import Any, Dict
from core.config import Settings
from core.llm_client import LLMClient
from core.structured_logging import get_logger

logger = get_logger(__name__)

# Required sections that Groq must return and polish
REQUIRED_SECTIONS = [
    "executive_summary",
    "evidence_overview",
    "methodology",
    "agent_deliberation_summary",
    "key_findings",
    "integrity_assessment",
    "object_scene_context",
    "metadata_and_provenance",
    "limitations",
    "final_conclusion",
    "reliability_notes"
]

# Blacklist of prohibited vendor/model phrases to ensure neutrality
PROHIBITED_WORDS = [
    "gemini", "groq", "cerebras", "openai", "llama", "google", "meta", "gpt-", "claude", "llm assisted", "llm-assisted"
]

async def refine_report_with_groq(
    deterministic_report: dict[str, Any],
    config: Settings
) -> tuple[dict[str, Any], bool]:
    """Uses Groq to polish the report narrative. Returns the updated report dict and a boolean indicating success."""
    
    llm_client = LLMClient(config=config, use_arbiter_tier=True)
    if not (config.llm_enable_post_synthesis and config.llm_api_key and llm_client.is_available):
        logger.info("Skipping Groq report polish: LLM disabled or api key unavailable.")
        return deterministic_report, False

    system_prompt = (
        "You are a forensic report editor assisting an arbiter.\n"
        "The arbiter has already computed the final verdict, confidence, evidence weights, limitations, and reliability notes.\n"
        "You must preserve those exactly. Under no circumstances should you change the verdict or confidence values.\n"
        "Your job is to improve clarity, cohesion, and professional structure of the narrative fields.\n"
        "STRICT CONSTRAINTS:\n"
        "1. DO NOT invent findings or add tools that were not executed.\n"
        "2. DO NOT change verdict or confidence.\n"
        "3. DO NOT mention Groq, Gemini, model names, or provider names (e.g. Gemini, OpenAI, Groq, Cerebras, NCFI, NCFTA).\n"
        "4. DO NOT describe visual content unless it is present in the provided visual context or tool findings.\n"
        "5. DO NOT treat missing API/LLM access as degradation. Only tool failures may appear as limitations.\n"
        "6. Every key finding in key_findings must keep the finding-first format: `[Finding] — [Tool(s)] ([Confidence]%)`.\n"
        "7. Return strict JSON only matching the schema of the provided input report.\n"
    )

    # Format the input package to only include the report sections and core determination
    input_payload = {
        "final_verdict": deterministic_report.get("final_verdict"),
        "confidence_score": deterministic_report.get("confidence_score"),
        "confidence_reason": deterministic_report.get("confidence_reason"),
        "executive_summary": deterministic_report.get("executive_summary"),
        "evidence_overview": deterministic_report.get("evidence_overview"),
        "methodology": deterministic_report.get("methodology"),
        "agent_deliberation_summary": deterministic_report.get("agent_deliberation_summary"),
        "key_findings": deterministic_report.get("key_findings"),
        "integrity_assessment": deterministic_report.get("integrity_assessment"),
        "object_scene_context": deterministic_report.get("object_scene_context"),
        "metadata_and_provenance": deterministic_report.get("metadata_and_provenance"),
        "limitations": deterministic_report.get("limitations"),
        "reliability_notes": deterministic_report.get("reliability_notes"),
        "final_conclusion": deterministic_report.get("final_conclusion")
    }

    try:
        raw_response = await llm_client.generate_synthesis(
            system_prompt=system_prompt,
            user_content=json.dumps(input_payload, indent=2, default=str),
            max_tokens=2048,
            timeout_override=45.0,
            json_mode=True,
            priority="critical"
        )
        if not raw_response:
            logger.warning("Groq report refiner returned empty response.")
            return deterministic_report, False

        cleaned_resp = raw_response.strip()
        if cleaned_resp.startswith("```"):
            lines = cleaned_resp.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned_resp = "\n".join(lines).strip()

        parsed = json.loads(cleaned_resp)
        
        # --- Perform Post-Groq Validation ---
        
        # 1. Check verdict and confidence are unchanged
        if parsed.get("final_verdict") != deterministic_report.get("final_verdict"):
            logger.warning("Groq attempt rejected: modified final_verdict.")
            return deterministic_report, False
            
        if parsed.get("confidence_score") != deterministic_report.get("confidence_score"):
            logger.warning("Groq attempt rejected: modified confidence_score.")
            return deterministic_report, False

        # 2. Check no provider names or prohibited words are mentioned
        for sec in REQUIRED_SECTIONS:
            sec_val = parsed.get(sec)
            if not sec_val:
                logger.warning(f"Groq attempt rejected: missing required section `{sec}`.")
                return deterministic_report, False
            
            text_to_check = ""
            if isinstance(sec_val, list):
                text_to_check = " ".join([str(x) for x in sec_val]).lower()
            else:
                text_to_check = str(sec_val).lower()
                
            for word in PROHIBITED_WORDS:
                if word in text_to_check:
                    logger.warning(f"Groq attempt rejected: prohibited word `{word}` found in section `{sec}`.")
                    return deterministic_report, False

        # 3. Validate key findings format
        refined_kfs = parsed.get("key_findings")
        if not isinstance(refined_kfs, list) or not refined_kfs:
            logger.warning("Groq attempt rejected: key_findings is not a list or is empty.")
            return deterministic_report, False
            
        for kf in refined_kfs:
            kf_str = str(kf)
            if " — " not in kf_str:
                logger.warning(f"Groq attempt rejected: key finding `{kf_str}` violates finding-first formatting.")
                return deterministic_report, False

        # Merge polished fields into report
        final_report = dict(deterministic_report)
        for sec in REQUIRED_SECTIONS:
            final_report[sec] = parsed[sec]

        # Add execution note to reliability_notes
        reliability_notes = list(final_report.get("reliability_notes") or [])
        # Remove the deterministic reliability note if present
        det_note = (
            "Reliability note: Final report narrative was generated deterministically from local tool findings and arbiter deliberation. "
            "No external text model was used."
        )
        if det_note in reliability_notes:
            reliability_notes.remove(det_note)
            
        groq_note = (
            "Reliability note: Final narrative cohesion was assisted by an external text model. "
            "The verdict, confidence, and evidentiary findings were computed by the arbiter from grounded tool outputs."
        )
        if groq_note not in reliability_notes:
            reliability_notes.append(groq_note)
            
        final_report["reliability_notes"] = reliability_notes
        
        logger.info("Successfully refined report narrative using Groq.")
        return final_report, True

    except Exception as e:
        logger.warning(f"Failed to refine report with Groq: {e}. Falling back to deterministic.")
        return deterministic_report, False
