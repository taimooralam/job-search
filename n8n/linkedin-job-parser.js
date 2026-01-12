// Parse the "Job nodes" array (strings) into structured job objects
// Used in n8n EEA - Architect workflow
// Updated: 2026-01-12 - Improved dedupeKey to use jobId (robust) instead of text-based (fragile)

function cleanText(s) {
  if (typeof s !== 'string') return s;

  // Replace all escaped newlines and carriage returns
  s = s.replace(/\\r\\n/g, ' ')
       .replace(/\\n/g, ' ')
       .replace(/\r?\n/g, ' ');

  // Remove tabs and excessive spaces
  s = s.replace(/\t/g, ' ')
       .replace(/\s{2,}/g, ' ')
       .trim();

  // Remove leftover HTML tags
  s = s.replace(/<[^>]*>/g, '');

  // Remove invisible unicode characters (like NBSP or LRM)
  s = s.replace(/[\u200B-\u200D\uFEFF]/g, '');

  return s;
}

/**
 * Normalize text for deduplication - remove all non-alphanumeric chars
 * "McKinsey & Company" -> "mckinseycompany"
 * "Riyadh, Saudi Arabia" -> "riyadhsaudiarabia"
 */
function normalizeForDedupe(s) {
  if (!s) return '';
  return s.toLowerCase().replace(/[^a-z0-9]/g, '');
}

/**
 * Generate dedupe key with source ID priority
 * Priority: jobId (unique) > normalized company|title|location (fallback)
 *
 * Examples:
 *   With jobId: "linkedin|3847291058"
 *   Fallback:   "linkedin|mckinseycompany|seniorconsultant|riyadhsaudiarabia"
 */
function generateDedupeKey(source, jobId, company, title, location) {
  // Primary: Use jobId if available (most reliable for LinkedIn)
  if (jobId) {
    return `${source}|${jobId}`;
  }

  // Fallback: Normalized text fields
  const normCompany = normalizeForDedupe(company);
  const normTitle = normalizeForDedupe(title);
  const normLocation = normalizeForDedupe(location);

  return `${source}|${normCompany}|${normTitle}|${normLocation}`;
}

function extractJob(raw = '') {
  // guard
  if (typeof raw !== 'string' || !raw.trim()) return null;

  // 1) split into lines and strip noise
  const lines = raw
    .split('\n')
    .map(l => l.trim())
    .filter(Boolean);

  // 2) jobUrl = first URL in square brackets  [https://...]
  //    Use a CAPTURE GROUP so we get m[1], not undefined.
  const m = raw.match(/\[(https?:\/\/[^\]\s]+)\]/i);
  const jobUrl = m ? m[1] : '';
  const jobIdMatch = jobUrl.match(/-(\d+)(?:\?|$)/);
  const jobId = jobIdMatch ? jobIdMatch[1] : '';
  const jobScrapingUrl = jobIdMatch ? `https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/${jobId}` : '';

  // 3) title = first non-empty line
  const title = lines[0] || '';

  // 4) company: find a line whose NEXT line is a company link
  let company = '';
  for (let i = 0; i < lines.length - 1; i++) {
    const next = lines[i + 1] || '';
    if (/company/.test(next.toLowerCase())) {
      company = lines[i].trim();
      break;
    }
  }

  // Fallback: Try to extract from LinkedIn company URL pattern
  if (!company) {
    const companyLinkMatch = raw.match(/linkedin\.com\/company\/([^\/\?\s\]]+)/i);
    if (companyLinkMatch) {
      // Convert slug to readable name: "mckinsey-and-company" -> "mckinsey and company"
      company = companyLinkMatch[1].replace(/-/g, ' ');
    }
  }

  // Final fallback: all-caps line detection
  if (!company) {
    const capsLines = lines
      .map((l, i) => ({ i, l }))
      .filter(o =>
        /^[A-Z0-9&\- .,/()]+$/.test(o.l.trim()) &&
        !/^https?:\/\//i.test(o.l)
      );

    // pick the LAST all-caps line, not the first
    if (capsLines.length) {
      company = capsLines[capsLines.length - 1].l.trim();
    }
  }

  // 5) location: first line that looks like a place
  let location = '';
  const countryWords =
    /(Saudi|Arabia|UAE|United|Emirates|Qatar|Oman|Riyadh|Jiddah|Jeddah|Dubai|Doha|Muscat)/i;
  for (const l of lines) {
    if (countryWords.test(l) && !/\b(Hiring|Applicant|month|day|week|hour)\b/i.test(l)) {
      location = l;
      break;
    }
  }

  // 6) postedAt: last line mentioning time
  let postedAt = '';
  for (let i = lines.length - 1; i >= 0; i--) {
    const l = lines[i];
    if (/\b(ago|today|yesterday|hour|day|week|month|recently|early applicant)\b/i.test(l)) {
      postedAt = l;
      break;
    }
  }

  if (!title || !jobUrl) return null;

  const source = 'linkedin';

  // Use jobId-based dedupe key (robust) instead of text-based (fragile)
  const dedupeKey = generateDedupeKey(source, jobId, company, title, location);

  return {
    title: cleanText(title),
    company: cleanText(company),
    location: cleanText(location),
    postedAt: cleanText(postedAt),
    url: jobUrl,
    jobScrapingUrl,
    jobId: cleanText(jobId),
    source,
    dedupeKey,
    createdAt: new Date().toISOString()
  };
}

// ----- entry point -----
const arr = $json['Job nodes'];
if (!Array.isArray(arr)) {
  return [{ json: { error: 'Expected array at json["Job nodes"]' } }];
}

const jobs = arr.map(extractJob).filter(Boolean);

// Emit ONE item per job (downstream nodes will run once per item)
const r = jobs.map(j => ({ json: j }));
return r;
