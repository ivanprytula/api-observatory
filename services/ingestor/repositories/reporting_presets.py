"""Dashboard presets and export jobs."""

from services.ingestor.api_schemas.reporting import (
    DashboardPreset,
    ExportJob,
    ExportJobRequest,
)
from services.ingestor.constants import REPORTING_DEFAULT_EXPORT_FORMAT
from services.ingestor.repositories.reporting_utils import _now_utc_naive


def list_dashboard_presets() -> list[DashboardPreset]:
    """Return built-in dashboard presets for BI consumers."""
    return [
        DashboardPreset(
            preset_id="ops-scorecard",
            name="Operations Scorecard",
            description="Daily operational view for reliability engineering and on-call teams.",
            widgets=[
                "provider_uptime",
                "compatibility_trend",
                "breaking_drift_heatmap",
                "delivery_suppression_ratio",
            ],
        ),
        DashboardPreset(
            preset_id="exec-weekly-summary",
            name="Executive Weekly Summary",
            description="Weekly leadership dashboard focused on risk and cost-to-value trends.",
            widgets=[
                "error_budget_burn",
                "cohort_ranking",
                "cost_to_value_ratio",
                "top_recommendations",
            ],
        ),
    ]


def create_export_job(payload: ExportJobRequest) -> ExportJob:
    """Create a deterministic export job response for current BI slice."""
    created_at = _now_utc_naive()
    export_format = payload.export_format or REPORTING_DEFAULT_EXPORT_FORMAT

    return ExportJob(
        export_id=f"export-{int(created_at.timestamp())}",
        status="completed",
        preset_id=payload.preset_id,
        export_format=export_format,
        created_at=created_at,
        detail="Export generated from reporting read models.",
    )
