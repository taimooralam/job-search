// rule_scoring.js
// Deterministic Level‑1 rule scoring for senior IC / lead engineering roles
// (Staff / Principal / Lead / Tech Lead / Engineering Lead / Team Lead).
// Can be required from Node/n8n and used to score LinkedIn job objects.

const TARGET_TITLES = [
  'staff software engineer',
  'principal software engineer',
  'lead software engineer',
  'technical lead',
  'tech lead',
  'engineering lead',
  'team lead',
];

// Keywords that indicate non-target roles even if the title
// superficially matches (e.g., Sales Engineering Manager).
const UNWANTED_TITLE_KEYWORDS = [
  'sales',
  'business',
  'accounting',
  'clinical',
];

const DESIRED_SENIORITY = [
  'mid-senior level',
  'senior',
  'director',
  'executive',
];

const UNWANTED_SENIORITY = [
  'entry level',
  'associate',
  'internship',
  'intern',
  'junior',
];

const ARCH_KEYWORDS = [
  'architecture',
  'architect',
  'system design',
  'distributed systems',
  'microservices',
  'event-driven',
  'event driven',
  'ddd',
  'domain-driven design',
  'cloud-native',
  'cloud native',
  'aws',
  'gcp',
  'azure',
];

function containsAny(text, keywords) {
  const t = (text || '').toLowerCase();
  return keywords.some((k) => t.includes(k));
}

function countKeywords(text, keywords) {
  const t = (text || '').toLowerCase();
  return keywords.reduce((acc, k) => (t.includes(k) ? acc + 1 : acc), 0);
}

function countUnwantedTitleKeywords(title) {
  const t = (title || '').toLowerCase();
  const words = t.split(/[^a-z0-9]+/).filter(Boolean);
  const wordSet = new Set(words);
  return UNWANTED_TITLE_KEYWORDS.reduce(
    (acc, kw) => (wordSet.has(kw) ? acc + 1 : acc),
    0,
  );
}

function hasTargetRoleTitle(title) {
  // Substring match so variants like "Senior Staff Software Engineer" or "Backend Tech Lead" are captured.
  return containsAny(title, TARGET_TITLES);
}

function computeRuleScore(job) {
  const title = job.title || '';
  const jobCriteria = job.job_criteria || '';
  const jobDescription = job.job_description || '';
  const location = job.location || '';

  const titleLower = title.toLowerCase();
  const critLower = jobCriteria.toLowerCase();
  const descLower = jobDescription.toLowerCase();
  const locLower = location.toLowerCase();

  // 1) Title score (0–40) for senior IC / lead engineering titles,
  //    with penalties for unwanted title keywords (sales, business, accounting, clinical).
  let titleScore = 0;
  if (hasTargetRoleTitle(titleLower)) {
    titleScore = 40;
  }
  const unwantedTitleCount = countUnwantedTitleKeywords(title);
  const unwantedTitlePenalty = Math.min(unwantedTitleCount * 40, 40);

  // 2) Seniority score (0–20).
  let seniorityScore = 0;
  for (const s of DESIRED_SENIORITY) {
    if (critLower.includes(s)) {
      seniorityScore = 20;
      break;
    }
  }
  if (seniorityScore === 0) {
    for (const s of UNWANTED_SENIORITY) {
      if (critLower.includes(s)) {
        seniorityScore = 0;
        break;
      }
    }
  }

  // 3) Architecture / domain keywords (0–20).
  const kwCount = countKeywords(`${descLower} ${critLower}`, ARCH_KEYWORDS);
  const archScore = Math.min(kwCount * 5, 20);

  // 4) Remote preference (−10 to +10).
  let remoteScore = 0;
  if (
    ['remote', 'remote-first', 'distributed', 'work from anywhere', 'rowe']
      .some((kw) => (locLower + ' ' + descLower).includes(kw))
  ) {
    remoteScore += 10;
  }
  if (
    ['onsite', 'on-site', 'on site', 'office only']
      .some((kw) => (locLower + ' ' + descLower).includes(kw))
  ) {
    remoteScore -= 10;
  }

  // 5) Language score (−10 to +10).
  let languageScore = 0;
  if (
    ['fluent arabic', 'arabic speaker', 'fluent spanish', 'spanish speaker']
      .some((kw) => descLower.includes(kw))
  ) {
    languageScore -= 10;
  }

  // Rough heuristic for non-English postings: lots of non-ASCII.
  const chars = Array.from(jobDescription || '');
  const nonAsciiChars = chars.filter((ch) => ch.charCodeAt(0) > 127).length;
  const totalChars = chars.length || 1;
  const nonAsciiRatio = nonAsciiChars / totalChars;
  if (nonAsciiRatio > 0.3) {
    languageScore -= 10;
  }

  const rawScore =
    titleScore +
    seniorityScore +
    archScore +
    remoteScore +
    languageScore -
    unwantedTitlePenalty;
  const score = Math.max(0, Math.min(100, rawScore));
  return Math.trunc(score);
}

function shouldPromoteToLevel2(job, threshold = 50) {
  // Deterministic Level‑1 check: Staff/Principal/Lead/Tech Lead/Engineering Lead/Team Lead title + score threshold.
  const title = job.title || '';
  if (!hasTargetRoleTitle(title)) {
    return false;
  }
  const score = computeRuleScore(job);
  return score >= threshold;
}

function scoreItems(items) {
  // items: array of { json: { ...job... } } as in n8n.
  return items.map((item) => {
    const job = item.json || {};
    const score = computeRuleScore(job);
    const promote = shouldPromoteToLevel2(job);
    const newJson = {
      ...job,
      rule_score: score,
      rule_promote_to_level_2: promote,
    };
    return { ...item, json: newJson };
  });
}

// CommonJS / Node export.
if (typeof module !== 'undefined') {
  module.exports = {
    computeRuleScore,
    shouldPromoteToLevel2,
    scoreItems,
  };
}
