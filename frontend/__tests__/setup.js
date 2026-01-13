/**
 * Jest Setup File
 *
 * Provides global mocks for browser APIs and external libraries
 * used by the frontend JavaScript files.
 */

// ============================================================
// Crypto API Mock
// ============================================================
const cryptoMock = {
  randomUUID: jest.fn(() => 'mock-uuid-' + Math.random().toString(36).substr(2, 9)),
  getRandomValues: jest.fn((arr) => {
    for (let i = 0; i < arr.length; i++) {
      arr[i] = Math.floor(Math.random() * 256);
    }
    return arr;
  }),
};

// Set on both global and window to ensure availability in all contexts
global.crypto = cryptoMock;
if (typeof window !== 'undefined') {
  window.crypto = cryptoMock;
}

// ============================================================
// Fetch API Mock
// ============================================================
global.fetch = jest.fn(() =>
  Promise.resolve({
    ok: true,
    json: () => Promise.resolve({}),
    text: () => Promise.resolve(''),
  })
);

// Helper to set up fetch mock responses
global.mockFetchResponse = (response, options = {}) => {
  const { ok = true, status = 200 } = options;
  global.fetch.mockImplementationOnce(() =>
    Promise.resolve({
      ok,
      status,
      json: () => Promise.resolve(response),
      text: () => Promise.resolve(JSON.stringify(response)),
    })
  );
};

global.mockFetchError = (error) => {
  global.fetch.mockImplementationOnce(() => Promise.reject(error));
};

// ============================================================
// Toast Notification Mock
// ============================================================
global.showToast = jest.fn();
window.showToast = global.showToast;

// ============================================================
// Navigator API Mocks
// ============================================================
Object.defineProperty(navigator, 'vibrate', {
  value: jest.fn(() => true),
  writable: true,
});

// ============================================================
// JDFormatter Mock (used by mobile-state.js)
// ============================================================
window.JDFormatter = {
  format: jest.fn((text) => `<p>${text}</p>`),
};

// ============================================================
// TipTap Editor Mock
// ============================================================
const createMockEditor = () => ({
  commands: {
    setContent: jest.fn(),
    focus: jest.fn(),
    blur: jest.fn(),
    toggleBold: jest.fn(),
    toggleItalic: jest.fn(),
    toggleUnderline: jest.fn(),
    toggleBulletList: jest.fn(),
    toggleOrderedList: jest.fn(),
    setFontSize: jest.fn(),
    setColor: jest.fn(),
    setHighlight: jest.fn(),
    undo: jest.fn(),
    redo: jest.fn(),
  },
  getHTML: jest.fn(() => '<p>Mock content</p>'),
  getJSON: jest.fn(() => ({ type: 'doc', content: [] })),
  getText: jest.fn(() => 'Mock content'),
  isActive: jest.fn(() => false),
  can: jest.fn(() => ({ undo: jest.fn(() => true), redo: jest.fn(() => true) })),
  on: jest.fn(),
  off: jest.fn(),
  destroy: jest.fn(),
  view: {
    dom: document.createElement('div'),
  },
});

window.tiptap = {
  Editor: jest.fn(() => createMockEditor()),
};

window.tiptapStarterKit = {
  StarterKit: {},
};

// Helper to create a fresh mock editor
global.createMockTipTapEditor = createMockEditor;

// ============================================================
// Alpine.js Mock
// ============================================================
// Alpine components are initialized via x-data="componentName()"
// We mock the Alpine object for testing component initialization
window.Alpine = {
  data: jest.fn(),
  store: jest.fn(),
  start: jest.fn(),
  effect: jest.fn(),
  magic: jest.fn(),
};

// ============================================================
// DOM Selection API Mock
// ============================================================
const createMockRange = () => ({
  getBoundingClientRect: jest.fn(() => ({
    top: 100,
    left: 100,
    bottom: 120,
    right: 200,
    width: 100,
    height: 20,
  })),
  commonAncestorContainer: document.body,
  startContainer: document.body,
  endContainer: document.body,
  startOffset: 0,
  endOffset: 10,
  setStart: jest.fn(),
  setEnd: jest.fn(),
  cloneRange: jest.fn(function() { return this; }),
  collapse: jest.fn(),
  toString: jest.fn(() => 'selected text'),
});

const createMockSelection = () => ({
  toString: jest.fn(() => 'selected text'),
  getRangeAt: jest.fn(() => createMockRange()),
  rangeCount: 1,
  removeAllRanges: jest.fn(),
  addRange: jest.fn(),
  isCollapsed: false,
  anchorNode: null,
  focusNode: null,
});

document.getSelection = jest.fn(() => createMockSelection());

// Caret position detection (used in annotation)
document.caretRangeFromPoint = jest.fn((x, y) => createMockRange());

// ============================================================
// RequestAnimationFrame Mock
// ============================================================
global.requestAnimationFrame = jest.fn((cb) => setTimeout(cb, 16));
global.cancelAnimationFrame = jest.fn((id) => clearTimeout(id));

// ============================================================
// Location Mock
// ============================================================
delete window.location;
window.location = {
  href: 'http://localhost/',
  origin: 'http://localhost',
  pathname: '/',
  search: '',
  hash: '',
  assign: jest.fn(),
  replace: jest.fn(),
  reload: jest.fn(),
};

// ============================================================
// Scroll Mock
// ============================================================
Element.prototype.scrollIntoView = jest.fn();
window.scrollTo = jest.fn();

// ============================================================
// Intersection Observer Mock
// ============================================================
global.IntersectionObserver = jest.fn(() => ({
  observe: jest.fn(),
  unobserve: jest.fn(),
  disconnect: jest.fn(),
}));

// ============================================================
// Resize Observer Mock
// ============================================================
global.ResizeObserver = jest.fn(() => ({
  observe: jest.fn(),
  unobserve: jest.fn(),
  disconnect: jest.fn(),
}));

// ============================================================
// Test Fixtures
// ============================================================
global.fixtures = {
  job: {
    _id: 'job123',
    title: 'Senior Software Engineer',
    company_name: 'Test Corp',
    location: 'Remote',
    salary_text: '$150,000 - $200,000',
    jd_text: 'We are looking for a senior engineer...',
    cv_text: null,
    is_batch: false,
    applied_at: null,
    discarded_at: null,
  },

  jobWithCV: {
    _id: 'job456',
    title: 'Staff Engineer',
    company_name: 'Tech Inc',
    location: 'San Francisco',
    jd_text: 'Lead engineering team...',
    cv_text: '# John Doe\n## Summary\nExperienced engineer...',
    is_batch: true,
  },

  annotation: {
    id: 'ann123',
    text: 'Python experience required',
    relevance: 'critical',
    requirement: 'must',
    passion: 0,
    identity: 0,
    notes: 'Core requirement',
    is_active: true,
    source: 'manual',
    status: 'approved',
  },

  annotationsList: {
    annotations: [
      { id: 'ann1', text: 'Python', relevance: 'critical', requirement: 'must' },
      { id: 'ann2', text: 'AWS', relevance: 'high', requirement: 'should' },
      { id: 'ann3', text: 'Leadership', relevance: 'medium', requirement: 'nice' },
    ],
    persona: 'Experienced Python developer with cloud expertise',
    coverage: { critical: 2, high: 3, medium: 1 },
  },

  jobsList: {
    jobs: [
      { _id: 'job1', title: 'Engineer', company_name: 'Co A' },
      { _id: 'job2', title: 'Manager', company_name: 'Co B' },
    ],
    next_cursor: null,
    total: 2,
  },

  cvGenerationStatus: {
    status: 'completed',
    cv_text: '# Generated CV\n...',
    run_id: 'run123',
  },

  masterCV: {
    metadata: {
      candidate_name: 'John Doe',
      email: 'john@example.com',
      phone: '+1234567890',
    },
    roles: [
      { id: 'role1', title: 'Software Engineer', markdown: '...' },
    ],
    taxonomy: {
      roles: {
        'Software Engineer': {
          sections: [{ skills: ['Python', 'JavaScript'] }],
        },
      },
    },
  },
};

// ============================================================
// Console Mock (optional - suppress noise in tests)
// ============================================================
// Uncomment to suppress console output during tests:
// global.console = {
//   ...console,
//   log: jest.fn(),
//   debug: jest.fn(),
//   info: jest.fn(),
//   warn: jest.fn(),
//   error: jest.fn(),
// };

// ============================================================
// Cleanup after each test
// ============================================================
beforeEach(() => {
  // Reset all mocks before each test
  jest.clearAllMocks();

  // Reset fetch mock
  global.fetch.mockImplementation(() =>
    Promise.resolve({
      ok: true,
      json: () => Promise.resolve({}),
      text: () => Promise.resolve(''),
    })
  );

  // Clear DOM
  document.body.innerHTML = '';
});

afterEach(() => {
  // Clean up any remaining timers
  jest.clearAllTimers();
});
