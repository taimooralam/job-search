"""
Job Search Service

Provides pull-on-demand job search across multiple sources (Indeed, Bayt, Himalayas)
with caching and a searchable job index.

Architecture:
    - Searches are executed in real-time when requested
    - Results are cached with configurable TTL (default: 6 hours)
    - Discovered jobs are stored in a separate index (not level-2)
    - Jobs can be promoted from index to level-2 for pipeline processing

Usage:
    service = JobSearchService(db)
    results = await service.search(
        job_titles=["Senior Software Engineer"],
        regions=["gulf", "worldwide_remote"],
        sources=["indeed", "bayt", "himalayas"]
    )
"""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from bson import ObjectId
from pymongo.database import Database
from pymongo import ASCENDING, DESCENDING, TEXT

from src.services.job_sources import IndeedSource, HimalayasSource, BaytSource, JobData
from src.common.job_search_config import JobSearchConfig

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Result from a job search operation."""
    success: bool
    cache_hit: bool
    cache_key: str
    search_duration_ms: int
    total_results: int
    results_by_source: Dict[str, int]
    jobs: List[Dict[str, Any]]
    error: Optional[str] = None


class JobSearchService:
    """
    Coordinates job searches across sources with caching.

    Collections used:
        - job_search_cache: Stores cache entries with TTL
        - job_search_index: Stores all discovered jobs (searchable)
        - level-2: Target for promoted jobs (pipeline)
    """

    # Collection names
    CACHE_COLLECTION = "job_search_cache"
    INDEX_COLLECTION = "job_search_index"
    LEVEL2_COLLECTION = "level-2"

    def __init__(
        self,
        db: Database,
        config: Optional[JobSearchConfig] = None
    ):
        """
        Initialize the job search service.

        Args:
            db: MongoDB database instance
            config: Optional configuration (loads from env if not provided)
        """
        self.db = db
        self.config = config or JobSearchConfig.from_env()

        # Get collections
        self.cache = db[self.CACHE_COLLECTION]
        self.index = db[self.INDEX_COLLECTION]
        self.level2 = db[self.LEVEL2_COLLECTION]

        # Initialize sources
        self.sources = {
            "indeed": IndeedSource(),
            "bayt": BaytSource(),
            "himalayas": HimalayasSource(),
        }

        # Ensure indexes exist
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        """Create required MongoDB indexes if they don't exist."""
        try:
            # Cache collection indexes
            # TTL index for automatic expiration
            self.cache.create_index(
                "expires_at",
                expireAfterSeconds=0,
                background=True
            )
            # Unique cache key lookup
            self.cache.create_index(
                "cache_key",
                unique=True,
                background=True
            )

            # Index collection indexes
            # Unique deduplication key
            self.index.create_index(
                "dedupeKey",
                unique=True,
                background=True
            )
            # Compound index for filtering
            self.index.create_index(
                [("source", ASCENDING), ("region", ASCENDING), ("discovered_at", DESCENDING)],
                background=True
            )
            # Text index for full-text search
            self.index.create_index(
                [("title", TEXT), ("company", TEXT), ("description", TEXT)],
                background=True
            )
            # Filter indexes
            self.index.create_index("promoted_to_level2", background=True)
            self.index.create_index("hidden", background=True)
            self.index.create_index("quick_score", background=True)

            logger.info("Job search indexes ensured")
        except Exception as e:
            logger.warning(f"Error creating indexes (may already exist): {e}")

    def _generate_cache_key(self, params: dict) -> str:
        """
        Generate a deterministic cache key from search parameters.

        Normalizes and sorts parameters to ensure same logical search
        produces same cache key.
        """
        normalized = {
            "job_titles": sorted([t.lower().strip() for t in params.get("job_titles", [])]),
            "regions": sorted(params.get("regions", [])),
            "sources": sorted(params.get("sources", [])),
            "remote_only": bool(params.get("remote_only", False)),
        }

        key_string = json.dumps(normalized, sort_keys=True)
        return hashlib.sha256(key_string.encode()).hexdigest()[:32]

    def _check_cache(self, cache_key: str) -> Optional[dict]:
        """Check if valid cache entry exists."""
        entry = self.cache.find_one({
            "cache_key": cache_key,
            "expires_at": {"$gt": datetime.utcnow()}
        })
        return entry

    def _generate_dedupe_key(self, job: Dict[str, Any], source: str) -> str:
        """Generate deduplication key for a job."""
        company = (job.get("company") or "").lower().strip()
        title = (job.get("title") or "").lower().strip()
        location = (job.get("location") or "").lower().strip()
        return f"{company}|{title}|{location}|{source}"

    async def search(
        self,
        job_titles: List[str],
        regions: List[str],
        sources: List[str],
        remote_only: bool = False,
        use_cache: bool = True,
        max_results_per_source: Optional[int] = None,
    ) -> SearchResult:
        """
        Execute job search across specified sources.

        Args:
            job_titles: List of job titles to search (preset IDs or raw terms)
            regions: List of region IDs ("gulf", "worldwide_remote")
            sources: List of source IDs ("indeed", "bayt", "himalayas")
            remote_only: Only return remote jobs
            use_cache: Use cached results if available (default: True)
            max_results_per_source: Override max results per source

        Returns:
            SearchResult with jobs and metadata
        """
        start_time = datetime.utcnow()

        params = {
            "job_titles": job_titles,
            "regions": regions,
            "sources": sources,
            "remote_only": remote_only,
        }
        cache_key = self._generate_cache_key(params)

        # Check cache
        if use_cache:
            cache_entry = self._check_cache(cache_key)
            if cache_entry:
                logger.info(f"Cache hit for key {cache_key[:8]}...")
                jobs = list(self.index.find(
                    {"_id": {"$in": cache_entry.get("job_ids", [])}},
                    {"description": 0}  # Exclude large description field for list view
                ))

                # Convert ObjectId to string for JSON serialization
                for job in jobs:
                    job["job_id"] = str(job.pop("_id"))

                duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

                return SearchResult(
                    success=True,
                    cache_hit=True,
                    cache_key=cache_key,
                    search_duration_ms=duration_ms,
                    total_results=len(jobs),
                    results_by_source=cache_entry.get("results_by_source", {}),
                    jobs=jobs,
                )

        # Execute fresh search
        try:
            all_jobs = []
            results_by_source = {}

            # Build search configs
            search_configs = self.config.build_search_configs(
                job_titles=job_titles,
                regions=regions,
                sources=sources,
                remote_only=remote_only,
                max_results=max_results_per_source,
            )

            # Search each source
            for config in search_configs:
                source_id = config["source"]
                source_jobs = await self._search_source(config)
                results_by_source[source_id] = len(source_jobs)
                all_jobs.extend(source_jobs)

            # Deduplicate and upsert to index
            job_ids = self._upsert_jobs(all_jobs)

            # Create cache entry
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            self._create_cache_entry(
                cache_key=cache_key,
                params=params,
                job_ids=job_ids,
                results_by_source=results_by_source,
                duration_ms=duration_ms,
            )

            # Fetch jobs from index for response
            jobs = list(self.index.find(
                {"_id": {"$in": job_ids}},
                {"description": 0}
            ))

            # Convert ObjectId to string
            for job in jobs:
                job["job_id"] = str(job.pop("_id"))

            return SearchResult(
                success=True,
                cache_hit=False,
                cache_key=cache_key,
                search_duration_ms=duration_ms,
                total_results=len(jobs),
                results_by_source=results_by_source,
                jobs=jobs,
            )

        except Exception as e:
            logger.error(f"Search failed: {e}")
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            return SearchResult(
                success=False,
                cache_hit=False,
                cache_key=cache_key,
                search_duration_ms=duration_ms,
                total_results=0,
                results_by_source={},
                jobs=[],
                error=str(e),
            )

    async def _search_source(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Search a single source with the given configuration.

        Args:
            config: Search configuration from build_search_configs()

        Returns:
            List of job dictionaries
        """
        source_id = config["source"]
        source = self.sources.get(source_id)

        if not source:
            logger.warning(f"Unknown source: {source_id}")
            return []

        all_jobs = []
        search_terms = config.get("search_terms", [])
        results_wanted = config.get("results_wanted", 25)
        regions = config.get("regions", [])

        for term in search_terms:
            for region in regions:
                try:
                    # Build source-specific search config
                    search_config = {
                        "search_term": term,
                        "results_wanted": results_wanted,
                    }

                    # Add Indeed-specific parameters
                    if source_id == "indeed":
                        if region.get("is_remote"):
                            search_config["is_remote"] = True
                        elif region.get("countries"):
                            # Search each country
                            for country in region["countries"]:
                                if country.get("indeed_code"):
                                    search_config["country"] = country["indeed_code"]
                                    jobs = source.fetch_jobs(search_config)
                                    for job in jobs:
                                        job_dict = self._job_data_to_dict(
                                            job, source_id, region["id"]
                                        )
                                        all_jobs.append(job_dict)
                            continue  # Skip the main fetch

                    # Add Himalayas-specific parameters
                    if source_id == "himalayas":
                        search_config = {
                            "keywords": [term],
                            "max_results": results_wanted,
                            "worldwide_only": region.get("is_remote", False),
                        }

                    # Fetch jobs
                    jobs = source.fetch_jobs(search_config)

                    for job in jobs:
                        job_dict = self._job_data_to_dict(job, source_id, region["id"])
                        all_jobs.append(job_dict)

                except Exception as e:
                    logger.error(f"Error searching {source_id} for '{term}': {e}")
                    continue

        return all_jobs

    def _job_data_to_dict(
        self,
        job: JobData,
        source_id: str,
        region_id: str
    ) -> Dict[str, Any]:
        """Convert JobData to dictionary for storage."""
        is_remote = "remote" in (job.location or "").lower()

        return {
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "description": job.description,
            "url": job.url,
            "salary": job.salary,
            "job_type": job.job_type,
            "posted_date": job.posted_date,
            "source_id": job.source_id,
            "source": source_id,
            "region": region_id,
            "is_remote": is_remote,
        }

    def _upsert_jobs(self, jobs: List[Dict[str, Any]]) -> List[ObjectId]:
        """
        Upsert jobs into the index, returning their ObjectIds.

        Uses dedupeKey for upsert to prevent duplicates.
        """
        job_ids = []
        now = datetime.utcnow()

        for job in jobs:
            dedupe_key = self._generate_dedupe_key(job, job.get("source", "unknown"))

            try:
                result = self.index.find_one_and_update(
                    {"dedupeKey": dedupe_key},
                    {
                        "$set": {
                            "title": job.get("title"),
                            "company": job.get("company"),
                            "location": job.get("location"),
                            "description": job.get("description"),
                            "url": job.get("url"),
                            "salary": job.get("salary"),
                            "job_type": job.get("job_type"),
                            "posted_date": job.get("posted_date"),
                            "source_id": job.get("source_id"),
                            "source": job.get("source"),
                            "region": job.get("region"),
                            "is_remote": job.get("is_remote", False),
                            "last_seen_at": now,
                        },
                        "$setOnInsert": {
                            "dedupeKey": dedupe_key,
                            "discovered_at": now,
                            "search_hits": 0,
                            "promoted_to_level2": False,
                            "promoted_at": None,
                            "promoted_job_id": None,
                            "hidden": False,
                            "hidden_at": None,
                            "quick_score": None,
                            "quick_score_rationale": None,
                            "scored_at": None,
                        },
                        "$inc": {"search_hits": 1},
                    },
                    upsert=True,
                    return_document=True,
                )
                if result:
                    job_ids.append(result["_id"])
            except Exception as e:
                logger.warning(f"Error upserting job: {e}")
                continue

        return job_ids

    def _create_cache_entry(
        self,
        cache_key: str,
        params: dict,
        job_ids: List[ObjectId],
        results_by_source: Dict[str, int],
        duration_ms: int,
    ) -> None:
        """Create or update cache entry."""
        now = datetime.utcnow()
        expires_at = now + timedelta(hours=self.config.cache_ttl_hours)

        try:
            self.cache.update_one(
                {"cache_key": cache_key},
                {
                    "$set": {
                        "cache_key": cache_key,
                        "search_params": params,
                        "job_ids": job_ids,
                        "results_count": len(job_ids),
                        "results_by_source": results_by_source,
                        "created_at": now,
                        "expires_at": expires_at,
                        "search_duration_ms": duration_ms,
                    }
                },
                upsert=True,
            )
        except Exception as e:
            logger.warning(f"Error creating cache entry: {e}")

    # =========================================================================
    # Index Query Methods
    # =========================================================================

    def query_index(
        self,
        query: Optional[str] = None,
        sources: Optional[List[str]] = None,
        regions: Optional[List[str]] = None,
        remote_only: bool = False,
        promoted: Optional[bool] = None,
        include_hidden: bool = False,
        min_score: Optional[int] = None,
        sort_by: str = "discovered_at",
        sort_order: str = "desc",
        offset: int = 0,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """
        Query the job search index with filters.

        Args:
            query: Full-text search query
            sources: Filter by sources
            regions: Filter by regions
            remote_only: Only remote jobs
            promoted: Filter by promotion status (True/False/None=all)
            include_hidden: Include hidden jobs
            min_score: Minimum quick score
            sort_by: Sort field
            sort_order: "asc" or "desc"
            offset: Pagination offset
            limit: Results per page (max 100)

        Returns:
            Dictionary with jobs, total count, and facets
        """
        # Build filter
        filter_query = {}

        if query:
            filter_query["$text"] = {"$search": query}

        if sources:
            filter_query["source"] = {"$in": sources}

        if regions:
            filter_query["region"] = {"$in": regions}

        if remote_only:
            filter_query["is_remote"] = True

        if promoted is not None:
            filter_query["promoted_to_level2"] = promoted

        if not include_hidden:
            filter_query["hidden"] = {"$ne": True}

        if min_score is not None:
            filter_query["quick_score"] = {"$gte": min_score}

        # Build sort
        sort_direction = DESCENDING if sort_order == "desc" else ASCENDING
        sort_spec = [(sort_by, sort_direction)]

        # Execute query
        limit = min(limit, 100)  # Cap at 100

        jobs = list(
            self.index.find(filter_query, {"description": 0})
            .sort(sort_spec)
            .skip(offset)
            .limit(limit)
        )

        # Convert ObjectIds
        for job in jobs:
            job["job_id"] = str(job.pop("_id"))

        # Get total count
        total = self.index.count_documents(filter_query)

        # Get facets
        facets = self._get_facets(filter_query)

        return {
            "jobs": jobs,
            "total": total,
            "facets": facets,
            "pagination": {
                "offset": offset,
                "limit": limit,
                "has_more": offset + len(jobs) < total,
            },
        }

    def _get_facets(self, base_filter: dict) -> Dict[str, Dict[str, int]]:
        """Get facet counts for filtering."""
        try:
            # Source facets
            source_pipeline = [
                {"$match": base_filter},
                {"$group": {"_id": "$source", "count": {"$sum": 1}}},
            ]
            source_results = list(self.index.aggregate(source_pipeline))
            by_source = {r["_id"]: r["count"] for r in source_results if r["_id"]}

            # Region facets
            region_pipeline = [
                {"$match": base_filter},
                {"$group": {"_id": "$region", "count": {"$sum": 1}}},
            ]
            region_results = list(self.index.aggregate(region_pipeline))
            by_region = {r["_id"]: r["count"] for r in region_results if r["_id"]}

            # Remote facets
            remote_pipeline = [
                {"$match": base_filter},
                {"$group": {"_id": "$is_remote", "count": {"$sum": 1}}},
            ]
            remote_results = list(self.index.aggregate(remote_pipeline))
            by_remote = {}
            for r in remote_results:
                key = "remote" if r["_id"] else "onsite"
                by_remote[key] = r["count"]

            return {
                "by_source": by_source,
                "by_region": by_region,
                "by_remote": by_remote,
            }
        except Exception as e:
            logger.warning(f"Error getting facets: {e}")
            return {"by_source": {}, "by_region": {}, "by_remote": {}}

    # =========================================================================
    # Job Actions
    # =========================================================================

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get a single job by ID with full details."""
        try:
            job = self.index.find_one({"_id": ObjectId(job_id)})
            if job:
                job["job_id"] = str(job.pop("_id"))
            return job
        except Exception as e:
            logger.error(f"Error getting job {job_id}: {e}")
            return None

    def promote_job(self, job_id: str, tier: Optional[str] = None) -> Dict[str, Any]:
        """
        Promote a job from the index to level-2 for pipeline processing.

        Args:
            job_id: Job ID in the index
            tier: Optional tier override

        Returns:
            Dictionary with promotion result
        """
        try:
            # Get job from index
            job = self.index.find_one({"_id": ObjectId(job_id)})
            if not job:
                return {"success": False, "error": "Job not found"}

            if job.get("promoted_to_level2"):
                return {
                    "success": False,
                    "error": "Job already promoted",
                    "level2_job_id": str(job.get("promoted_job_id")),
                }

            # Create level-2 document
            now = datetime.utcnow()
            level2_doc = {
                "company": job.get("company"),
                "title": job.get("title"),
                "location": job.get("location"),
                "jobUrl": job.get("url"),
                "description": job.get("description"),
                "dedupeKey": job.get("dedupeKey"),
                "createdAt": now,
                "status": "not processed",
                "source": f"{job.get('source')}_promoted",
                "auto_discovered": False,
                "quick_score": job.get("quick_score"),
                "quick_score_rationale": job.get("quick_score_rationale"),
                "tier": tier or self._derive_tier(job.get("quick_score")),
                "salary": job.get("salary"),
                "jobType": job.get("job_type"),
                "postedDate": job.get("posted_date"),
                "sourceId": job.get("source_id"),
                "promoted_from_index": True,
                "index_job_id": ObjectId(job_id),
            }

            # Insert into level-2
            result = self.level2.insert_one(level2_doc)
            level2_id = result.inserted_id

            # Update index job
            self.index.update_one(
                {"_id": ObjectId(job_id)},
                {
                    "$set": {
                        "promoted_to_level2": True,
                        "promoted_at": now,
                        "promoted_job_id": level2_id,
                    }
                },
            )

            return {
                "success": True,
                "index_job_id": job_id,
                "level2_job_id": str(level2_id),
                "tier": level2_doc.get("tier"),
            }

        except Exception as e:
            logger.error(f"Error promoting job {job_id}: {e}")
            return {"success": False, "error": str(e)}

    def hide_job(self, job_id: str) -> Dict[str, Any]:
        """Hide a job from future search results."""
        try:
            result = self.index.update_one(
                {"_id": ObjectId(job_id)},
                {
                    "$set": {
                        "hidden": True,
                        "hidden_at": datetime.utcnow(),
                    }
                },
            )

            if result.modified_count > 0:
                return {"success": True, "job_id": job_id, "hidden": True}
            else:
                return {"success": False, "error": "Job not found or already hidden"}

        except Exception as e:
            logger.error(f"Error hiding job {job_id}: {e}")
            return {"success": False, "error": str(e)}

    def unhide_job(self, job_id: str) -> Dict[str, Any]:
        """Unhide a previously hidden job."""
        try:
            result = self.index.update_one(
                {"_id": ObjectId(job_id)},
                {
                    "$set": {
                        "hidden": False,
                        "hidden_at": None,
                    }
                },
            )

            if result.modified_count > 0:
                return {"success": True, "job_id": job_id, "hidden": False}
            else:
                return {"success": False, "error": "Job not found"}

        except Exception as e:
            logger.error(f"Error unhiding job {job_id}: {e}")
            return {"success": False, "error": str(e)}

    def _derive_tier(self, score: Optional[int]) -> str:
        """Derive tier from quick score."""
        if score is None:
            return "Unscored"
        if score >= 85:
            return "Tier A"
        if score >= 70:
            return "Tier B+"
        if score >= 55:
            return "Tier B"
        return "Tier C"

    # =========================================================================
    # Cache Management
    # =========================================================================

    def clear_cache(self) -> Dict[str, Any]:
        """Clear all cache entries."""
        try:
            result = self.cache.delete_many({})
            return {
                "success": True,
                "cleared_count": result.deleted_count,
            }
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return {"success": False, "error": str(e)}

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        try:
            total = self.cache.count_documents({})
            active = self.cache.count_documents({"expires_at": {"$gt": datetime.utcnow()}})

            return {
                "total_entries": total,
                "active_entries": active,
                "expired_entries": total - active,
            }
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {"error": str(e)}

    def get_index_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        try:
            total = self.index.count_documents({})
            promoted = self.index.count_documents({"promoted_to_level2": True})
            hidden = self.index.count_documents({"hidden": True})
            scored = self.index.count_documents({"quick_score": {"$ne": None}})

            return {
                "total_jobs": total,
                "promoted": promoted,
                "hidden": hidden,
                "scored": scored,
                "active": total - hidden,
            }
        except Exception as e:
            logger.error(f"Error getting index stats: {e}")
            return {"error": str(e)}
