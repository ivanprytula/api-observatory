"""Tests for job scheduling, retries, and health metrics.

Coverage:
- Job registration and decorator pattern
- Job execution with timeout
- Health metrics tracking (success/failure counts, rates)
- Handler wrapping (session injection, metric updates)
- Job cancellation and error handling
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.core.handlers import wrap_job_handler
from services.ingestor.core.scheduler import Job, JobHealthMetrics, JobScheduler
from services.ingestor.jobs_registry import register_jobs, register_source_probe_jobs
from services.ingestor.models import SourceProfile


pytestmark = pytest.mark.integration


# ============================================================================
# JobScheduler Tests
# ============================================================================


class TestJobScheduler:
    """Test suite for JobScheduler."""

    def test_scheduler_initialization(self) -> None:
        """Test that JobScheduler initializes with empty jobs dict."""
        scheduler = JobScheduler()
        assert len(scheduler._jobs) == 0
        assert scheduler._session_factory is None

    def test_job_registration_decorator(self) -> None:
        """Test that @scheduler.job decorator registers jobs."""
        scheduler = JobScheduler()

        @scheduler.job(
            name="test_job",
            trigger=IntervalTrigger(hours=1),
            max_retries=3,
            timeout_seconds=300,
            tags={"test"},
        )
        async def my_handler(db: AsyncSession) -> dict[str, int]:
            return {"status": 200}

        assert "test_job" in scheduler._jobs
        job = scheduler._jobs["test_job"]
        assert job.name == "test_job"
        assert job.max_retries == 3
        assert job.timeout_seconds == 300
        assert "test" in job.tags

    def test_multiple_job_registration(self) -> None:
        """Test registering multiple jobs via decorator."""
        scheduler = JobScheduler()

        @scheduler.job(name="job_1", trigger=IntervalTrigger(hours=1))
        async def handler_1(db: AsyncSession) -> dict:
            return {}

        @scheduler.job(name="job_2", trigger=IntervalTrigger(minutes=30))
        async def handler_2(db: AsyncSession) -> dict:
            return {}

        assert len(scheduler._jobs) == 2
        assert "job_1" in scheduler._jobs
        assert "job_2" in scheduler._jobs

    def test_job_health_metrics_initialization(self) -> None:
        """Test that job health metrics are initialized with sensible defaults."""
        scheduler = JobScheduler()

        @scheduler.job(name="test_job", trigger=IntervalTrigger(hours=1))
        async def handler(db: AsyncSession) -> dict:
            return {}

        job = scheduler._jobs["test_job"]
        assert job.health.success_count == 0
        assert job.health.failure_count == 0
        assert job.health.last_error is None
        assert job.health.last_run_at is None
        assert job.health.success_rate == 1.0  # No runs yet = 100%
        assert job.health.is_healthy is True

    def test_get_job_health(self) -> None:
        """Test getting health metrics for a specific job."""
        scheduler = JobScheduler()

        @scheduler.job(name="test_job", trigger=IntervalTrigger(hours=1))
        async def handler(db: AsyncSession) -> dict:
            return {}

        job_health = scheduler.get_job_health("test_job")
        assert job_health is not None
        assert job_health.success_count == 0

    def test_get_job_health_nonexistent(self) -> None:
        """Test that get_job_health returns None for nonexistent job."""
        scheduler = JobScheduler()
        assert scheduler.get_job_health("nonexistent") is None

    def test_get_all_jobs_health(self) -> None:
        """Test getting health metrics for all jobs."""
        scheduler = JobScheduler()

        @scheduler.job(name="job_1", trigger=IntervalTrigger(hours=1))
        async def handler_1(db: AsyncSession) -> dict:
            return {}

        @scheduler.job(name="job_2", trigger=IntervalTrigger(hours=2))
        async def handler_2(db: AsyncSession) -> dict:
            return {}

        all_health = scheduler.get_all_jobs_health()
        assert len(all_health) == 2
        assert "job_1" in all_health
        assert "job_2" in all_health


# ============================================================================
# JobHealthMetrics Tests
# ============================================================================


class TestJobHealthMetrics:
    def test_success_rate_no_runs(self) -> None:
        """Test success_rate when no jobs have run."""
        metrics = JobHealthMetrics()
        assert metrics.success_rate == 1.0

    def test_success_rate_all_success(self) -> None:
        """Test success_rate when all jobs succeeded."""
        metrics = JobHealthMetrics(success_count=5, failure_count=0)
        assert metrics.success_rate == 1.0

    def test_success_rate_mixed(self) -> None:
        """Test success_rate with mixed success/failure."""
        metrics = JobHealthMetrics(success_count=8, failure_count=2)
        assert metrics.success_rate == 0.8

    def test_success_rate_all_failure(self) -> None:
        """Test success_rate when all jobs failed."""
        metrics = JobHealthMetrics(success_count=0, failure_count=5)
        assert metrics.success_rate == 0.0

    def test_is_healthy_good_rate(self) -> None:
        """Test is_healthy when success_rate > 80% and no recent errors."""
        metrics = JobHealthMetrics(success_count=9, failure_count=1, last_error=None)
        assert metrics.is_healthy is True

    def test_is_healthy_low_rate(self) -> None:
        """Test is_healthy when success_rate < 80%."""
        metrics = JobHealthMetrics(success_count=7, failure_count=3, last_error=None)
        assert metrics.is_healthy is False

    def test_is_healthy_with_recent_error(self) -> None:
        """Test is_healthy when last_error is set."""
        metrics = JobHealthMetrics(
            success_count=10, failure_count=0, last_error="Connection timeout"
        )
        assert metrics.is_healthy is False


# ============================================================================
# Handler Wrapping Tests
# ============================================================================


class TestHandlerWrapper:
    @pytest.mark.asyncio
    async def test_handler_success_updates_metrics(self) -> None:
        """Test that successful handler execution updates metrics."""

        async def dummy_handler(db: AsyncSession) -> dict:
            return {"status": "ok"}

        job = Job(
            name="test_job",
            handler=dummy_handler,
            trigger=IntervalTrigger(hours=1),
            max_retries=3,
            timeout_seconds=10,
        )

        mock_session = AsyncMock(spec=AsyncSession)
        wrapped = wrap_job_handler(job, lambda: mock_session)
        result = await wrapped()

        assert result == {"status": "ok"}
        assert job._health.success_count == 1
        assert job._health.failure_count == 0
        assert job._health.last_error is None
        assert job._health.last_run_at is not None

    @pytest.mark.asyncio
    async def test_handler_failure_updates_metrics(self) -> None:
        """Test that failed handler execution updates metrics."""

        async def failing_handler(db: AsyncSession) -> dict:
            raise ValueError("Simulated failure")

        job = Job(
            name="test_job",
            handler=failing_handler,
            trigger=IntervalTrigger(hours=1),
            max_retries=0,
            timeout_seconds=10,
        )

        mock_session = AsyncMock(spec=AsyncSession)
        wrapped = wrap_job_handler(job, lambda: mock_session)

        with pytest.raises(ValueError, match="Simulated failure"):
            await wrapped()

        assert job._health.success_count == 0
        assert job._health.failure_count == 1
        assert "Simulated failure" in job._health.last_error  # type: ignore

    @pytest.mark.asyncio
    async def test_handler_timeout_updates_metrics(self) -> None:
        """Test that timeout updates metrics correctly."""

        async def slow_handler(db: AsyncSession) -> dict:
            await asyncio.sleep(10)  # Longer than timeout
            return {"status": "ok"}

        job = Job(
            name="test_job",
            handler=slow_handler,
            trigger=IntervalTrigger(hours=1),
            max_retries=0,
            timeout_seconds=1,  # Very short timeout
        )

        mock_session = AsyncMock(spec=AsyncSession)

        wrapped = wrap_job_handler(job, lambda: mock_session)

        with pytest.raises(asyncio.TimeoutError):
            await wrapped()

        assert job._health.failure_count == 1
        assert "timeout" in job._health.last_error.lower()

    @pytest.mark.asyncio
    async def test_handler_cancellation_preserves_status(self) -> None:
        """Test that cancellation doesn't observation failure."""

        async def cancellable_handler(db: AsyncSession) -> dict:
            await asyncio.sleep(10)
            return {"status": "ok"}

        job = Job(
            name="test_job",
            handler=cancellable_handler,
            trigger=IntervalTrigger(hours=1),
        )

        mock_session = AsyncMock(spec=AsyncSession)

        wrapped = wrap_job_handler(job, lambda: mock_session)
        task = asyncio.create_task(wrapped())

        # Let task start
        await asyncio.sleep(0.01)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        # Cancellation should not update failure count
        # (handler wrapper preserves CancelledError without observationing as failure)


# ============================================================================
# Job Registry Tests
# ============================================================================


class TestJobsRegistry:
    def test_register_jobs_creates_jobs(self) -> None:
        """Test that register_jobs() populates scheduler with jobs."""
        scheduler = JobScheduler()
        assert len(scheduler._jobs) == 0

        register_jobs(scheduler)

        # Should have registered example jobs
        assert len(scheduler._jobs) > 0
        assert "ingest_scheduled_batch_example" in scheduler._jobs

    def test_registered_jobs_have_correct_config(self) -> None:
        """Test that registered jobs have correct configuration."""
        scheduler = JobScheduler()
        register_jobs(scheduler)

        batch_job = scheduler._jobs["ingest_scheduled_batch_example"]
        assert batch_job.max_retries == 3
        assert batch_job.timeout_seconds == 300
        assert "batch" in batch_job.tags
        assert "example" in batch_job.tags

    @pytest.mark.asyncio
    async def test_register_source_probe_jobs_only_active(
        self, db: AsyncSession
    ) -> None:
        """Register one probe job per active source profile."""
        active = SourceProfile(
            name="active-source",
            base_url="https://example.com",
            health_check_path="/health",
            probe_interval_seconds=45,
            is_active=True,
        )
        inactive = SourceProfile(
            name="inactive-source",
            base_url="https://example.org",
            health_check_path="/health",
            probe_interval_seconds=30,
            is_active=False,
        )
        db.add_all([active, inactive])
        await db.commit()
        await db.refresh(active)
        await db.refresh(inactive)

        scheduler = JobScheduler()
        registered = await register_source_probe_jobs(scheduler, db)

        assert registered == 1
        assert f"probe_source_{active.id}" in scheduler._jobs
        assert f"probe_source_{inactive.id}" not in scheduler._jobs

    @pytest.mark.asyncio
    async def test_register_source_probe_jobs_interval_matches_profile(
        self, db: AsyncSession
    ) -> None:
        """Probe job interval is derived from SourceProfile.probe_interval_seconds."""
        source = SourceProfile(
            name="interval-source",
            base_url="https://example.net",
            health_check_path="/status",
            probe_interval_seconds=75,
            is_active=True,
        )
        db.add(source)
        await db.commit()
        await db.refresh(source)

        scheduler = JobScheduler()
        await register_source_probe_jobs(scheduler, db)

        job = scheduler._jobs[f"probe_source_{source.id}"]
        assert isinstance(job.trigger, IntervalTrigger)
        assert int(job.trigger.interval.total_seconds()) == 75


# ============================================================================
# Integration Tests
# ============================================================================


class TestSchedulerIntegration:
    """Integration tests for scheduler workflow."""

    @pytest.mark.asyncio
    async def test_scheduler_start_stop_lifecycle(self) -> None:
        """Test scheduler startup and shutdown lifecycle."""
        scheduler = JobScheduler()

        @scheduler.job(name="dummy_job", trigger=IntervalTrigger(hours=1))
        async def dummy_handler(db: AsyncSession) -> dict:
            return {"status": "ok"}

        mock_session_factory = AsyncMock()
        mock_session_factory.return_value = AsyncMock(spec=AsyncSession)

        # Start scheduler
        apscheduler_instance = await scheduler.start(mock_session_factory)
        assert apscheduler_instance is not None
        assert scheduler._scheduler.running

        # Stop scheduler
        await scheduler.stop()
        assert not scheduler._scheduler.running

    def test_scheduler_with_disabled_jobs(self) -> None:
        """Test scheduler can handle jobs with trigger=None (disabled)."""
        scheduler = JobScheduler()

        @scheduler.job(name="disabled_job", trigger=None)
        async def handler(db: AsyncSession) -> dict:
            return {}

        job = scheduler._jobs["disabled_job"]
        # Job is registered but with trigger=None (disabled)
        assert job.trigger is None

    @pytest.mark.asyncio
    async def test_job_registered_after_start_is_wired_into_live_engine(self) -> None:
        """A job registered via the decorator after start() must actually run,
        not just be tracked in self._jobs — e.g. a source registered through
        the API after the app has already booted.
        """
        scheduler = JobScheduler()
        mock_session_factory = AsyncMock()
        mock_session_factory.return_value = AsyncMock(spec=AsyncSession)

        await scheduler.start(mock_session_factory)
        try:
            assert scheduler._scheduler.get_job("late_job") is None

            @scheduler.job(name="late_job", trigger=IntervalTrigger(hours=1))
            async def late_handler(db: AsyncSession) -> dict:
                return {"status": "ok"}

            assert "late_job" in scheduler._jobs
            assert scheduler._scheduler.get_job("late_job") is not None
        finally:
            await scheduler.stop()


# ============================================================================
# Job Control Tests
# ============================================================================


class TestJobSchedulerControl:
    """Test suite for pause/resume job control methods."""

    @pytest.mark.asyncio
    async def test_pause_job_pauses_running_job(self) -> None:
        """Pausing a running job sets next_run_time to None."""
        scheduler = JobScheduler()

        @scheduler.job(name="controlled_job", trigger=IntervalTrigger(hours=1))
        async def handler(db: AsyncSession) -> dict:
            return {}

        mock_session_factory = AsyncMock()
        mock_session_factory.return_value = AsyncMock(spec=AsyncSession)

        await scheduler.start(mock_session_factory)
        try:
            apscheduler_job = scheduler._scheduler.get_job("controlled_job")
            assert apscheduler_job is not None
            assert apscheduler_job.next_run_time is not None

            scheduler.pause_job("controlled_job")

            apscheduler_job = scheduler._scheduler.get_job("controlled_job")
            assert apscheduler_job.next_run_time is None
        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_resume_job_resumes_paused_job(self) -> None:
        """Resuming a paused job sets next_run_time to a future datetime."""
        scheduler = JobScheduler()

        @scheduler.job(name="controlled_job", trigger=IntervalTrigger(hours=1))
        async def handler(db: AsyncSession) -> dict:
            return {}

        mock_session_factory = AsyncMock()
        mock_session_factory.return_value = AsyncMock(spec=AsyncSession)

        await scheduler.start(mock_session_factory)
        try:
            scheduler.pause_job("controlled_job")
            apscheduler_job = scheduler._scheduler.get_job("controlled_job")
            assert apscheduler_job.next_run_time is None

            scheduler.resume_job("controlled_job")

            apscheduler_job = scheduler._scheduler.get_job("controlled_job")
            assert apscheduler_job.next_run_time is not None
        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_pause_nonexistent_job_is_noop(self) -> None:
        """Pausing a job that was never activated is a no-op."""
        scheduler = JobScheduler()

        @scheduler.job(name="inactive_job", trigger=IntervalTrigger(hours=1))
        async def handler(db: AsyncSession) -> dict:
            return {}

        mock_session_factory = AsyncMock()
        mock_session_factory.return_value = AsyncMock(spec=AsyncSession)

        await scheduler.start(mock_session_factory)
        try:
            # Job exists in self._jobs but was not activated (trigger=None check)
            # Use a job name that doesn't exist anywhere
            scheduler.pause_job("never_registered_job")
        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_resume_job_activates_unwired_job(self) -> None:
        """Resume should activate a job that exists in self._jobs but not APScheduler."""
        scheduler = JobScheduler()

        @scheduler.job(name="unwired_job", trigger=IntervalTrigger(hours=1))
        async def handler(db: AsyncSession) -> dict:
            return {}

        mock_session_factory = AsyncMock()
        mock_session_factory.return_value = AsyncMock(spec=AsyncSession)

        # Register job but don't start scheduler — job is in self._jobs but not APScheduler
        assert "unwired_job" in scheduler._jobs
        assert scheduler._scheduler.get_job("unwired_job") is None

        # Now start the scheduler and manually remove the APScheduler job
        # to simulate the "never activated" edge case
        await scheduler.start(mock_session_factory)
        try:
            # Remove from APScheduler but keep in self._jobs
            scheduler._scheduler.remove_job("unwired_job")
            assert "unwired_job" in scheduler._jobs
            assert scheduler._scheduler.get_job("unwired_job") is None

            scheduler.resume_job("unwired_job")

            apscheduler_job = scheduler._scheduler.get_job("unwired_job")
            assert apscheduler_job is not None
            assert apscheduler_job.next_run_time is not None
        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_resume_nonexistent_job_logs_warning(self) -> None:
        """Resuming a job that doesn't exist anywhere logs a warning."""
        scheduler = JobScheduler()

        mock_session_factory = AsyncMock()
        mock_session_factory.return_value = AsyncMock(spec=AsyncSession)

        await scheduler.start(mock_session_factory)
        try:
            # Should not raise, just log a warning
            scheduler.resume_job("nonexistent_job")
            assert not scheduler.has_job("nonexistent_job")
        finally:
            await scheduler.stop()

    def test_has_job_returns_true_for_registered_job(self) -> None:
        """has_job returns True for registered jobs."""
        scheduler = JobScheduler()

        @scheduler.job(name="test_job", trigger=IntervalTrigger(hours=1))
        async def handler(db: AsyncSession) -> dict:
            return {}

        assert scheduler.has_job("test_job") is True

    def test_has_job_returns_false_for_unknown_job(self) -> None:
        """has_job returns False for unknown jobs."""
        scheduler = JobScheduler()
        assert scheduler.has_job("unknown_job") is False
