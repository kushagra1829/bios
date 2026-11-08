import threading
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from backend.app.db.session import SessionLocal
from backend.app.monitoring.engine import continuous_monitoring_engine

logger = logging.getLogger("bios.monitoring.scheduler")


class BackgroundMonitoringScheduler:
    """
    Lightweight background worker and cron scheduler for continuous analytics governance.
    Runs in a dedicated thread or separate process; safe for container and standalone execution.
    """

    def __init__(self, interval_seconds: int = 3600):
        self.interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_run: Optional[datetime] = None
        self._next_run: Optional[datetime] = None
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def next_run(self) -> Optional[datetime]:
        return self._next_run

    @property
    def last_run(self) -> Optional[datetime]:
        return self._last_run

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            logger.info("Scheduler already active.")
            return

        self._stop_event.clear()
        self._is_running = True
        self._next_run = datetime.now(timezone.utc) + timedelta(seconds=self.interval_seconds)
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="BIOS-GovernanceScheduler")
        self._thread.start()
        logger.info("Governance monitoring scheduler started (interval: %ss).", self.interval_seconds)

    def stop(self) -> None:
        self._stop_event.set()
        self._is_running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        logger.info("Governance monitoring scheduler stopped.")

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            # Wait for next scheduled run or stop signal
            if self._stop_event.wait(timeout=self.interval_seconds):
                break

            try:
                logger.info("Executing scheduled continuous governance evaluation...")
                self._last_run = datetime.now(timezone.utc)
                self._next_run = self._last_run + timedelta(seconds=self.interval_seconds)

                db = SessionLocal()
                try:
                    continuous_monitoring_engine.run_monitoring_job(
                        db=db,
                        job_type="FULL_CONTINUOUS_SCAN",
                        triggered_by="SCHEDULED_TIMER",
                    )
                finally:
                    db.close()
            except Exception as e:
                logger.error("Error during scheduled governance execution: %s", e, exc_info=True)

    def trigger_immediate(self, job_type: str = "FULL_CONTINUOUS_SCAN", actor: str = "MANUAL_TRIGGER") -> Dict[str, Any]:
        """Execute an immediate synchronous monitoring job."""
        db = SessionLocal()
        try:
            job = continuous_monitoring_engine.run_monitoring_job(
                db=db,
                job_type=job_type,
                triggered_by=actor,
            )
            self._last_run = datetime.now(timezone.utc)
            return {
                "job_id": job.job_id,
                "job_type": job.job_type,
                "status": job.status,
                "records_processed": job.records_processed,
                "findings_generated": job.findings_generated,
                "findings_resolved": job.findings_resolved,
                "duration_ms": job.duration_ms,
                "errors": job.errors,
            }
        finally:
            db.close()


# Global scheduler instance
monitoring_scheduler = BackgroundMonitoringScheduler()

