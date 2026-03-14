// rule_scoring_ai.js
// Level-1 rule scoring for AI/GenAI/LLM engineering and architecture roles.
// Keyword taxonomy sourced from:
//   - reports/ai_architect_skills_analysis.md (150 LinkedIn JDs)
//   - reports/architect-skills-analysis.json (2,702 jobs, 528 AI/ML focused)
//   - src/common/ai_classifier.py (11-category regex classifier)
//
// Supported Roles:
// 1. AI Engineer (Senior/Lead/Staff/Principal)
// 2. AI Architect / AI Solutions Architect
// 3. GenAI Engineer / Generative AI Engineer
// 4. LLM Engineer / LLM Architect
// 5. Agentic AI Engineer / AI Agent Architect
// 6. Head of AI / Director of AI / VP of AI
// 7. Applied AI Engineer

// =============================================================================
// CONFIGURATION
// =============================================================================

const TARGET_ROLE_FILTER = [
  // Uncomment to restrict scoring to specific roles:
  'ai_engineer',
  'ai_architect',
  'genai_engineer',
  'llm_engineer',
  'agentic_ai_engineer',
  'ai_leadership',
  'applied_ai_engineer',
];

// Minimum score threshold for Level-2 promotion
const PROMOTION_THRESHOLD = 60;

// =============================================================================
// ROLE DEFINITIONS - Title patterns for each AI role category
// =============================================================================

const ROLE_DEFINITIONS = {
  // -------------------------------------------------------------------------
  // AI ENGINEER
  // -------------------------------------------------------------------------
  ai_engineer: {
    displayName: 'AI Engineer',
    titleWeight: 40,
    exactTitles: [
      'ai engineer',
      'artificial intelligence engineer',
      'senior ai engineer',
      'lead ai engineer',
      'staff ai engineer',
      'principal ai engineer',
      'ai software engineer',
      'ai developer',
      'senior artificial intelligence engineer',
    ],
    partialTitles: [
      'ai engineer',
      'artificial intelligence engineer',
    ],
    excludeIfContains: [
      'sales', 'pre-sales', 'presales', 'marketing',
      'recruiter', 'data analyst', 'business analyst',
    ],
  },

  // -------------------------------------------------------------------------
  // AI ARCHITECT / AI SOLUTIONS ARCHITECT
  // -------------------------------------------------------------------------
  ai_architect: {
    displayName: 'AI Architect',
    titleWeight: 45,
    exactTitles: [
      'ai architect',
      'ai solutions architect',
      'ai solution architect',
      'artificial intelligence architect',
      'senior ai architect',
      'lead ai architect',
      'principal ai architect',
      'chief ai architect',
      'genai architect',
      'generative ai architect',
      'llm architect',
      'ai platform architect',
      'ai infrastructure architect',
      'ai cloud architect',
    ],
    partialTitles: [
      'ai architect',
      'ai solutions architect',
      'genai architect',
      'llm architect',
    ],
    excludeIfContains: [
      'sales', 'pre-sales', 'presales',
    ],
  },

  // -------------------------------------------------------------------------
  // GENAI ENGINEER
  // -------------------------------------------------------------------------
  genai_engineer: {
    displayName: 'GenAI Engineer',
    titleWeight: 45,
    exactTitles: [
      'genai engineer',
      'generative ai engineer',
      'gen ai engineer',
      'senior genai engineer',
      'lead genai engineer',
      'staff genai engineer',
      'senior generative ai engineer',
      'lead generative ai engineer',
    ],
    partialTitles: [
      'genai engineer',
      'generative ai engineer',
      'gen ai engineer',
    ],
    excludeIfContains: [
      'sales', 'pre-sales', 'presales', 'marketing',
    ],
  },

  // -------------------------------------------------------------------------
  // LLM ENGINEER
  // -------------------------------------------------------------------------
  llm_engineer: {
    displayName: 'LLM Engineer',
    titleWeight: 45,
    exactTitles: [
      'llm engineer',
      'llm developer',
      'large language model engineer',
      'senior llm engineer',
      'lead llm engineer',
      'staff llm engineer',
      'llm infrastructure engineer',
    ],
    partialTitles: [
      'llm engineer',
      'llm developer',
      'large language model',
    ],
    excludeIfContains: [
      'sales', 'pre-sales', 'presales',
    ],
  },

  // -------------------------------------------------------------------------
  // AGENTIC AI ENGINEER
  // -------------------------------------------------------------------------
  agentic_ai_engineer: {
    displayName: 'Agentic AI Engineer',
    titleWeight: 45,
    exactTitles: [
      'agentic ai engineer',
      'ai agent engineer',
      'ai agent architect',
      'ai agent developer',
      'agentic engineer',
      'multi-agent engineer',
    ],
    partialTitles: [
      'agentic ai',
      'ai agent',
      'multi-agent',
    ],
    excludeIfContains: [
      'sales', 'pre-sales', 'presales', 'customer',
    ],
  },

  // -------------------------------------------------------------------------
  // APPLIED AI ENGINEER
  // -------------------------------------------------------------------------
  applied_ai_engineer: {
    displayName: 'Applied AI Engineer',
    titleWeight: 40,
    exactTitles: [
      'applied ai engineer',
      'applied ai scientist',
      'applied ai researcher',
      'rag engineer',
      'deep learning engineer',
      'ai application engineer',
    ],
    partialTitles: [
      'applied ai',
      'rag engineer',
      'deep learning engineer',
    ],
    excludeIfContains: [
      'sales', 'pre-sales', 'presales',
    ],
  },

  // -------------------------------------------------------------------------
  // AI LEADERSHIP (Head / Director / VP)
  // -------------------------------------------------------------------------
  ai_leadership: {
    displayName: 'Head of AI',
    titleWeight: 50,
    exactTitles: [
      'head of ai',
      'head of artificial intelligence',
      'head of genai',
      'head of generative ai',
      'director of ai',
      'director of artificial intelligence',
      'director of genai',
      'director ai',
      'vp of ai',
      'vp ai',
      'vice president of ai',
      'vice president ai',
      'ai engineering lead',
      'ai engineering manager',
      'ai team lead',
      'chief ai officer',
      'caio',
    ],
    partialTitles: [
      'head of ai',
      'director of ai',
      'vp of ai',
      'vp ai',
      'chief ai',
    ],
    excludeIfContains: [],
  },
};

// =============================================================================
// UNWANTED TITLE KEYWORDS - Reject non-AI roles
// =============================================================================

const UNWANTED_TITLE_KEYWORDS = [
  'sales', 'business development', 'accounting', 'clinical',
  'marketing', 'hr', 'human resources', 'recruiter', 'recruiting',
  'customer success', 'customer support', 'support engineer',
  'pre-sales', 'presales', 'field engineer', 'implementation',
  'data analyst', 'business analyst', 'project manager', 'program manager',
  'scrum master', 'product owner', 'qa engineer', 'test engineer', 'sdet',
  'network engineer', 'systems administrator',
  // Pure SWE roles (we want AI-specific, not generic)
  'frontend engineer', 'frontend developer', 'ui engineer', 'ux engineer',
  'ios developer', 'android developer', 'mobile developer',
];

// =============================================================================
// SENIORITY LEVELS
// =============================================================================

const SENIORITY_LEVELS = {
  executive: {
    keywords: ['executive', 'c-level', 'c-suite', 'chief', 'caio'],
    score: 15,
  },
  director: {
    keywords: ['director', 'vp', 'vice president', 'head of', 'head'],
    score: 12,
  },
  senior_ic: {
    keywords: ['staff', 'principal', 'distinguished', 'fellow'],
    score: 10,
  },
  lead: {
    keywords: ['lead', 'tech lead', 'team lead'],
    score: 8,
  },
  senior: {
    keywords: ['senior', 'sr.', 'sr '],
    score: 6,
  },
  mid: {
    keywords: ['mid', 'intermediate'],
    score: 0,
  },
  junior: {
    keywords: ['junior', 'jr.', 'jr ', 'entry', 'associate', 'intern', 'trainee', 'graduate'],
    score: -25,
  },
};

// =============================================================================
// AI-SPECIFIC KEYWORD CATEGORIES
// Sources: ai_architect_skills_analysis.md + architect-skills-analysis.json
// =============================================================================

// GENAI & LLM CORE (highest signal — 67+50 mentions in LinkedIn analysis)
const GENAI_LLM_KEYWORDS = [
  'generative ai', 'genai', 'gen ai', 'llm', 'large language model',
  'gpt', 'chatgpt', 'claude', 'gemini', 'openai', 'anthropic',
  'transformer', 'foundation model', 'llm integration', 'llm systems',
  'llm applications', 'llm ecosystem', 'llm proxy', 'vllm',
  'text generation', 'language model', 'multimodal',
];

// AGENTIC AI & FRAMEWORKS (69 mentions — top AI keyword)
const AGENTIC_AI_KEYWORDS = [
  'agentic', 'agentic ai', 'ai agent', 'ai agents', 'agent framework',
  'agentic framework', 'agentic workflow', 'agentic workflow orchestration',
  'multi-agent', 'multi agent', 'tool calling', 'function calling',
  'langchain', 'langgraph', 'crewai', 'autogen', 'semantic kernel',
  'agent orchestration', 'autonomous agent',
];

// RAG & RETRIEVAL (51 mentions)
const RAG_RETRIEVAL_KEYWORDS = [
  'rag', 'retrieval augmented generation', 'retrieval-augmented generation',
  'rag pipeline', 'rag pipelines', 'rag systems',
  'vector database', 'vector databases', 'vector store', 'vector search',
  'embedding', 'embeddings', 'semantic search',
  'pinecone', 'weaviate', 'qdrant', 'chroma', 'chromadb', 'faiss',
  'milvus', 'pgvector', 'opensearch',
  'knowledge graph', 'knowledge base', 'document retrieval',
];

// EVALUATION & QUALITY (emerging — evals stack, eval harness in JDs)
const EVAL_QUALITY_KEYWORDS = [
  'llm evaluation', 'llm eval', 'eval harness', 'evals stack',
  'evaluation systems', 'model evaluation', 'benchmark',
  'golden dataset', 'ground truth', 'hallucination detection',
  'guardrails', 'content filtering', 'safety testing',
  'red teaming', 'prompt injection', 'adversarial testing',
  'langfuse', 'langsmith', 'weights & biases', 'weights and biases', 'wandb',
  'mlflow', 'arize', 'trulens',
];

// FINE-TUNING & TRAINING (24 mentions)
const FINE_TUNING_KEYWORDS = [
  'fine-tuning', 'fine tuning', 'finetuning', 'model fine-tuning',
  'lora', 'qlora', 'rlhf', 'peft', 'sft', 'supervised fine-tuning',
  'instruction tuning', 'domain adaptation', 'transfer learning',
  'llm training', 'llm finetuning', 'model training',
  'distillation', 'quantization', 'model optimization',
];

// AI GOVERNANCE & RESPONSIBLE AI (21 mentions — growing fast)
const AI_GOVERNANCE_KEYWORDS = [
  'ai governance', 'responsible ai', 'ai ethics', 'ai safety',
  'ai compliance', 'ai risk', 'model card', 'ai policy',
  'eu ai act', 'nist ai', 'iso 42001',
  'bias detection', 'fairness', 'transparency', 'explainability',
  'model context protocol', 'mcp',
];

// PROMPT ENGINEERING & DESIGN (32 mentions)
const PROMPT_ENGINEERING_KEYWORDS = [
  'prompt engineering', 'prompt design', 'prompt optimization',
  'prompt template', 'few-shot', 'zero-shot', 'chain of thought',
  'in-context learning', 'prompt chaining',
];

// AI/ML INFRASTRUCTURE & PLATFORMS (from architect-skills-analysis.json)
const AI_INFRA_KEYWORDS = [
  'sagemaker', 'bedrock', 'vertex ai', 'azure openai', 'azure ai',
  'mlops', 'llmops', 'model serving', 'model deployment',
  'model monitoring', 'model registry', 'ml pipeline', 'model pipeline',
  'inference', 'streaming inference', 'distributed inference',
  'ml inference optimization', 'gpu', 'cuda', 'tpu',
  'pytorch', 'tensorflow', 'hugging face', 'huggingface',
  'deep learning', 'deep learning systems', 'neural network',
];

// CLOUD & INFRASTRUCTURE (top skills: AWS 89, Azure 82, GCP 60)
const CLOUD_INFRA_KEYWORDS = [
  'aws', 'gcp', 'azure', 'cloud', 'cloud native', 'cloud-native',
  'kubernetes', 'k8s', 'docker', 'terraform',
  'serverless', 'lambda', 'ecs', 'eks',
  'kafka', 'data pipelines',
  'ci/cd', 'cicd', 'devops', 'gitops',
];

// ARCHITECTURE & SYSTEM DESIGN (from existing scoring)
const ARCHITECTURE_KEYWORDS = [
  'architecture', 'system design', 'systems design', 'platform',
  'microservices', 'event-driven', 'event driven',
  'distributed systems', 'api design', 'api', 'rest api', 'graphql',
  'scalability', 'high availability', 'fault tolerance',
];

// PROGRAMMING LANGUAGES (Python #1 at 62 mentions in AI JDs)
const LANGUAGES_KEYWORDS = [
  'python', 'typescript', 'javascript', 'node.js', 'nodejs',
  'java', 'go', 'golang', 'rust', 'c++', 'scala',
  'fastapi', 'flask', 'django',
  'react', 'next.js', 'nextjs',
  'postgresql', 'postgres', 'mongodb', 'redis', 'sql', 'nosql',
];

// DATA & KNOWLEDGE (from architect-skills-analysis.json domain: data_knowledge)
const DATA_KNOWLEDGE_KEYWORDS = [
  'data science', 'data engineering', 'data platform',
  'feature store', 'data lake', 'data mesh', 'data pipeline',
  'etl', 'elt', 'data warehouse', 'analytics',
  'nlp', 'natural language processing', 'computer vision',
  'text mining', 'text classification', 'named entity recognition',
];

// LEADERSHIP & STRATEGY (top soft skills: Strategy 101, Leadership 100)
const AI_LEADERSHIP_KEYWORDS = [
  'ai strategy', 'ai roadmap', 'ai transformation',
  'technology strategy', 'technical strategy', 'digital transformation',
  'vision', 'strategic', 'roadmap', 'innovation',
  'leadership', 'cross-functional', 'stakeholder', 'executive',
  'build team', 'grow team', 'mentor', 'coaching',
  'engineering excellence', 'best practices',
];

// ACHIEVEMENT INDICATORS
const ACHIEVEMENT_KEYWORDS = [
  'scaled', 'grew', 'built', 'transformed', 'modernized', 'migrated', 'led',
  'delivered', 'shipped', 'launched', 'deployed', 'implemented',
  'reduced', 'improved', 'increased', 'saved', 'achieved', 'drove',
  'production', 'revenue', 'cost reduction', 'efficiency',
  'latency', 'throughput', 'accuracy', 'precision', 'recall',
];

// =============================================================================
// LOCATION & LANGUAGE PREFERENCES
// =============================================================================

const REMOTE_POSITIVE = [
  'remote', 'remote-first', 'distributed', 'work from anywhere', 'wfh',
  'hybrid', 'flexible location', 'global', 'work from home', 'worldwide',
];

const REMOTE_NEGATIVE = [
  'onsite only', 'on-site only', 'office only', 'no remote',
  'must relocate', 'relocation required', 'in-office',
];

const LANGUAGE_NEGATIVE = [
  'fluent arabic', 'arabic speaker', 'native arabic',
  'fluent spanish', 'spanish speaker', 'native spanish',
  'fluent french', 'french speaker', 'native french',
  'fluent german', 'german speaker', 'native german',
  'fluent mandarin', 'mandarin speaker', 'native mandarin',
  'fluent japanese', 'japanese speaker', 'native japanese',
  'fluent korean', 'korean speaker', 'native korean',
];

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

function containsAny(text, keywords) {
  const t = (text || '').toLowerCase();
  return keywords.some((k) => t.includes(k.toLowerCase()));
}

function countKeywords(text, keywords) {
  const t = (text || '').toLowerCase();
  return keywords.reduce((acc, k) => (t.includes(k.toLowerCase()) ? acc + 1 : acc), 0);
}

function countKeywordsWeighted(text, keywords, weightPerMatch = 1, maxScore = Infinity) {
  const count = countKeywords(text, keywords);
  return Math.min(count * weightPerMatch, maxScore);
}

function detectRole(title) {
  const t = (title || '').toLowerCase().trim();

  // Check each role in order of specificity (most specific first)
  const roleOrder = [
    'ai_leadership',
    'agentic_ai_engineer',
    'llm_engineer',
    'genai_engineer',
    'ai_architect',
    'applied_ai_engineer',
    'ai_engineer',
  ];

  for (const roleKey of roleOrder) {
    const role = ROLE_DEFINITIONS[roleKey];

    // Check exact titles first
    for (const exactTitle of role.exactTitles) {
      if (t === exactTitle || t.includes(exactTitle)) {
        if (role.excludeIfContains && role.excludeIfContains.length > 0) {
          const hasExclusion = role.excludeIfContains.some((ex) => t.includes(ex.toLowerCase()));
          if (hasExclusion) continue;
        }
        return roleKey;
      }
    }
  }

  // Fallback: check partial titles
  for (const roleKey of roleOrder) {
    const role = ROLE_DEFINITIONS[roleKey];
    for (const partial of role.partialTitles) {
      if (t.includes(partial.toLowerCase())) {
        if (role.excludeIfContains && role.excludeIfContains.length > 0) {
          const hasExclusion = role.excludeIfContains.some((ex) => t.includes(ex.toLowerCase()));
          if (hasExclusion) continue;
        }
        return roleKey;
      }
    }
  }

  // Extra fallback: title doesn't match but description may contain strong AI signals
  // Return null — the keyword scoring will still work via default weights
  return null;
}

function getTitleScore(title, detectedRole) {
  if (!detectedRole) return 0;

  const t = (title || '').toLowerCase().trim();
  const role = ROLE_DEFINITIONS[detectedRole];

  for (const exactTitle of role.exactTitles) {
    if (t === exactTitle) return role.titleWeight;
  }

  for (const exactTitle of role.exactTitles) {
    if (t.includes(exactTitle)) return Math.round(role.titleWeight * 0.9);
  }

  for (const partial of role.partialTitles) {
    if (t.includes(partial.toLowerCase())) return Math.round(role.titleWeight * 0.8);
  }

  return Math.round(role.titleWeight * 0.5);
}

function getSeniorityScore(text) {
  const t = (text || '').toLowerCase();
  for (const [level, config] of Object.entries(SENIORITY_LEVELS)) {
    for (const kw of config.keywords) {
      if (t.includes(kw.toLowerCase())) {
        return { level, score: config.score };
      }
    }
  }
  return { level: 'unknown', score: 0 };
}

function countUnwantedTitleKeywords(title) {
  const t = (title || '').toLowerCase();
  return UNWANTED_TITLE_KEYWORDS.reduce(
    (acc, kw) => (t.includes(kw.toLowerCase()) ? acc + 1 : acc),
    0,
  );
}

// =============================================================================
// ROLE-SPECIFIC WEIGHT CONFIGURATIONS
// =============================================================================

const ROLE_WEIGHTS = {
  ai_engineer: {
    genaiLlm:        { weight: 3,   max: 30 },  // Core competency
    agenticAi:       { weight: 2.5, max: 25 },
    ragRetrieval:    { weight: 2.5, max: 25 },
    evalQuality:     { weight: 2,   max: 20 },
    fineTuning:      { weight: 1.5, max: 15 },
    aiGovernance:    { weight: 1,   max: 10 },
    promptEng:       { weight: 1.5, max: 10 },
    aiInfra:         { weight: 2,   max: 20 },
    cloudInfra:      { weight: 1.5, max: 15 },
    architecture:    { weight: 1.5, max: 15 },
    languages:       { weight: 2,   max: 20 },
    dataKnowledge:   { weight: 1,   max: 10 },
    aiLeadership:    { weight: 1,   max: 10 },
    achievement:     { weight: 1,   max: 10 },
  },
  ai_architect: {
    genaiLlm:        { weight: 3,   max: 30 },
    agenticAi:       { weight: 2.5, max: 25 },
    ragRetrieval:    { weight: 2.5, max: 25 },
    evalQuality:     { weight: 2,   max: 20 },
    fineTuning:      { weight: 1.5, max: 15 },
    aiGovernance:    { weight: 2,   max: 20 },  // Architects need governance
    promptEng:       { weight: 1,   max: 10 },
    aiInfra:         { weight: 2.5, max: 25 },
    cloudInfra:      { weight: 2,   max: 20 },
    architecture:    { weight: 3,   max: 30 },  // Core competency
    languages:       { weight: 1.5, max: 15 },
    dataKnowledge:   { weight: 1.5, max: 15 },
    aiLeadership:    { weight: 2,   max: 20 },  // Strategic role
    achievement:     { weight: 1.5, max: 15 },
  },
  genai_engineer: {
    genaiLlm:        { weight: 3.5, max: 35 },  // Highest — core identity
    agenticAi:       { weight: 2.5, max: 25 },
    ragRetrieval:    { weight: 2.5, max: 25 },
    evalQuality:     { weight: 2,   max: 20 },
    fineTuning:      { weight: 2,   max: 20 },
    aiGovernance:    { weight: 1,   max: 10 },
    promptEng:       { weight: 2,   max: 15 },
    aiInfra:         { weight: 2,   max: 20 },
    cloudInfra:      { weight: 1.5, max: 15 },
    architecture:    { weight: 1.5, max: 15 },
    languages:       { weight: 2,   max: 20 },
    dataKnowledge:   { weight: 1,   max: 10 },
    aiLeadership:    { weight: 1,   max: 10 },
    achievement:     { weight: 1,   max: 10 },
  },
  llm_engineer: {
    genaiLlm:        { weight: 3.5, max: 35 },  // Core identity
    agenticAi:       { weight: 2,   max: 20 },
    ragRetrieval:    { weight: 2.5, max: 25 },
    evalQuality:     { weight: 2.5, max: 25 },  // Eval is key for LLM work
    fineTuning:      { weight: 2.5, max: 25 },  // Fine-tuning is key
    aiGovernance:    { weight: 1,   max: 10 },
    promptEng:       { weight: 2,   max: 15 },
    aiInfra:         { weight: 2.5, max: 25 },  // Inference, serving
    cloudInfra:      { weight: 1.5, max: 15 },
    architecture:    { weight: 1.5, max: 15 },
    languages:       { weight: 2,   max: 20 },
    dataKnowledge:   { weight: 1,   max: 10 },
    aiLeadership:    { weight: 0.5, max: 5 },
    achievement:     { weight: 1,   max: 10 },
  },
  agentic_ai_engineer: {
    genaiLlm:        { weight: 2.5, max: 25 },
    agenticAi:       { weight: 3.5, max: 35 },  // Core identity
    ragRetrieval:    { weight: 2.5, max: 25 },
    evalQuality:     { weight: 2,   max: 20 },
    fineTuning:      { weight: 1,   max: 10 },
    aiGovernance:    { weight: 1.5, max: 15 },  // Safety for agents
    promptEng:       { weight: 2,   max: 15 },
    aiInfra:         { weight: 2,   max: 20 },
    cloudInfra:      { weight: 1.5, max: 15 },
    architecture:    { weight: 2,   max: 20 },  // Agent orchestration = architecture
    languages:       { weight: 2,   max: 20 },
    dataKnowledge:   { weight: 1,   max: 10 },
    aiLeadership:    { weight: 1,   max: 10 },
    achievement:     { weight: 1,   max: 10 },
  },
  applied_ai_engineer: {
    genaiLlm:        { weight: 2.5, max: 25 },
    agenticAi:       { weight: 2,   max: 20 },
    ragRetrieval:    { weight: 3,   max: 30 },  // RAG/retrieval is applied AI bread & butter
    evalQuality:     { weight: 2,   max: 20 },
    fineTuning:      { weight: 2,   max: 20 },
    aiGovernance:    { weight: 1,   max: 10 },
    promptEng:       { weight: 1.5, max: 15 },
    aiInfra:         { weight: 2,   max: 20 },
    cloudInfra:      { weight: 1.5, max: 15 },
    architecture:    { weight: 1.5, max: 15 },
    languages:       { weight: 2.5, max: 25 },  // Hands-on coding
    dataKnowledge:   { weight: 2,   max: 20 },
    aiLeadership:    { weight: 0.5, max: 5 },
    achievement:     { weight: 1,   max: 10 },
  },
  ai_leadership: {
    genaiLlm:        { weight: 2,   max: 20 },
    agenticAi:       { weight: 2,   max: 20 },
    ragRetrieval:    { weight: 1.5, max: 15 },
    evalQuality:     { weight: 1.5, max: 15 },
    fineTuning:      { weight: 1,   max: 10 },
    aiGovernance:    { weight: 2.5, max: 25 },  // Leaders own governance
    promptEng:       { weight: 0.5, max: 5 },
    aiInfra:         { weight: 1.5, max: 15 },
    cloudInfra:      { weight: 1,   max: 10 },
    architecture:    { weight: 1.5, max: 15 },
    languages:       { weight: 0.5, max: 5 },
    dataKnowledge:   { weight: 1,   max: 10 },
    aiLeadership:    { weight: 3,   max: 30 },  // Core competency
    achievement:     { weight: 2.5, max: 25 },
  },
};

// Default weights for jobs where title doesn't match but has AI keywords
const DEFAULT_WEIGHTS = {
  genaiLlm:        { weight: 2.5, max: 25 },
  agenticAi:       { weight: 2,   max: 20 },
  ragRetrieval:    { weight: 2,   max: 20 },
  evalQuality:     { weight: 1.5, max: 15 },
  fineTuning:      { weight: 1.5, max: 15 },
  aiGovernance:    { weight: 1,   max: 10 },
  promptEng:       { weight: 1,   max: 10 },
  aiInfra:         { weight: 1.5, max: 15 },
  cloudInfra:      { weight: 1.5, max: 15 },
  architecture:    { weight: 1.5, max: 15 },
  languages:       { weight: 1.5, max: 15 },
  dataKnowledge:   { weight: 1,   max: 10 },
  aiLeadership:    { weight: 1.5, max: 15 },
  achievement:     { weight: 1,   max: 10 },
};

// =============================================================================
// MAIN SCORING FUNCTION
// =============================================================================

function computeRuleScore(job) {
  const title = job.title || '';
  const jobCriteria = job.job_criteria || '';
  const jobDescription = job.job_description || '';
  const location = job.location || '';

  const titleLower = title.toLowerCase();
  const critLower = jobCriteria.toLowerCase();
  const descLower = jobDescription.toLowerCase();
  const locLower = location.toLowerCase();

  const fullText = `${titleLower} ${critLower} ${descLower}`;
  const locAndDesc = `${locLower} ${descLower}`;

  // -------------------------------------------------------------------------
  // DETECT ROLE
  // -------------------------------------------------------------------------
  const detectedRole = detectRole(title);

  const isTargetRole = TARGET_ROLE_FILTER.length === 0 ||
    (detectedRole && TARGET_ROLE_FILTER.includes(detectedRole));

  // For AI scoring: even if title doesn't match, check if description has
  // strong AI signals. This catches generic titles like "Solutions Architect"
  // with AI-heavy JDs.
  const hasStrongAiSignal = !detectedRole && (
    countKeywords(fullText, GENAI_LLM_KEYWORDS) >= 3 ||
    countKeywords(fullText, AGENTIC_AI_KEYWORDS) >= 2 ||
    countKeywords(fullText, RAG_RETRIEVAL_KEYWORDS) >= 2
  );

  if (!isTargetRole && !hasStrongAiSignal) {
    return {
      score: 0,
      detectedRole: detectedRole,
      isTargetRole: false,
      hasStrongAiSignal: false,
      breakdown: {},
    };
  }

  const weights = detectedRole ? ROLE_WEIGHTS[detectedRole] || DEFAULT_WEIGHTS : DEFAULT_WEIGHTS;

  // -------------------------------------------------------------------------
  // 1) TITLE SCORE (0-50 points)
  // -------------------------------------------------------------------------
  const titleScore = getTitleScore(title, detectedRole);
  const unwantedCount = countUnwantedTitleKeywords(title);
  const unwantedPenalty = Math.min(unwantedCount * 30, 50);

  // -------------------------------------------------------------------------
  // 2) SENIORITY SCORE (-25 to +15 points)
  // -------------------------------------------------------------------------
  const seniorityResult = getSeniorityScore(`${titleLower} ${critLower}`);
  const seniorityScore = seniorityResult.score;

  // -------------------------------------------------------------------------
  // 3) AI KEYWORD SCORES (role-weighted)
  // -------------------------------------------------------------------------
  const genaiLlmScore = countKeywordsWeighted(
    fullText, GENAI_LLM_KEYWORDS, weights.genaiLlm.weight, weights.genaiLlm.max);
  const agenticAiScore = countKeywordsWeighted(
    fullText, AGENTIC_AI_KEYWORDS, weights.agenticAi.weight, weights.agenticAi.max);
  const ragRetrievalScore = countKeywordsWeighted(
    fullText, RAG_RETRIEVAL_KEYWORDS, weights.ragRetrieval.weight, weights.ragRetrieval.max);
  const evalQualityScore = countKeywordsWeighted(
    fullText, EVAL_QUALITY_KEYWORDS, weights.evalQuality.weight, weights.evalQuality.max);
  const fineTuningScore = countKeywordsWeighted(
    fullText, FINE_TUNING_KEYWORDS, weights.fineTuning.weight, weights.fineTuning.max);
  const aiGovernanceScore = countKeywordsWeighted(
    fullText, AI_GOVERNANCE_KEYWORDS, weights.aiGovernance.weight, weights.aiGovernance.max);
  const promptEngScore = countKeywordsWeighted(
    fullText, PROMPT_ENGINEERING_KEYWORDS, weights.promptEng.weight, weights.promptEng.max);
  const aiInfraScore = countKeywordsWeighted(
    fullText, AI_INFRA_KEYWORDS, weights.aiInfra.weight, weights.aiInfra.max);
  const cloudInfraScore = countKeywordsWeighted(
    fullText, CLOUD_INFRA_KEYWORDS, weights.cloudInfra.weight, weights.cloudInfra.max);
  const architectureScore = countKeywordsWeighted(
    fullText, ARCHITECTURE_KEYWORDS, weights.architecture.weight, weights.architecture.max);
  const languagesScore = countKeywordsWeighted(
    fullText, LANGUAGES_KEYWORDS, weights.languages.weight, weights.languages.max);
  const dataKnowledgeScore = countKeywordsWeighted(
    fullText, DATA_KNOWLEDGE_KEYWORDS, weights.dataKnowledge.weight, weights.dataKnowledge.max);
  const aiLeadershipScore = countKeywordsWeighted(
    fullText, AI_LEADERSHIP_KEYWORDS, weights.aiLeadership.weight, weights.aiLeadership.max);
  const achievementScore = countKeywordsWeighted(
    fullText, ACHIEVEMENT_KEYWORDS, weights.achievement.weight, weights.achievement.max);

  // -------------------------------------------------------------------------
  // 4) REMOTE PREFERENCE (-10 to +10)
  // -------------------------------------------------------------------------
  let remoteScore = 0;
  if (containsAny(locAndDesc, REMOTE_POSITIVE)) remoteScore += 10;
  if (containsAny(locAndDesc, REMOTE_NEGATIVE)) remoteScore -= 10;

  // -------------------------------------------------------------------------
  // 5) LANGUAGE REQUIREMENTS (-10 to 0)
  // -------------------------------------------------------------------------
  let languageScore = 0;
  if (containsAny(descLower, LANGUAGE_NEGATIVE)) languageScore -= 10;
  const chars = Array.from(jobDescription || '');
  const nonAsciiChars = chars.filter((ch) => ch.charCodeAt(0) > 127).length;
  const totalChars = chars.length || 1;
  if (nonAsciiChars / totalChars > 0.3) languageScore -= 10;

  // -------------------------------------------------------------------------
  // CALCULATE TOTAL
  // -------------------------------------------------------------------------
  const keywordTotal = genaiLlmScore + agenticAiScore + ragRetrievalScore +
    evalQualityScore + fineTuningScore + aiGovernanceScore + promptEngScore +
    aiInfraScore + cloudInfraScore + architectureScore + languagesScore +
    dataKnowledgeScore + aiLeadershipScore + achievementScore;

  const rawScore =
    titleScore +
    seniorityScore +
    keywordTotal +
    remoteScore +
    languageScore -
    unwantedPenalty;

  const maxKeywordScore = Object.values(weights).reduce((sum, w) => sum + w.max, 0);
  const maxPossible = 50 + 15 + maxKeywordScore + 10;

  const normalizedScore = Math.max(0, Math.min(100, Math.round((rawScore / maxPossible) * 100)));

  return {
    score: normalizedScore,
    detectedRole: detectedRole,
    isTargetRole: isTargetRole || hasStrongAiSignal,
    hasStrongAiSignal: hasStrongAiSignal,
    seniorityLevel: seniorityResult.level,
    breakdown: {
      title: titleScore,
      seniority: seniorityScore,
      genaiLlm: Math.round(genaiLlmScore),
      agenticAi: Math.round(agenticAiScore),
      ragRetrieval: Math.round(ragRetrievalScore),
      evalQuality: Math.round(evalQualityScore),
      fineTuning: Math.round(fineTuningScore),
      aiGovernance: Math.round(aiGovernanceScore),
      promptEng: Math.round(promptEngScore),
      aiInfra: Math.round(aiInfraScore),
      cloudInfra: Math.round(cloudInfraScore),
      architecture: Math.round(architectureScore),
      languages: Math.round(languagesScore),
      dataKnowledge: Math.round(dataKnowledgeScore),
      aiLeadership: Math.round(aiLeadershipScore),
      achievement: Math.round(achievementScore),
      remote: remoteScore,
      language: languageScore,
      unwantedPenalty: -unwantedPenalty,
    },
  };
}

// =============================================================================
// PROMOTION DECISION
// =============================================================================

function shouldPromoteToLevel2(scoreResult) {
  if (!scoreResult.isTargetRole) return false;
  return scoreResult.score >= PROMOTION_THRESHOLD;
}

// =============================================================================
// N8N ENTRY POINT
// =============================================================================

function scoreItems(items) {
  return items.map((item) => {
    const job = item.json || {};
    const scoreResult = computeRuleScore(job);
    const promote = shouldPromoteToLevel2(scoreResult);

    const newJson = {
      ...job,
      rule_score: scoreResult.score,
      rule_detected_role: scoreResult.detectedRole,
      rule_is_target_role: scoreResult.isTargetRole,
      rule_has_strong_ai_signal: scoreResult.hasStrongAiSignal,
      rule_seniority_level: scoreResult.seniorityLevel,
      rule_promote_to_level_2: promote,
      rule_score_breakdown: scoreResult.breakdown,
    };
    return { ...item, json: newJson };
  });
}

// Execute for n8n
const results = scoreItems($input.all());
return results;
