# 🧠 Complete List of Prompting Techniques (Extracted from NetworkChuck Video)

This is a distilled, LLM-ready list of EVERY prompting technique mentioned or demonstrated in the video **“You SUCK at Prompting AI (Here’s the Secret)”**.  
Use this as your universal prompting cheat-sheet.

---

# 1. Foundational Techniques

## 1.1. Personas

Tell the model _who_ it is.

Examples:

- “You are a CEO.”
- “You are a senior software architect.”
- “Act as a YouTube creator.”
- “Act as McKinsey management consultant.”

Why it matters:

- It sets expectations, tone, expertise level, domain vocabulary.
- Models adjust reasoning to different mental frameworks.

---

## 1.2. Context

Give the model the information it needs to reason properly.

Types of Context:

- Background info
- Examples
- Constraints
- Objectives
- Audience

Example:

- “Here is the email draft…”
- “Here is the job description…”
- “These are the business goals…”

Without context → hallucination or generic answers  
With context → tailored answers

---

## 1.3. Format Instructions

Tell the model EXACTLY what form the output should take.

Examples:

- “Output as a table.”
- “Use bullet points.”
- “Return only JSON.”
- “Write as a 30-sec YouTube script.”

Why:

- Format shapes the _thinking_ of the model.
- Models optimize around predictable structures.

---

# 2. Intermediate Techniques

## 2.1. Step-by-Step / Chain-of-Thought (CoT)

Explicit reasoning improves correctness.

Example:

- “Think step-by-step.”
- “Before answering, outline your reasoning process.”
- “List the steps you would take first.”

Benefits:

- Higher accuracy
- Less hallucinations
- Better structured output

---

## 2.2. Reasoning First, Output Later

Force separation:

1. **Internal reasoning**
2. **Final answer**

Format:

```
First, think through the reasoning step-by-step.
Then give the final answer in <final> tags.
```

Models love this. It dramatically increases quality.

---

## 2.3. Few-Shot Examples

Show the model samples of what “good” looks like.

Example:

```
Example input:
Example output:

Now apply the same style to this input:
```

This is the MOST important technique for consistent style and tone.

---

## 2.4. Show + Ask (Rubric Prompting)

Give the model:

1. An example
2. A rubric for what makes it good
3. Ask it to apply the rubric

---

# 3. Advanced Techniques

## 3.1. Tree-of-Thoughts

Ask the model to generate multiple possible approaches, then pick the best.

Example:

```
Generate 3 different strategies.
Evaluate each one.
Choose the best strategy and explain why.
```

Benefits:

- Better creativity
- Better reasoning
- Better decisions

---

## 3.2. “Battle of the Bots” (Evaluator vs. Generator)

Run two models against each other:

- Model A generates
- Model B critiques and improves

Format:

```
Model A: Produce solution.
Model B: Critique using XYZ rubric.
Model A: Improve the solution based on the critique.
```

This is one of the most powerful expert-level prompting loops.

---

## 3.3. Iterative Refinement

Ask:

- “Improve this.”
- “Refine this.”
- “Make it more formal.”
- “Make version 2.0 with better structure.”

AI thrives on iteration, not one-shot prompting.

---

## 3.4. Anti-Hallucination Guardrails

Examples:

- “If you don’t know, say ‘I don’t know.’”
- “Cite details from the provided text only.”
- “Do not invent facts.”

---

## 3.5. Constraint-Based Prompting

Add hard constraints:

- Length limits
- Tone
- Strict structures
- Must include X, must exclude Y

Example:

```
Must be under 200 words.
Must include 3 bullets.
Must not use the word “optimize.”
```

---

## 3.6. Output Calibration

Ask the model to:

- Rate confidence
- Detect missing information
- Identify ambiguities

Example:

```
List what information you need from me before giving an accurate answer.
```

This transforms the model into a proactive collaborator.

---

# 4. Meta-Techniques (“The Meta-Skill”)

## 4.1. Prompt → Evaluate → Improve → Repeat

Your job is not prompting — it is _iterating_ on prompts.

Process:

1. Ask AI to evaluate your prompt.
2. Ask it to rewrite your prompt.
3. Ask it to critique the rewritten prompt.
4. Save the improved version.

This loop yields exponential improvement.

---

## 4.2. Prompt Improver Pattern

Ask the AI to FIX your prompt:

```
Analyze this prompt for ambiguity, missing context, weak instructions, and unclear outcomes.
Rewrite it to maximize clarity, structure, and quality.
```

Or:

```
Act as a prompt engineer.
Improve my prompt using best practices from OpenAI, Google, Anthropic.
```

---

## 4.3. AI as a Collaborative Developer of Prompts

Ask:

- “What else can I add?”
- “What’s missing?”
- “How would an expert prompt engineer improve this?”

The model will help you build the perfect input.

---

# 5. Ultra-Advanced Techniques

## 5.1. Self-Consistency

Ask the model to generate multiple answers,
then synthesize the best.

Example:

```
Generate 5 answers.
Combine the best elements into one final response.
```

---

## 5.2. Debate Mode

Have the model argue both sides of an issue.

```
Argument for X.
Argument against X.
Now resolve the debate into a final position.
```

Improves reasoning significantly.

---

## 5.3. Calibration via Scoring

Ask the model to score its answers:

```
Score this answer 1–10 on clarity, accuracy, completeness.
Rewrite to achieve a score of 9+.
```

This massively boosts quality over time.

---

# 6. The Universal Prompt Structure (Summary)

A perfect prompt generally includes:

1. **Persona**
2. **Task**
3. **Context**
4. **Constraints**
5. **Examples**
6. **Output Format**
7. **Reasoning style**
8. **Improvement loop**

---

# 7. Meta-Skill Summary

> Prompting is not a one-shot command — it is a collaboration loop.

You build:

- The persona
- The context
- The structure
- The constraints
- The examples
- The evaluation rules

AI builds the output.

---

# End of Cheat Sheet

Take this markdown block and paste it into your:

- n8n
- Obsidian
- Notion
- VSCode prompt library
- Job-Intelligence pipeline
- LangGraph flows

Done. 🚀
