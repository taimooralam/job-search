// rule_scoring_unified.js
// Unified Level-1 rule scoring for multiple engineering leadership roles.
// Comprehensive keyword matching from taxonomy and master-cv for granular scoring.
//
// Supported Roles:
// 1. Senior Software Engineer
// 2. Staff Software Engineer
// 3. Lead Software Engineer / Tech Lead
// 4. Software Architect
// 5. Engineering Manager
// 6. Head of Engineering / Head of Technology
// 7. Director of Engineering
// 8. CTO / Chief Technology Officer

// =============================================================================
// CONFIGURATION - Set your target roles here
// =============================================================================

// Set to specific roles to filter, or leave empty to score all roles
const TARGET_ROLE_FILTER = [
  // Uncomment the roles you want to target:
  'senior_engineer',
  'staff_engineer',
  'lead_engineer',
  'tech_lead',
  'software_architect',
  'engineering_manager',
  'head_of_engineering',
  'director_of_engineering',
  'cto',
];

// Minimum score threshold for Level-2 promotion
const PROMOTION_THRESHOLD = 25;

// =============================================================================
// ROLE DEFINITIONS - Title patterns for each role category
// =============================================================================

const ROLE_DEFINITIONS = {
  // -------------------------------------------------------------------------
  // SENIOR SOFTWARE ENGINEER
  // -------------------------------------------------------------------------
  senior_engineer: {
    displayName: 'Senior Software Engineer',
    titleWeight: 30, // Lower weight - more common role
    exactTitles: [
      'senior software engineer',
      'senior engineer',
      'senior developer',
      'senior software developer',
      'sr software engineer',
      'sr engineer',
      'sr developer',
      'senior backend engineer',
      'senior frontend engineer',
      'senior full stack engineer',
      'senior fullstack engineer',
      'senior full-stack engineer',
      'software engineer iii',
      'software engineer 3',
      'engineer iii',
    ],
    partialTitles: [
      'senior',
      'sr.',
      'sr ',
    ],
    excludeIfContains: [
      'staff',
      'principal',
      'lead',
      'manager',
      'director',
      'head',
      'vp',
      'chief',
      'architect',
    ],
  },

  // -------------------------------------------------------------------------
  // STAFF SOFTWARE ENGINEER
  // -------------------------------------------------------------------------
  staff_engineer: {
    displayName: 'Staff Software Engineer',
    titleWeight: 40,
    exactTitles: [
      'staff software engineer',
      'staff engineer',
      'staff developer',
      'principal software engineer',
      'principal engineer',
      'principal developer',
      'distinguished engineer',
      'software engineer iv',
      'software engineer 4',
      'engineer iv',
      'senior staff engineer',
      'staff backend engineer',
      'staff frontend engineer',
      'staff full stack engineer',
    ],
    partialTitles: [
      'staff',
      'principal',
      'distinguished',
    ],
    excludeIfContains: [
      'manager',
      'director',
      'head',
      'vp',
      'chief',
    ],
  },

  // -------------------------------------------------------------------------
  // SOFTWARE ARCHITECT
  // -------------------------------------------------------------------------
  software_architect: {
    displayName: 'Software Architect',
    titleWeight: 45,
    exactTitles: [
      'software architect',
      'solution architect',
      'solutions architect',
      'enterprise architect',
      'technical architect',
      'cloud architect',
      'systems architect',
      'system architect',
      'platform architect',
      'infrastructure architect',
      'data architect',
      'application architect',
      'integration architect',
      'senior software architect',
      'senior architect',
      'lead architect',
      'principal architect',
      'chief architect',
      'staff architect',
      'senior solutions architect',
      'senior technical architect',
      'senior cloud architect',
      'senior enterprise architect',
      'aws architect',
      'azure architect',
      'gcp architect',
    ],
    partialTitles: [
      'architect',
      'software architect',
      'solution architect',
      'technical architect',
      'cloud architect',
      'enterprise architect',
    ],
    excludeIfContains: [
      'manager',
      'director',
      'head',
      'vp',
      'chief',
      'sales',
      'pre-sales',
      'presales',
    ],
  },

  // -------------------------------------------------------------------------
  // ENGINEERING MANAGER
  // -------------------------------------------------------------------------
  engineering_manager: {
    displayName: 'Engineering Manager',
    titleWeight: 42,
    exactTitles: [
      'engineering manager',
      'software engineering manager',
      'engineering manager ii',
      'engineering manager iii',
      'engineering manager 2',
      'engineering manager 3',
      'senior engineering manager',
      'software development manager',
      'development manager',
      'software manager',
      'manager software engineering',
      'manager of engineering',
      'manager of software engineering',
      'manager, software engineering',
      'manager, engineering',
      'team manager engineering',
      'engineering team manager',
      'backend engineering manager',
      'frontend engineering manager',
      'platform engineering manager',
      'infrastructure engineering manager',
      'em',
    ],
    partialTitles: [
      'engineering manager',
      'software engineering manager',
      'development manager',
      'software manager',
    ],
    excludeIfContains: [
      'director',
      'head',
      'vp',
      'chief',
      'senior director',
      'group manager',
      'general manager',
    ],
  },

  // -------------------------------------------------------------------------
  // LEAD SOFTWARE ENGINEER
  // -------------------------------------------------------------------------
  lead_engineer: {
    displayName: 'Lead Software Engineer',
    titleWeight: 40,
    exactTitles: [
      'lead software engineer',
      'lead engineer',
      'lead developer',
      'software engineering lead',
      'engineering lead',
      'development lead',
      'team lead engineer',
      'lead backend engineer',
      'lead frontend engineer',
      'lead full stack engineer',
      'software lead',
      'technical lead engineer',
    ],
    partialTitles: [
      'lead engineer',
      'lead developer',
      'engineering lead',
    ],
    excludeIfContains: [
      'manager',
      'director',
      'head',
      'vp',
      'chief',
    ],
  },

  // -------------------------------------------------------------------------
  // TECH LEAD
  // -------------------------------------------------------------------------
  tech_lead: {
    displayName: 'Tech Lead',
    titleWeight: 40,
    exactTitles: [
      'tech lead',
      'tech-lead',
      'technical lead',
      'technical leader',
      'technology lead',
      'techlead',
    ],
    partialTitles: [
      'tech lead',
      'tech-lead',
      'technical lead',
    ],
    excludeIfContains: [
      'manager',
      'director',
      'head',
      'vp',
      'chief',
    ],
  },

  // -------------------------------------------------------------------------
  // HEAD OF ENGINEERING / HEAD OF TECHNOLOGY
  // -------------------------------------------------------------------------
  head_of_engineering: {
    displayName: 'Head of Engineering',
    titleWeight: 45,
    exactTitles: [
      'head of engineering',
      'head of technology',
      'head of software engineering',
      'head of software',
      'head of development',
      'head of tech',
      'head of product engineering',
      'head of platform',
      'head of infrastructure',
      'engineering head',
      'technology head',
    ],
    partialTitles: [
      'head of engineering',
      'head of technology',
      'head of software',
      'head of tech',
      'head of development',
    ],
    excludeIfContains: [],
  },

  // -------------------------------------------------------------------------
  // DIRECTOR OF ENGINEERING
  // -------------------------------------------------------------------------
  director_of_engineering: {
    displayName: 'Director of Engineering',
    titleWeight: 45,
    exactTitles: [
      'director of engineering',
      'director of technology',
      'director of software engineering',
      'director of software development',
      'director engineering',
      'director technology',
      'director software engineering',
      'engineering director',
      'technology director',
      'software engineering director',
      'software director',
      'development director',
      'director of platform',
      'director of infrastructure',
      'senior director of engineering',
      'senior engineering director',
    ],
    partialTitles: [
      'director of engineering',
      'director of technology',
      'director engineering',
      'engineering director',
      'technology director',
    ],
    excludeIfContains: [],
  },

  // -------------------------------------------------------------------------
  // CTO / CHIEF TECHNOLOGY OFFICER
  // -------------------------------------------------------------------------
  cto: {
    displayName: 'CTO',
    titleWeight: 50, // Highest weight
    exactTitles: [
      'cto',
      'chief technology officer',
      'chief technical officer',
      'technical co-founder',
      'technical cofounder',
      'cofounder cto',
      'co-founder cto',
      'founding cto',
      'cto & co-founder',
      'cto and co-founder',
      'vp engineering',
      'vp of engineering',
      'vice president engineering',
      'vice president of engineering',
      'svp engineering',
      'svp of engineering',
      'evp engineering',
    ],
    partialTitles: [
      'cto',
      'chief technology',
      'chief technical',
      'vp engineering',
      'vp of engineering',
      'vice president engineering',
    ],
    excludeIfContains: [],
  },
};

// =============================================================================
// UNWANTED TITLE KEYWORDS - Applies to all roles
// =============================================================================

const UNWANTED_TITLE_KEYWORDS = [
  'sales',
  'business development',
  'accounting',
  'clinical',
  'marketing',
  'hr',
  'human resources',
  'recruiter',
  'recruiting',
  'customer success',
  'customer support',
  'support engineer',
  'solutions engineer',
  'pre-sales',
  'presales',
  'field engineer',
  'implementation',
  'consultant',
  'data analyst',
  'business analyst',
  'project manager',
  'program manager',
  'scrum master',
  'product manager',
  'product owner',
  'qa engineer',
  'test engineer',
  'sdet',
  'security engineer',
  'network engineer',
  'systems administrator',
  'devops engineer',
  'sre',
  'site reliability',
  'data engineer',
  'machine learning engineer',
  'ml engineer',
  'ai engineer',
  'research scientist',
  'research engineer',
];

// =============================================================================
// SENIORITY LEVELS
// =============================================================================

const SENIORITY_LEVELS = {
  executive: {
    keywords: ['executive', 'c-level', 'c-suite', 'chief', 'cto', 'ceo', 'coo', 'cfo'],
    score: 15,
  },
  director: {
    keywords: ['director', 'vp', 'vice president', 'head of', 'head'],
    score: 12,
  },
  senior_ic: {
    keywords: ['staff', 'principal', 'distinguished', 'fellow', 'architect'],
    score: 10,
  },
  lead: {
    keywords: ['lead', 'tech lead', 'team lead'],
    score: 8,
  },
  senior: {
    keywords: ['senior', 'sr.', 'sr ', 'mid-senior'],
    score: 6,
  },
  mid: {
    keywords: ['mid', 'intermediate', 'regular'],
    score: 0,
  },
  junior: {
    keywords: ['junior', 'jr.', 'jr ', 'entry', 'associate', 'intern', 'trainee', 'graduate'],
    score: -25,
  },
};

// =============================================================================
// KEYWORD CATEGORIES - Derived from role_skills_taxonomy.json
// =============================================================================

// TECHNOLOGY VISION & STRATEGY (CTO/Head/Director focus)
const VISION_STRATEGY_KEYWORDS = [
  'technology strategy', 'technical strategy', 'technology vision', 'technical vision',
  'digital transformation', 'transformation', 'innovation', 'roadmap', 'strategic',
  'vision', 'modernization', 'platform strategy',
  // AI/ML
  'ai', 'artificial intelligence', 'ml', 'machine learning', 'llm', 'large language model',
  'generative ai', 'deep learning', 'data science', 'nlp', 'computer vision',
  // Growth
  'growth', 'scale', 'scaling', 'hypergrowth', '0-1', 'zero to one', '0 to 1',
  'series a', 'series b', 'series c', 'startup', 'scaleup',
];

// BUSINESS PARTNERSHIP (Executive/Director focus)
const BUSINESS_KEYWORDS = [
  'executive', 'c-level', 'c-suite', 'board', 'leadership team', 'leadership',
  'founder', 'co-founder', 'business', 'revenue', 'budget', 'p&l', 'profit',
  'stakeholder', 'investor', 'fundraising', 'due diligence', 'hiring', 'recruiting',
  'talent', 'build team', 'grow team', 'cross-functional', 'product', 'partnership', 'vendor',
];

// ENGINEERING ORGANIZATION (Head/Director/Manager focus)
const ORG_KEYWORDS = [
  'engineering organization', 'organization', 'org design', 'team building', 'culture',
  'engineering culture', 'engineering excellence', 'build team', 'scale team',
  'multiple teams', 'engineering team', 'tech team', 'agile', 'scrum', 'okr',
  'objectives', 'monitoring', 'reliability', 'sre', 'performance management',
  'career development', 'mentoring', 'coaching', '1:1', 'one-on-one', 'direct reports',
];

// TECHNICAL LEADERSHIP (All roles)
const TECHNICAL_LEADERSHIP_KEYWORDS = [
  'technical leadership', 'tech leadership', 'engineering leadership', 'lead engineers',
  'mentor', 'technical direction', 'architect', 'technical vision', 'engineering excellence',
  'technical strategy', 'code review', 'design review', 'architecture review',
  'technical hiring', 'technical interviews', 'engineering standards', 'best practices',
];

// ARCHITECTURE & DESIGN (Staff/Principal/Lead focus)
const ARCHITECTURE_KEYWORDS = [
  'architecture', 'software architecture', 'cloud architecture', 'system design',
  'systems design', 'platform', 'technical', 'tech stack', 'microservices',
  'event-driven', 'event driven', 'distributed systems', 'distributed', 'api design',
  'api', 'rest api', 'graphql', 'ddd', 'domain-driven design', 'domain driven design',
  'cqrs', 'event sourcing', 'bounded contexts', 'hexagonal', 'clean architecture',
  'scalability', 'high availability', 'fault tolerance', 'resilience',
];

// CLOUD & INFRASTRUCTURE (All roles)
const CLOUD_INFRA_KEYWORDS = [
  'aws', 'gcp', 'azure', 'cloud', 'cloud native', 'cloud-native', 'kubernetes', 'k8s',
  'docker', 'containerization', 'infrastructure', 'infrastructure as code', 'iac',
  'terraform', 'serverless', 'lambda', 'ecs', 'eks', 'fargate',
  'kafka', 'data pipelines', 'data engineering', 'big data', 'analytics',
  'ci/cd', 'cicd', 'devops', 'gitops', 'github actions', 'jenkins',
  'observability', 'monitoring', 'logging', 'tracing', 'datadog', 'grafana', 'prometheus',
];

// PROGRAMMING LANGUAGES & FRAMEWORKS (All roles, especially IC)
const LANGUAGES_FRAMEWORKS_KEYWORDS = [
  // Languages
  'typescript', 'python', 'javascript', 'node.js', 'nodejs', 'java', 'go', 'golang',
  'c++', 'c#', 'rust', 'scala', 'kotlin', 'ruby', 'php', 'swift',
  // Frontend
  'react', 'angular', 'vue', 'vue.js', 'next.js', 'nextjs', 'svelte',
  // Backend
  'nestjs', 'flask', 'fastapi', 'django', 'spring', 'spring boot', 'express',
  '.net', 'rails', 'laravel',
  // Databases
  'postgresql', 'postgres', 'mongodb', 'mysql', 'redis', 'elasticsearch', 'opensearch',
  'dynamodb', 'cassandra', 'sql', 'nosql',
];

// DELIVERY & QUALITY (All roles)
const DELIVERY_KEYWORDS = [
  'agile', 'scrum', 'kanban', 'sprint', 'delivery', 'ship', 'release', 'deployment',
  'quality', 'testing', 'tdd', 'bdd', 'unit testing', 'integration testing',
  'production', 'incident', 'on-call', 'reliability', 'sla', 'uptime',
  'performance', 'optimization', 'latency', 'throughput',
];

// COMPLIANCE & SECURITY (Director/CTO focus)
const COMPLIANCE_KEYWORDS = [
  'compliance', 'security', 'gdpr', 'sox', 'hipaa', 'pci', 'iso 27001',
  'data protection', 'privacy', 'audit', 'certification', 'risk management',
];

// ACHIEVEMENT INDICATORS (All roles)
const ACHIEVEMENT_KEYWORDS = [
  'scaled', 'grew', 'built', 'transformed', 'modernized', 'migrated', 'led',
  'delivered', 'shipped', 'launched', 'released', 'deployed', 'implemented',
  'reduced', 'improved', 'increased', 'saved', 'achieved', 'drove',
  'revenue', 'cost reduction', 'efficiency', 'performance improvement',
  '99.9%', '99.99%', 'zero downtime', 'hired', 'onboarded', 'retention',
];

// =============================================================================
// LOCATION & LANGUAGE PREFERENCES
// =============================================================================

const REMOTE_POSITIVE = [
  'remote', 'remote-first', 'distributed', 'work from anywhere', 'wfh',
  'hybrid', 'flexible location', 'global', 'work from home',
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
    'cto',
    'director_of_engineering',
    'head_of_engineering',
    'engineering_manager',
    'software_architect',
    'staff_engineer',
    'tech_lead',
    'lead_engineer',
    'senior_engineer',
  ];

  for (const roleKey of roleOrder) {
    const role = ROLE_DEFINITIONS[roleKey];

    // Check exact titles first
    for (const exactTitle of role.exactTitles) {
      if (t === exactTitle || t.includes(exactTitle)) {
        // Check exclusions
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

  return null;
}

function getTitleScore(title, detectedRole) {
  if (!detectedRole) return 0;

  const t = (title || '').toLowerCase().trim();
  const role = ROLE_DEFINITIONS[detectedRole];

  // Check for exact match
  for (const exactTitle of role.exactTitles) {
    if (t === exactTitle) {
      return role.titleWeight;
    }
  }

  // Partial match gets slightly less
  for (const exactTitle of role.exactTitles) {
    if (t.includes(exactTitle)) {
      return Math.round(role.titleWeight * 0.9);
    }
  }

  // Partial title match
  for (const partial of role.partialTitles) {
    if (t.includes(partial.toLowerCase())) {
      return Math.round(role.titleWeight * 0.8);
    }
  }

  return Math.round(role.titleWeight * 0.5);
}

function getSeniorityScore(text) {
  const t = (text || '').toLowerCase();

  // Check from highest to lowest
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
  senior_engineer: {
    vision: { weight: 1, max: 10 },
    business: { weight: 0.5, max: 5 },
    org: { weight: 1, max: 10 },
    techLeadership: { weight: 1.5, max: 15 },
    architecture: { weight: 2, max: 20 },
    cloudInfra: { weight: 2, max: 20 },
    languages: { weight: 2.5, max: 25 },
    delivery: { weight: 1.5, max: 15 },
    compliance: { weight: 0.5, max: 5 },
    achievement: { weight: 1, max: 10 },
  },
  staff_engineer: {
    vision: { weight: 1.5, max: 15 },
    business: { weight: 1, max: 10 },
    org: { weight: 1.5, max: 15 },
    techLeadership: { weight: 2, max: 20 },
    architecture: { weight: 2.5, max: 25 },
    cloudInfra: { weight: 2, max: 20 },
    languages: { weight: 2, max: 20 },
    delivery: { weight: 1.5, max: 15 },
    compliance: { weight: 1, max: 10 },
    achievement: { weight: 1.5, max: 15 },
  },
  software_architect: {
    vision: { weight: 2, max: 20 },
    business: { weight: 1.5, max: 15 },
    org: { weight: 1.5, max: 15 },
    techLeadership: { weight: 2.5, max: 25 },
    architecture: { weight: 3, max: 30 },  // Highest weight - core competency
    cloudInfra: { weight: 2.5, max: 25 },
    languages: { weight: 1.5, max: 15 },
    delivery: { weight: 1.5, max: 15 },
    compliance: { weight: 1.5, max: 15 },
    achievement: { weight: 1.5, max: 15 },
  },
  engineering_manager: {
    vision: { weight: 1.5, max: 15 },
    business: { weight: 2, max: 20 },      // Hiring, stakeholders, cross-functional
    org: { weight: 3, max: 30 },           // Highest - team building, culture, mentoring
    techLeadership: { weight: 2.5, max: 25 },
    architecture: { weight: 1.5, max: 15 },
    cloudInfra: { weight: 1, max: 10 },
    languages: { weight: 1, max: 10 },     // Lower - less hands-on coding expected
    delivery: { weight: 2.5, max: 25 },    // High - delivery is key responsibility
    compliance: { weight: 1, max: 10 },
    achievement: { weight: 2, max: 20 },
  },
  lead_engineer: {
    vision: { weight: 1, max: 10 },
    business: { weight: 1, max: 10 },
    org: { weight: 2, max: 20 },
    techLeadership: { weight: 2.5, max: 25 },
    architecture: { weight: 2, max: 20 },
    cloudInfra: { weight: 1.5, max: 15 },
    languages: { weight: 2, max: 20 },
    delivery: { weight: 2, max: 20 },
    compliance: { weight: 0.5, max: 5 },
    achievement: { weight: 1.5, max: 15 },
  },
  tech_lead: {
    vision: { weight: 1, max: 10 },
    business: { weight: 1, max: 10 },
    org: { weight: 2, max: 20 },
    techLeadership: { weight: 2.5, max: 25 },
    architecture: { weight: 2, max: 20 },
    cloudInfra: { weight: 1.5, max: 15 },
    languages: { weight: 2, max: 20 },
    delivery: { weight: 2, max: 20 },
    compliance: { weight: 0.5, max: 5 },
    achievement: { weight: 1.5, max: 15 },
  },
  head_of_engineering: {
    vision: { weight: 2.5, max: 25 },
    business: { weight: 2, max: 20 },
    org: { weight: 2.5, max: 25 },
    techLeadership: { weight: 2, max: 20 },
    architecture: { weight: 1.5, max: 15 },
    cloudInfra: { weight: 1, max: 10 },
    languages: { weight: 1, max: 10 },
    delivery: { weight: 1.5, max: 15 },
    compliance: { weight: 1.5, max: 15 },
    achievement: { weight: 2, max: 20 },
  },
  director_of_engineering: {
    vision: { weight: 2.5, max: 25 },
    business: { weight: 2, max: 20 },
    org: { weight: 2.5, max: 25 },
    techLeadership: { weight: 2, max: 20 },
    architecture: { weight: 1.5, max: 15 },
    cloudInfra: { weight: 1, max: 10 },
    languages: { weight: 1, max: 10 },
    delivery: { weight: 1.5, max: 15 },
    compliance: { weight: 1.5, max: 15 },
    achievement: { weight: 2, max: 20 },
  },
  cto: {
    vision: { weight: 3, max: 30 },
    business: { weight: 2.5, max: 25 },
    org: { weight: 2, max: 20 },
    techLeadership: { weight: 2, max: 20 },
    architecture: { weight: 1.5, max: 15 },
    cloudInfra: { weight: 1, max: 10 },
    languages: { weight: 0.5, max: 5 },
    delivery: { weight: 1, max: 10 },
    compliance: { weight: 2, max: 20 },
    achievement: { weight: 2.5, max: 25 },
  },
};

// Default weights if role not detected
const DEFAULT_WEIGHTS = {
  vision: { weight: 1.5, max: 15 },
  business: { weight: 1.5, max: 15 },
  org: { weight: 1.5, max: 15 },
  techLeadership: { weight: 2, max: 20 },
  architecture: { weight: 2, max: 20 },
  cloudInfra: { weight: 1.5, max: 15 },
  languages: { weight: 1.5, max: 15 },
  delivery: { weight: 1.5, max: 15 },
  compliance: { weight: 1, max: 10 },
  achievement: { weight: 1.5, max: 15 },
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

  // Combined text for keyword searching
  const fullText = `${titleLower} ${critLower} ${descLower}`;
  const locAndDesc = `${locLower} ${descLower}`;

  // -------------------------------------------------------------------------
  // DETECT ROLE
  // -------------------------------------------------------------------------
  const detectedRole = detectRole(title);

  // Check if role is in our target filter
  const isTargetRole = TARGET_ROLE_FILTER.length === 0 ||
    (detectedRole && TARGET_ROLE_FILTER.includes(detectedRole));

  if (!isTargetRole) {
    return {
      score: 0,
      detectedRole: detectedRole,
      isTargetRole: false,
      breakdown: {},
    };
  }

  // Get role-specific weights
  const weights = detectedRole ? ROLE_WEIGHTS[detectedRole] || DEFAULT_WEIGHTS : DEFAULT_WEIGHTS;

  // -------------------------------------------------------------------------
  // 1) TITLE SCORE (0-50 points)
  // -------------------------------------------------------------------------
  const titleScore = getTitleScore(title, detectedRole);

  // Penalty for unwanted title keywords
  const unwantedCount = countUnwantedTitleKeywords(title);
  const unwantedPenalty = Math.min(unwantedCount * 30, 50);

  // -------------------------------------------------------------------------
  // 2) SENIORITY SCORE (-25 to +15 points)
  // -------------------------------------------------------------------------
  const seniorityResult = getSeniorityScore(`${titleLower} ${critLower}`);
  const seniorityScore = seniorityResult.score;

  // -------------------------------------------------------------------------
  // 3) KEYWORD SCORES (role-weighted)
  // -------------------------------------------------------------------------
  const visionScore = countKeywordsWeighted(
    fullText, VISION_STRATEGY_KEYWORDS, weights.vision.weight, weights.vision.max
  );

  const businessScore = countKeywordsWeighted(
    fullText, BUSINESS_KEYWORDS, weights.business.weight, weights.business.max
  );

  const orgScore = countKeywordsWeighted(
    fullText, ORG_KEYWORDS, weights.org.weight, weights.org.max
  );

  const techLeadershipScore = countKeywordsWeighted(
    fullText, TECHNICAL_LEADERSHIP_KEYWORDS, weights.techLeadership.weight, weights.techLeadership.max
  );

  const architectureScore = countKeywordsWeighted(
    fullText, ARCHITECTURE_KEYWORDS, weights.architecture.weight, weights.architecture.max
  );

  const cloudInfraScore = countKeywordsWeighted(
    fullText, CLOUD_INFRA_KEYWORDS, weights.cloudInfra.weight, weights.cloudInfra.max
  );

  const languagesScore = countKeywordsWeighted(
    fullText, LANGUAGES_FRAMEWORKS_KEYWORDS, weights.languages.weight, weights.languages.max
  );

  const deliveryScore = countKeywordsWeighted(
    fullText, DELIVERY_KEYWORDS, weights.delivery.weight, weights.delivery.max
  );

  const complianceScore = countKeywordsWeighted(
    fullText, COMPLIANCE_KEYWORDS, weights.compliance.weight, weights.compliance.max
  );

  const achievementScore = countKeywordsWeighted(
    fullText, ACHIEVEMENT_KEYWORDS, weights.achievement.weight, weights.achievement.max
  );

  // -------------------------------------------------------------------------
  // 4) REMOTE PREFERENCE (-10 to +10)
  // -------------------------------------------------------------------------
  let remoteScore = 0;
  if (containsAny(locAndDesc, REMOTE_POSITIVE)) {
    remoteScore += 10;
  }
  if (containsAny(locAndDesc, REMOTE_NEGATIVE)) {
    remoteScore -= 10;
  }

  // -------------------------------------------------------------------------
  // 5) LANGUAGE REQUIREMENTS (-10 to 0)
  // -------------------------------------------------------------------------
  let languageScore = 0;
  if (containsAny(descLower, LANGUAGE_NEGATIVE)) {
    languageScore -= 10;
  }

  // Non-English posting detection
  const chars = Array.from(jobDescription || '');
  const nonAsciiChars = chars.filter((ch) => ch.charCodeAt(0) > 127).length;
  const totalChars = chars.length || 1;
  const nonAsciiRatio = nonAsciiChars / totalChars;
  if (nonAsciiRatio > 0.3) {
    languageScore -= 10;
  }

  // -------------------------------------------------------------------------
  // CALCULATE TOTAL
  // -------------------------------------------------------------------------
  const keywordTotal = visionScore + businessScore + orgScore + techLeadershipScore +
    architectureScore + cloudInfraScore + languagesScore + deliveryScore +
    complianceScore + achievementScore;

  const rawScore =
    titleScore +           // 0-50
    seniorityScore +       // -25 to 15
    keywordTotal +         // 0-~180 (varies by role)
    remoteScore +          // -10 to 10
    languageScore -        // -20 to 0
    unwantedPenalty;       // 0-50 penalty

  // Calculate max possible for this role
  const maxKeywordScore = Object.values(weights).reduce((sum, w) => sum + w.max, 0);
  const maxPossible = 50 + 15 + maxKeywordScore + 10; // title + seniority + keywords + remote

  // Normalize to 0-100
  const normalizedScore = Math.max(0, Math.min(100, Math.round((rawScore / maxPossible) * 100)));

  return {
    score: normalizedScore,
    detectedRole: detectedRole,
    isTargetRole: true,
    seniorityLevel: seniorityResult.level,
    breakdown: {
      title: titleScore,
      seniority: seniorityScore,
      vision: Math.round(visionScore),
      business: Math.round(businessScore),
      org: Math.round(orgScore),
      techLeadership: Math.round(techLeadershipScore),
      architecture: Math.round(architectureScore),
      cloudInfra: Math.round(cloudInfraScore),
      languages: Math.round(languagesScore),
      delivery: Math.round(deliveryScore),
      compliance: Math.round(complianceScore),
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
  if (!scoreResult.isTargetRole) {
    return false;
  }
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
