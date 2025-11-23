# Project Evaluation Prompt for AI Code Review

## Context
This is a **7-layer LangGraph job intelligence pipeline** that automates hyper-personalized job application preparation. It replaces a manual n8n workflow with a Python-based system.

## System Role / Perspective
Act as an auditor and my best wisher, giving me tough love and helping organize this complete system. Act also as an expert CV reviewer and as the hiring manager at my next company. Judge the job intelligence pipeline, analyze it using `architecture.md`, `ROADMAP.md`, and `feedback.md`. Give me the best and most strategic feedback to keep quality high, enable hyper-personalization, minimize hallucinations at scale, and achieve a dossier better than `sample-dosier.txt` in the end. Assume this should work for every job and scale up to 100–200 jobs per day. Propose ways to improve and extract maximum value from my available time, and design a system that makes the hiring manager on the other end in awe and already biased toward hiring me.

## Your Task
Please analyze this entire codebase and provide:

1. **Code Quality Rating** (1-10 scale for each):
   - Architecture design and pattern usage
   - Code organization and modularity
   - Error handling and resilience
   - Testing coverage and approach
   - Documentation quality
   - Production readiness
   - Scalability potential
   - Personalization depth

2. **High-Level Assessment**:
   - Is this pipeline suitable for processing 50+ jobs/day at scale?
   - How effective is the hyper-personalization (using STAR records from `knowledge-base.md`)?
   - Are the outputs (dossier, cover letter, CV) truly tailored or generic?
   - What's the quality gap vs. the original n8n workflow (see `sample-dossier.txt` for reference)?

3. **Technical Architecture Review**:
   - Evaluate the 7-layer design (see `architecture.md`)
   - Assess LangGraph usage vs. alternatives
   - Review integration approach (MongoDB, FireCrawl, OpenAI, Google APIs)
   - Identify architectural strengths and weaknesses

4. **Scalability Analysis**:
   - Can this handle 100+ jobs/day?
   - What are the bottlenecks? (LLM calls, scraping, database, etc.)
   - Cost projection for processing 1000 jobs/month
   - Recommendations for optimization

5. **Personalization Effectiveness**:
   - How well does it leverage the STAR records?
   - Does Layer 4 (Opportunity Mapper) create genuine job-candidate fit analysis?
   - Are cover letters truly personalized or template-based?
   - Suggestions to increase personalization depth

6. **Improvement Recommendations**:
   - **Critical**: Must-fix issues before production
   - **High Priority**: Important enhancements for next sprint
   - **Medium Priority**: Nice-to-have improvements
   - **Low Priority**: Future considerations

7. **Update AGENTS.md**:
   - Document your evaluation findings
   - Add recommended agent/workflow improvements
   - Suggest new LangGraph nodes or layers if needed

---

## What to Analyze

### **Core Files**
- `src/workflow.py` - Main LangGraph orchestration
- `src/layer*/` - All 7 layer implementations
- `src/common/state.py` - State schema
- `src/common/config.py` - Configuration

### **Scripts**
- `scripts/run_pipeline.py` - CLI entry point
- `scripts/list_jobs.py` - Job discovery
- `scripts/test_layer*.py` - Test suite

### **Documentation**
- `architecture.md` - System design
- `ROADMAP.md` - Project phases
- `goal-16-nov.md` - Today's scope
- `PROGRESS.md` - Implementation status
- `knowledge-base.md` - Candidate STAR records (11 detailed achievements)
- `sample-dossier.txt` - Reference output format

### **Key Questions to Answer**

#### **1. Personalization Quality**
- Does the pipeline use the 11 STAR records effectively?
- Are pain points mapped to specific candidate achievements?
- Is the fit scoring (0-100) meaningful or superficial?
- Do cover letters reference concrete candidate accomplishments?

#### **2. Scalability Assessment**
- Current pipeline takes ~30 seconds per job
- How many concurrent jobs can it handle?
- What's the cost per job at current LLM usage?
- Can it process 50 jobs/day within budget constraints?

#### **3. Output Quality**
- Compare generated outputs to `sample-dossier.txt` (the gold standard)
- Rate completeness: Today generates ~40% of the full dossier
- Is the simplified version (Phase 1.2) good enough for actual applications?
- What's missing vs. the n8n workflow?

#### **4. Architecture Soundness**
- Is LangGraph the right choice vs. alternatives (Prefect, Temporal, plain orchestration)?
- Are layers properly decoupled?
- Is error handling robust enough for production?
- Does the state schema scale to full dossier requirements?

#### **5. Integration Quality**
- FireCrawl integration: Effective or could be improved?
- MongoDB schema: Well-designed for job storage and retrieval?
- Google APIs: Proper usage or workarounds needed?
- LangSmith: Adequate observability?

#### **6. Code Quality**
- Is TDD approach (Layers 4, 6, 7) consistent?
- Are prompts well-engineered or brittle?
- Error handling: Graceful degradation working properly?
- Type safety: Good use of TypedDict for JobState?

#### **7. Production Readiness**
- What's needed to deploy this to a VPS?
- Are credentials and secrets handled securely?
- Logging and monitoring sufficient?
- Retry logic and fault tolerance adequate?

---

## Specific Evaluation Criteria

### **Rating Scale (1-10)**

#### **Architecture (Weight: 25%)**
- Layer separation and cohesion
- State management design
- Event flow and dependencies
- Extensibility for new features

#### **Personalization (Weight: 30%)**
- STAR record utilization
- Candidate-job matching depth
- Output customization quality
- Uniqueness of generated content

#### **Scalability (Weight: 20%)**
- Throughput capacity
- Cost efficiency
- Resource utilization
- Bottleneck identification

#### **Code Quality (Weight: 15%)**
- Readability and maintainability
- Test coverage and quality
- Error handling robustness
- Documentation completeness

#### **Production Readiness (Weight: 10%)**
- Security practices
- Monitoring and observability
- Deployment readiness
- Operational considerations

---

## Comparison Benchmark

**Original n8n Workflow (sample-dossier.txt) includes:**
- ✅ 10-section comprehensive dossier
- ✅ Company signals (funding, acquisitions, growth)
- ✅ Hiring reasoning and timing analysis
- ✅ People Mapper (8-12 LinkedIn contacts with personalized outreach EACH)
- ✅ Per-person LinkedIn messages and email templates
- ✅ Strategic pain point analysis (needs, risks, success metrics)
- ✅ Validation metadata
- ✅ FireCrawl query logging

**Current LangGraph Pipeline (Phase 1.2) generates:**
- ✅ 5 pain points (basic bullets)
- ✅ 2-3 sentence company summary
- ✅ Fit score (0-100) + 2-3 sentence rationale
- ✅ Simple 3-paragraph cover letter
- ✅ Basic tailored CV (.docx)
- ✅ Google Sheets tracking
- ❌ No people mapper
- ❌ No company signals or timing analysis
- ❌ No hiring reasoning
- ❌ No per-person outreach

**Gap Analysis Required:**
- What % of the full dossier functionality is implemented?
- How hard to reach feature parity with n8n?
- Is the simplified version valuable for actual job applications?
- What's the minimum viable product for real-world use?

---

## Output Format

Please structure your evaluation as:

```markdown
# Project Evaluation: Job Intelligence Pipeline

## Executive Summary
[2-3 paragraph overview]

## Ratings (1-10 scale)
- Architecture: X/10
- Personalization: X/10
- Scalability: X/10
- Code Quality: X/10
- Production Readiness: X/10
- **Overall Score: X/10**

## Detailed Analysis

### 1. Architecture Review
[Analysis]

### 2. Personalization Effectiveness
[Analysis]

### 3. Scalability Assessment
[Analysis with cost projections]

### 4. Code Quality
[Analysis]

### 5. Production Readiness
[Analysis]

### 6. Gap Analysis (vs. n8n Workflow)
[Comparison table]

### 7. Improvement Recommendations

#### Critical (Must-Fix)
- [ ] Issue 1
- [ ] Issue 2

#### High Priority
- [ ] Enhancement 1
- [ ] Enhancement 2

#### Medium Priority
- [ ] Improvement 1

#### Low Priority
- [ ] Nice-to-have 1

## AGENTS.md Updates
[Suggested content for AGENTS.md]

## Conclusion
[Final assessment and go/no-go recommendation]
```

---

## Key Files to Examine

### **Implementation Quality**
```
src/layer2/pain_point_miner.py       - LLM prompt engineering
src/layer3/company_researcher.py     - FireCrawl integration + LLM
src/layer4/opportunity_mapper.py     - Fit scoring logic
src/layer6/generator.py              - Cover letter + CV generation
src/layer7/output_publisher.py       - Google APIs integration
```

### **Prompts to Review**
Check these for quality:
- Layer 2: Pain point extraction prompt
- Layer 3: Company summarization prompt
- Layer 4: Fit scoring prompt (references STAR records?)
- Layer 6: Cover letter generation prompt (personalization depth?)

### **Test Coverage**
```
scripts/test_layer2.py
scripts/test_layer3.py
scripts/test_layer4.py
scripts/test_layer6.py
scripts/test_layer7.py
```
Are these comprehensive? What's missing?

### **Configuration**
```
src/common/config.py    - Is configuration flexible enough?
.env.example            - Are all required vars documented?
```

---

## Special Focus Areas

### **1. STAR Record Usage**
The `knowledge-base.md` contains 11 detailed STAR records. Evaluate:
- Does Layer 4 actually reference specific STAR records?
- Are achievements mapped to job pain points?
- Do cover letters cite concrete examples from STAR records?
- **Or is personalization superficial?**

### **2. LLM Prompt Quality**
Review all prompts for:
- Clarity and specificity
- Few-shot examples usage
- Output format enforcement
- Temperature settings appropriateness
- Token efficiency

### **3. Error Resilience**
Check:
- Retry logic (tenacity usage)
- Graceful degradation (Layer 7 file upload failures)
- Error propagation through state
- Logging and debugging capabilities

### **4. Cost Analysis**
Calculate costs:
- Tokens per layer (Layer 2: ~1500, Layer 3: ~800, Layer 4: ~1200, Layer 6: ~2000)
- Total tokens per job: ~5500 tokens
- Cost per job with GPT-4o: ~$0.10-0.15
- Cost for 1000 jobs/month: $100-150
- **Is this sustainable?**

---

## Deliverables

1. **Evaluation Report** (markdown format above)
2. **Updated AGENTS.md** with findings and recommendations
3. **Improvement Roadmap** prioritized by impact
4. **Go/No-Go Decision** for production deployment
5. **Cost-Benefit Analysis** vs. manual application process

---

## Additional Context

**Developer's Goal:**
- Process 3,135 jobs from MongoDB `level-2` collection
- Generate hyper-personalized applications at scale
- Maintain high quality matching n8n workflow
- Deploy to VPS for automated daily processing
- Target: 50 jobs/day throughput

**Current Status:**
- Phase 1.2 COMPLETE (basic vertical slice working)
- Successfully processed real MongoDB job
- All integrations functional (MongoDB, FireCrawl, OpenAI, Google APIs)
- LangSmith tracing active
- ~40% of full dossier functionality implemented

**Known Limitations:**
- Google Drive file uploads fail (service account quota)
- No People Mapper (Layer 5) yet
- Simplified outputs vs. full dossier
- No batch processing yet
- No company signals or timing analysis

---

## Success Metrics

Rate the pipeline on:
- **Effectiveness**: Will this get interviews for targeted roles?
- **Efficiency**: Can it process enough jobs to find good matches?
- **Quality**: Are outputs professional and compelling?
- **Scalability**: Can it grow to 100+ jobs/day?
- **Maintainability**: Can it be extended to full dossier format?

**Final Question:** Would you trust this pipeline to apply for your dream job?

---

## Bonus Analysis (If Time)

- Suggest alternative architectures (Prefect, Temporal, plain async)
- Recommend specific LLM models per layer (GPT-4o vs. 4o-mini vs. Claude)
- Propose caching strategies (company research, candidate profiles)
- Design batch processing approach
- Outline deployment architecture (Docker, VPS, monitoring)

---

**Start your analysis by reading the entire codebase, then provide the comprehensive evaluation above.**

---

## Tasks for This Evaluation
- [ ] Review current pipeline docs and samples  
- [ ] Draft professional evaluation prompt into `EVAL_PROMPT.md`  
- [ ] Design improvements for quality and personalization at scale  
- [ ] Summarize tough-love feedback and next actions  
