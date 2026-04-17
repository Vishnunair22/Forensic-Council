"""
Monitoring & Infrastructure Health
==================================

Lightweight observers for monitoring event loop health and forensic tool performance.
"""

import asyncio
import logging
import time
from typing import NoReturn

from core.structured_logging import get_logger

logger = get_logger(__name__)

class HeartbeatMonitor:
    """
    Monitors the asyncio event loop for stalls or long-running synchronous code.
    Essential for ensuring forensic analysis doesn't block critical WebSocket/API I/O.
    """
    
    def __init__(self, interval: float = 0.05, threshold: float = 0.1):
        """
        Initialize the monitor.
        
        Args:
            interval: How often to wake up and check loop time (seconds)
            threshold: Latency threshold over interval to trigger warning (seconds)
        """
        self.interval = interval
        self.threshold = threshold
        self._stop_event = asyncio.Event()

    async def start(self) -> NoReturn:
        """Start the heartbeat monitoring loop."""
        logger.info(
            "Starting event loop heartbeat sentinel",
            interval_ms=self.interval * 1000,
            threshold_ms=self.threshold * 1000
        )
        
        loop = asyncio.get_running_loop()
        
        while not self._stop_event.is_set():
            start_time = loop.time()
            
            # Yield control back to loop
            await asyncio.sleep(self.interval)
            
            # Measure actual elapsed time vs expected interval
            end_time = loop.time()
            actual_elapsed = end_time - start_time
            latency = actual_elapsed - self.interval
            
            if latency > self.threshold:
                logger.warning(
                    "Event loop stall detected",
                    latency_ms=round(latency * 1000, 2),
                    total_elapsed_ms=round(actual_elapsed * 1000, 2),
                    description="A task blocked the event loop longer than allowed by the threshold."
                )
    
    def stop(self) -> None:
        """Signal the monitor to stop."""
        self._stop_event.set()

async def start_monitoring(app_state: dict) -> None:
    """Initialize health monitoring as a background task in the app lifespan."""
    monitor = HeartbeatMonitor()
    app_state["heartbeat_monitor"] = monitor
    # Run as a background task
    asyncio.create_task(monitor.start())
