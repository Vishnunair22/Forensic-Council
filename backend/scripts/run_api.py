"""
Run API Server Script
=====================

Starts the FastAPI server with uvicorn.
"""

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=os.getenv("RELOAD", "false").lower() == "true",
        log_level="info",
    )
