"""
Forensic summary interpreters for tool results.
Extracted from react_loop.py to improve maintainability.
"""

from typing import Any

# Registry of tool-specific summary generators.
# Each entry is a callable that takes a tool output dict and returns a string.
_TOOL_INTERPRETERS: dict[str, Any] = {
    # ── Image tools ───────────────────────────────────────────────────
    "ela_full_image": lambda o: (
        # ELA not applicable for lossless formats (PNG, BMP, TIFF, etc.)
        o.get("ela_limitation_note", "")
        if o.get("ela_not_applicable")
        # Make the region count more human and avoid implying that
        # every connected component is a large "region".
        else (
            lambda count, max_a: (
                "ELA detected "
                + (
                    "no anomaly regions "
                    if count == 0
                    else "a small number of localized anomaly regions "
                    if count < 50
                    else "dozens of clustered anomaly regions "
                    if count < 200
                    else "hundreds of clustered anomaly regions "
                    if count < 2000
                    else "extensive anomaly patterns (thousands of small regions) "
                )
                + f"(~{count} connected region(s)) with a maximum deviation of {max_a:.1f} "
                + (
                    "(significant manipulation signature)."
                    if max_a > 20
                    else "within normal compression range."
                )
            )
        )(
            int(o.get("num_anomaly_regions", 0) or 0),
            float(o.get("max_anomaly", 0) or 0.0),
        )
    ),
    "jpeg_ghost_detect": lambda o: (
        o.get(
            "ghost_limitation_note",
            "JPEG ghost detection: not applicable for this file type.",
        )
        if o.get("ghost_not_applicable")
        else f"JPEG ghost analysis {'detected double-compression artifacts' if o.get('ghost_detected') else 'found no ghost artifacts'} "
        f"with {o.get('confidence', 0):.0%} confidence across {len(o.get('ghost_regions', []))} region(s)."
    ),
    "frequency_domain_analysis": lambda o: (
        f"Frequency domain analysis yielded anomaly score {o.get('anomaly_score', 0):.3f} "
        f"(high-freq ratio: {o.get('high_freq_ratio', 0):.3f}, "
        f"{'anomalous high-frequency content detected' if o.get('anomaly_score', 0) > 0.4 else 'frequency distribution appears natural'})."
    ),
    "noise_fingerprint": lambda o: (
        o.get(
            "file_format_note",
            "PRNU noise fingerprint analysis not applicable for this file type.",
        )
        if o.get("noise_fingerprint_not_applicable")
        else (
            f"PRNU noise fingerprint: {o.get('verdict', 'INCONCLUSIVE')} — "
            f"consistency score {o.get('noise_consistency_score', 0):.3f}, "
            f"{o.get('outlier_region_count', 0)} of {o.get('total_regions', 0)} region(s) flagged as outliers."
        )
    ),
    "copy_move_detect": lambda o: (
        f"Copy-move detection: {o.get('match_count', o.get('num_matches', 0))} keypoint match(es). "
        + (
            "Copy-move forgery detected."
            if o.get("copy_move_detected")
            else "No copy-move cloning detected."
        )
    ),
    "splicing_detect": lambda o: (
        f"Splicing detection: {'SPLICING DETECTED' if o.get('splicing_detected') else 'No splicing found'}. "
        f"{o.get('num_inconsistent_blocks', 0)} of {o.get('total_blocks', 0)} blocks flagged "
        f"(ratio {o.get('inconsistency_ratio', 0):.3f})."
    ),
    "image_splice_check": lambda o: (
        f"Image splice check: {'SPLICING DETECTED' if o.get('splicing_detected') else 'No splicing found'}. "
        f"{o.get('num_inconsistent_blocks', 0)} of {o.get('total_blocks', 0)} blocks flagged."
    ),
    "file_hash_verify": lambda o: (
        "Hash verification: SHA-256 = "
        + str(o.get("current_hash", o.get("original_hash", "")))[:20]
        + "... "
        + (
            "Hash matches chain-of-custody record — file integrity confirmed."
            if o.get("hash_matches")
            else "WARNING: hash mismatch — file may have been modified after ingestion."
        )
    ),
    "adversarial_robustness_check": lambda o: (
        f"Adversarial robustness: {'EVASION DETECTED — findings may be adversarially engineered.' if o.get('adversarial_pattern_detected') else 'Findings are stable under perturbation — robust.'} "
        f"Method: {o.get('method', 'perturbation stability')}."
    ),
    # ── Object detection tools (Agent 3) ─────────────────────────────
    "object_detection": lambda o: (
        f"YOLO object detection: {o.get('detection_count', len(o.get('detections', [])))} object(s) detected "
        f"({', '.join(o.get('classes_found', [])[:8]) or 'none'}). "
        + (
            f"WEAPON CLASSES DETECTED: {', '.join(d['class_name'] for d in o.get('weapon_detections', []))}."
            if o.get("weapon_detections")
            else "No weapons detected."
        )
    ),
    "secondary_classification": lambda o: (
        f"Secondary CLIP classification of '{o.get('input_object_class', 'object')}': "
        f"top match = '{o.get('top_refined_match', 'unknown')}' ({o.get('top_confidence', 0):.0%}). "
        + ("CONCERN FLAGGED." if o.get("concern_flag") else "No concern flag.")
    ),
    "scale_validation": lambda o: (
        f"Scale/proportion analysis: {'consistent perspective angles' if o.get('scale_consistent') else 'INCONSISTENT perspective — possible compositing'}. "
        f"Line angle std: {o.get('angle_std_deg', 0):.1f}° across {o.get('line_count', 0)} lines."
    ),
    "scene_incongruence": lambda o: (
        f"Scene noise coherence: {o.get('contextual_anomalies_detected', 0)} anomalous region(s) detected. "
        f"Noise std across quadrants: {o.get('noise_variance_across_quadrants', 0):.1f} "
        f"(mean: {o.get('mean_noise_level', 0):.1f}). "
        + (o.get("anomaly_description", "") or "")
    ),
    "contraband_database": lambda o: (
        f"Contraband/CLIP analysis: top match = '{o.get('top_matches', [{}])[0].get('category', 'none') if o.get('top_matches') else 'none'}'. "
        + (
            "CONCERN FLAG raised."
            if o.get("concern_flag")
            else "No concern flag raised."
        )
    ),
    "lighting_consistency": lambda o: (
        f"Lighting/shadow consistency: {'INCONSISTENCY detected' if o.get('inconsistency_detected') else 'consistent across scene'}. "
        + (f"Details: {o.get('details', '')}" if o.get("details") else "")
        + (f" Flags: {'; '.join(o.get('flags', []))}" if o.get("flags") else "")
    ),
    # ── Metadata tools (Agent 5) ─────────────────────────────────────
    "exif_extract": lambda o: (
        f"File: {o.get('file_name', 'unknown')} ({o.get('file_size_human', '')}) · {o.get('mime_type', '')}. "
        + (
            f"Device: {o.get('device_model', o.get('camera_make', '') + ' ' + o.get('camera_model', '')).strip()}. "
            if o.get("device_model") or o.get("camera_make")
            else "Device: not recorded. "
        )
        + (
            f"Captured: {o.get('datetime_original', '')}. "
            if o.get("datetime_original")
            else "Capture time: not in EXIF. "
        )
        + (
            f"Modified: {o.get('datetime_modified', '')}. "
            if o.get("datetime_modified")
            else ""
        )
        + (f"Software: {o.get('software', '')}. " if o.get("software") else "")
        + (
            f"Dimensions: {o.get('image_dimensions', '')}. "
            if o.get("image_dimensions")
            else ""
        )
        + f"GPS: {'Present' if o.get('gps_coordinates') else 'Absent'}. "
        + f"{o.get('total_fields_extracted', 0)} EXIF field(s) extracted. "
        + (
            f"Missing mandatory fields: {', '.join(str(f) for f in o.get('absent_mandatory_fields', [])[:5])}."
            if o.get("absent_mandatory_fields")
            else (
                o.get("file_format_note")
                or "All mandatory EXIF fields present."
            )
        )
    ),
    "gps_timezone_validate": lambda o: (
        "No GPS coordinates embedded — location origin cannot be verified from metadata."
        if o.get("plausible") is None
        and any(
            "no gps" in str(i).lower() or "no gps data" in str(i).lower()
            for i in o.get("issues", [])
        )
        else (
            "No timestamp in EXIF — GPS-timezone cross-validation not possible."
            if o.get("plausible") is None
            and any("timestamp" in str(i).lower() for i in o.get("issues", []))
            else (
                "GPS-timezone is INCONSISTENT — "
                + "; ".join(o.get("issues", ["Unknown issue"]))
                if o.get("plausible") is False
                else f"GPS-timestamp timezone cross-validation passed. Timezone: {o.get('timezone', 'N/A')}."
            )
        )
    ),
    "steganography_scan": lambda o: (
        f"LSB steganography scan: {'HIDDEN DATA SUSPECTED' if o.get('stego_suspected') else 'no hidden data found'}. "
        f"LSB deviation from random: {o.get('lsb_statistics', {}).get('average_deviation', 0):.4f}."
    ),
    "file_structure_analysis": lambda o: (
        f"File structure: header {'valid' if o.get('header_valid') else 'INVALID'}, "
        f"trailer {'valid' if o.get('trailer_valid', True) else 'INVALID'}, "
        f"appended data: {'YES — ' + str(o.get('file_size', 0)) + ' bytes' if o.get('has_appended_data') else 'none'}. "
        f"Anomalies: {len(o.get('anomalies', []))} — {'; '.join(o.get('anomalies', [])) or 'none'}."
    ),
    "hex_signature_scan": lambda o: (
        f"Hex signature scan {'detected editing software: ' + ', '.join(o.get('software_signatures', [])) if o.get('editing_software_detected') else 'found no editing software signatures'} "
        f"across {o.get('bytes_scanned', 0):,} bytes."
    ),
    "timestamp_analysis": lambda o: (
        f"Timestamp cross-check found {len(o.get('inconsistencies', []))} inconsistency(ies). "
        + (
            f"Issues: {'; '.join(o.get('inconsistencies', []))}"
            if o.get("inconsistencies")
            else "All timestamps are consistent."
        )
    ),
    "metadata_anomaly_score": lambda o: (
        f"ML anomaly score: {o.get('anomaly_score', 0):.3f} "
        + (
            "(ANOMALOUS). "
            if o.get("is_anomalous")
            else "(within normal range). "
        )
        + (
            "Anomalous fields: " + ", ".join(o.get("anomalous_fields", [])[:5])
            if o.get("anomalous_fields")
            else ""
        )
    ),
    "device_fingerprint_db": lambda o: (
        f"Device fingerprint: {o.get('camera_make', 'Unknown')} {o.get('camera_model', '')}. "
        f"{'SUSPICIOUS — ' + '; '.join(o.get('inconsistencies', [])) if o.get('exif_fingerprint_suspicious') else 'PRNU pattern consistent with declared device.'}. "
        f"PRNU variance: {o.get('prnu_variance', 0):.3f}."
    ),
    # ── OCR tools ────────────────────────────────────────────────────
    "extract_evidence_text": lambda o: (
        "OCR extracted " + str(o.get("word_count", 0)) + " word(s) "
        "via " + str(o.get("method", "OCR")) + " "
        "(confidence: "
        + f"{o.get('confidence', 0):.0%}"
        + "). "
        + (
            "Preview: '" + str(o.get("full_text", ""))[:120] + "...'"
            if o.get("full_text")
            else "No text content detected."
        )
    ),
    "extract_text_from_image": lambda o: (
        "Tesseract OCR extracted "
        + str(o.get("word_count", 0))
        + " word(s). "
        + (
            "Preview: '"
            + str(o.get("text", o.get("full_text", "")))[:100]
            + "...'"
            if o.get("text") or o.get("full_text")
            else "No visible text found."
        )
    ),
    # ── MediaInfo tools ───────────────────────────────────────────────
    "mediainfo_profile": lambda o: (
        "MediaInfo profiled: "
        + str(o.get("format", "unknown"))
        + " / "
        + str(o.get("video_codec", o.get("codec", "unknown")))
        + ". Forensic flags: "
        + str(len(o.get("forensic_flags", [])))
        + (
            " — " + "; ".join(o.get("forensic_flags", []))[:200]
            if o.get("forensic_flags")
            else " — none detected."
        )
    ),
    "av_file_identity": lambda o: (
        "AV pre-screen: "
        + str(o.get("format", "unknown"))
        + " / "
        + str(o.get("primary_video_codec", o.get("codec", "unknown")))
        + " "
        + str(o.get("duration_seconds", "?"))
        + "s "
        + str(o.get("resolution", ""))
        + ". "
        + (
            "HIGH-SEVERITY FLAGS: "
            + ", ".join(o.get("high_severity_flags", []))
            if o.get("high_severity_flags")
            else "No high-severity flags."
        )
    ),
    # ── Audio tools (Agent 2) ───────────────────────────────────────────────
    "speaker_diarize": lambda o: (
        f"Speaker diarization: {o.get('speaker_count', o.get('num_speakers', 0))} speaker(s) identified, "
        f"{len(o.get('segments', []))} segment(s). "
        f"Backend: {o.get('backend', 'unknown')}."
    ),
    "anti_spoofing_detect": lambda o: (
        f"Anti-spoofing: {'SYNTHETIC/REPLAYED speech detected' if o.get('spoofing_detected', o.get('is_spoofed')) else 'speech appears genuine'}. "
        f"Synthetic probability: {o.get('synthetic_probability', o.get('spoof_score', 0)):.3f}. "
        f"Backend: {o.get('backend', 'unknown')}."
    ),
    "prosody_analyze": lambda o: (
        f"Prosody analysis: F0={o.get('f0_mean_hz', 0):.1f}Hz, "
        f"jitter={o.get('jitter_local', 0):.5f}, shimmer={o.get('shimmer_local', 0):.5f}, "
        f"HNR={o.get('hnr_db', 0):.1f}dB. "
        + (
            "PROSODY ANOMALY DETECTED."
            if o.get("prosody_anomaly_detected")
            else "Prosody within normal range."
        )
    ),
    # ── Video tools (Agent 4) ─────────────────────────────────────────
    "optical_flow_analysis": lambda o: (
        f"Optical flow: {o.get('anomaly_frame_count', o.get('num_anomaly_frames', 0))} anomalous frame(s). "
        f"Mean magnitude: {o.get('mean_flow_magnitude', 0):.3f}. "
        + (
            "Temporal discontinuity detected."
            if o.get("discontinuity_detected")
            else "Flow is temporally consistent."
        )
    ),
    "face_swap_detection": lambda o: (
        f"Face-swap: {o.get('faces_detected', 0)} face(s) analyzed. "
        + (
            "Face-swap event detected."
            if o.get("face_swap_detected")
            else "No face-swap artifacts found."
        )
        + f" Max embedding distance: {o.get('max_distance', 0):.3f}."
    ),
    # ── Gemini vision tools (Agents 1, 3, 5 deep pass) ───────────────
    "gemini_identify_content": lambda o: (
        f"Gemini Vision Error: {o.get('error')}."
        if o.get("error")
        else f"Gemini Vision content identification: {o.get('gemini_content_type', o.get('file_type_assessment', 'unknown type'))}. "
        f"Scene: {str(o.get('gemini_scene', o.get('content_description', '')))[:150]}. "
        + (
            f"Manipulation signals: {'; '.join(o.get('gemini_manipulation_signals', o.get('manipulation_signals', [])))[:200]}."
            if o.get("gemini_manipulation_signals")
            or o.get("manipulation_signals")
            else "No manipulation signals identified."
        )
    ),
    "gemini_cross_validate_manipulation": lambda o: (
        f"Gemini Vision Error: {o.get('error')}."
        if o.get("error")
        else f"Gemini cross-validation: {str(o.get('gemini_authenticity_assessment', o.get('content_description', '')))[:200]}. "
        + (
            f"Additional anomalies: {'; '.join(str(s) for s in o.get('gemini_additional_anomalies', o.get('manipulation_signals', [])))[:200]}."
            if o.get("gemini_additional_anomalies")
            or o.get("manipulation_signals")
            else "No additional anomalies identified."
        )
    ),
    "gemini_object_scene_analysis": lambda o: (
        f"Gemini Vision Error: {o.get('error')}."
        if o.get("error")
        else f"Gemini object/scene analysis: {str(o.get('gemini_scene_coherence', o.get('content_description', '')))[:200]}. "
        f"Validated objects: {', '.join(str(x) for x in o.get('gemini_validated_objects', o.get('detected_objects', [])))[:150] or 'none identified'}. "
        + (
            f"Compositing signals: {'; '.join(str(s) for s in o.get('gemini_compositing_signals', o.get('manipulation_signals', [])))[:200]}."
            if o.get("gemini_compositing_signals")
            or o.get("manipulation_signals")
            else "No compositing signals detected."
        )
    ),
    "gemini_metadata_visual_consistency": lambda o: (
        f"Gemini Vision Error: {o.get('error')}."
        if o.get("error")
        else f"Gemini metadata-visual consistency: {str(o.get('gemini_metadata_verdict', o.get('content_description', '')))[:200]}. "
        + (
            f"Provenance flags: {'; '.join(str(s) for s in o.get('gemini_provenance_flags', o.get('manipulation_signals', [])))[:200]}."
            if o.get("gemini_provenance_flags") or o.get("manipulation_signals")
            else "No provenance flags raised."
        )
    ),
    "gemini_deep_forensic": lambda o: (
        f"Gemini Vision Error: {o.get('error')}."
        if o.get("error")
        else (
            lambda ctype=(o.get("gemini_content_type", o.get("file_type_assessment", "")) or "unidentified content"), narrative=(str(o.get("gemini_narrative", o.get("content_description", ""))) or "Visual analysis complete."), objects=o.get("gemini_detected_objects", o.get("gemini_validated_objects", o.get("detected_objects", []))), texts=o.get("gemini_extracted_text", []), verdict=o.get("gemini_verdict", ""), meta_consistency=str(o.get("gemini_metadata_consistency", "")), iface=o.get("gemini_interface", ""), signals=list(o.get("gemini_manipulation_signals") or o.get("manipulation_signals") or []): (
                "Gemini deep forensic complete. "
                + f"Content: {ctype}. "
                + (f"Interface/UI: {iface}. " if iface else "")
                + (f"Scene: {narrative[:400]}. " if narrative else "")
                + (
                    f"Objects/subjects detected: {', '.join(str(x) for x in objects[:12])}. "
                    if objects
                    else "No specific objects identified. "
                )
                + (
                    f"Text extracted from image ({len(texts)} item(s)): {' | '.join(str(t) for t in texts[:8])}. "
                    if texts
                    else "No text found in image. "
                )
                + (f"Authenticity verdict: {verdict}. " if verdict else "")
                + (
                    f"Metadata vs visual: {meta_consistency[:200]}. "
                    if meta_consistency
                    else ""
                )
                + (
                    f"Manipulation signals: {'; '.join(str(s) for s in signals[:6])}."
                    if signals
                    else "No manipulation signals detected."
                )
            )
        )()
    ),
    "prnu_analysis": lambda o: (
        o.get(
            "file_format_note",
            "PRNU camera fingerprint analysis not applicable for this file type.",
        )
        if o.get("prnu_not_applicable")
        else (
            f"PRNU camera sensor fingerprint: {o.get('prnu_verdict', 'INCONCLUSIVE')}. "
            f"Mean block correlation: {o.get('mean_block_correlation', 0):.4f}, "
            f"min: {o.get('min_block_correlation', 0):.4f}, "
            f"noise variance CV: {o.get('noise_variance_cv', 0):.4f}. "
            f"{o.get('outlier_block_count', 0)} of {o.get('total_blocks', 0)} block(s) inconsistent. "
            + (
                "MULTI-SOURCE SENSOR DETECTED — possible splice/compositing."
                if o.get("inconsistent")
                else "Single camera source confirmed."
            )
        )
    ),
    "cfa_demosaicing": lambda o: (
        f"CFA demosaicing pattern: {o.get('cfa_verdict', 'INCONCLUSIVE')}. "
        f"Inconsistency ratio: {o.get('inconsistency_ratio', 0):.4f}, "
        f"{o.get('outlier_block_count', 0)} outlier block(s) of {o.get('total_blocks_analyzed', 0)}. "
        f"R/G corr std: {o.get('rg_correlation_std', 0):.4f}, G/B corr std: {o.get('gb_correlation_std', 0):.4f}. "
        + (
            "CFA INCONSISTENCY — region may originate from a different sensor pipeline or AI generation."
            if o.get("inconsistent")
            else "CFA pattern internally consistent — single sensor pipeline."
        )
    ),
    "voice_clone_detect": lambda o: (
        f"Voice clone detection: {o.get('verdict', 'UNKNOWN')}. "
        f"Synthetic probability: {o.get('synthetic_probability', 0):.3f}. "
        f"Spectral flatness: {o.get('spectral_flatness', 0):.4f}, "
        f"pitch stability (ZCR std): {o.get('pitch_stability_zcr_std', 0):.4f}, "
        f"energy CV: {o.get('energy_coefficient_of_variation', 0):.3f}. "
        + (
            f"Flags: {'; '.join(o.get('flags', []))}"
            if o.get("flags")
            else "No synthetic speech indicators detected."
        )
    ),
    "enf_analysis": lambda o: (
        f"ENF analysis: {o.get('verdict', 'NO_ENF_SIGNAL')}. "
        f"Grid standard: {o.get('grid_standard', 'unknown')} ({o.get('enf_frequency_hz', '?')} Hz). "
        f"Consistency score: {o.get('enf_consistency_score', 0):.4f}. "
        f"Splice candidate points: {o.get('splice_candidate_points', 0)}. "
        f"Duration analyzed: {o.get('duration_analyzed_s', '?')}s."
        if o.get("enf_detected")
        else f"ENF analysis: {o.get('verdict', 'NO_ENF_SIGNAL')}. "
        + (o.get("note", "No ENF signal present."))
    ),
    "object_text_ocr": lambda o: (
        f"Object OCR: text {'found' if o.get('text_found') else 'not found'} "
        f"in {o.get('regions_analyzed', 0)} region(s), {o.get('total_words', 0)} word(s) total. "
        + (
            f"Preview: '{o.get('combined_text_preview', '')[:200]}'"
            if o.get("text_found")
            else "No legible text detected."
        )
    ),
    "document_authenticity": lambda o: (
        f"Document authenticity: {o.get('verdict', 'UNKNOWN')} "
        f"(forgery score {o.get('forgery_score', 0):.3f}). "
        f"Font inconsistency CV: {o.get('font_inconsistency_cv', 0):.4f}, "
        f"frequency peaks: {o.get('frequency_domain_peaks', 0)}. "
        + (
            f"Flags: {'; '.join(o.get('flags', []))}"
            if o.get("flags")
            else "No forgery indicators detected."
        )
    ),
    "c2pa_verify": lambda o: (
        f"C2PA Content Credentials: {o.get('verdict', 'UNKNOWN')}. "
        + ("XMP C2PA present. " if o.get("xmp_c2pa_found") else "")
        + ("JUMBF manifest present. " if o.get("jumbf_present") else "")
        + (o.get("forensic_note", "") if o.get("forensic_note") else "")
    ),
    "thumbnail_mismatch": lambda o: (
        f"Thumbnail mismatch: {o.get('verdict', 'NO_THUMBNAIL')}. "
        + (
            f"MAD={o.get('mean_absolute_difference', 0):.1f}, "
            f"Hamming={o.get('phash_hamming_distance', 'N/A')}. "
            if o.get("thumbnail_present")
            else ""
        )
        + (o.get("forensic_note", "") if o.get("forensic_note") else "")
    ),
    "ela_anomaly_classify": lambda o: (
        o.get(
            "ela_limitation_note",
            "ELA block classification not applicable for this file format.",
        )
        if o.get("ela_not_applicable")
        else f"ELA anomaly classification: {o.get('anomaly_block_count', o.get('num_anomaly_regions', 0))} "
        f"anomalous block(s) out of {o.get('total_blocks', '?')} total. "
        f"ELA mean: {o.get('ela_mean', 0):.3f}, max deviation: {o.get('max_anomaly', 0)}. "
        + (
            "Anomaly detected — possible manipulation."
            if o.get("anomaly_detected")
            else "No significant anomaly blocks."
        )
    ),
    "deepfake_frequency_check": lambda o: (
        o.get(
            "limitation_note",
            "GAN/deepfake frequency analysis not applicable for this file format.",
        )
        if o.get("gan_not_applicable")
        else f"GAN/deepfake frequency check: anomaly score {o.get('anomaly_score', 0):.3f}, "
        f"high-frequency ratio {o.get('high_freq_ratio', 0):.4f}. "
        + (
            "GAN-style frequency artifacts detected — possible synthetic image origin."
            if o.get("gan_artifact_detected")
            else "Frequency distribution appears natural — no GAN artifacts detected."
        )
    ),
    "roi_extract": lambda o: (
        f"ROI extraction: bounding box {o.get('bounding_box', {})}. "
        f"Region hash: {str(o.get('roi_hash', o.get('sha256', '')))[:16]}{'...' if o.get('roi_hash') or o.get('sha256') else 'not computed'}."
    ),
    "perceptual_hash": lambda o: (
        f"Perceptual hash (pHash): {o.get('phash', o.get('hash_value', 'not computed'))}. "
        + (
            f"Hamming distance from reference: {o.get('hamming_distance')}."
            if "hamming_distance" in o
            else "No reference hash comparison performed."
        )
    ),
    "analyze_image_content": lambda o: (
        f"CLIP semantic analysis: image identified as '{o.get('image_type', o.get('top_match', 'unknown'))}' "
        f"at {o.get('confidence', o.get('top_confidence', 0)):.0%} confidence"
        + (
            f" — context: {str(o.get('semantic_context', ''))[:120]}."
            if o.get("semantic_context")
            else ". "
        )
        + (
            "CONCERN FLAG raised — content may be sensitive or anomalous."
            if o.get("concern_flag")
            else "No concern flags raised."
        )
    ),
    "sensor_db_query": lambda o: (
        f"Sensor/PRNU analysis: camera {o.get('camera_make', 'Unknown')} {o.get('camera_model', '')} "
        f"classified as {o.get('sensor_class', 'unknown')} "
        f"(PRNU variance {o.get('prnu_variance', 0):.4f}, std {o.get('prnu_block_std', 0):.4f}). "
        + (
            "Inconsistent noise profile — possible regional insertion."
            if o.get("inconsistent_noise_profile")
            else "Sensor noise profile is internally consistent."
        )
    ),
    "audio_splice_detect": lambda o: (
        f"Audio splice detection: {o.get('splice_count', len(o.get('splice_points', [])))} splice point(s) found. "
        + (
            "Splicing detected — audio may have been cut and re-joined."
            if o.get("splice_detected")
            else "No splice points detected — audio appears continuous."
        )
    ),
    "background_noise_analysis": lambda o: (
        f"Background noise consistency: {o.get('inconsistency_count', 0)} segment shift(s) detected "
        f"across {o.get('segment_count', '?')} segment(s). "
        + (
            "INCONSISTENT background noise — possible audio splice or re-recording."
            if o.get("inconsistency_detected")
            else "Background noise is consistent throughout recording."
        )
    ),
    "codec_fingerprinting": lambda o: (
        f"Codec fingerprint: {o.get('codec', o.get('audio_codec', 'unknown'))}, "
        f"sample rate {o.get('sample_rate', '?')}Hz, channels {o.get('channels', '?')}. "
        + (
            f"Encoding chain: {o.get('encoding_chain', o.get('encoding_history', ''))}. "
            if o.get("encoding_chain") or o.get("encoding_history")
            else "No multi-generation encoding detected. "
        )
        + (
            f"Duration: {o.get('duration_seconds', o.get('duration', '?'))}s."
            if o.get("duration_seconds") or o.get("duration")
            else ""
        )
    ),
    "audio_visual_sync": lambda o: (
        f"A/V sync: offset {o.get('av_offset_ms', o.get('sync_offset_ms', 0)):.1f}ms. "
        + (
            "SYNC DRIFT DETECTED — audio and video timestamps diverge."
            if o.get("sync_drift_detected", o.get("desync_detected"))
            else "Audio-visual sync is within acceptable tolerance."
        )
    ),
    "frame_extraction": lambda o: (
        f"Frame extraction: {o.get('frame_count', 0)} frame(s) extracted "
        f"(frames {o.get('start_frame', '?')}-{o.get('end_frame', '?')})."
    ),
    "frame_consistency_analysis": lambda o: (
        f"Frame consistency: {o.get('inconsistent_frame_count', 0)} inconsistent frame(s) "
        f"out of {o.get('total_frames', '?')} analyzed. "
        + (
            "Frame inconsistency detected — possible splice or compositing."
            if o.get("inconsistency_detected")
            else "Frames are visually consistent across the window."
        )
    ),
    "rolling_shutter_validation": lambda o: (
        f"Rolling shutter: {'VIOLATION detected — inconsistent scanline skew.' if o.get('violation_detected') else 'consistent with claimed device characteristics.'} "
        + (f"Details: {o.get('details', '')}" if o.get("details") else "")
    ),
    "video_metadata": lambda o: (
        f"Video metadata: codec {o.get('codec', 'unknown')}, "
        f"{o.get('fps', 0):.1f}fps, {o.get('resolution', '?')}, "
        f"duration {o.get('duration', '?')}s. "
        + (
            f"Encoding tool: {o.get('encoding_tool', '')}."
            if o.get("encoding_tool")
            else "No encoding tool recorded in metadata."
        )
    ),
    "anomaly_classification": lambda o: (
        f"Anomaly classification result: {o.get('classification', 'INCONCLUSIVE')}. "
        + (
            f"Details: {o.get('note', '')}"
            if o.get("note")
            else "No additional detail available."
        )
    ),
    "extract_deep_metadata": lambda o: (
        f"Deep metadata extraction: {o.get('total_fields', o.get('field_count', 0))} field(s) extracted. "
        + (
            f"MakerNotes: {o.get('makernotes_summary', 'none present')}. "
            if o.get("makernotes_summary")
            else "No MakerNotes extracted. "
        )
        + (
            f"XMP data: {str(o.get('xmp_summary', ''))[:100]}."
            if o.get("xmp_summary")
            else "No XMP data."
        )
    ),
    "get_physical_address": lambda o: (
        f"GPS reverse geocoding: {o.get('address', o.get('formatted_address', 'no address resolved'))}. "
        + (
            f"Coordinates: {o.get('latitude', '?')}, {o.get('longitude', '?')}."
            if o.get("latitude")
            else "No GPS coordinates available."
        )
    ),
}


def _flag_list(o: dict[str, Any]) -> str:
    flags = o.get("flags") or o.get("anomalies") or o.get("software_signatures") or []
    if not flags:
        return "No specific flags reported."
    return "Flags: " + "; ".join(str(x) for x in flags[:6]) + "."


_TOOL_INTERPRETERS.update(
    {
        # Agent 1 neural image tools.
        "neural_ela": _TOOL_INTERPRETERS["ela_full_image"],
        "noiseprint_cluster": _TOOL_INTERPRETERS["noise_fingerprint"],
        "neural_splicing": lambda o: (
            f"Neural splicing analysis {'found localized composition evidence' if o.get('splicing_detected') or o.get('manipulation_detected') else 'found no localized splice evidence'}. "
            f"Regions flagged: {len(o.get('forgery_regions', o.get('anomaly_regions', [])))}. "
            f"Score: {o.get('confidence', o.get('anomaly_score', 0)):.3f}."
        ),
        "neural_copy_move": lambda o: (
            f"Copy-move neural ensemble {'found duplicated image content' if o.get('copy_move_detected') else 'found no duplicated regions above threshold'}. "
            f"Candidate matches: {o.get('match_count', o.get('num_matches', len(o.get('matches', []))))}. "
            f"Score: {o.get('confidence', 0):.3f}."
        ),
        "diffusion_artifact_detector": lambda o: (
            f"Diffusion/synthetic-media detector {'flagged AI-generation artifacts' if o.get('is_ai_generated') or o.get('diffusion_detected') else 'did not find a strong AI-generation signature'}. "
            f"Probability/score: {o.get('diffusion_probability', o.get('ai_probability', o.get('confidence', 0))):.3f}. "
            + _flag_list(o)
        ),
        "f3_net_frequency": _TOOL_INTERPRETERS["deepfake_frequency_check"],
        "anomaly_tracer": lambda o: (
            f"Universal anomaly tracing {'localized suspicious manipulation regions' if o.get('manipulation_detected') or o.get('anomaly_regions') else 'found no stable localized anomaly map'}. "
            f"Regions: {len(o.get('anomaly_regions', []))}; score: {o.get('confidence', o.get('anomaly_score', 0)):.3f}."
        ),
        "neural_fingerprint": lambda o: (
            f"Neural perceptual fingerprint generated for provenance comparison. "
            f"Top similarity: {o.get('top_similarity', o.get('similarity', o.get('confidence', 0))):.3f}. "
            f"{'Similar prior media was found.' if o.get('match_found') else 'No high-confidence prior match was reported.'}"
        ),

        # Agent 2 refined audio tools.
        "neural_prosody": lambda o: (
            f"Neural prosody screen {'found acoustic irregularities consistent with synthetic or edited speech' if o.get('prosody_anomaly_detected') or o.get('anomaly_detected') else 'found no strong acoustic prosody irregularity'}. "
            f"Score: {o.get('confidence', o.get('anomaly_score', 0)):.3f}. "
            + _flag_list(o)
        ),
        "audio_gen_signature": lambda o: (
            f"Generative-audio signature scan {'flagged TTS/vocoder-like spectral traces' if o.get('synthetic_detected') or o.get('is_synthetic') or o.get('anomaly_detected') else 'found no strong TTS/vocoder signature'}. "
            f"Score: {o.get('confidence', o.get('synthetic_probability', o.get('anomaly_score', 0))):.3f}. "
            + _flag_list(o)
        ),
        "voice_clone_deep_ensemble": _TOOL_INTERPRETERS["voice_clone_detect"],
        "anti_spoofing_deep_ensemble": _TOOL_INTERPRETERS["anti_spoofing_detect"],

        # Agent 3 object/context tools.
        "vector_contraband_search": lambda o: (
            f"Threat/contraband vector search top match: {o.get('top_match', 'none')} "
            f"({o.get('confidence', o.get('top_confidence', 0)):.0%}). "
            + ("Potential threat item flagged." if o.get("concern_flag") else "No threat/contraband match above concern threshold.")
        ),
        "lighting_correlation_initial": lambda o: (
            f"Initial lighting correlation {'flagged possible compositing' if o.get('inconsistency_detected') or o.get('lighting_consistent') is False else 'did not find a stable lighting mismatch'}. "
            f"Score: {o.get('confidence', o.get('consistency_score', 0)):.3f}. "
            + (str(o.get("note", ""))[:160] if o.get("note") else "")
        ),

        # Agent 4 video tools.
        "vfi_error_map": lambda o: (
            f"Video interpolation/motion error map {'flagged synthetic or interpolated motion' if o.get('vfi_artifact_detected') or o.get('inconsistency_detected') else 'found no strong interpolation artifact'}. "
            f"Frames/regions flagged: {o.get('flagged_frame_count', o.get('inconsistent_frame_count', 0))}. "
            f"Score: {o.get('confidence', o.get('anomaly_score', 0)):.3f}."
        ),
        "thumbnail_coherence": lambda o: (
            f"Embedded thumbnail coherence {'flagged a preview/content mismatch' if o.get('thumbnail_mismatch') or o.get('mismatch_detected') else 'found no preview/content mismatch'}. "
            + (str(o.get("note", ""))[:180] if o.get("note") else "")
        ),
        "interframe_forgery_detector": lambda o: (
            f"Inter-frame forgery detector {'found temporal edit/discontinuity candidates' if o.get('forgery_detected') or o.get('inconsistency_detected') else 'found no strong temporal edit signature'}. "
            f"Candidate frames: {o.get('candidate_count', o.get('anomaly_frame_count', 0))}. "
            f"Score: {o.get('confidence', o.get('anomaly_score', 0)):.3f}."
        ),
        "compression_artifact_analysis": lambda o: (
            f"Video compression audit measured frame-size variation CV={o.get('coefficient_of_variation', 0):.4f} "
            f"across {o.get('frames_analyzed', 0)} sampled frames. "
            + ("Compression pattern is irregular." if o.get("inconsistency_detected") else "No strong codec discontinuity was detected.")
        ),

        # Agent 5 metadata/provenance tools.
        "compression_risk_audit": lambda o: (
            f"Compression/platform audit: {o.get('detected_platform') or 'no social/chat platform footprint detected'}. "
            f"Reliability impact: {o.get('forensic_reliability_impact', 'NONE')}. "
            f"Penalty factor: {o.get('compression_penalty', 1.0):.2f}."
        ),
        "exif_isolation_forest": lambda o: (
            f"EXIF outlier screen score {o.get('anomaly_score', 0):.3f}. "
            + ("Metadata fields are statistically unusual. " if o.get("is_anomalous") else "Metadata fields are within expected range. ")
            + _flag_list(o)
        ),
        "astro_grounding": lambda o: (
            f"Astronomical grounding {'found a sun/shadow/time mismatch' if o.get('inconsistency_detected') or o.get('plausible') is False else 'did not find a verifiable sun/shadow mismatch'}. "
            + (str(o.get("note", ""))[:180] if o.get("note") else "")
        ),
        "provenance_chain_verify": lambda o: (
            f"C2PA/provenance check: {o.get('verdict', 'NO_CONTENT_CREDENTIALS')}. "
            + ("Signed provenance was found. " if o.get("c2pa_present") or o.get("content_credentials_present") else "No signed content credentials were found; absence alone is not suspicious. ")
            + _flag_list(o)
        ),
        "c2pa_validator": lambda o: _TOOL_INTERPRETERS["provenance_chain_verify"](o),
        "camera_profile_match": lambda o: (
            f"Camera/device profile: {o.get('camera_make', o.get('make', 'Unknown'))} {o.get('camera_model', o.get('model', ''))}. "
            + ("Declared device profile is inconsistent with metadata. " if o.get("exif_fingerprint_suspicious") or o.get("profile_mismatch") else "No device-profile contradiction was detected. ")
            + _flag_list(o)
        ),
        "device_fingerprint_db": lambda o: _TOOL_INTERPRETERS["camera_profile_match"](o),
        "metadata_anomaly_scorer": lambda o: _TOOL_INTERPRETERS["metadata_anomaly_score"](o),
    }
)
