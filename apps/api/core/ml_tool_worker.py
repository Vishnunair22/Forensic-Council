"""
ML Tool Worker Mode Utilities
==============================

Provides common worker mode and warmup mode implementations for all ML tools.
This eliminates code duplication and ensures consistent behavior.

Usage in ML tool:
    from core.ml_tool_worker import run_worker_mode, run_warmup_mode

    def load_model():
        # Your model loading logic
        return model

    def run_inference(input_path, extra_args=None):
        # Your inference logic
        return result

    if __name__ == "__main__":
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--worker", action="store_true")
        parser.add_argument("--warmup", action="store_true")
        parser.add_argument("--input", type=str)
        args = parser.parse_args()

        if args.worker:
            run_worker_mode(run_inference)
        elif args.warmup:
            run_warmup_mode(load_model)
        elif args.input:
            result = run_inference(args.input)
            print(json.dumps(result))
"""

import json
import sys
import time
from collections.abc import Callable

from core.structured_logging import get_logger

logger = get_logger(__name__)


def run_worker_mode(
    inference_fn: Callable[[str, list | None], dict],
    model_loader: Callable | None = None,
):
    """
    Run persistent worker mode - reads JSON from stdin, writes JSON to stdout.

    Args:
        inference_fn: Function that takes (input_path, extra_args) and returns dict
        model_loader: Optional function to preload model (called once at startup)
    """
    # Preload model if provided
    if model_loader:
        try:
            logger.info("Loading model for worker mode...")
            model_loader()
            logger.info("Model loaded successfully")
        except Exception as e:
            logger.error("Failed to load model", error=str(e), exc_info=True)
            print(json.dumps({"error": f"Model load failed: {str(e)}", "available": False}))
            sys.exit(1)

    logger.info("Worker mode started, reading from stdin...")

    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
                input_path = request.get("input")
                extra_args = request.get("extra_args", [])

                if not input_path:
                    print(json.dumps({"error": "Missing 'input' field", "available": False}))
                    sys.stdout.flush()
                    continue

                # Run inference
                result = inference_fn(input_path, extra_args)
                print(json.dumps(result))
                sys.stdout.flush()

            except json.JSONDecodeError as e:
                logger.error("Invalid JSON from stdin", error=str(e))
                print(json.dumps({"error": f"Invalid JSON: {str(e)}", "available": False}))
                sys.stdout.flush()
            except Exception as e:
                logger.error("Inference failed", error=str(e), exc_info=True)
                print(json.dumps({"error": str(e), "available": False}))
                sys.stdout.flush()
    except KeyboardInterrupt:
        logger.info("Worker interrupted, shutting down...")
    except Exception as e:
        logger.critical("Worker crashed", error=str(e), exc_info=True)
        sys.exit(1)


def run_warmup_mode(model_loader: Callable, timeout: float = 60.0):
    """
    Run warmup mode - preload model into memory without inference.

    Args:
        model_loader: Function that loads the model
        timeout: Maximum time to wait for warmup (seconds)
    """
    start_time = time.time()

    try:
        logger.info("Starting model warmup...")
        model = model_loader()
        elapsed = time.time() - start_time

        if model is None:
            print(json.dumps({
                "status": "warmup_failed",
                "error": "Model loader returned None",
                "elapsed_seconds": round(elapsed, 2)
            }))
            sys.exit(1)

        logger.info(f"Model warmup completed in {elapsed:.1f}s")
        print(json.dumps({
            "status": "warmed_up",
            "elapsed_seconds": round(elapsed, 2),
            "model_type": type(model).__name__
        }))

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error("Model warmup failed", error=str(e), exc_info=True)
        print(json.dumps({
            "status": "warmup_failed",
            "error": str(e),
            "elapsed_seconds": round(elapsed, 2)
        }))
        sys.exit(1)
