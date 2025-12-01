"""
LangGraph Workflow: Job Intelligence Pipeline

Orchestrates all 7 layers in a sequential workflow.
Today's vertical slice: Layers 2, 3, 4, 6, 7 (skipping Layer 5 - People Mapper).
"""

import os
import time
import uuid
try:
    from langsmith import uuid7
except ImportError:  # LangSmith not installed; fall back to uuid4
    uuid7 = None
from datetime import datetime
from typing import Dict, Any
from langgraph.graph import StateGraph, END
from src.common.config import Config
from src.common.state import JobState
from src.common.logger import setup_logging, get_logger
from src.common.structured_logger import get_structured_logger, StructuredLogger
from src.common.tracing import TracingContext, log_trace_info, is_tracing_enabled
from src.common.token_tracker import get_global_tracker
from src.common.llm_factory import set_run_context, clear_run_context
from src.common.database import Database

# Initialize logging
log_level = os.getenv("LOG_LEVEL", "INFO")
log_format = os.getenv("LOG_FORMAT", "simple")  # "simple" or "json"
setup_logging(level=log_level, format=log_format)

logger = get_logger(__name__)

# Import all layer node functions
from src.layer1_4 import jd_extractor_node  # CV Gen V2: JD Extractor
from src.layer2.pain_point_miner import pain_point_miner_node
from src.layer2_5 import select_stars  # Phase 1.3: STAR Selector
from src.layer3.company_researcher import company_researcher_node
from src.layer3.role_researcher import role_researcher_node  # Phase 5.2: Role Researcher
from src.layer4.opportunity_mapper import opportunity_mapper_node
from src.layer5 import people_mapper_node  # Phase 1.3: People Mapper
from src.layer6 import outreach_generator_node  # Phase 9: Outreach Generator
from src.layer6.generator import generator_node  # Legacy CV generator
from src.layer6_v2 import cv_generator_v2_node  # CV Gen V2: 6-phase pipeline
from src.layer7.output_publisher import output_publisher_node


def save_pipeline_run_start(run_id: str, job_id: str, job_data: Dict[str, Any]) -> None:
    """
    Save pipeline run start to MongoDB (GAP-043).

    Creates a record in pipeline_runs collection when a run begins.
    """
    try:
        db = Database()
        run_doc = {
            "run_id": run_id,
            "job_id": job_id,
            "job_title": job_data.get("title", ""),
            "company": job_data.get("company", ""),
            "job_url": job_data.get("url", ""),
            "source": job_data.get("source", "manual"),
            "status": "processing",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "duration_ms": None,
            "fit_score": None,
            "fit_category": None,
            "errors": [],
            "trace_url": None,
            "total_cost_usd": None,
        }
        db.pipeline_runs.insert_one(run_doc)
        logger.debug(f"Pipeline run started: {run_id}")
    except Exception as e:
        logger.warning(f"Failed to save pipeline run start: {e}")


def update_pipeline_run_complete(
    run_id: str,
    status: str,
    duration_ms: int,
    fit_score: int = None,
    fit_category: str = None,
    errors: list = None,
    trace_url: str = None,
    total_cost_usd: float = None,
) -> None:
    """
    Update pipeline run with completion data (GAP-043).

    Updates the pipeline_runs record with results after pipeline finishes.
    """
    try:
        db = Database()
        update_doc = {
            "$set": {
                "status": status,
                "updated_at": datetime.utcnow(),
                "duration_ms": duration_ms,
                "fit_score": fit_score,
                "fit_category": fit_category,
                "errors": errors or [],
                "trace_url": trace_url,
                "total_cost_usd": total_cost_usd,
            }
        }
        db.pipeline_runs.update_one({"run_id": run_id}, update_doc)
        logger.debug(f"Pipeline run updated: {run_id} -> {status}")
    except Exception as e:
        logger.warning(f"Failed to update pipeline run: {e}")


def create_workflow() -> StateGraph:
    """
    Create the LangGraph workflow connecting all layers.

    Flow:
    1. Layer 1.4: JD Extractor (extract structured JD intelligence - CV Gen V2)
    2. Layer 2: Pain-Point Miner (extract pain points from job description)
    3. Layer 2.5: STAR Selector (select 2-3 best-fit achievements - Phase 1.3)
    4. Layer 3.0: Company Researcher (scrape company signals - Phase 5.1)
    5. Layer 3.5: Role Researcher (analyze role business impact - Phase 5.2)
    6. Layer 4: Opportunity Mapper (generate fit score + rationale)
    7. Layer 5: People Mapper (identify contacts, generate personalized outreach - Phase 7)
    8. Layer 6b: Outreach Generator (package outreach into OutreachPackage objects - Phase 9)
    9. Layer 6a: Generator (create cover letter + CV)
       - CV Gen V2 (default): 6-phase pipeline with per-role generation, QA, and grading
       - Legacy: Single-pass two-stage CV builder
    10. Layer 7: Output Publisher (upload to Drive, log to Sheets)

    Config flags:
    - ENABLE_CV_GEN_V2: Use 6-phase CV generation pipeline (default: true)
    - ENABLE_JD_EXTRACTOR: Extract structured JD intelligence (default: true)

    Returns:
        Compiled StateGraph ready to execute
    """
    # Create graph with JobState schema
    workflow = StateGraph(JobState)

    # Add nodes for each layer
    if Config.ENABLE_JD_EXTRACTOR:
        workflow.add_node("jd_extractor", jd_extractor_node)  # CV Gen V2: Layer 1.4
    workflow.add_node("pain_point_miner", pain_point_miner_node)
    if Config.ENABLE_STAR_SELECTOR:
        workflow.add_node("star_selector", select_stars)  # Phase 1.3
    workflow.add_node("company_researcher", company_researcher_node)  # Phase 5.1
    workflow.add_node("role_researcher", role_researcher_node)  # Phase 5.2
    workflow.add_node("opportunity_mapper", opportunity_mapper_node)
    workflow.add_node("people_mapper", people_mapper_node)  # Phase 7
    workflow.add_node("outreach_generator", outreach_generator_node)  # Phase 9
    # CV Generator: V2 (6-phase pipeline) or legacy
    if Config.ENABLE_CV_GEN_V2:
        workflow.add_node("generator", cv_generator_v2_node)  # CV Gen V2
        logger.info("Using CV Generation V2 (6-phase pipeline)")
    else:
        workflow.add_node("generator", generator_node)  # Legacy
        logger.info("Using legacy CV generator")
    workflow.add_node("output_publisher", output_publisher_node)

    # Define sequential edges
    # Layer 1.4 (if enabled) is the entry point, otherwise Layer 2
    if Config.ENABLE_JD_EXTRACTOR:
        workflow.set_entry_point("jd_extractor")
        workflow.add_edge("jd_extractor", "pain_point_miner")  # Layer 1.4 -> Layer 2
    else:
        workflow.set_entry_point("pain_point_miner")

    if Config.ENABLE_STAR_SELECTOR:
        workflow.add_edge("pain_point_miner", "star_selector")  # Layer 2 -> Layer 2.5
        workflow.add_edge("star_selector", "company_researcher")  # Layer 2.5 -> Layer 3.0
    else:
        workflow.add_edge("pain_point_miner", "company_researcher")
    workflow.add_edge("company_researcher", "role_researcher")  # Layer 3.0 -> Layer 3.5 (Phase 5)
    workflow.add_edge("role_researcher", "opportunity_mapper")  # Layer 3.5 -> Layer 4
    workflow.add_edge("opportunity_mapper", "people_mapper")  # Layer 4 -> Layer 5
    workflow.add_edge("people_mapper", "outreach_generator")  # Layer 5 -> Layer 6b (Phase 9)
    workflow.add_edge("outreach_generator", "generator")  # Layer 6b -> Layer 6a
    workflow.add_edge("generator", "output_publisher")  # Layer 6a -> Layer 7
    workflow.add_edge("output_publisher", END)

    # Compile graph
    app = workflow.compile()

    return app


def run_pipeline(
    job_data: Dict[str, Any],
    candidate_profile: str,
    tier_config: Any = None
) -> JobState:
    """
    Run the complete job intelligence pipeline.

    Args:
        job_data: Dict with job details (job_id, title, company, description, url, source)
        candidate_profile: String with candidate profile/CV text
        tier_config: Optional TierConfig for tiered processing (GAP-045)

    Returns:
        Final JobState with all outputs populated
    """
    # Generate metadata
    run_id = str(uuid7()) if uuid7 else str(uuid.uuid4())
    created_at = datetime.utcnow().isoformat() + 'Z'
    pipeline_start_time = time.time()

    # Create run-specific logger
    run_logger = get_logger(__name__, run_id=run_id)

    # Create structured logger for JSON events
    job_id = job_data.get("job_id", "")
    struct_logger = get_structured_logger(job_id)

    # GAP-066: Set run context for automatic token tracking
    set_run_context(run_id=run_id, job_id=job_id)

    run_logger.info("="*70)
    run_logger.info("STARTING JOB INTELLIGENCE PIPELINE")
    run_logger.info("="*70)
    run_logger.info(f"Job: {job_data.get('title')} at {job_data.get('company')}")
    run_logger.info(f"Job ID: {job_data.get('job_id')}")
    run_logger.info(f"Run ID: {run_id}")
    run_logger.info(f"Started: {created_at}")
    run_logger.info("="*70)

    # Emit structured pipeline_start event
    struct_logger.pipeline_start(metadata={
        "job_title": job_data.get("title"),
        "company": job_data.get("company"),
        "run_id": run_id,
    })

    # GAP-043: Save run start to MongoDB
    save_pipeline_run_start(run_id, job_id, job_data)

    # Initialize state
    initial_state: JobState = {
        "job_id": job_data.get("job_id", ""),
        "title": job_data.get("title", ""),
        "company": job_data.get("company", ""),
        "job_description": job_data.get("description", ""),
        "scraped_job_posting": None,
        "job_url": job_data.get("url", ""),
        "source": job_data.get("source", "manual"),
        "candidate_profile": candidate_profile,

        # Output fields (will be populated by layers)
        "extracted_jd": None,  # CV Gen V2: Layer 1.4 structured JD
        "pain_points": None,
        "strategic_needs": None,  # Phase 1.3: Layer 2 JSON
        "risks_if_unfilled": None,  # Phase 1.3: Layer 2 JSON
        "success_metrics": None,  # Phase 1.3: Layer 2 JSON
        "selected_stars": None,  # Phase 1.3: Layer 2.5
        "star_to_pain_mapping": None,  # Phase 1.3: Layer 2.5
        "all_stars": None,  # Phase 8.2: Full STAR library for CV generation
        "company_research": None,  # Phase 5.1: Layer 3.0 structured signals
        "company_summary": None,  # Legacy (populated from company_research)
        "company_url": None,  # Legacy (populated from company_research)
        "role_research": None,  # Phase 5.2: Layer 3.5 business impact
        "fit_score": None,
        "fit_rationale": None,
        "fit_category": None,  # Phase 6: Layer 4 category
        "primary_contacts": None,  # Phase 7: Layer 5 primary contacts
        "secondary_contacts": None,  # Phase 7: Layer 5 secondary contacts
        "people": None,  # Legacy: Layer 5 (deprecated, use primary_contacts + secondary_contacts)
        "outreach_packages": None,  # Phase 7/9: Per-contact outreach
        "fallback_cover_letters": None,  # Fallback letters when contacts are unavailable
        "cover_letter": None,
        "cv_path": None,
        "cv_reasoning": None,  # Phase 8.2: STAR-driven CV tailoring rationale
        "drive_folder_url": None,
        "sheet_row_id": None,

        # Metadata
        "run_id": run_id,
        "created_at": created_at,
        "errors": [],
        "status": "processing",
        "trace_url": None,  # OB-3: LangSmith trace URL

        # GAP-036: Cost tracking
        "total_cost_usd": None,
        "token_usage": None,

        # GAP-045: Tiered processing
        "processing_tier": tier_config.tier.value if tier_config else None,
        "tier_config": {
            "cv_model": tier_config.cv_model,
            "role_model": tier_config.role_model,
            "research_model": tier_config.research_model,
            "pain_points_model": tier_config.pain_points_model,
            "fit_scoring_model": tier_config.fit_scoring_model,
            "max_contacts": tier_config.max_contacts,
            "discover_contacts": tier_config.discover_contacts,
            "generate_cv": tier_config.generate_cv,
            "use_star_enforcement": tier_config.use_star_enforcement,
            "generate_outreach": tier_config.generate_outreach,
        } if tier_config else None,
    }

    # Log tier configuration
    if tier_config:
        run_logger.info(f"Processing Tier: {tier_config.tier.value} - {tier_config.description}")
        run_logger.info(f"  CV Model: {tier_config.cv_model}")
        run_logger.info(f"  Research Model: {tier_config.research_model}")
        run_logger.info(f"  Max Contacts: {tier_config.max_contacts}")

    # Create and run workflow
    app = create_workflow()

    # Log tracing configuration (OB-3)
    if is_tracing_enabled():
        run_logger.info("LangSmith tracing enabled")
        log_trace_info(run_id, job_id)
    else:
        run_logger.info("LangSmith tracing disabled (set LANGCHAIN_TRACING_V2=true to enable)")

    # Execute workflow with distributed tracing (OB-3)
    trace_url = None
    try:
        run_logger.info("Executing LangGraph workflow")

        # Wrap execution with TracingContext for LangSmith integration
        with TracingContext(
            run_id=run_id,
            job_id=job_id,
            tags=[f"company:{job_data.get('company', 'unknown')}", f"source:{job_data.get('source', 'manual')}"],
            metadata={
                "job_title": job_data.get("title"),
                "company": job_data.get("company"),
                "job_url": job_data.get("url"),
            }
        ) as trace:
            final_state = app.invoke(initial_state)
            trace_url = trace.trace_url

        # Store trace URL in final state
        final_state["trace_url"] = trace_url

        # GAP-036: Capture token usage and cost from global tracker
        try:
            tracker = get_global_tracker()
            summary = tracker.get_summary()
            final_state["total_cost_usd"] = summary.total_cost_usd
            final_state["token_usage"] = {
                provider: {
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "estimated_cost_usd": usage.estimated_cost_usd,
                }
                for provider, usage in summary.by_provider.items()
            }
            run_logger.info(f"Token usage: ${summary.total_cost_usd:.4f} USD total")
        except Exception as e:
            run_logger.warning(f"Failed to capture token usage: {e}")

        # Update status based on errors
        if final_state.get("errors"):
            # Check if critical outputs are missing
            critical_missing = (
                not final_state.get("pain_points") or
                not final_state.get("fit_score") or
                not final_state.get("cover_letter")
            )
            final_state["status"] = "failed" if critical_missing else "partial"
            run_logger.warning(f"Pipeline completed with errors: {final_state.get('errors')}")
        else:
            final_state["status"] = "completed"
            run_logger.info("Pipeline completed successfully")

        # Emit structured completion event
        pipeline_duration = int((time.time() - pipeline_start_time) * 1000)
        struct_logger.pipeline_complete(
            status=final_state["status"],
            duration_ms=pipeline_duration,
            metadata={
                "fit_score": final_state.get("fit_score"),
                "errors_count": len(final_state.get("errors", [])),
                "trace_url": trace_url,  # OB-3: Include trace URL in structured log
            },
        )

        # GAP-043: Update run completion in MongoDB
        update_pipeline_run_complete(
            run_id=run_id,
            status=final_state["status"],
            duration_ms=pipeline_duration,
            fit_score=final_state.get("fit_score"),
            fit_category=final_state.get("fit_category"),
            errors=final_state.get("errors"),
            trace_url=trace_url,
            total_cost_usd=final_state.get("total_cost_usd"),
        )

    except Exception as e:
        run_logger.exception(f"Pipeline failed with exception: {e}")
        # Emit structured error event
        pipeline_duration = int((time.time() - pipeline_start_time) * 1000)
        struct_logger.pipeline_complete(
            status="error",
            duration_ms=pipeline_duration,
            metadata={"error": str(e), "trace_url": trace_url},
        )
        # GAP-043: Update run as failed in MongoDB
        update_pipeline_run_complete(
            run_id=run_id,
            status="failed",
            duration_ms=pipeline_duration,
            errors=[f"Pipeline exception: {str(e)}"],
            trace_url=trace_url,
        )
        # Create minimal final state with error
        final_state = initial_state.copy()
        final_state["errors"] = [f"Pipeline exception: {str(e)}"]
        final_state["status"] = "failed"
        final_state["trace_url"] = trace_url
        # GAP-066: Clear run context on error
        clear_run_context()
        raise

    # Write final state to JSON file for runner service to read
    import json
    from pathlib import Path
    state_output_path = Path(f".pipeline_state_{final_state.get('job_id', 'unknown')}.json")
    try:
        # Convert datetime objects to ISO strings for JSON serialization
        serializable_state = {}
        for key, value in final_state.items():
            if isinstance(value, datetime):
                serializable_state[key] = value.isoformat()
            else:
                serializable_state[key] = value

        state_output_path.write_text(json.dumps(serializable_state, indent=2, default=str))
        run_logger.info(f"Pipeline state written to: {state_output_path}")
    except Exception as e:
        run_logger.warning(f"Failed to write pipeline state: {e}")

    # Log summary
    run_logger.info("="*70)
    run_logger.info("PIPELINE COMPLETE")
    run_logger.info("="*70)
    run_logger.info(f"Run ID: {final_state.get('run_id')}")
    run_logger.info(f"Status: {final_state.get('status')}")
    run_logger.info(f"Fit Score: {final_state.get('fit_score')}/100")
    run_logger.info(f"Drive Folder: {final_state.get('drive_folder_url')}")
    run_logger.info(f"Sheets Row: {final_state.get('sheet_row_id')}")
    if final_state.get("trace_url"):
        run_logger.info(f"LangSmith Trace: {final_state.get('trace_url')}")

    # GAP-036: Log cost tracking info
    if final_state.get("total_cost_usd") is not None:
        run_logger.info(f"Total Cost: ${final_state.get('total_cost_usd'):.4f} USD")
    if final_state.get("token_usage"):
        for provider, usage in final_state["token_usage"].items():
            run_logger.info(f"  {provider}: {usage.get('input_tokens', 0):,} in / {usage.get('output_tokens', 0):,} out (${usage.get('estimated_cost_usd', 0):.4f})")

    if final_state.get("errors"):
        run_logger.warning("Warnings/Errors:")
        for error in final_state["errors"]:
            run_logger.warning(f"  - {error}")

    run_logger.info("="*70)

    # GAP-066: Clear run context after pipeline completes
    clear_run_context()

    return final_state


if __name__ == "__main__":
    # Simple test
    test_job = {
        "job_id": "test123",
        "title": "Senior Software Engineer",
        "company": "Test Corp",
        "description": "Build amazing software...",
        "url": "https://example.com/job",
        "source": "test"
    }

    test_profile = "Experienced software engineer with 5+ years..."

    result = run_pipeline(test_job, test_profile)
    print("Test complete!")
