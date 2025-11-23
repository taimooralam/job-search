"""
Process a single jobId from assets/pipline.md through the pipeline.

Reads the first jobId from the queue file, runs the pipeline for that job,
and removes the jobId from the queue only if the run completes successfully.
"""

import argparse
from pathlib import Path
import sys
from typing import List, Tuple

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.common.config import Config  # noqa: E402
from src.workflow import run_pipeline  # noqa: E402
from scripts.run_pipeline import load_candidate_profile, load_job_from_mongo  # noqa: E402


def read_job_ids(queue_path: Path) -> List[str]:
    """Read jobIds from the queue file, skipping blank lines."""
    if not queue_path.exists():
        return []
    lines = queue_path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip()]


def write_job_ids(queue_path: Path, job_ids: List[str]) -> None:
    """Persist jobIds back to the queue file, one per line."""
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    contents = "\n".join(job_ids)
    queue_path.write_text(contents, encoding="utf-8")


def pop_next_job(queue_path: Path) -> Tuple[str, List[str]]:
    """Return the next jobId and the remaining queue."""
    job_ids = read_job_ids(queue_path)
    if not job_ids:
        raise ValueError(f"No jobIds found in {queue_path}")
    return job_ids[0], job_ids[1:]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run pipeline for the next jobId in assets/pipline.md."
    )
    parser.add_argument(
        "--queue",
        default=str(Path("assets") / "pipline.md"),
        help="Path to the jobId queue file (default: assets/pipline.md).",
    )
    parser.add_argument(
        "--profile",
        default=Config.CANDIDATE_PROFILE_PATH,
        help="Path to candidate profile markdown file.",
    )

    args = parser.parse_args()
    queue_path = Path(args.queue)

    # Validate configuration and load profile up front
    Config.validate()
    candidate_profile = load_candidate_profile(args.profile)

    try:
        job_id, remaining_job_ids = pop_next_job(queue_path)
    except ValueError as exc:
        print(f"⚠️  {exc}")
        return

    print(f"Processing jobId: {job_id}")

    try:
        job_data = load_job_from_mongo(job_id)
        final_state = run_pipeline(job_data, candidate_profile)
    except Exception as exc:  # noqa: BLE001 - surface pipeline failure info
        print(f"❌ Pipeline run failed: {exc}")
        return

    status = final_state.get("status")
    print(f"Pipeline status: {status}")

    if status == "completed":
        write_job_ids(queue_path, remaining_job_ids)
        print(f"✓ JobId {job_id} removed from queue.")
    else:
        print("JobId retained in queue for retry.")


if __name__ == "__main__":
    main()
