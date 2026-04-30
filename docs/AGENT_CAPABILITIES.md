# Forensic Agent Capabilities (v1.4.0)

This document provides a definitive list of the diagnostic tools available to each specialist agent in the Forensic Council. Every tool includes a "Court Defensible" seal when running in its primary (ML-backed) mode.

## 1. Image Forensic Agent (Agent 1)
| Tool | Function | Court Defensible |
|------|----------|:----------------:|
| `ela_full_image` | Detects pixel-level compression inconsistencies. | ✅ |
| `roi_extract` | Extracts high-resolution crops for targeted analysis. | ✅ |
| `jpeg_ghost_detect` | Identifies regions with multiple JPEG compression saves. | ✅ |
| `ela_anomaly_classify` | ML categorization of ELA heatmap anomalies. | ✅ |
| `splicing_detect` | Detects SRM noise residual discontinuities. | ✅ |
| `noise_fingerprint` | PRNU sensor noise consistency for lossless images. | ✅ |
| `deepfake_frequency` | FFT-based GAN artifact detection. | ✅ |
| `copy_move_detect` | SIFT-based cloning and patch detection. | ✅ |
| `adversarial_check` | Detects perturbations designed to evade ML. | ✅ |
| `diffusion_detector` | Identifies Stable Diffusion / Midjourney hallmarks. | ✅ |

## 2. Audio Forensic Agent (Agent 2)
| Tool | Function | Court Defensible |
|------|----------|:----------------:|
| `speaker_diarization` | Establishes voice-count baseline and IDs speakers. | ✅ |
| `anti_spoofing` | Detects synthesized / replayed voice signals. | ✅ |
| `prosody_analysis` | Verifies natural rhythm, pitch, and cadence. | ✅ |
| `noise_analysis` | Checks background noise floor for splice events. | ✅ |
| `codec_fingerprint` | Identifies transcoding and re-encoding history. | ✅ |
| `audio_splice_detect` | Spectral flux analysis for edit point detection. | ✅ |
| `av_sync_verify` | Correlates audio events with video motion. | ✅ |
| `voice_clone_detect` | Detects ElevenLabs and VALL-E vocal artifacts. | ✅ |
| `enf_analysis` | Verifies time/location via Electrical Network Frequency. | ✅ |

## 3. Object-Scene Agent (Agent 3)
| Tool | Function | Court Defensible |
|------|----------|:----------------:|
| `object_detection` | YOLOv11 primary scene object identification. | ✅ |
| `secondary_classify` | CLIP-based refinement of low-confidence objects. | ✅ |
| `scale_validation` | Perspective and vanishing point convergence check. | ✅ |
| `lighting_check` | Inter-quadrant lighting/shadow consistency. | ✅ |
| `scene_incongruence` | Identifies objects out of place in the context. | ✅ |
| `contraband_scan` | Cross-references objects against restricted databases. | ✅ |

## 4. Video Forensic Agent (Agent 4)
| Tool | Function | Court Defensible |
|------|----------|:----------------:|
| `optical_flow` | Maps temporal anomalies and frame motion vectors. | ✅ |
| `frame_extraction` | Accurate frame retrieval for pixel-perfect audit. | ✅ |
| `frame_consistency` | Histogram and edge correlation across the stream. | ✅ |
| `face_swap_detect` | Haar-cascade + DeepFace landmark consistency. | ✅ |
| `video_metadata` | Probes container streams, codecs, and GOP structures. | ✅ |
| `forgery_detector` | Detects frame dropping and inter-frame interpolation. | ✅ |
| `liveness_check` | rPPG pulse extraction (Green-channel flux) from faces. | ✅ |
| `frequency_gan` | Spatio-temporal GAN artifact detection. | ✅ |
| `rolling_shutter` | Validates horizontal skew against device profiles. | ✅ |

## 5. Metadata Agent (Agent 5)
| Tool | Function | Court Defensible |
|------|----------|:----------------:|
| `exif_extract` | Comprehensive tag extraction (ExifTool backed). | ✅ |
| `anomaly_score` | ML scoring of metadata entropy and missing fields. | ✅ |
| `gps_timezone` | Validates location against claimed capture time. | ✅ |
| `steganography_scan` | LSB and DCT-coefficient hidden payload detection. | ✅ |
| `structure_audit` | Deep file structure and JUMBF segment audit. | ✅ |
| `hex_scan` | Hex-signature scanning for software artifacts. | ✅ |
| `hash_verify` | SHA-256 integrity verification against ledger. | ✅ |
| `astronomical_check` | Confirms sun elevation vs. claimed GPS/Time. | ✅ |
| `reverse_search` | Checks for prior appearance of evidence online. | ✅ |
| `c2pa_validator` | Verifies C2PA Content Credentials/Provenance. | ✅ |
| `ocr_text_extract` | Tesseract-backed evidence text extraction. | ✅ |
