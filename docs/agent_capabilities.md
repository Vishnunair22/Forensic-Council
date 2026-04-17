# Forensic Agent Capabilities (v1.3.0)

This document provides a definitive list of the diagnostic tools available to each specialist agent in the Forensic Council. Every tool includes a "Court Defensible" seal when running in its primary (ML-backed) mode.

## 1. Image Forensic Agent (Agent 1)
| Tool | Function | Court Defensible |
|------|----------|:----------------:|
| `ela_full_image` | Detects pixel-level compression inconsistencies. | âœ… |
| `roi_extract` | Extracts high-resolution crops for targeted analysis. | âœ… |
| `jpeg_ghost_detect` | Identifies regions with multiple JPEG compression saves. | âœ… |
| `ela_anomaly_classify` | ML categorization of ELA heatmap anomalies. | âœ… |
| `splicing_detect` | Detects SRM noise residual discontinuities. | âœ… |
| `noise_fingerprint` | PRNU sensor noise consistency for lossless images. | âœ… |
| `deepfake_frequency` | FFT-based GAN artifact detection. | âœ… |
| `copy_move_detect` | SIFT-based cloning and patch detection. | âœ… |
| `adversarial_check` | Detects perturbations designed to evade ML. | âœ… |
| `diffusion_detector` | Identifies Stable Diffusion / Midjourney hallmarks. | âœ… |

## 2. Audio Forensic Agent (Agent 2)
| Tool | Function | Court Defensible |
|------|----------|:----------------:|
| `speaker_diarization` | Establishes voice-count baseline and IDs speakers. | âœ… |
| `anti_spoofing` | Detects synthesized / replayed voice signals. | âœ… |
| `prosody_analysis` | Verifies natural rhythm, pitch, and cadence. | âœ… |
| `noise_analysis` | Checks background noise floor for splice events. | âœ… |
| `codec_fingerprint` | Identifies transcoding and re-encoding history. | âœ… |
| `audio_splice_detect` | Spectral flux analysis for edit point detection. | âœ… |
| `av_sync_verify` | Correlates audio events with video motion. | âœ… |
| `voice_clone_detect` | Detects ElevenLabs and VALL-E vocal artifacts. | âœ… |
| `enf_analysis` | Verifies time/location via Electrical Network Frequency. | âœ… |

## 3. Object-Scene Agent (Agent 3)
| Tool | Function | Court Defensible |
|------|----------|:----------------:|
| `object_detection` | YOLOv11 primary scene object identification. | âœ… |
| `secondary_classify` | CLIP-based refinement of low-confidence objects. | âœ… |
| `scale_validation` | Perspective and vanishing point convergence check. | âœ… |
| `lighting_check` | Inter-quadrant lighting/shadow consistency. | âœ… |
| `scene_incongruence` | Identifies objects out of place in the context. | âœ… |
| `contraband_scan` | Cross-references objects against restricted databases. | âœ… |

## 4. Video Forensic Agent (Agent 4)
| Tool | Function | Court Defensible |
|------|----------|:----------------:|
| `optical_flow` | Maps temporal anomalies and frame motion vectors. | âœ… |
| `frame_extraction` | Accurate frame retrieval for pixel-perfect audit. | âœ… |
| `frame_consistency` | Histogram and edge correlation across the stream. | âœ… |
| `face_swap_detect` | Haar-cascade + DeepFace landmark consistency. | âœ… |
| `video_metadata` | Probes container streams, codecs, and GOP structures. | âœ… |
| `forgery_detector` | Detects frame dropping and inter-frame interpolation. | âœ… |
| `liveness_check` | rPPG pulse extraction (Green-channel flux) from faces. | âœ… |
| `frequency_gan` | Spatio-temporal GAN artifact detection. | âœ… |
| `rolling_shutter` | Validates horizontal skew against device profiles. | âœ… |

## 5. Metadata Agent (Agent 5)
| Tool | Function | Court Defensible |
|------|----------|:----------------:|
| `exif_extract` | Comprehensive tag extraction (ExifTool backed). | âœ… |
| `anomaly_score` | ML scoring of metadata entropy and missing fields. | âœ… |
| `gps_timezone` | Validates location against claimed capture time. | âœ… |
| `steganography_scan` | LSB and DCT-coefficient hidden payload detection. | âœ… |
| `structure_audit` | Deep file structure and JUMBF segment audit. | âœ… |
| `hex_scan` | Hex-signature scanning for software artifacts. | âœ… |
| `hash_verify` | SHA-256 integrity verification against ledger. | âœ… |
| `astronomical_check` | Confirms sun elevation vs. claimed GPS/Time. | âœ… |
| `reverse_search` | Checks for prior appearance of evidence online. | âœ… |
| `c2pa_validator` | Verifies C2PA Content Credentials/Provenance. | âœ… |
| `ocr_text_extract` | Tesseract-backed evidence text extraction. | âœ… |

