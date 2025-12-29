// rule_scoring_cto.js
// Enhanced deterministic Level-1 rule scoring for CTO / Technical Executive roles.
// Comprehensive keyword matching from taxonomy and master-cv for granular scoring.

// =============================================================================
// TITLE MATCHING (High Weight: 0-50 points)
// =============================================================================

const TARGET_TITLES = [
  // Primary CTO titles (exact match bonus)
  'cto',
  'chief technology officer',
  'chief technical officer',

  // Co-founder variants
  'technical co-founder',
  'technical cofounder',
  'cofounder cto',
  'co-founder cto',
  'founding cto',

  // VP/Head level (stepping stone roles)
  'vp engineering',
  'vp of engineering',
  'vice president engineering',
  'vice president of engineering',
  'head of engineering',
  'head of technology',
  'head of tech',

  // Director level
  'director of engineering',
  'engineering director',
  'director of technology',
  'technology director',
  'director engineering',

  // Principal/Staff (technical track to CTO)
  'principal engineer',
  'staff engineer',
  'distinguished engineer',
  'principal architect',
  'chief architect',
  'enterprise architect',
];

// Exact CTO titles get maximum score
const EXACT_CTO_TITLES = [
  'cto',
  'chief technology officer',
  'chief technical officer',
  'technical co-founder',
  'technical cofounder',
  'cofounder cto',
  'co-founder cto',
  'founding cto',
];

// Keywords that indicate non-target roles
const UNWANTED_TITLE_KEYWORDS = [
  'sales',
  'business development',
  'accounting',
  'clinical',
  'marketing',
  'hr',
  'human resources',
  'recruiting',
  'customer success',
  'support',
  'operations manager', // non-tech ops
];

// =============================================================================
// SENIORITY MATCHING (0-15 points)
// =============================================================================

const DESIRED_SENIORITY = [
  'executive',
  'c-level',
  'c-suite',
  'director',
  'vp',
  'vice president',
  'head',
  'chief',
  'senior',
  'mid-senior level',
  'principal',
  'staff',
];

const UNWANTED_SENIORITY = [
  'entry level',
  'associate',
  'internship',
  'intern',
  'junior',
  'graduate',
  'trainee',
];

// =============================================================================
// TECHNOLOGY VISION & STRATEGY KEYWORDS (0-25 points)
// From CTO taxonomy section - highest priority for CTO roles
// =============================================================================

const VISION_STRATEGY_KEYWORDS = [
  // Core vision keywords
  'technology strategy',
  'technical strategy',
  'technology vision',
  'technical vision',
  'digital transformation',
  'transformation',
  'innovation',
  'roadmap',
  'strategic',
  'vision',

  // AI/ML (hot for CTO roles)
  'ai',
  'artificial intelligence',
  'ml',
  'machine learning',
  'llm',
  'large language model',
  'generative ai',
  'deep learning',
  'data science',

  // Growth & Scale
  'growth',
  'scale',
  'scaling',
  'hypergrowth',
  '0-1',
  'zero to one',
  '0 to 1',
  'series a',
  'series b',
  'series c',
  'startup',
  'scaleup',
];

// =============================================================================
// BUSINESS PARTNERSHIP KEYWORDS (0-20 points)
// Executive-level business alignment
// =============================================================================

const BUSINESS_KEYWORDS = [
  // Executive presence
  'executive',
  'c-level',
  'c-suite',
  'board',
  'leadership team',
  'leadership',
  'founder',
  'co-founder',

  // Business alignment
  'business',
  'revenue',
  'budget',
  'p&l',
  'profit',
  'stakeholder',
  'investor',
  'fundraising',
  'due diligence',

  // Hiring & Talent
  'hiring',
  'recruiting',
  'talent',
  'build team',
  'grow team',

  // Cross-functional
  'cross-functional',
  'product',
  'partnership',
  'vendor',
];

// =============================================================================
// ENGINEERING ORGANIZATION KEYWORDS (0-15 points)
// Organization building capabilities
// =============================================================================

const ORG_KEYWORDS = [
  'engineering organization',
  'organization',
  'org design',
  'team building',
  'culture',
  'engineering culture',
  'engineering excellence',
  'build team',
  'scale team',
  'multiple teams',
  'engineering team',
  'tech team',
  'agile',
  'scrum',
  'okr',
  'objectives',
  'monitoring',
  'reliability',
  'sre',
];

// =============================================================================
// TECHNICAL AUTHORITY KEYWORDS (0-20 points)
// Architecture and platform expertise
// =============================================================================

const TECHNICAL_AUTHORITY_KEYWORDS = [
  // Architecture
  'architecture',
  'software architecture',
  'cloud architecture',
  'system design',
  'systems design',
  'platform',
  'technical',
  'tech stack',

  // Patterns
  'microservices',
  'event-driven',
  'event driven',
  'distributed systems',
  'distributed',
  'api design',
  'api',
  'rest api',
  'graphql',

  // Cloud & Infrastructure
  'aws',
  'gcp',
  'azure',
  'cloud',
  'cloud native',
  'cloud-native',
  'kubernetes',
  'k8s',
  'docker',
  'containerization',
  'infrastructure',
  'infrastructure as code',
  'iac',
  'terraform',
  'serverless',

  // Data & Streaming
  'kafka',
  'data pipelines',
  'data engineering',
  'big data',
  'analytics',

  // Compliance & Security
  'compliance',
  'security',
  'gdpr',
  'sox',
  'hipaa',
  'pci',
];

// =============================================================================
// HARD SKILLS FROM MASTER CV (0-15 points)
// Technical skills that demonstrate hands-on capability
// =============================================================================

const HARD_SKILLS_KEYWORDS = [
  // Languages (from master CV)
  'typescript',
  'python',
  'javascript',
  'node.js',
  'nodejs',
  'java',
  'go',
  'golang',
  'c++',
  'c#',
  'rust',

  // Frameworks
  'react',
  'angular',
  'nestjs',
  'flask',
  'fastapi',

  // Databases
  'postgresql',
  'postgres',
  'mongodb',
  'mysql',
  'redis',
  'elasticsearch',
  'opensearch',

  // AWS Services (from master CV)
  'lambda',
  'ecs',
  'eventbridge',
  's3',
  'cloudfront',
  'fargate',
  'sns',
  'sqs',
  'dynamodb',

  // DevOps & CI/CD
  'ci/cd',
  'cicd',
  'github actions',
  'jenkins',
  'devops',
  'gitops',

  // Observability
  'observability',
  'datadog',
  'grafana',
  'prometheus',
  'logging',
  'monitoring',
  'tracing',

  // Messaging
  'rabbitmq',
  'kafka',
  'pub/sub',
  'message queue',

  // Methodologies
  'ddd',
  'domain-driven design',
  'domain driven design',
  'cqrs',
  'event sourcing',
  'tdd',
  'bdd',
];

// =============================================================================
// SOFT SKILLS & LEADERSHIP (0-10 points)
// Leadership and executive presence
// =============================================================================

const LEADERSHIP_KEYWORDS = [
  'technical leadership',
  'engineering leadership',
  'mentoring',
  'coaching',
  'stakeholder management',
  'executive communication',
  'strategic planning',
  'change management',
  'performance management',
  'talent development',
  'career development',
  'team development',
  'innovation culture',
  'thought leadership',
  'decision making',
  'risk management',
];

// =============================================================================
// ACHIEVEMENT THEMES (0-10 points)
// Evidence of impact and transformation
// =============================================================================

const ACHIEVEMENT_KEYWORDS = [
  // Scale & Growth
  'scaled',
  'grew',
  'built',
  'transformed',
  'modernized',
  'migrated',

  // Metrics
  'revenue',
  'cost reduction',
  'efficiency',
  'performance improvement',
  'latency reduction',
  'uptime',
  '99.9%',
  '99.99%',
  'sla',

  // Team building
  'hired',
  'onboarded',
  'retention',
  'promoted',

  // Delivery
  'delivered',
  'shipped',
  'launched',
  'released',
  'deployed',

  // Compliance & Trust
  'audit',
  'certification',
  'compliant',
  'zero downtime',
];

// =============================================================================
// REMOTE/LOCATION PREFERENCES (-10 to +10)
// =============================================================================

const REMOTE_POSITIVE = [
  'remote',
  'remote-first',
  'distributed',
  'work from anywhere',
  'wfh',
  'hybrid',
  'flexible location',
  'global',
];

const REMOTE_NEGATIVE = [
  'onsite only',
  'on-site only',
  'office only',
  'no remote',
  'must relocate',
  'relocation required',
];

// =============================================================================
// LANGUAGE REQUIREMENTS (-10 to 0)
// =============================================================================

const LANGUAGE_NEGATIVE = [
  'fluent arabic',
  'arabic speaker',
  'native arabic',
  'fluent spanish',
  'spanish speaker',
  'fluent french',
  'french speaker',
  'fluent german',
  'german speaker',
  'fluent mandarin',
  'mandarin speaker',
  'fluent japanese',
  'japanese speaker',
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

function hasExactCTOTitle(title) {
  const t = (title || '').toLowerCase().trim();
  return EXACT_CTO_TITLES.some((ctoTitle) => {
    // Check if title starts with or equals the CTO title
    return t === ctoTitle || t.startsWith(ctoTitle + ' ') || t.startsWith(ctoTitle + ',') || t.startsWith(ctoTitle + '/');
  });
}

function hasTargetRoleTitle(title) {
  return containsAny(title, TARGET_TITLES);
}

function countUnwantedTitleKeywords(title) {
  const t = (title || '').toLowerCase();
  return UNWANTED_TITLE_KEYWORDS.reduce(
    (acc, kw) => (t.includes(kw.toLowerCase()) ? acc + 1 : acc),
    0,
  );
}

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

  // -------------------------------------------------------------------------
  // 1) TITLE SCORE (0-50 points) - Highest weight for CTO matching
  // -------------------------------------------------------------------------
  let titleScore = 0;

  if (hasExactCTOTitle(titleLower)) {
    // Exact CTO title match = maximum title score
    titleScore = 50;
  } else if (hasTargetRoleTitle(titleLower)) {
    // VP/Head/Director level = good but not maximum
    if (containsAny(titleLower, ['vp', 'vice president', 'head of'])) {
      titleScore = 35;
    } else if (containsAny(titleLower, ['director'])) {
      titleScore = 30;
    } else if (containsAny(titleLower, ['principal', 'staff', 'architect'])) {
      titleScore = 25;
    } else {
      titleScore = 20;
    }
  }

  // Penalty for unwanted title keywords
  const unwantedTitleCount = countUnwantedTitleKeywords(title);
  const unwantedTitlePenalty = Math.min(unwantedTitleCount * 25, 50);

  // -------------------------------------------------------------------------
  // 2) SENIORITY SCORE (0-15 points)
  // -------------------------------------------------------------------------
  let seniorityScore = 0;
  for (const s of DESIRED_SENIORITY) {
    if (critLower.includes(s) || titleLower.includes(s)) {
      seniorityScore = 15;
      break;
    }
  }
  // Penalty for junior/entry level
  for (const s of UNWANTED_SENIORITY) {
    if (critLower.includes(s) || titleLower.includes(s)) {
      seniorityScore = -20; // Strong penalty
      break;
    }
  }

  // -------------------------------------------------------------------------
  // 3) VISION & STRATEGY SCORE (0-25 points) - Critical for CTO
  // -------------------------------------------------------------------------
  const visionScore = countKeywordsWeighted(fullText, VISION_STRATEGY_KEYWORDS, 3, 25);

  // -------------------------------------------------------------------------
  // 4) BUSINESS PARTNERSHIP SCORE (0-20 points)
  // -------------------------------------------------------------------------
  const businessScore = countKeywordsWeighted(fullText, BUSINESS_KEYWORDS, 2, 20);

  // -------------------------------------------------------------------------
  // 5) ORG BUILDING SCORE (0-15 points)
  // -------------------------------------------------------------------------
  const orgScore = countKeywordsWeighted(fullText, ORG_KEYWORDS, 2, 15);

  // -------------------------------------------------------------------------
  // 6) TECHNICAL AUTHORITY SCORE (0-20 points)
  // -------------------------------------------------------------------------
  const techScore = countKeywordsWeighted(fullText, TECHNICAL_AUTHORITY_KEYWORDS, 1.5, 20);

  // -------------------------------------------------------------------------
  // 7) HARD SKILLS SCORE (0-15 points)
  // -------------------------------------------------------------------------
  const hardSkillsScore = countKeywordsWeighted(fullText, HARD_SKILLS_KEYWORDS, 1, 15);

  // -------------------------------------------------------------------------
  // 8) LEADERSHIP SCORE (0-10 points)
  // -------------------------------------------------------------------------
  const leadershipScore = countKeywordsWeighted(fullText, LEADERSHIP_KEYWORDS, 2, 10);

  // -------------------------------------------------------------------------
  // 9) ACHIEVEMENT SCORE (0-10 points)
  // -------------------------------------------------------------------------
  const achievementScore = countKeywordsWeighted(fullText, ACHIEVEMENT_KEYWORDS, 1.5, 10);

  // -------------------------------------------------------------------------
  // 10) REMOTE PREFERENCE (-10 to +10)
  // -------------------------------------------------------------------------
  let remoteScore = 0;
  const locAndDesc = `${locLower} ${descLower}`;
  if (containsAny(locAndDesc, REMOTE_POSITIVE)) {
    remoteScore += 10;
  }
  if (containsAny(locAndDesc, REMOTE_NEGATIVE)) {
    remoteScore -= 10;
  }

  // -------------------------------------------------------------------------
  // 11) LANGUAGE REQUIREMENTS (-10 to 0)
  // -------------------------------------------------------------------------
  let languageScore = 0;
  if (containsAny(descLower, LANGUAGE_NEGATIVE)) {
    languageScore -= 10;
  }

  // Non-English posting detection (high non-ASCII ratio)
  const chars = Array.from(jobDescription || '');
  const nonAsciiChars = chars.filter((ch) => ch.charCodeAt(0) > 127).length;
  const totalChars = chars.length || 1;
  const nonAsciiRatio = nonAsciiChars / totalChars;
  if (nonAsciiRatio > 0.3) {
    languageScore -= 10;
  }

  // -------------------------------------------------------------------------
  // FINAL SCORE CALCULATION
  // -------------------------------------------------------------------------
  const rawScore =
    titleScore +           // 0-50
    seniorityScore +       // -20 to 15
    visionScore +          // 0-25
    businessScore +        // 0-20
    orgScore +             // 0-15
    techScore +            // 0-20
    hardSkillsScore +      // 0-15
    leadershipScore +      // 0-10
    achievementScore +     // 0-10
    remoteScore +          // -10 to 10
    languageScore -        // -20 to 0
    unwantedTitlePenalty;  // 0-50 penalty

  // Normalize to 0-100 scale
  // Max possible: 50+15+25+20+15+20+15+10+10+10 = 190
  // Normalize by dividing by 1.9 to get 0-100 scale
  const normalizedScore = Math.max(0, Math.min(100, Math.round(rawScore / 1.9)));

  return normalizedScore;
}

// =============================================================================
// PROMOTION DECISION
// =============================================================================

function shouldPromoteToLevel2(job, threshold = 25) {
  const title = job.title || '';

  // Must have at least a target role title
  if (!hasTargetRoleTitle(title)) {
    return false;
  }

  const score = computeRuleScore(job);
  return score >= threshold;
}

// =============================================================================
// SCORE BREAKDOWN (for debugging/transparency)
// =============================================================================

function computeScoreBreakdown(job) {
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

  // Calculate individual scores
  let titleScore = 0;
  if (hasExactCTOTitle(titleLower)) {
    titleScore = 50;
  } else if (hasTargetRoleTitle(titleLower)) {
    if (containsAny(titleLower, ['vp', 'vice president', 'head of'])) {
      titleScore = 35;
    } else if (containsAny(titleLower, ['director'])) {
      titleScore = 30;
    } else if (containsAny(titleLower, ['principal', 'staff', 'architect'])) {
      titleScore = 25;
    } else {
      titleScore = 20;
    }
  }

  let seniorityScore = 0;
  for (const s of DESIRED_SENIORITY) {
    if (critLower.includes(s) || titleLower.includes(s)) {
      seniorityScore = 15;
      break;
    }
  }
  for (const s of UNWANTED_SENIORITY) {
    if (critLower.includes(s) || titleLower.includes(s)) {
      seniorityScore = -20;
      break;
    }
  }

  return {
    title: titleScore,
    seniority: seniorityScore,
    vision: countKeywordsWeighted(fullText, VISION_STRATEGY_KEYWORDS, 3, 25),
    business: countKeywordsWeighted(fullText, BUSINESS_KEYWORDS, 2, 20),
    org: countKeywordsWeighted(fullText, ORG_KEYWORDS, 2, 15),
    technical: countKeywordsWeighted(fullText, TECHNICAL_AUTHORITY_KEYWORDS, 1.5, 20),
    hardSkills: countKeywordsWeighted(fullText, HARD_SKILLS_KEYWORDS, 1, 15),
    leadership: countKeywordsWeighted(fullText, LEADERSHIP_KEYWORDS, 2, 10),
    achievement: countKeywordsWeighted(fullText, ACHIEVEMENT_KEYWORDS, 1.5, 10),
    remote: containsAny(locAndDesc, REMOTE_POSITIVE) ? 10 : (containsAny(locAndDesc, REMOTE_NEGATIVE) ? -10 : 0),
    unwantedTitlePenalty: -Math.min(countUnwantedTitleKeywords(title) * 25, 50),
  };
}

// =============================================================================
// N8N ENTRY POINT
// =============================================================================

function scoreItems(items) {
  return items.map((item) => {
    const job = item.json || {};
    const score = computeRuleScore(job);
    const promote = shouldPromoteToLevel2(job);
    const breakdown = computeScoreBreakdown(job);

    const newJson = {
      ...job,
      rule_score: score,
      rule_promote_to_level_2: promote,
      rule_score_breakdown: breakdown,
    };
    return { ...item, json: newJson };
  });
}

// Execute for n8n
const results = scoreItems($input.all());
return results;
