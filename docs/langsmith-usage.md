# LangSmith Observability Guide

## What is LangSmith?

LangSmith is LangChain's observability and debugging platform that automatically traces your LangGraph pipeline execution. It captures every layer execution, LLM call, timing, inputs, outputs, and errors.

## Accessing Your Traces

### 1. **LangSmith Dashboard**
Your pipeline traces are automatically sent to LangSmith (configured in `.env`):

```bash
# From your .env file
LANGSMITH_API_KEY=lsv2_pt_...
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=job-intelligence-pipeline
```

### 2. **View Traces Online**
1. Go to: **https://smith.langchain.com/**
2. Sign in with your account
3. Navigate to your project: **"job-intelligence-pipeline"**
4. You'll see a list of all pipeline runs

---

## Understanding Your Pipeline Traces

### **Trace Structure**

Each pipeline run shows:
```
Pipeline Run (root)
├── Layer 2: Pain-Point Miner
│   ├── LLM Call (GPT-4o)
│   │   ├── Input: Job description
│   │   ├── Output: Pain points list
│   │   └── Latency: 2.3s
│   └── Processing time: 2.5s
├── Layer 3: Company Researcher
│   ├── FireCrawl Scrape
│   ├── LLM Call (GPT-4o)
│   └── Processing time: 3.1s
├── Layer 4: Opportunity Mapper
│   ├── LLM Call (GPT-4o)
│   └── Processing time: 2.8s
├── Layer 6: Generator
│   ├── LLM Call (Cover Letter)
│   └── Processing time: 3.5s
└── Layer 7: Publisher
    └── Processing time: 1.2s

Total Duration: 13.1s
```

---

## Key Features

### **1. Performance Analysis**

**Find Slow Layers:**
- Click on any run to see layer-by-layer timing
- Look for layers with high latency (>5s)
- Identify bottlenecks (usually LLM calls or FireCrawl)

**Example:**
```
Layer 3 taking 8 seconds?
→ Check if FireCrawl is slow or timing out
→ Consider caching company research results
```

### **2. Debugging Errors**

**Error Traces:**
- Failed runs are marked in red
- Click to see full error stack trace
- View exact input that caused the failure

**Example Error Investigation:**
```
Layer 2 failed?
→ Click on the failed layer
→ See the exact job description that caused parsing issues
→ View the LLM response that couldn't be parsed
→ Fix prompt or parsing logic
```

### **3. Viewing Inputs/Outputs**

**Layer Details:**
Each layer shows:
- **Input State**: What data the layer received
- **Output Updates**: What the layer produced
- **LLM Prompts**: Exact prompts sent to GPT-4
- **LLM Responses**: Full responses from the model

**Example Workflow:**
```
1. Click on "Layer 2: Pain-Point Miner"
2. See "Input" tab → View job description
3. See "Output" tab → View extracted pain points
4. See "Metadata" → View model used (gpt-4o), temperature (0.3), tokens used
```

### **4. Cost Tracking**

LangSmith tracks:
- **Token Usage**: Input + output tokens per LLM call
- **Cost**: Estimated cost per run (based on OpenAI pricing)
- **Total Spend**: Aggregate costs across all runs

**Example:**
```
Pipeline Run #42:
├── Total Tokens: 8,234
├── Estimated Cost: $0.12
└── LLM Calls: 4
```

---

## Common Use Cases

### **Use Case 1: Pipeline is Slow**

**Steps:**
1. Open LangSmith dashboard
2. Find a slow run (>20s)
3. Expand the trace tree
4. Identify which layer took the most time
5. Optimize that layer (caching, faster model, etc.)

**Example Finding:**
```
Layer 3 (Company Researcher): 12s
→ FireCrawl scraping taking 10s
→ Solution: Cache company summaries by company name
```

### **Use Case 2: Pipeline Failed**

**Steps:**
1. Filter traces by "Status: Error"
2. Click on failed run
3. See which layer failed
4. View error message and stack trace
5. Check input data that caused failure

**Example Error:**
```
Layer 4 failed with: "fit_score is missing"
→ Check Layer 4 code
→ See that LLM response parsing failed
→ Improve regex pattern or prompt format
```

### **Use Case 3: Verifying Quality**

**Steps:**
1. Open a successful run
2. Navigate to Layer 4 (Opportunity Mapper)
3. View the LLM prompt sent
4. View the fit score and rationale generated
5. Verify quality meets expectations

**Example Check:**
```
Job: Software Architect at talent wins
Candidate: Marketing professional (Alex Thompson)
Fit Score: 30/100 ✅ (correctly identified poor match)
Rationale: "marketing professional... not aligned with software architecture" ✅
```

### **Use Case 4: A/B Testing Prompts**

**Compare Two Runs:**
1. Run pipeline with Prompt V1
2. Note the run ID or timestamp
3. Modify prompt, run again with Prompt V2
4. Compare outputs side-by-side in LangSmith
5. Choose better performing prompt

**Example:**
```
Prompt V1: "Extract pain points..."
→ Generated 3 pain points

Prompt V2: "Extract 5 specific pain points with business context..."
→ Generated 5 detailed pain points ✅ Better!
```

---

## Dashboard Navigation

### **Main View**
- **Runs List**: All pipeline executions
- **Filter by**: Date, status (success/error), duration
- **Search**: Find runs by job ID or company name

### **Run Detail View**
- **Trace Tree**: Hierarchical view of all layers
- **Timeline**: Visual timeline of execution
- **Inputs/Outputs**: Full state at each step
- **Metadata**: Model configs, tokens, costs

### **Filters**
```
Status: [All | Success | Error]
Date: [Last hour | Last 24h | Last 7 days | Custom]
Duration: [< 10s | 10-30s | > 30s]
Tags: [job_id, company_name, etc.]
```

---

## Tips for Effective Monitoring

### **1. Tag Your Runs**
Add metadata to identify runs:
```python
# In your pipeline code
langsmith_extra = {
    "metadata": {
        "job_id": state["job_id"],
        "company": state["company"],
        "fit_score": state.get("fit_score")
    }
}
```

### **2. Set Alerts**
Configure LangSmith alerts for:
- Pipeline failures
- Runs exceeding 30s duration
- High token costs (>1000 tokens/run)

### **3. Regular Review**
- **Weekly**: Review average latency per layer
- **After Changes**: Compare performance before/after
- **Cost Monitoring**: Track spend trends over time

### **4. Debug Locally with Traces**
When debugging, find the trace URL:
```
Pipeline complete! View trace:
https://smith.langchain.com/o/.../projects/p/.../runs/r/...
```
Open the URL to see exactly what happened.

---

## Accessing LangSmith Programmatically

### **Get Run Statistics**
```python
from langsmith import Client

client = Client()

# Get all runs for your project
runs = client.list_runs(
    project_name="job-intelligence-pipeline",
    start_time=datetime.now() - timedelta(days=7)
)

for run in runs:
    print(f"Job: {run.metadata.get('job_id')}")
    print(f"Duration: {run.duration_ms}ms")
    print(f"Status: {run.status}")
```

### **Analyze Trends**
```python
# Find slowest layers
runs = client.list_runs(project_name="job-intelligence-pipeline")
layer_times = {}

for run in runs:
    for child in run.child_runs:
        layer = child.name
        duration = child.duration_ms
        layer_times.setdefault(layer, []).append(duration)

# Calculate averages
for layer, times in layer_times.items():
    avg = sum(times) / len(times)
    print(f"{layer}: {avg:.0f}ms average")
```

---

## Example: Debugging Session

### **Scenario:** Pipeline generated poor fit score for a good match

**Investigation Steps:**

1. **Find the Run**
   - Go to LangSmith dashboard
   - Search for job_id: 4335713702
   - Open the run

2. **Check Layer 4 (Opportunity Mapper)**
   - Click "Layer 4: Opportunity Mapper"
   - View "Inputs" tab:
     - Did it receive pain_points? ✅
     - Did it receive company_summary? ✅
     - Did it receive candidate_profile? ✅

3. **Examine LLM Call**
   - See the exact prompt sent to GPT-4
   - Check if prompt is clear and specific
   - View the raw LLM response

4. **Identify Issue**
   - LLM response: "SCORE: 30"
   - Why? Prompt says: "candidate is a marketing professional"
   - But job needs: "software architect"
   - **Root Cause:** Wrong candidate profile loaded!

5. **Fix**
   - Update `knowledge-base.md` with correct profile
   - Re-run pipeline
   - Verify new fit score is accurate

---

## Advanced Features

### **Comparing Runs**
1. Select 2+ runs with checkboxes
2. Click "Compare"
3. See side-by-side differences in:
   - Execution time
   - Outputs
   - Token usage

### **Exporting Data**
- Export runs as JSON for analysis
- Download trace data for auditing
- Integrate with BI tools

### **Playgrounds**
- Test prompts interactively
- Modify inputs and see outputs
- Iterate quickly without running full pipeline

---

## Troubleshooting

### **Issue: No traces appearing**

**Check:**
```bash
# Verify environment variables
cat .env | grep LANGSMITH

# Should see:
LANGSMITH_API_KEY=lsv2_pt_...
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=job-intelligence-pipeline
```

**Solution:**
- Ensure variables are set before running pipeline
- Check LangSmith API key is valid
- Verify network connectivity

### **Issue: Traces incomplete**

**Cause:** Layer failed before completing

**Solution:**
- Check error logs
- View partial trace in LangSmith
- Fix failing layer

### **Issue: High costs**

**Analysis:**
- Check token usage per layer
- Identify layers with excessive tokens
- Consider cheaper models (gpt-4o-mini) for simple tasks

---

## Next Steps

1. **Run a pipeline** and get the trace URL
2. **Open LangSmith** and explore the trace
3. **Identify bottlenecks** in your pipeline
4. **Optimize** based on insights
5. **Monitor trends** over multiple runs

**Your LangSmith Project URL:**
```
https://smith.langchain.com/
→ Projects
→ job-intelligence-pipeline
```

---

## Resources

- **LangSmith Docs**: https://docs.smith.langchain.com/
- **LangGraph Observability**: https://langchain-ai.github.io/langgraph/how-tos/observability/
- **Best Practices**: https://docs.smith.langchain.com/observability/best-practices

---

**Remember:** Every time you run `python scripts/run_pipeline.py`, a trace is automatically created in LangSmith. No extra code needed! 🎉
