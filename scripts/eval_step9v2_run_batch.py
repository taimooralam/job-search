#!/usr/bin/env python3
"""Step 9 v2 batch runner: generate CVs for 4 anchors sequentially, freeze snapshots."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from src.common.utils import sanitize_path_component  # noqa: E402

ANCHORS = [
    ("ai_architect_global", "696808c4515e64c5ca05acee",
     "data/eval/raw/ai_architect_global/jd_texts/01_algominds_software_architect_cloud_ai_distributed_systems.md"),
    ("head_of_ai_global", "69825fa77d41dc1e8a360e27",
     "data/eval/raw/head_of_ai_global/jd_texts/01_crossover_senior_software_engineer_learnwithai_remote_100000year_usd.md"),
    ("staff_ai_engineer_eea", "6957aaad6dd552ab7ec2ccd8",
     "data/eval/raw/staff_ai_engineer_eea/jd_texts/01_reddit_inc_staff_software_engineer_ml_search.md"),
    ("tech_lead_ai_eea", "6925a6c845fa3c355f83f8ec",
     "data/eval/raw/tech_lead_ai_eea/jd_texts/01_samsara_senior_software_engineer_ii_tech_lead_ml_new_products.md"),
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot_state(path: Path):
    if not path.exists():
        return {"exists": False}
    st = path.stat()
    return {"exists": True, "size": st.st_size, "mtime": st.st_mtime, "sha256": sha256(path)}


CV_PATH_RE = re.compile(r"(?:📋\s*CV:|CV saved to:)\s*(.+\.md)\s*$", re.MULTILINE)


def parse_cv_path_from_log(log_text: str) -> list[str]:
    hits = []
    for m in CV_PATH_RE.finditer(log_text):
        candidate = m.group(1).strip()
        if candidate and candidate not in hits:
            hits.append(candidate)
    return hits


def resolve_cv_path(log_text: str, expected_path: Path, pre_state: dict) -> tuple[Path | None, str]:
    # 1) parse log
    for candidate in parse_cv_path_from_log(log_text):
        p = Path(candidate)
        if p.exists():
            return p, "log_parse"
    # 2) deterministic expected path
    if expected_path.exists():
        post = snapshot_state(expected_path)
        if not pre_state.get("exists") or post.get("sha256") != pre_state.get("sha256"):
            return expected_path, "deterministic"
    # 3) mongo fallback
    try:
        from scripts.run_pipeline import load_job_from_mongo  # noqa: F401
        # Not calling — would need job_id; skip here. Handled in main loop.
    except Exception:
        pass
    return None, "unresolved"


def resolve_via_mongo(job_id: str) -> Path | None:
    try:
        import pymongo

        from src.common.config import Config
        client = pymongo.MongoClient(Config.MONGODB_URI)
        db = client[Config.MONGODB_DATABASE]
        for coll in ("level-2", "level-1"):
            doc = db[coll].find_one({"_id": __import__("bson").ObjectId(job_id)})
            if doc and doc.get("cv_path"):
                p = Path(doc["cv_path"])
                if p.exists():
                    return p
    except Exception as e:
        print(f"  mongo cv_path lookup failed: {e}")
    return None


def run_anchor(cat: str, jid: str, jd: str, run_root: Path) -> dict:
    print(f"\n========== {cat} ({jid}) ==========")
    jd_stem = Path(jd).stem
    log_path = run_root / "logs" / f"{cat}.log"
    meta_path = run_root / "meta" / f"{cat}.json"
    snap_dir = run_root / "snapshots" / cat
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap_path = snap_dir / f"{jd_stem}__generated.md"

    # Derive expected deterministic path using Mongo-known title/company
    from scripts.run_pipeline import load_job_from_mongo
    job = load_job_from_mongo(jid)
    company = sanitize_path_component(job.get("company", "Unknown"))
    title = sanitize_path_component(job.get("title", "Unknown"))
    expected = Path("outputs") / company / f"cv_{title}.md"
    pre_state = snapshot_state(expected)
    print(f"  expected path: {expected}")
    print(f"  pre-state: {pre_state}")

    # Run pipeline
    start = time.time()
    with open(log_path, "w", encoding="utf-8") as logf:
        proc = subprocess.run(
            [".venv/bin/python", "scripts/run_pipeline.py", "--job-id", jid],
            stdout=logf, stderr=subprocess.STDOUT, cwd=ROOT,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
    elapsed = time.time() - start
    print(f"  exit_code={proc.returncode}, elapsed={elapsed:.1f}s")

    log_text = log_path.read_text()

    # Resolve CV path
    cv_path, capture_method = resolve_cv_path(log_text, expected, pre_state)
    if cv_path is None:
        mongo_path = resolve_via_mongo(jid)
        if mongo_path:
            cv_path, capture_method = mongo_path, "mongo"

    scoreable = cv_path is not None and cv_path.exists()
    post_state = snapshot_state(cv_path) if cv_path else {}

    # Freeze snapshot
    if scoreable:
        shutil.copy2(cv_path, snap_path)
        print(f"  SNAPSHOT: {snap_path}")
    else:
        print("  UNSCOREABLE: no cv path resolved")

    meta = {
        "category": cat,
        "job_id": jid,
        "jd_path": jd,
        "jd_stem": jd_stem,
        "exit_code": proc.returncode,
        "elapsed_seconds": round(elapsed, 1),
        "expected_deterministic_path": str(expected),
        "pre_state": pre_state,
        "post_state": post_state,
        "resolved_cv_path": str(cv_path) if cv_path else None,
        "capture_method": capture_method,
        "snapshot_path": str(snap_path) if scoreable else None,
        "scoreable": scoreable,
        "log_tail": "\n".join(log_text.splitlines()[-15:]),
    }
    meta_path.write_text(json.dumps(meta, indent=2))
    print(f"  META: {meta_path}")
    return meta


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--anchors-json", help="JSON file with list of {category_id, job_id, jd_path}")
    parser.add_argument("--tag", default="step9_v2", help="Run-root tag; used to locate LATEST_<tag>.txt")
    args = parser.parse_args()

    # Resolve anchor list
    if args.anchors_json:
        anchors_data = json.loads(Path(args.anchors_json).read_text(encoding="utf-8"))
        anchors = [(a["category_id"], a["job_id"], a["jd_path"]) for a in anchors_data]
    else:
        anchors = ANCHORS

    # Resolve run root
    latest_file = Path(f"data/eval/generated_cvs/LATEST_{args.tag.upper()}.txt")
    if not latest_file.exists():
        # fall back to legacy pointer for backward compat
        latest_file = Path("data/eval/generated_cvs/LATEST_V2.txt")
    run_root = Path(latest_file.read_text().strip())
    if not run_root.exists():
        print(f"run root missing: {run_root}", file=sys.stderr)
        sys.exit(1)
    print(f"Run root: {run_root}")
    print(f"Anchors: {len(anchors)} pair(s) from {args.anchors_json or 'hardcoded default'}")

    results = []
    for cat, jid, jd in anchors:
        try:
            r = run_anchor(cat, jid, jd, run_root)
        except Exception as e:
            print(f"  {cat} FAILED WITH EXCEPTION: {e}")
            r = {"category": cat, "job_id": jid, "jd_path": jd, "scoreable": False, "error": str(e)}
        results.append(r)

    (run_root / "meta" / "batch_summary.json").write_text(json.dumps(results, indent=2))
    print("\n== Batch summary ==")
    for r in results:
        print(f"  {r['category']}: scoreable={r.get('scoreable')}, path={r.get('snapshot_path')}")


if __name__ == "__main__":
    main()
