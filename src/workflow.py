"""
LangGraph Workflow: Job Intelligence Pipeline

Orchestrates all 7 layers in a sequential workflow.
Today's vertical slice: Layers 2, 3, 4, 6, 7 (skipping Layer 5 - People Mapper).
"""

import os
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

# Initialize logging
log_level = os.getenv("LOG_LEVEL", "INFO")
log_format = os.getenv("LOG_FORMAT", "simple")  # "simple" or "json"
setup_logging(level=log_level, format=log_format)

logger = get_logger(__name__)

# Import all layer node functions
from src.layer2.pain_point_miner import pain_point_miner_node
from src.layer2_5 import select_stars  # Phase 1.3: STAR Selector
from src.layer3.company_researcher import company_researcher_node
from src.layer3.role_researcher import role_researcher_node  # Phase 5.2: Role Researcher
from src.layer4.opportunity_mapper import opportunity_mapper_node
from src.layer5 import people_mapper_node  # Phase 1.3: People Mapper
from src.layer6 import outreach_generator_node  # Phase 9: Outreach Generator
from src.layer6.generator import generator_node
from src.layer7.output_publisher import output_publisher_node


def create_workflow() -> StateGraph:
    """
    Create the LangGraph workflow connecting all layers.

    Flow:
    1. Layer 2: Pain-Point Miner (extract pain points from job description)
    2. Layer 2.5: STAR Selector (select 2-3 best-fit achievements - Phase 1.3)
    3. Layer 3.0: Company Researcher (scrape company signals - Phase 5.1)
    4. Layer 3.5: Role Researcher (analyze role business impact - Phase 5.2)
    5. Layer 4: Opportunity Mapper (generate fit score + rationale)
    6. Layer 5: People Mapper (identify contacts, generate personalized outreach - Phase 7)
    7. Layer 6b: Outreach Generator (package outreach into OutreachPackage objects - Phase 9)
    8. Layer 6a: Generator (create cover letter + CV - Phase 8)
    9. Layer 7: Output Publisher (upload to Drive, log to Sheets)

    Returns:
        Compiled StateGraph ready to execute
    """
    # Create graph with JobState schema
    workflow = StateGraph(JobState)

    # Add nodes for each layer
    workflow.add_node("pain_point_miner", pain_point_miner_node)
    if Config.ENABLE_STAR_SELECTOR:
        workflow.add_node("star_selector", select_stars)  # Phase 1.3
    workflow.add_node("company_researcher", company_researcher_node)  # Phase 5.1
    workflow.add_node("role_researcher", role_researcher_node)  # Phase 5.2
    workflow.add_node("opportunity_mapper", opportunity_mapper_node)
    workflow.add_node("people_mapper", people_mapper_node)  # Phase 7
    workflow.add_node("outreach_generator", outreach_generator_node)  # Phase 9
    workflow.add_node("generator", generator_node)
    workflow.add_node("output_publisher", output_publisher_node)

    # Define sequential edges
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


def run_pipeline(job_data: Dict[str, Any], candidate_profile: str) -> JobState:
    """
    Run the complete job intelligence pipeline.

    Args:
        job_data: Dict with job details (job_id, title, company, description, url, source)
        candidate_profile: String with candidate profile/CV text

    Returns:
        Final JobState with all outputs populated
    """
    # Generate metadata
    run_id = str(uuid7()) if uuid7 else str(uuid.uuid4())
    created_at = datetime.utcnow().isoformat() + 'Z'

    # Create run-specific logger
    run_logger = get_logger(__name__, run_id=run_id)

    run_logger.info("="*70)
    run_logger.info("STARTING JOB INTELLIGENCE PIPELINE")
    run_logger.info("="*70)
    run_logger.info(f"Job: {job_data.get('title')} at {job_data.get('company')}")
    run_logger.info(f"Job ID: {job_data.get('job_id')}")
    run_logger.info(f"Run ID: {run_id}")
    run_logger.info(f"Started: {created_at}")
    run_logger.info("="*70)

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
        "status": "processing"
    }

    # Create and run workflow
    app = create_workflow()

    # Execute workflow
    try:
        run_logger.info("Executing LangGraph workflow")
        final_state = app.invoke(initial_state)

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

    except Exception as e:
        run_logger.exception(f"Pipeline failed with exception: {e}")
        # Create minimal final state with error
        final_state = initial_state.copy()
        final_state["errors"] = [f"Pipeline exception: {str(e)}"]
        final_state["status"] = "failed"
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

    if final_state.get("errors"):
        run_logger.warning("Warnings/Errors:")
        for error in final_state["errors"]:
            run_logger.warning(f"  - {error}")

    run_logger.info("="*70)

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
