/**
 * Tests for mobile-state.js
 *
 * Tests the Alpine.js component that powers the mobile job swiping interface.
 * The component is exposed as window.mobileApp() and returns a reactive data object.
 */

const fs = require('fs');
const path = require('path');

describe('Mobile App Component', () => {
  let mobileApp;
  let component;

  beforeAll(() => {
    // Ensure crypto is available before loading
    if (!window.crypto || !window.crypto.randomUUID) {
      window.crypto = {
        randomUUID: () => 'mock-uuid-' + Math.random().toString(36).substr(2, 9),
        getRandomValues: (arr) => {
          for (let i = 0; i < arr.length; i++) arr[i] = Math.floor(Math.random() * 256);
          return arr;
        },
      };
    }

    // Load the mobile-state.js file
    const filePath = path.join(__dirname, '../../static/js/mobile/mobile-state.js');
    const code = fs.readFileSync(filePath, 'utf-8');

    // Execute using Function constructor
    const fn = new Function(code);
    fn.call(window);

    mobileApp = window.mobileApp;
  });

  beforeEach(() => {
    // Create a fresh component instance for each test
    component = mobileApp();

    // Mock Alpine.js $refs
    component.$refs = {
      currentCard: {
        offsetWidth: 300,
        classList: {
          add: jest.fn(),
          remove: jest.fn(),
        },
        style: {},
        querySelectorAll: jest.fn(() => []),
      },
    };

    // Mock Alpine.js $nextTick
    component.$nextTick = jest.fn((cb) => cb());

    // Reset fetch mock
    jest.clearAllMocks();
  });

  // =========================================================================
  // Method Existence Tests
  // =========================================================================
  describe('Method Existence', () => {
    test('mobileApp is defined as a function', () => {
      expect(typeof window.mobileApp).toBe('function');
    });

    test('returns an object with expected state properties', () => {
      expect(component).toHaveProperty('mode');
      expect(component).toHaveProperty('timeFilter');
      expect(component).toHaveProperty('leadershipOnly');
      expect(component).toHaveProperty('jobs');
      expect(component).toHaveProperty('currentIndex');
      expect(component).toHaveProperty('isLoading');
      expect(component).toHaveProperty('cvProgress');
    });

    test('returns an object with cvViewer state', () => {
      expect(component).toHaveProperty('cvViewer');
      expect(component.cvViewer).toHaveProperty('show');
      expect(component.cvViewer).toHaveProperty('jobId');
      expect(component.cvViewer).toHaveProperty('cvHtml');
      expect(component.cvViewer).toHaveProperty('isLoading');
    });

    test('returns an object with annotation state', () => {
      expect(component).toHaveProperty('annotationMode');
      expect(component).toHaveProperty('annotation');
      expect(component.annotation).toHaveProperty('annotations');
      expect(component.annotation).toHaveProperty('personaStatement');
      expect(component.annotation).toHaveProperty('autoGenerating');
    });

    test('returns an object with annotationSheet state', () => {
      expect(component).toHaveProperty('annotationSheet');
      expect(component.annotationSheet).toHaveProperty('show');
      expect(component.annotationSheet).toHaveProperty('selectedText');
      expect(component.annotationSheet).toHaveProperty('relevance');
      expect(component.annotationSheet).toHaveProperty('editingId');
    });

    test('returns an object with swipe state', () => {
      expect(component).toHaveProperty('isDragging');
      expect(component).toHaveProperty('startX');
      expect(component).toHaveProperty('swipeProgress');
    });

    // Core methods
    const coreMethods = [
      'init',
      'setMode',
      'setTimeFilter',
      'loadJobs',
      'loadMoreJobs',
      'nextCard',
    ];

    coreMethods.forEach((method) => {
      test(`has ${method} method`, () => {
        expect(typeof component[method]).toBe('function');
      });
    });

    // Swipe methods
    const swipeMethods = [
      'onTouchStart',
      'onTouchMove',
      'onTouchEnd',
      'commitSwipeLeft',
      'commitSwipeRight',
    ];

    swipeMethods.forEach((method) => {
      test(`has ${method} method`, () => {
        expect(typeof component[method]).toBe('function');
      });
    });

    // CV methods
    const cvMethods = [
      'triggerCvGeneration',
      'regenerateCvAndNext',
      'pollCvProgress',
      'hasGeneratedCv',
      'openCvViewer',
      'closeCvViewer',
      'openCvInDesktop',
      'markdownToHtml',
      'prosemirrorToHtml',
    ];

    cvMethods.forEach((method) => {
      test(`has ${method} method`, () => {
        expect(typeof component[method]).toBe('function');
      });
    });

    // Annotation methods
    const annotationMethods = [
      'openAnnotationMode',
      'closeAnnotationMode',
      'autoAnnotate',
      'reloadAnnotations',
      'checkIdentityAnnotations',
      'generateProcessedJdHtml',
      'handleAnnotationTap',
      'getTextFromTappedElement',
      'getSentenceAtPoint',
      'closeAnnotationSheet',
      'editAnnotation',
      'deleteAnnotation',
      'autoSaveAnnotation',
      'saveAnnotation',
      'generatePersona',
      'formatJD',
      'getAnnotationJdHtml',
      'applyHighlightsToHtml',
      'applyHighlightsPostRender',
      'findExistingAnnotation',
      'formatJdForAnnotation',
    ];

    annotationMethods.forEach((method) => {
      test(`has ${method} method`, () => {
        expect(typeof component[method]).toBe('function');
      });
    });
  });

  // =========================================================================
  // Default State Tests
  // =========================================================================
  describe('Default State', () => {
    test('mode defaults to batch', () => {
      expect(component.mode).toBe('batch');
    });

    test('timeFilter defaults to 1h', () => {
      expect(component.timeFilter).toBe('1h');
    });

    test('leadershipOnly defaults to false', () => {
      expect(component.leadershipOnly).toBe(false);
    });

    test('jobs defaults to empty array', () => {
      expect(component.jobs).toEqual([]);
    });

    test('currentIndex defaults to 0', () => {
      expect(component.currentIndex).toBe(0);
    });

    test('isLoading defaults to false', () => {
      expect(component.isLoading).toBe(false);
    });

    test('cvProgress defaults to null', () => {
      expect(component.cvProgress).toBeNull();
    });

    test('annotationMode defaults to false', () => {
      expect(component.annotationMode).toBe(false);
    });

    test('annotation.annotations defaults to empty array', () => {
      expect(component.annotation.annotations).toEqual([]);
    });

    test('annotationSheet.show defaults to false', () => {
      expect(component.annotationSheet.show).toBe(false);
    });

    test('annotationSheet has optimistic defaults', () => {
      expect(component.annotationSheet.relevance).toBe('core_strength');
      expect(component.annotationSheet.requirement).toBe('must_have');
      expect(component.annotationSheet.identity).toBe('strong_identity');
      expect(component.annotationSheet.passion).toBe('enjoy');
    });
  });

  // =========================================================================
  // Computed Property Tests
  // =========================================================================
  describe('Computed Properties', () => {
    test('currentJob returns null when jobs array is empty', () => {
      component.jobs = [];
      component.currentIndex = 0;
      expect(component.currentJob).toBeNull();
    });

    test('currentJob returns correct job at currentIndex', () => {
      component.jobs = [
        { _id: 'job1', title: 'Engineer' },
        { _id: 'job2', title: 'Manager' },
      ];
      component.currentIndex = 1;
      expect(component.currentJob).toEqual({ _id: 'job2', title: 'Manager' });
    });

    test('cardStyle returns empty string when not dragging', () => {
      component.isDragging = false;
      expect(component.cardStyle).toBe('');
    });

    test('cardStyle returns transform when dragging', () => {
      component.isDragging = true;
      component.swipeProgress = 0.5;
      expect(component.cardStyle).toContain('transform:');
      expect(component.cardStyle).toContain('translateX');
      expect(component.cardStyle).toContain('rotate');
    });
  });

  // =========================================================================
  // setMode Tests
  // =========================================================================
  describe('setMode', () => {
    test('changes mode and triggers loadJobs', async () => {
      mockFetchResponse({ jobs: [] });

      component.mode = 'batch';
      component.setMode('main');

      expect(component.mode).toBe('main');
    });

    test('does not reload if mode is the same', () => {
      const loadJobsSpy = jest.spyOn(component, 'loadJobs');
      component.mode = 'batch';
      component.setMode('batch');

      expect(loadJobsSpy).not.toHaveBeenCalled();
    });
  });

  // =========================================================================
  // setTimeFilter Tests
  // =========================================================================
  describe('setTimeFilter', () => {
    test('changes timeFilter and triggers loadJobs', async () => {
      mockFetchResponse({ jobs: [] });

      component.timeFilter = '1h';
      component.setTimeFilter('24h');

      expect(component.timeFilter).toBe('24h');
    });

    test('does not reload if filter is the same', () => {
      const loadJobsSpy = jest.spyOn(component, 'loadJobs');
      component.timeFilter = '1h';
      component.setTimeFilter('1h');

      expect(loadJobsSpy).not.toHaveBeenCalled();
    });
  });

  // =========================================================================
  // loadJobs Tests
  // =========================================================================
  describe('loadJobs', () => {
    test('calls correct API endpoint with parameters', async () => {
      mockFetchResponse({ jobs: fixtures.jobsList.jobs });

      await component.loadJobs();

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/mobile/jobs?')
      );
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('mode=batch')
      );
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('time_filter=1h')
      );
    });

    test('sets isLoading to true during load', async () => {
      let loadingDuringFetch = false;

      global.fetch.mockImplementationOnce(() => {
        loadingDuringFetch = component.isLoading;
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ jobs: [] }),
        });
      });

      await component.loadJobs();

      expect(loadingDuringFetch).toBe(true);
      expect(component.isLoading).toBe(false);
    });

    test('populates jobs array on success', async () => {
      mockFetchResponse({ jobs: fixtures.jobsList.jobs });

      await component.loadJobs();

      expect(component.jobs).toHaveLength(2);
      expect(component.jobs[0]._id).toBe('job1');
    });

    test('resets currentIndex on load', async () => {
      mockFetchResponse({ jobs: fixtures.jobsList.jobs });
      component.currentIndex = 5;

      await component.loadJobs();

      expect(component.currentIndex).toBe(0);
    });

    test('shows toast on error', async () => {
      mockFetchResponse({ error: 'Server error' }, { ok: false, status: 500 });

      await component.loadJobs();

      expect(showToast).toHaveBeenCalledWith(
        expect.any(String),
        'error'
      );
    });
  });

  // =========================================================================
  // loadMoreJobs Tests
  // =========================================================================
  describe('loadMoreJobs', () => {
    test('calls API with cursor parameter', async () => {
      component.jobs = [{ _id: 'lastjob' }];
      mockFetchResponse({ jobs: [{ _id: 'newjob' }] });

      await component.loadMoreJobs();

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('cursor=lastjob')
      );
    });

    test('appends new jobs to existing list', async () => {
      component.jobs = [{ _id: 'existing' }];
      mockFetchResponse({ jobs: [{ _id: 'newjob' }] });

      await component.loadMoreJobs();

      expect(component.jobs).toHaveLength(2);
    });

    test('filters out duplicate jobs', async () => {
      component.jobs = [{ _id: 'existing' }];
      mockFetchResponse({ jobs: [{ _id: 'existing' }, { _id: 'new' }] });

      await component.loadMoreJobs();

      expect(component.jobs).toHaveLength(2);
      expect(component.jobs.map((j) => j._id)).toEqual(['existing', 'new']);
    });

    test('does nothing if already loading', async () => {
      component.isLoading = true;

      await component.loadMoreJobs();

      expect(fetch).not.toHaveBeenCalled();
    });
  });

  // =========================================================================
  // nextCard Tests
  // =========================================================================
  describe('nextCard', () => {
    test('removes current job from array', () => {
      component.jobs = [{ _id: 'job1' }, { _id: 'job2' }];
      component.currentIndex = 0;

      component.nextCard();

      expect(component.jobs).toHaveLength(1);
      expect(component.jobs[0]._id).toBe('job2');
    });

    test('resets swipeProgress', () => {
      component.swipeProgress = 0.8;

      component.nextCard();

      expect(component.swipeProgress).toBe(0);
    });

    test('triggers loadMoreJobs when running low on jobs', () => {
      const loadMoreSpy = jest.spyOn(component, 'loadMoreJobs').mockImplementation(() => {});
      component.jobs = [{ _id: '1' }, { _id: '2' }, { _id: '3' }];

      component.nextCard();

      expect(loadMoreSpy).toHaveBeenCalled();
    });
  });

  // =========================================================================
  // commitSwipeLeft Tests
  // =========================================================================
  describe('commitSwipeLeft', () => {
    beforeEach(() => {
      component.jobs = [fixtures.job];
      component.currentIndex = 0;
    });

    test('calls discard API with correct parameters', async () => {
      mockFetchResponse({ success: true });

      await component.commitSwipeLeft();

      expect(fetch).toHaveBeenCalledWith('/api/jobs/status', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          job_id: 'job123',
          status: 'discarded',
        }),
      });
    });

    test('triggers haptic feedback on success', async () => {
      mockFetchResponse({ success: true });

      await component.commitSwipeLeft();

      expect(navigator.vibrate).toHaveBeenCalled();
    });

    test('shows discard toast', async () => {
      mockFetchResponse({ success: true });

      await component.commitSwipeLeft();

      expect(showToast).toHaveBeenCalledWith('Job discarded', 'info');
    });

    test('does nothing if no current job', async () => {
      component.jobs = [];

      await component.commitSwipeLeft();

      expect(fetch).not.toHaveBeenCalled();
    });
  });

  // =========================================================================
  // commitSwipeRight Tests
  // =========================================================================
  describe('commitSwipeRight', () => {
    beforeEach(() => {
      component.jobs = [fixtures.job];
      component.currentIndex = 0;
      jest.useFakeTimers();
    });

    afterEach(() => {
      jest.useRealTimers();
    });

    test('in main mode, calls move-to-batch API', () => {
      component.mode = 'main';
      mockFetchResponse({ success: true });

      component.commitSwipeRight();

      // Fast-forward past the animation timeout
      jest.advanceTimersByTime(400);

      expect(fetch).toHaveBeenCalledWith('/api/jobs/move-to-batch', expect.any(Object));
    });

    test('in batch mode without CV, triggers CV generation', () => {
      component.mode = 'batch';
      component.jobs = [{ _id: 'job123', generated_cv: false }];
      mockFetchResponse({ run_id: 'run123' });

      component.commitSwipeRight();

      jest.advanceTimersByTime(400);

      expect(fetch).toHaveBeenCalledWith(
        '/api/runner/jobs/job123/operations/generate-cv/queue',
        expect.any(Object)
      );
    });

    test('in batch mode with existing CV, shows skip toast', () => {
      component.mode = 'batch';
      component.jobs = [{ _id: 'job123', generated_cv: true }];

      component.commitSwipeRight();

      expect(showToast).toHaveBeenCalledWith('CV exists - skipped', 'info');
    });
  });

  // =========================================================================
  // triggerCvGeneration Tests
  // =========================================================================
  describe('triggerCvGeneration', () => {
    test('calls correct API endpoint', () => {
      mockFetchResponse({ run_id: 'run123' });

      component.triggerCvGeneration('job456');

      expect(fetch).toHaveBeenCalledWith(
        '/api/runner/jobs/job456/operations/generate-cv/queue',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ tier: 'quality' }),
        })
      );
    });
  });

  // =========================================================================
  // hasGeneratedCv Tests
  // =========================================================================
  describe('hasGeneratedCv', () => {
    test('returns false for null job', () => {
      expect(component.hasGeneratedCv(null)).toBe(false);
    });

    test('returns true if generated_cv is true', () => {
      expect(component.hasGeneratedCv({ generated_cv: true })).toBe(true);
    });

    test('returns true if cv_text exists', () => {
      expect(component.hasGeneratedCv({ cv_text: '# CV' })).toBe(true);
    });

    test('returns false if no CV indicators', () => {
      expect(component.hasGeneratedCv({ _id: 'job1' })).toBe(false);
    });
  });

  // =========================================================================
  // Annotation Mode Tests
  // =========================================================================
  describe('openAnnotationMode', () => {
    beforeEach(() => {
      component.jobs = [fixtures.job];
      component.currentIndex = 0;
    });

    test('fetches annotations from correct API', async () => {
      mockFetchResponse({
        annotations: {
          annotations: fixtures.annotationsList.annotations,
          processed_jd_html: '<p>Structured JD</p>',
        },
      });

      await component.openAnnotationMode();

      expect(fetch).toHaveBeenCalledWith('/api/jobs/job123/jd-annotations');
    });

    test('sets annotationMode to true', async () => {
      mockFetchResponse({ annotations: { annotations: [] } });

      await component.openAnnotationMode();

      expect(component.annotationMode).toBe(true);
    });

    test('populates annotations from response', async () => {
      mockFetchResponse({
        annotations: {
          annotations: fixtures.annotationsList.annotations,
        },
      });

      await component.openAnnotationMode();

      expect(component.annotation.annotations).toHaveLength(3);
    });

    test('stores processed JD HTML', async () => {
      mockFetchResponse({
        annotations: {
          annotations: [],
          processed_jd_html: '<p>LLM structured</p>',
        },
      });

      await component.openAnnotationMode();

      expect(component.annotation.processedJdHtml).toBe('<p>LLM structured</p>');
    });
  });

  describe('closeAnnotationMode', () => {
    test('sets annotationMode to false', () => {
      component.annotationMode = true;

      component.closeAnnotationMode();

      expect(component.annotationMode).toBe(false);
    });
  });

  // =========================================================================
  // autoAnnotate Tests
  // =========================================================================
  describe('autoAnnotate', () => {
    beforeEach(() => {
      component.jobs = [fixtures.job];
      component.currentIndex = 0;
    });

    test('calls generate-annotations API', async () => {
      mockFetchResponse({ success: true, created: 5 });
      // Mock reloadAnnotations
      component.reloadAnnotations = jest.fn();

      await component.autoAnnotate();

      expect(fetch).toHaveBeenCalledWith(
        '/api/runner/jobs/job123/generate-annotations',
        expect.objectContaining({ method: 'POST' })
      );
    });

    test('sets autoGenerating flag during operation', async () => {
      let flagDuringFetch = false;

      global.fetch.mockImplementationOnce(() => {
        flagDuringFetch = component.annotation.autoGenerating;
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ success: true, created: 0 }),
        });
      });

      component.reloadAnnotations = jest.fn();

      await component.autoAnnotate();

      expect(flagDuringFetch).toBe(true);
      expect(component.annotation.autoGenerating).toBe(false);
    });

    test('reloads annotations on success', async () => {
      mockFetchResponse({ success: true, created: 3 });
      component.reloadAnnotations = jest.fn();

      await component.autoAnnotate();

      expect(component.reloadAnnotations).toHaveBeenCalled();
    });

    test('does nothing if already generating', async () => {
      component.annotation.autoGenerating = true;

      await component.autoAnnotate();

      expect(fetch).not.toHaveBeenCalled();
    });
  });

  // =========================================================================
  // reloadAnnotations Tests
  // =========================================================================
  describe('reloadAnnotations', () => {
    beforeEach(() => {
      component.jobs = [fixtures.job];
      component.currentIndex = 0;
    });

    test('fetches from correct API', async () => {
      mockFetchResponse({ annotations: { annotations: [] } });

      await component.reloadAnnotations();

      expect(fetch).toHaveBeenCalledWith('/api/jobs/job123/jd-annotations');
    });

    test('updates annotations array', async () => {
      mockFetchResponse({
        annotations: {
          annotations: fixtures.annotationsList.annotations,
        },
      });

      await component.reloadAnnotations();

      expect(component.annotation.annotations).toHaveLength(3);
    });
  });

  // =========================================================================
  // checkIdentityAnnotations Tests
  // =========================================================================
  describe('checkIdentityAnnotations', () => {
    test('sets hasIdentityAnnotations true for core_identity', () => {
      component.annotation.annotations = [
        { identity: 'core_identity', is_active: true },
      ];

      component.checkIdentityAnnotations();

      expect(component.annotation.hasIdentityAnnotations).toBe(true);
    });

    test('sets hasIdentityAnnotations true for love_it passion', () => {
      component.annotation.annotations = [
        { passion: 'love_it', is_active: true },
      ];

      component.checkIdentityAnnotations();

      expect(component.annotation.hasIdentityAnnotations).toBe(true);
    });

    test('sets hasIdentityAnnotations true for core_strength', () => {
      component.annotation.annotations = [
        { relevance: 'core_strength', is_active: true },
      ];

      component.checkIdentityAnnotations();

      expect(component.annotation.hasIdentityAnnotations).toBe(true);
    });

    test('sets hasIdentityAnnotations false for inactive annotations', () => {
      component.annotation.annotations = [
        { identity: 'core_identity', is_active: false },
      ];

      component.checkIdentityAnnotations();

      expect(component.annotation.hasIdentityAnnotations).toBe(false);
    });

    test('handles non-array annotations gracefully', () => {
      component.annotation.annotations = null;

      expect(() => component.checkIdentityAnnotations()).not.toThrow();
      expect(component.annotation.hasIdentityAnnotations).toBe(false);
    });
  });

  // =========================================================================
  // saveAnnotation Tests
  // =========================================================================
  describe('saveAnnotation', () => {
    beforeEach(() => {
      component.jobs = [fixtures.job];
      component.currentIndex = 0;
      component.annotationSheet.selectedText = 'Python experience';
      component.annotationSheet.show = true;
    });

    test('saveAnnotation method exists and is callable', () => {
      expect(typeof component.saveAnnotation).toBe('function');
    });

    test('updates existing annotation when editing', async () => {
      component.annotation.annotations = [{
        id: 'ann1',
        target: { text: 'Python' },
        relevance: 'high',
      }];
      component.annotationSheet.editingId = 'ann1';
      component.annotationSheet.relevance = 'core_strength';
      mockFetchResponse({ success: true });

      await component.saveAnnotation();

      expect(component.annotation.annotations[0].relevance).toBe('core_strength');
    });

    test('requires selectedText to save', async () => {
      component.annotationSheet.selectedText = '';
      mockFetchResponse({ success: true });

      await component.saveAnnotation();

      // Should not call API without selected text
      expect(fetch).not.toHaveBeenCalled();
    });

    test('requires currentJob to save', async () => {
      component.jobs = [];
      mockFetchResponse({ success: true });

      await component.saveAnnotation();

      // Should not call API without current job
      expect(fetch).not.toHaveBeenCalled();
    });
  });

  // =========================================================================
  // deleteAnnotation Tests
  // =========================================================================
  describe('deleteAnnotation', () => {
    beforeEach(() => {
      component.jobs = [fixtures.job];
      component.currentIndex = 0;
      component.annotation.annotations = [
        { id: 'ann1', target: { text: 'Python' } },
        { id: 'ann2', target: { text: 'AWS' } },
      ];
      component.annotationSheet.editingId = 'ann1';
      component.annotationSheet.show = true;
    });

    test('removes annotation from array', () => {
      mockFetchResponse({ success: true });

      component.deleteAnnotation();

      expect(component.annotation.annotations).toHaveLength(1);
      expect(component.annotation.annotations[0].id).toBe('ann2');
    });

    test('increments annotationVersion', () => {
      const prevVersion = component.annotationVersion;
      mockFetchResponse({ success: true });

      component.deleteAnnotation();

      expect(component.annotationVersion).toBe(prevVersion + 1);
    });

    test('closes annotation sheet', () => {
      mockFetchResponse({ success: true });

      component.deleteAnnotation();

      expect(component.annotationSheet.show).toBe(false);
    });

    test('does nothing if no editingId', () => {
      component.annotationSheet.editingId = null;

      component.deleteAnnotation();

      expect(component.annotation.annotations).toHaveLength(2);
    });
  });

  // =========================================================================
  // findExistingAnnotation Tests
  // =========================================================================
  describe('findExistingAnnotation', () => {
    beforeEach(() => {
      component.annotation.annotations = [
        { id: 'ann1', target: { text: 'Python programming experience' }, is_active: true },
        { id: 'ann2', target: { text: 'AWS Cloud' }, is_active: true },
        { id: 'ann3', target: { text: 'Inactive skill' }, is_active: false },
      ];
    });

    test('returns undefined for empty text', () => {
      expect(component.findExistingAnnotation('')).toBeUndefined();
    });

    test('finds exact match (case insensitive)', () => {
      const result = component.findExistingAnnotation('AWS Cloud');
      expect(result.id).toBe('ann2');
    });

    test('finds when new text is contained in existing annotation', () => {
      const result = component.findExistingAnnotation('Python programming');
      expect(result.id).toBe('ann1');
    });

    test('ignores inactive annotations', () => {
      const result = component.findExistingAnnotation('Inactive skill');
      expect(result).toBeUndefined();
    });
  });

  // =========================================================================
  // editAnnotation Tests
  // =========================================================================
  describe('editAnnotation', () => {
    beforeEach(() => {
      component.annotation.annotations = [
        {
          id: 'ann1',
          target: { text: 'Python' },
          relevance: 'high',
          requirement_type: 'must',
          identity: 'strong_identity',
          passion: 'enjoy',
          source: 'human',
        },
      ];
    });

    test('loads annotation data into sheet', () => {
      component.editAnnotation('ann1');

      expect(component.annotationSheet.selectedText).toBe('Python');
      expect(component.annotationSheet.relevance).toBe('high');
      expect(component.annotationSheet.editingId).toBe('ann1');
    });

    test('shows annotation sheet', () => {
      component.editAnnotation('ann1');

      expect(component.annotationSheet.show).toBe(true);
    });

    test('does nothing for unknown annotation ID', () => {
      component.editAnnotation('unknown');

      expect(component.annotationSheet.show).toBe(false);
    });

    test('loads AI info for auto-generated annotations', () => {
      component.annotation.annotations = [
        {
          id: 'ann1',
          target: { text: 'Python' },
          source: 'auto_generated',
          original_values: {
            confidence: 0.85,
            match_method: 'sentence_embedding',
          },
        },
      ];

      component.editAnnotation('ann1');

      expect(component.annotationSheet.aiInfo).not.toBeNull();
      expect(component.annotationSheet.aiInfo.pct).toBe(85);
    });
  });

  // =========================================================================
  // generatePersona Tests
  // =========================================================================
  describe('generatePersona', () => {
    beforeEach(() => {
      component.jobs = [fixtures.job];
      component.currentIndex = 0;
      component.annotation.annotations = fixtures.annotationsList.annotations;
    });

    test('calls APIs for persona generation', async () => {
      // Mock all API calls to succeed
      global.fetch.mockImplementation(() => Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ success: true, persona: 'Test persona' }),
      }));

      await component.generatePersona();

      // Should call APIs
      expect(fetch).toHaveBeenCalled();
    });

    test('updates personaStatement on success', async () => {
      global.fetch.mockImplementation(() => Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ success: true, persona: 'Generated persona' }),
      }));

      await component.generatePersona();

      // personaStatement should be set (may be directly or via state update)
      expect(typeof component.annotation.personaStatement).toBe('string');
    });

    test('manages personaLoading state', async () => {
      global.fetch.mockImplementation(() => Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ success: true, persona: 'Test' }),
      }));

      await component.generatePersona();

      // After completion, loading should be false
      expect(component.annotation.personaLoading).toBe(false);
    });

    test('does nothing if already loading', async () => {
      component.annotation.personaLoading = true;

      await component.generatePersona();

      expect(fetch).not.toHaveBeenCalled();
    });
  });

  // =========================================================================
  // CV Viewer Tests
  // =========================================================================
  describe('openCvViewer', () => {
    test('fetches job from correct API', async () => {
      mockFetchResponse({ job: fixtures.jobWithCV });

      await component.openCvViewer('job456');

      expect(fetch).toHaveBeenCalledWith('/api/jobs/job456');
    });

    test('sets cvViewer.show to true', async () => {
      mockFetchResponse({ job: fixtures.jobWithCV });

      await component.openCvViewer('job456');

      expect(component.cvViewer.show).toBe(true);
    });

    test('processes cv_text into displayable format', async () => {
      mockFetchResponse({
        job: {
          _id: 'job456',
          cv_text: '# Test CV\n\n## Summary\n\nTest content',
        },
      });

      await component.openCvViewer('job456');

      // Should have processed the CV text
      expect(component.cvViewer.cvHtml).toBeTruthy();
    });

    test('manages loading state during fetch', async () => {
      mockFetchResponse({ job: fixtures.jobWithCV });

      await component.openCvViewer('job456');

      // After completion, loading should be false
      expect(component.cvViewer.isLoading).toBe(false);
    });
  });

  describe('closeCvViewer', () => {
    test('sets cvViewer.show to false', () => {
      component.cvViewer.show = true;

      component.closeCvViewer();

      expect(component.cvViewer.show).toBe(false);
    });

    test('clears cvHtml', () => {
      component.cvViewer.cvHtml = '<div>CV content</div>';

      component.closeCvViewer();

      expect(component.cvViewer.cvHtml).toBeNull();
    });
  });

  describe('openCvInDesktop', () => {
    test('opens window with correct URL', () => {
      window.open = jest.fn();
      component.cvViewer.jobId = 'job789';

      component.openCvInDesktop();

      expect(window.open).toHaveBeenCalledWith('/job/job789', '_blank');
    });
  });

  // =========================================================================
  // markdownToHtml Tests
  // =========================================================================
  describe('markdownToHtml', () => {
    test('converts headings', () => {
      const result = component.markdownToHtml('# Title\n## Section\n### Subsection');

      expect(result).toContain('<h1');
      expect(result).toContain('<h2');
      expect(result).toContain('<h3');
    });

    test('converts bold text', () => {
      const result = component.markdownToHtml('**bold text**');

      expect(result).toContain('<strong');
      expect(result).toContain('bold text');
    });

    test('converts bullet lists', () => {
      const result = component.markdownToHtml('- Item 1\n- Item 2');

      expect(result).toContain('<li');
      expect(result).toContain('<ul');
    });

    test('returns empty string for null input', () => {
      expect(component.markdownToHtml(null)).toBe('');
    });
  });

  // =========================================================================
  // prosemirrorToHtml Tests
  // =========================================================================
  describe('prosemirrorToHtml', () => {
    test('converts paragraph nodes', () => {
      const doc = {
        type: 'doc',
        content: [
          { type: 'paragraph', content: [{ type: 'text', text: 'Hello' }] },
        ],
      };

      const result = component.prosemirrorToHtml(doc);

      expect(result).toContain('<p');
      expect(result).toContain('Hello');
    });

    test('converts heading nodes', () => {
      const doc = {
        type: 'doc',
        content: [
          { type: 'heading', attrs: { level: 2 }, content: [{ type: 'text', text: 'Title' }] },
        ],
      };

      const result = component.prosemirrorToHtml(doc);

      expect(result).toContain('<h2');
      expect(result).toContain('Title');
    });

    test('applies bold marks', () => {
      const doc = {
        type: 'doc',
        content: [
          {
            type: 'paragraph',
            content: [
              { type: 'text', text: 'bold', marks: [{ type: 'bold' }] },
            ],
          },
        ],
      };

      const result = component.prosemirrorToHtml(doc);

      expect(result).toContain('<strong');
    });

    test('returns empty string for null doc', () => {
      expect(component.prosemirrorToHtml(null)).toBe('');
    });
  });

  // =========================================================================
  // formatJD Tests
  // =========================================================================
  describe('formatJD', () => {
    test('uses JDFormatter when available', () => {
      const result = component.formatJD('Test JD');

      expect(window.JDFormatter.format).toHaveBeenCalledWith('Test JD');
    });

    test('returns placeholder for empty text', () => {
      const result = component.formatJD('');

      expect(result).toContain('No description available');
    });

    test('falls back to line break replacement when JDFormatter unavailable', () => {
      const originalFormatter = window.JDFormatter;
      window.JDFormatter = null;

      const result = component.formatJD('Line 1\nLine 2');

      expect(result).toContain('<br>');

      window.JDFormatter = originalFormatter;
    });
  });

  // =========================================================================
  // applyHighlightsToHtml Tests
  // =========================================================================
  describe('applyHighlightsToHtml', () => {
    test('adds mark tags for annotations', () => {
      component.annotation.annotations = [
        { id: 'ann1', target: { text: 'Python' }, relevance: 'critical', is_active: true },
      ];

      const result = component.applyHighlightsToHtml('<p>Python experience required</p>');

      expect(result).toContain('<mark class="annotation-highlight"');
      expect(result).toContain('data-annotation-id="ann1"');
      expect(result).toContain('data-relevance="critical"');
    });

    test('skips inactive annotations', () => {
      component.annotation.annotations = [
        { id: 'ann1', target: { text: 'Python' }, is_active: false },
      ];

      const result = component.applyHighlightsToHtml('<p>Python experience</p>');

      expect(result).not.toContain('annotation-highlight');
    });

    test('skips short text annotations', () => {
      component.annotation.annotations = [
        { id: 'ann1', target: { text: 'JS' }, is_active: true },
      ];

      const result = component.applyHighlightsToHtml('<p>JS experience</p>');

      expect(result).not.toContain('annotation-highlight');
    });

    test('returns original html when no annotations', () => {
      component.annotation.annotations = [];

      const html = '<p>Test content</p>';
      const result = component.applyHighlightsToHtml(html);

      expect(result).toBe(html);
    });
  });

  // =========================================================================
  // Swipe Handler Tests
  // =========================================================================
  describe('onTouchStart', () => {
    test('sets isDragging to true', () => {
      component.jobs = [fixtures.job];
      const event = {
        target: document.createElement('div'),
        touches: [{ clientX: 100, clientY: 200 }],
      };

      component.onTouchStart(event);

      expect(component.isDragging).toBe(true);
    });

    test('records start position', () => {
      component.jobs = [fixtures.job];
      const event = {
        target: document.createElement('div'),
        touches: [{ clientX: 150, clientY: 250 }],
      };

      component.onTouchStart(event);

      expect(component.startX).toBe(150);
      expect(component.startY).toBe(250);
    });

    test('does nothing when no current job', () => {
      component.jobs = [];
      const event = {
        target: document.createElement('div'),
        touches: [{ clientX: 100, clientY: 200 }],
      };

      component.onTouchStart(event);

      expect(component.isDragging).toBe(false);
    });

    test('detects touch in scrollable element', () => {
      component.jobs = [fixtures.job];

      const scrollable = document.createElement('div');
      scrollable.className = 'overflow-y-auto';
      const target = document.createElement('span');
      scrollable.appendChild(target);

      const event = {
        target: target,
        touches: [{ clientX: 100, clientY: 200 }],
      };

      component.onTouchStart(event);

      expect(component.touchInScrollable).toBe(true);
    });
  });

  describe('onTouchMove', () => {
    beforeEach(() => {
      component.jobs = [fixtures.job];
      component.isDragging = true;
      component.startX = 100;
      component.startY = 200;
    });

    test('calculates swipeProgress', () => {
      const event = {
        preventDefault: jest.fn(),
        touches: [{ clientX: 200, clientY: 200 }],
      };

      component.onTouchMove(event);

      expect(component.swipeProgress).toBeGreaterThan(0);
    });

    test('clamps swipeProgress between -1 and 1', () => {
      const event = {
        preventDefault: jest.fn(),
        touches: [{ clientX: 1000, clientY: 200 }],
      };

      component.onTouchMove(event);

      expect(component.swipeProgress).toBeLessThanOrEqual(1);
    });

    test('does nothing when not dragging', () => {
      component.isDragging = false;
      const event = {
        preventDefault: jest.fn(),
        touches: [{ clientX: 200, clientY: 200 }],
      };

      component.onTouchMove(event);

      expect(event.preventDefault).not.toHaveBeenCalled();
    });
  });

  describe('onTouchEnd', () => {
    beforeEach(() => {
      component.jobs = [fixtures.job];
      component.isDragging = true;
      jest.useFakeTimers();
    });

    afterEach(() => {
      jest.useRealTimers();
    });

    test('commits swipe left when threshold exceeded', () => {
      component.swipeProgress = -0.5;
      const commitLeftSpy = jest.spyOn(component, 'commitSwipeLeft').mockImplementation(() => {});

      component.onTouchEnd({});

      expect(commitLeftSpy).toHaveBeenCalled();
    });

    test('commits swipe right when threshold exceeded', () => {
      component.swipeProgress = 0.5;
      const commitRightSpy = jest.spyOn(component, 'commitSwipeRight').mockImplementation(() => {});

      component.onTouchEnd({});

      expect(commitRightSpy).toHaveBeenCalled();
    });

    test('snaps back when threshold not exceeded', () => {
      component.swipeProgress = 0.2;

      component.onTouchEnd({});

      expect(component.swipeProgress).toBe(0);
    });

    test('sets isDragging to false', () => {
      component.swipeProgress = 0.2;

      component.onTouchEnd({});

      expect(component.isDragging).toBe(false);
    });
  });

  // =========================================================================
  // Time Filter Options Tests
  // =========================================================================
  describe('Time Filter Options', () => {
    test('has expected time filter values', () => {
      const values = component.timeFilters.map((f) => f.value);

      expect(values).toContain('1h');
      expect(values).toContain('24h');
      expect(values).toContain('1w');
      expect(values).toContain('1m');
    });
  });

  // =========================================================================
  // Annotation Options Tests
  // =========================================================================
  describe('Annotation Options', () => {
    test('has relevance options', () => {
      expect(component.annotationOptions.relevance).toHaveLength(5);
      expect(component.annotationOptions.relevance[0].value).toBe('core_strength');
    });

    test('has requirement options', () => {
      expect(component.annotationOptions.requirement).toHaveLength(4);
      expect(component.annotationOptions.requirement[0].value).toBe('must_have');
    });

    test('has identity options', () => {
      expect(component.annotationOptions.identity).toHaveLength(5);
      expect(component.annotationOptions.identity[0].value).toBe('core_identity');
    });

    test('has passion options', () => {
      expect(component.annotationOptions.passion).toHaveLength(5);
      expect(component.annotationOptions.passion[0].value).toBe('love_it');
    });
  });
});
