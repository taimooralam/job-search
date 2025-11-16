"""
LangGraph Workflow: Job Intelligence Pipeline

Orchestrates all 7 layers in a sequential workflow.
Today's vertical slice: Layers 2, 3, 4, 6, 7 (skipping Layer 5 - People Mapper).
"""

from typing import Dict, Any
from langgraph.graph import StateGraph, END
from src.common.state import JobState

# Import all layer node functions
from src.layer2.pain_point_miner import pain_point_miner_node
from src.layer3.company_researcher import company_researcher_node
from src.layer4.opportunity_mapper import opportunity_mapper_node
from src.layer6.generator import generator_node
from src.layer7.output_publisher import output_publisher_node


def create_workflow() -> StateGraph:
    """
    Create the LangGraph workflow connecting all layers.

    Flow:
    1. Layer 2: Pain-Point Miner (extract pain points from job description)
    2. Layer 3: Company Researcher (scrape + summarize company)
    3. Layer 4: Opportunity Mapper (generate fit score + rationale)
    4. Layer 6: Generator (create cover letter + CV)
    5. Layer 7: Output Publisher (upload to Drive, log to Sheets)

    Returns:
        Compiled StateGraph ready to execute
    """
    # Create graph with JobState schema
    workflow = StateGraph(JobState)

    # Add nodes for each layer
    workflow.add_node("pain_point_miner", pain_point_miner_node)
    workflow.add_node("company_researcher", company_researcher_node)
    workflow.add_node("opportunity_mapper", opportunity_mapper_node)
    workflow.add_node("generator", generator_node)
    workflow.add_node("output_publisher", output_publisher_node)

    # Define sequential edges (linear flow for today's slice)
    workflow.set_entry_point("pain_point_miner")
    workflow.add_edge("pain_point_miner", "company_researcher")
    workflow.add_edge("company_researcher", "opportunity_mapper")
    workflow.add_edge("opportunity_mapper", "generator")
    workflow.add_edge("generator", "output_publisher")
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
    print("\n" + "="*70)
    print("🚀 STARTING JOB INTELLIGENCE PIPELINE")
    print("="*70)
    print(f"Job: {job_data.get('title')} at {job_data.get('company')}")
    print(f"Job ID: {job_data.get('job_id')}")
    print("="*70 + "\n")

    # Initialize state
    initial_state: JobState = {
        "job_id": job_data.get("job_id", ""),
        "title": job_data.get("title", ""),
        "company": job_data.get("company", ""),
        "job_description": job_data.get("description", ""),
        "job_url": job_data.get("url", ""),
        "source": job_data.get("source", "manual"),
        "candidate_profile": candidate_profile,

        # Output fields (will be populated by layers)
        "pain_points": None,
        "company_summary": None,
        "company_url": None,
        "fit_score": None,
        "fit_rationale": None,
        "cover_letter": None,
        "cv_path": None,
        "drive_folder_url": None,
        "sheet_row_id": None,

        # Metadata
        "run_id": None,
        "created_at": None,
        "errors": None,
        "status": "processing"
    }

    # Create and run workflow
    app = create_workflow()

    # Execute workflow
    final_state = app.invoke(initial_state)

    # Print summary
    print("\n" + "="*70)
    print("✅ PIPELINE COMPLETE")
    print("="*70)
    print(f"Fit Score: {final_state.get('fit_score')}/100")
    print(f"Drive Folder: {final_state.get('drive_folder_url')}")
    print(f"Sheets Row: {final_state.get('sheet_row_id')}")

    if final_state.get("errors"):
        print(f"\n⚠️  Warnings/Errors:")
        for error in final_state["errors"]:
            print(f"  - {error}")

    print("="*70 + "\n")

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
