"""Pydantic models for iteration-4.1 blueprint artifacts and snapshot allow-list."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.layer1_4.claude_jd_extractor import (
    CandidateArchetype,
    CompetencyWeightsModel,
    ExtractedJDModel,
    IdealCandidateProfileModel,
    RemotePolicy,
    RoleCategory,
    SeniorityLevel,
)


class EvidenceRef(BaseModel):
    source: str
    locator: str | None = None
    quote: str | None = None


class DeterministicField(BaseModel):
    value: Any
    locator: str | None = None


class JDJudgeAddition(BaseModel):
    field: str
    value: Any
    evidence_span: EvidenceRef
    confidence: Literal["high", "medium", "low"] = "high"


class JDJudgeFlag(BaseModel):
    field: str
    deterministic_value: Any | None = None
    proposed_value: Any | None = None
    severity: Literal["info", "warn", "blocking"] = "warn"
    reasoning: str
    evidence_span: EvidenceRef
    confidence: Literal["high", "medium", "low"] = "medium"


def _normalize_slug(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
    else:
        items = [str(item).strip() for item in value]
    return [item for item in items if item]


class JDFactsExtractionOutput(ExtractedJDModel):
    """Runner-parity extraction output with preenrich-only transport extras."""

    salary_range: str | None = None
    application_url: str | None = None

    @field_validator("role_category", mode="before")
    @classmethod
    def normalize_role_category(cls, value: Any) -> Any:
        return _normalize_slug(value)

    @field_validator("seniority_level", mode="before")
    @classmethod
    def normalize_seniority_level(cls, value: Any) -> Any:
        return _normalize_slug(value)

    @field_validator("remote_policy", mode="before")
    @classmethod
    def normalize_remote_policy(cls, value: Any) -> Any:
        return _normalize_slug(value)

    @field_validator("responsibilities", "qualifications", "nice_to_haves", "technical_skills", "soft_skills", "implied_pain_points", "success_metrics", "top_keywords", mode="before")
    @classmethod
    def normalize_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @field_validator("ideal_candidate_profile", mode="before")
    @classmethod
    def normalize_ideal_candidate_profile(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        if "archetype" in payload:
            payload["archetype"] = _normalize_slug(payload["archetype"])
        for key in ("key_traits", "culture_signals"):
            if key in payload:
                payload[key] = _normalize_string_list(payload[key])
        return payload

    def to_compat_projection(self) -> dict[str, Any]:
        """Compatibility projection for level-2.extracted_jd consumers."""
        extracted = self.to_extracted_jd()
        extracted["company_name"] = self.company
        extracted["required_qualifications"] = list(self.qualifications)
        extracted["key_responsibilities"] = list(self.responsibilities)
        if self.salary_range:
            extracted["salary"] = self.salary_range
        return extracted


class JDFactsDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    level2_job_id: str
    jd_text_hash: str
    extractor_version: str
    judge_prompt_version: str
    deterministic: dict[str, Any] = Field(default_factory=dict)
    llm_additions: list[JDJudgeAddition] = Field(default_factory=list)
    llm_flags: list[JDJudgeFlag] = Field(default_factory=list)
    confirmations: dict[str, bool] = Field(default_factory=dict)
    extraction: JDFactsExtractionOutput | None = None
    merged_view: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, str] = Field(default_factory=dict)


class ClassificationDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_role_category: str
    secondary_role_categories: list[str] = Field(default_factory=list)
    search_profiles: list[str] = Field(default_factory=list)
    selector_profiles: list[str] = Field(default_factory=list)
    tone_family: str
    taxonomy_version: str
    ambiguity_score: float = 0.0
    ai_relevance: dict[str, Any] = Field(default_factory=dict)


class CompanyProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_name: str | None = None
    company_type: str | None = None
    summary: str | None = None
    url: str | None = None
    signals: list[dict[str, Any]] = Field(default_factory=list)


class ResearchEnrichmentDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    level2_job_id: str
    jd_facts_id: str
    research_input_hash: str
    prompt_version: str
    status: Literal["completed", "skipped", "no_research", "unresolved"] = "completed"
    capability_flags: dict[str, Any] = Field(default_factory=dict)
    company_profile: CompanyProfile = Field(default_factory=CompanyProfile)
    sources: list[EvidenceRef] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ApplicationSurfaceDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["resolved", "unresolved", "ambiguous", "skipped"] = "resolved"
    job_url: str | None = None
    application_url: str | None = None
    portal_family: str | None = None
    is_direct_apply: bool = False
    friction_signals: list[str] = Field(default_factory=list)
    candidates: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class InferenceField(BaseModel):
    field: str
    value: Any
    confidence: Literal["high", "medium"] = "medium"
    evidence_spans: list[EvidenceRef] = Field(default_factory=list)


class JobInferenceDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    level2_job_id: str
    jd_facts_id: str
    research_enrichment_id: str | None = None
    prompt_version: str
    taxonomy_version: str
    primary_role_category: str
    tone_family: str
    semantic_role_model: dict[str, Any] = Field(default_factory=dict)
    company_model: dict[str, Any] = Field(default_factory=dict)
    qualifications: dict[str, Any] = Field(default_factory=dict)
    application_surface: ApplicationSurfaceDoc = Field(default_factory=ApplicationSurfaceDoc)
    inferences: list[InferenceField] = Field(default_factory=list)


class JobHypothesis(BaseModel):
    field: str
    value: Any
    confidence: Literal["low"] = "low"
    reasoning: str
    source_hints: list[str] = Field(default_factory=list)


class JobHypothesesDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    level2_job_id: str
    jd_facts_id: str
    research_enrichment_id: str | None = None
    prompt_version: str
    taxonomy_version: str
    hypotheses: list[JobHypothesis] = Field(default_factory=list)


class GuidelineBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    bullets: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)

    @field_validator("evidence_refs")
    @classmethod
    def validate_evidence_refs(cls, value: list[EvidenceRef]) -> list[EvidenceRef]:
        if not value:
            raise ValueError("guideline blocks require evidence references")
        return value


class CVGuidelinesDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    level2_job_id: str
    jd_facts_id: str
    job_inference_id: str
    research_enrichment_id: str | None = None
    prompt_version: str
    title_guidance: GuidelineBlock
    identity_guidance: GuidelineBlock
    bullet_theme_guidance: GuidelineBlock
    ats_keyword_guidance: GuidelineBlock
    cover_letter_expectations: GuidelineBlock
    skills_guidance: list[GuidelineBlock] = Field(default_factory=list)
    challenges_guidance: list[GuidelineBlock] = Field(default_factory=list)


class JobBlueprintSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classification: dict[str, Any]
    application_surface: dict[str, Any]
    company_research: dict[str, Any]
    role_research: dict[str, Any]
    cv_guidelines: dict[str, Any]
    pain_points: list[str] = Field(default_factory=list)
    strategic_needs: list[str] = Field(default_factory=list)
    risks_if_unfilled: list[str] = Field(default_factory=list)
    success_metrics: list[str] = Field(default_factory=list)
    ats_keywords: list[str] = Field(default_factory=list)
    title_guidance: str | None = None
    identity_guidance: str | None = None
    bullet_guidance: list[str] = Field(default_factory=list)
    cover_letter_expectations: list[str] = Field(default_factory=list)


class JobBlueprintDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    level2_job_id: str
    blueprint_version: str
    taxonomy_version: str
    jd_facts_id: str
    job_inference_id: str
    research_enrichment_id: str | None = None
    application_surface: ApplicationSurfaceDoc
    cv_guidelines_id: str
    job_hypotheses_id: str | None = None
    snapshot: JobBlueprintSnapshot
    compatibility_projection: dict[str, Any] = Field(default_factory=dict)
