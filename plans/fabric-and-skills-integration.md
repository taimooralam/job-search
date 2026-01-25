# Plan: Fabric & Awesome Claude Skills Integration

**Created**: 2026-01-24
**Status**: Draft
**Priority**: P2 - Enhance Claude Code Capabilities

---

## Overview

Two powerful repositories that can supercharge your Claude Code workflow:

| Repository | Purpose | Stars | Best For |
|------------|---------|-------|----------|
| [danielmiessler/Fabric](https://github.com/danielmiessler/fabric) | AI prompt patterns framework | 28k+ | Reusable prompts, CLI workflows |
| [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) | Curated Claude Skills collection | 25k+ | Ready-to-use skills, app integrations |

---

## Part 1: Fabric - AI Prompt Patterns Framework

### What Is Fabric?

Fabric is an open-source framework that solves AI's **integration problem** by providing:
- **Patterns**: Reusable AI prompts organized by task
- **CLI**: Command-line interface for applying patterns to any input
- **Multi-provider**: Works with Claude, GPT, Gemini, Ollama, etc.
- **REST API**: Integrate into any application

```
┌─────────────────────────────────────────────────────────────────┐
│                         FABRIC                                   │
│                                                                  │
│  Input (text, video, URL, clipboard)                            │
│           │                                                      │
│           ▼                                                      │
│  ┌─────────────────┐                                            │
│  │    Pattern      │ ← summarize, extract_wisdom, analyze, etc. │
│  │   (AI Prompt)   │                                            │
│  └────────┬────────┘                                            │
│           │                                                      │
│           ▼                                                      │
│  ┌─────────────────┐                                            │
│  │   AI Provider   │ ← Claude, GPT, Gemini, Ollama              │
│  └────────┬────────┘                                            │
│           │                                                      │
│           ▼                                                      │
│       Output                                                     │
└─────────────────────────────────────────────────────────────────┘
```

### Installation

```bash
# Install Fabric
go install github.com/danielmiessler/fabric@latest

# Or with pipx
pipx install fabric-ai

# Setup (configure AI providers)
fabric --setup
```

### Patterns Useful for Your Job Search Project

#### Job Search & Career

| Pattern | Description | Use Case |
|---------|-------------|----------|
| `answer_interview_question` | Generate tailored interview responses | Interview prep |
| `extract_skills` | Classify skills from job descriptions | JD analysis |
| `identify_job_stories` | Identify key job stories and requirements | Role understanding |

#### Resume/CV Writing

| Pattern | Description | Use Case |
|---------|-------------|----------|
| `improve_writing` | Refine grammar, style, clarity | Polish CV bullets |
| `create_formal_email` | Professional email structure | Outreach messages |
| `humanize` | Make AI text sound natural | CV/cover letter polish |
| `write_essay_pg` | Clear writing in Paul Graham style | Profile summary |

#### Research & Analysis

| Pattern | Description | Use Case |
|---------|-------------|----------|
| `extract_wisdom` | Extract insights from content | Company research |
| `summarize` | 20-word summary + main points | JD summarization |
| `analyze_paper` | Summarize research findings | Industry research |
| `youtube_summary` | Timestamped video summaries | Video learning |

#### Productivity

| Pattern | Description | Use Case |
|---------|-------------|----------|
| `create_recursive_outline` | Break complex tasks into steps | Project planning |
| `create_flash_cards` | Q&A flashcards | Interview prep |
| `to_flashcards` | Convert to Anki format | Spaced repetition |

### Usage Examples for Your Project

```bash
# Summarize a job description
cat job_description.txt | fabric --pattern summarize

# Extract skills from JD
cat jd.txt | fabric --pattern extract_skills

# Improve CV bullet writing
echo "Built AI pipeline for job matching" | fabric --pattern improve_writing

# Prepare for interview
echo "Tell me about a time you scaled a system" | fabric --pattern answer_interview_question

# Research a company from their about page
fabric -u https://company.com/about -p extract_wisdom

# Summarize a YouTube video about the company
fabric -y "https://youtube.com/watch?v=xxx" --pattern summarize
```

### Integrating Fabric with Claude Code

**Option 1: Call Fabric from Claude Code via Bash**

```bash
# In Claude Code, you can run:
cat data/jobs/neom-ai-lead.txt | fabric --pattern extract_skills
```

**Option 2: Create a Claude Code Skill that Uses Fabric**

```markdown
# .claude/skills/fabric-research/skill.md
---
name: fabric-research
description: Use Fabric patterns for deep research
trigger: /fabric-research
---

# Fabric Research Skill

When researching a company or role, use Fabric patterns:

1. For company website: `fabric -u [URL] -p extract_wisdom`
2. For YouTube videos: `fabric -y [URL] -p youtube_summary`
3. For job descriptions: `cat [file] | fabric -p extract_skills`

Combine outputs into a structured research report.
```

**Option 3: Fabric REST API Integration**

```python
# Start Fabric server
# fabric --serve

# Then call from Python
import requests

response = requests.post("http://localhost:8080/api/pattern", json={
    "pattern": "summarize",
    "input": "Your text here..."
})
```

---

## Part 2: Awesome Claude Skills

### What Is It?

A curated collection of **ready-to-use Claude Skills** that you can copy into your `.claude/skills/` directory.

### Skills Relevant to Your Job Search Project

#### Directly Applicable

| Skill | Description | How to Use |
|-------|-------------|------------|
| **[tailored-resume-generator](https://github.com/ComposioHQ/awesome-claude-skills/tree/master/tailored-resume-generator)** | Analyzes JDs and generates tailored resumes | Copy to `.claude/skills/` |
| **[langsmith-fetch](https://github.com/ComposioHQ/awesome-claude-skills/tree/master/langsmith-fetch)** | Debug LangGraph agents via LangSmith traces | You use LangGraph! |
| **[lead-research-assistant](https://github.com/ComposioHQ/awesome-claude-skills/tree/master/lead-research-assistant)** | Research and qualify leads | Adapt for company research |
| **[content-research-writer](https://github.com/ComposioHQ/awesome-claude-skills/tree/master/content-research-writer)** | Research + write with citations | LinkedIn posts, cover letters |
| **[meeting-insights-analyzer](https://github.com/ComposioHQ/awesome-claude-skills/tree/master/meeting-insights-analyzer)** | Analyze meeting transcripts | Interview recordings |

#### Development & Productivity

| Skill | Description | How to Use |
|-------|-------------|------------|
| **[changelog-generator](https://github.com/ComposioHQ/awesome-claude-skills/tree/master/changelog-generator)** | Generate changelogs from git | Document your pipeline |
| **[mcp-builder](https://github.com/ComposioHQ/awesome-claude-skills/tree/master/mcp-builder)** | Create MCP servers | Build custom integrations |
| **[skill-creator](https://github.com/ComposioHQ/awesome-claude-skills/tree/master/skill-creator)** | Guidance for creating skills | Make your own skills |
| **[webapp-testing](https://github.com/ComposioHQ/awesome-claude-skills/tree/master/webapp-testing)** | Test web apps with Playwright | Test your frontend |

#### App Integrations (via Composio)

| Skill | Description | How to Use |
|-------|-------------|------------|
| **[connect-apps](https://github.com/ComposioHQ/awesome-claude-skills/tree/master/connect-apps)** | Connect Claude to 500+ apps | Gmail, Slack, Notion, etc. |

### Installing Skills from awesome-claude-skills

```bash
# Clone the repo
git clone https://github.com/ComposioHQ/awesome-claude-skills.git ~/awesome-skills

# Copy a skill to your project
cp -r ~/awesome-skills/tailored-resume-generator ~/.claude/skills/

# Or to your project specifically
cp -r ~/awesome-skills/langsmith-fetch /Users/ala0001t/pers/projects/job-search/.claude/skills/
```

### Skills to Install for Your Project

**Priority 1: Immediate Value**

```bash
# LangSmith debugging (you use LangGraph!)
cp -r ~/awesome-skills/langsmith-fetch .claude/skills/

# Resume generation
cp -r ~/awesome-skills/tailored-resume-generator .claude/skills/
```

**Priority 2: Research & Content**

```bash
# Company research
cp -r ~/awesome-skills/lead-research-assistant .claude/skills/

# Content writing with citations
cp -r ~/awesome-skills/content-research-writer .claude/skills/
```

**Priority 3: Development**

```bash
# Changelog generation
cp -r ~/awesome-skills/changelog-generator .claude/skills/

# Skill creation guidance
cp -r ~/awesome-skills/skill-creator .claude/skills/
```

---

## Part 3: Combined Workflow

### Example: Deep Company Research

```
1. Use Fabric to extract wisdom from company website:
   fabric -u https://company.com/about -p extract_wisdom

2. Use Fabric to summarize YouTube videos:
   fabric -y "https://youtube.com/watch?v=xxx" -p youtube_summary

3. Use Claude Code with lead-research-assistant skill:
   /lead-research-assistant

4. Combine into company research document in your pipeline
```

### Example: CV Generation Enhancement

```
1. Use Fabric to extract skills from JD:
   cat jd.txt | fabric -p extract_skills

2. Use tailored-resume-generator skill:
   /tailored-resume-generator

3. Use Fabric to humanize/polish:
   cat cv_draft.md | fabric -p humanize

4. Use your cv-validator skill to check ATS compliance
```

### Example: Interview Preparation

```
1. Use Fabric for interview question prep:
   echo "Tell me about scaling challenges" | fabric -p answer_interview_question

2. Use meeting-insights-analyzer on practice recordings

3. Create flashcards with Fabric:
   cat company_research.md | fabric -p create_flash_cards
```

---

## Implementation Plan

### Phase 1: Install Fabric (30 min)

```bash
# Install
go install github.com/danielmiessler/fabric@latest

# Or
pipx install fabric-ai

# Setup with your API keys
fabric --setup

# List all patterns
fabric --listpatterns
```

### Phase 2: Install Key Skills (15 min)

```bash
# Clone awesome-skills
git clone https://github.com/ComposioHQ/awesome-claude-skills.git ~/awesome-skills

# Install to your project
cd /Users/ala0001t/pers/projects/job-search

# Priority skills
cp -r ~/awesome-skills/langsmith-fetch .claude/skills/
cp -r ~/awesome-skills/tailored-resume-generator .claude/skills/
cp -r ~/awesome-skills/skill-creator .claude/skills/
```

### Phase 3: Create Integration Skills (1 hour)

Create a skill that combines Fabric + Claude Code:

```markdown
# .claude/skills/deep-research/skill.md
---
name: deep-research
description: Deep company/role research using Fabric + Claude
trigger: /deep-research
---

# Deep Research Skill

## Workflow

1. **Website Analysis**
   ```bash
   fabric -u [company_url] -p extract_wisdom > /tmp/company_wisdom.md
   ```

2. **YouTube Research** (if available)
   ```bash
   fabric -y [video_url] -p youtube_summary >> /tmp/company_wisdom.md
   ```

3. **Synthesis**
   - Read /tmp/company_wisdom.md
   - Combine with job description
   - Create structured research report

## Output Format
[Structured report template]
```

---

## Key Takeaways

### Fabric

- **185+ patterns** covering summarization, analysis, writing, coding
- **CLI-first** - pipe anything through patterns
- **Multi-provider** - use Claude, GPT, Gemini, or local models
- **Best for**: Quick transformations, research, content extraction

### awesome-claude-skills

- **30+ ready-to-use skills** organized by category
- **Directly compatible** with Claude Code `.claude/skills/`
- **Composio integration** for connecting to 500+ apps
- **Best for**: Complex workflows, app integrations, ready-made solutions

### Combined Power

| Task | Fabric Pattern | Claude Skill |
|------|----------------|--------------|
| Company research | `extract_wisdom`, `summarize` | `lead-research-assistant` |
| Resume tailoring | `extract_skills`, `improve_writing` | `tailored-resume-generator` |
| Interview prep | `answer_interview_question`, `create_flash_cards` | `meeting-insights-analyzer` |
| Pipeline debugging | - | `langsmith-fetch` |
| Content creation | `humanize`, `write_essay_pg` | `content-research-writer` |

---

## Sources

- [Fabric GitHub Repository](https://github.com/danielmiessler/fabric)
- [Fabric Pattern Explanations](https://github.com/danielmiessler/Fabric/blob/main/data/patterns/pattern_explanations.md)
- [Fabric Patterns Directory](https://github.com/danielmiessler/Fabric/tree/main/data/patterns)
- [Awesome Claude Skills Repository](https://github.com/ComposioHQ/awesome-claude-skills)
- [Patterns Explained Discussion](https://github.com/danielmiessler/Fabric/discussions/1091)
