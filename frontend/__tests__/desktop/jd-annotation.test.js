/**
 * Tests for jd-annotation.js
 *
 * Tests the AnnotationManager class and UndoManager class
 * that powers the desktop JD annotation interface.
 */

const fs = require('fs');
const path = require('path');

describe('JD Annotation System', () => {
  let UndoManager;
  let AnnotationManager;
  let annotationManager;

  beforeAll(() => {
    // Load the jd-annotation.js file
    const filePath = path.join(__dirname, '../../static/js/jd-annotation.js');
    const code = fs.readFileSync(filePath, 'utf-8');

    // Transform to expose classes and functions to window
    const transformedCode = code
      // Transform class declarations: class Foo -> window.Foo = class Foo
      .replace(/^class\s+(\w+)/gm, 'window.$1 = class $1')
      // Transform const declarations at file scope
      .replace(/^const\s+(\w+)\s*=/gm, 'window.$1 =')
      // Transform function declarations
      .replace(/^function\s+(\w+)\s*\(/gm, 'window.$1 = function(')
      .replace(/^async function\s+(\w+)\s*\(/gm, 'window.$1 = async function(')
      // Transform let declarations (for annotationManager global)
      .replace(/^let\s+(\w+)\s*=/gm, 'window.$1 =');

    // Execute the transformed code
    const fn = new Function(transformedCode);
    fn.call(window);

    // Get class references from window
    UndoManager = window.UndoManager;
    AnnotationManager = window.AnnotationManager;
  });

  beforeEach(() => {
    // Reset DOM
    document.body.innerHTML = `
      <div id="jd-annotation-panel"></div>
      <div id="jd-processed-content"></div>
      <div id="annotation-popover" class="hidden"></div>
      <div id="annotation-items"></div>
      <div id="jd-loading"></div>
      <div id="jd-empty"></div>
      <div id="annotation-save-indicator"></div>
      <div id="jd-annotation-overlay"></div>
      <div id="popover-star-selector"></div>
      <div id="annotation-count"></div>
      <div id="active-annotation-count"></div>
      <div id="annotation-coverage-bar"></div>
      <div id="annotation-coverage-pct"></div>
      <div id="total-boost-value"></div>
      <div id="persona-panel-container"></div>
      <div id="undo-btn"></div>
      <div id="redo-btn"></div>
    `;

    // Create fresh manager for each test
    annotationManager = new AnnotationManager('job123');

    jest.clearAllMocks();
  });

  // =========================================================================
  // UndoManager Tests
  // =========================================================================
  describe('UndoManager', () => {
    let undoManager;

    beforeEach(() => {
      undoManager = new UndoManager();
    });

    describe('constructor', () => {
      test('initializes with empty stacks', () => {
        expect(undoManager.undoStack).toEqual([]);
        expect(undoManager.redoStack).toEqual([]);
      });

      test('accepts custom maxHistory', () => {
        const customManager = new UndoManager(10);
        expect(customManager.maxHistory).toBe(10);
      });

      test('defaults to maxHistory of 50', () => {
        expect(undoManager.maxHistory).toBe(50);
      });
    });

    describe('push', () => {
      test('adds action to undo stack', () => {
        undoManager.push({ type: 'add', annotation: { id: 'ann1' } });

        expect(undoManager.undoStack).toHaveLength(1);
        expect(undoManager.undoStack[0].type).toBe('add');
      });

      test('clears redo stack when new action pushed', () => {
        undoManager.redoStack = [{ type: 'delete', annotation: { id: 'old' } }];

        undoManager.push({ type: 'add', annotation: { id: 'ann1' } });

        expect(undoManager.redoStack).toEqual([]);
      });

      test('deep clones annotation to prevent mutation', () => {
        const annotation = { id: 'ann1', nested: { value: 1 } };
        undoManager.push({ type: 'add', annotation });

        // Mutate original
        annotation.nested.value = 2;

        // Cloned version should be unchanged
        expect(undoManager.undoStack[0].annotation.nested.value).toBe(1);
      });

      test('enforces maxHistory limit', () => {
        const smallManager = new UndoManager(3);

        smallManager.push({ type: 'add', annotation: { id: '1' } });
        smallManager.push({ type: 'add', annotation: { id: '2' } });
        smallManager.push({ type: 'add', annotation: { id: '3' } });
        smallManager.push({ type: 'add', annotation: { id: '4' } });

        expect(smallManager.undoStack).toHaveLength(3);
        expect(smallManager.undoStack[0].annotation.id).toBe('2');
      });

      test('preserves previousState for update actions', () => {
        undoManager.push({
          type: 'update',
          annotation: { id: 'ann1', relevance: 'high' },
          previousState: { id: 'ann1', relevance: 'low' },
        });

        expect(undoManager.undoStack[0].previousState.relevance).toBe('low');
      });
    });

    describe('undo', () => {
      test('returns null when stack is empty', () => {
        expect(undoManager.undo()).toBeNull();
      });

      test('returns and removes last action from undo stack', () => {
        undoManager.push({ type: 'add', annotation: { id: 'ann1' } });
        undoManager.push({ type: 'add', annotation: { id: 'ann2' } });

        const action = undoManager.undo();

        expect(action.annotation.id).toBe('ann2');
        expect(undoManager.undoStack).toHaveLength(1);
      });

      test('moves action to redo stack', () => {
        undoManager.push({ type: 'add', annotation: { id: 'ann1' } });

        undoManager.undo();

        expect(undoManager.redoStack).toHaveLength(1);
        expect(undoManager.redoStack[0].annotation.id).toBe('ann1');
      });
    });

    describe('redo', () => {
      test('returns null when stack is empty', () => {
        expect(undoManager.redo()).toBeNull();
      });

      test('returns and removes last action from redo stack', () => {
        undoManager.push({ type: 'add', annotation: { id: 'ann1' } });
        undoManager.undo();

        const action = undoManager.redo();

        expect(action.annotation.id).toBe('ann1');
        expect(undoManager.redoStack).toHaveLength(0);
      });

      test('moves action back to undo stack', () => {
        undoManager.push({ type: 'add', annotation: { id: 'ann1' } });
        undoManager.undo();

        undoManager.redo();

        expect(undoManager.undoStack).toHaveLength(1);
      });
    });

    describe('canUndo / canRedo', () => {
      test('canUndo returns false when empty', () => {
        expect(undoManager.canUndo()).toBe(false);
      });

      test('canUndo returns true when has actions', () => {
        undoManager.push({ type: 'add', annotation: { id: 'ann1' } });
        expect(undoManager.canUndo()).toBe(true);
      });

      test('canRedo returns false when empty', () => {
        expect(undoManager.canRedo()).toBe(false);
      });

      test('canRedo returns true after undo', () => {
        undoManager.push({ type: 'add', annotation: { id: 'ann1' } });
        undoManager.undo();
        expect(undoManager.canRedo()).toBe(true);
      });
    });

    describe('clear', () => {
      test('empties both stacks', () => {
        undoManager.push({ type: 'add', annotation: { id: 'ann1' } });
        undoManager.undo();

        undoManager.clear();

        expect(undoManager.undoStack).toEqual([]);
        expect(undoManager.redoStack).toEqual([]);
      });
    });

    describe('undoCount / redoCount', () => {
      test('returns correct counts', () => {
        undoManager.push({ type: 'add', annotation: { id: '1' } });
        undoManager.push({ type: 'add', annotation: { id: '2' } });

        expect(undoManager.undoCount).toBe(2);
        expect(undoManager.redoCount).toBe(0);

        undoManager.undo();

        expect(undoManager.undoCount).toBe(1);
        expect(undoManager.redoCount).toBe(1);
      });
    });
  });

  // =========================================================================
  // AnnotationManager Tests
  // =========================================================================
  describe('AnnotationManager', () => {
    describe('constructor', () => {
      test('initializes with jobId', () => {
        expect(annotationManager.jobId).toBe('job123');
      });

      test('initializes with default config', () => {
        expect(annotationManager.config.panelId).toBe('jd-annotation-panel');
        expect(annotationManager.config.contentId).toBe('jd-processed-content');
        expect(annotationManager.config.popoverId).toBe('annotation-popover');
      });

      test('accepts custom config', () => {
        const customManager = new AnnotationManager('job456', {
          panelId: 'custom-panel',
          contentId: 'custom-content',
        });

        expect(customManager.config.panelId).toBe('custom-panel');
        expect(customManager.config.contentId).toBe('custom-content');
      });

      test('initializes empty annotations array', () => {
        expect(annotationManager.annotations).toEqual([]);
      });

      test('initializes UndoManager', () => {
        expect(annotationManager.undoManager).toBeInstanceOf(UndoManager);
      });

      test('initializes default settings', () => {
        expect(annotationManager.settings).toHaveProperty('auto_highlight');
        expect(annotationManager.settings).toHaveProperty('show_confidence');
      });

      test('initializes popoverState with optimistic defaults', () => {
        expect(annotationManager.popoverState.relevance).toBe('core_strength');
        expect(annotationManager.popoverState.requirement).toBe('must_have');
        expect(annotationManager.popoverState.passion).toBe('enjoy');
        expect(annotationManager.popoverState.identity).toBe('strong_identity');
      });

      test('initializes personaState', () => {
        expect(annotationManager.personaState.statement).toBeNull();
        expect(annotationManager.personaState.isLoading).toBe(false);
        expect(annotationManager.personaState.isExpanded).toBe(false);
      });
    });

    describe('destroy', () => {
      test('sets _destroyed flag', () => {
        annotationManager.destroy();
        expect(annotationManager._destroyed).toBe(true);
      });

      test('clears pending save timeout', () => {
        annotationManager.saveTimeout = setTimeout(() => {}, 10000);
        const clearSpy = jest.spyOn(global, 'clearTimeout');

        annotationManager.destroy();

        expect(clearSpy).toHaveBeenCalled();
        expect(annotationManager.saveTimeout).toBeNull();
      });

      test('hides popover', () => {
        const popover = document.getElementById('annotation-popover');
        popover.classList.remove('hidden');

        annotationManager.destroy();

        expect(popover.classList.contains('hidden')).toBe(true);
      });
    });

    describe('loadAnnotations', () => {
      test('fetches from correct API endpoints', async () => {
        mockFetchResponse({ success: true, annotations: { annotations: [] } });
        mockFetchResponse({ job: fixtures.job });

        await annotationManager.loadAnnotations();

        expect(fetch).toHaveBeenCalledWith('/api/jobs/job123/jd-annotations');
        expect(fetch).toHaveBeenCalledWith('/api/jobs/job123');
      });

      test('populates annotations array', async () => {
        mockFetchResponse({
          success: true,
          annotations: {
            annotations: fixtures.annotationsList.annotations,
          },
        });
        mockFetchResponse({ job: fixtures.job });

        await annotationManager.loadAnnotations();

        expect(annotationManager.annotations).toHaveLength(3);
      });

      test('normalizes is_active to true by default', async () => {
        mockFetchResponse({
          success: true,
          annotations: {
            annotations: [
              { id: 'ann1', is_active: undefined },
              { id: 'ann2', is_active: false },
            ],
          },
        });
        mockFetchResponse({ job: fixtures.job });

        await annotationManager.loadAnnotations();

        expect(annotationManager.annotations[0].is_active).toBe(true);
        expect(annotationManager.annotations[1].is_active).toBe(false);
      });

      test('stores processed JD HTML', async () => {
        mockFetchResponse({
          success: true,
          annotations: {
            annotations: [],
            processed_jd_html: '<p>Structured JD</p>',
          },
        });
        mockFetchResponse({ job: fixtures.job });

        await annotationManager.loadAnnotations();

        expect(annotationManager.processedJdHtml).toBe('<p>Structured JD</p>');
      });

      test('loads stored persona', async () => {
        mockFetchResponse({
          success: true,
          annotations: {
            annotations: [],
            synthesized_persona: {
              persona_statement: 'Test persona',
              is_user_edited: true,
            },
          },
        });
        mockFetchResponse({ job: fixtures.job });

        await annotationManager.loadAnnotations();

        expect(annotationManager.personaState.statement).toBe('Test persona');
        expect(annotationManager.personaState.isUserEdited).toBe(true);
      });
    });

    describe('saveAnnotations', () => {
      test('calls correct API endpoint', async () => {
        annotationManager.annotations = fixtures.annotationsList.annotations;
        mockFetchResponse({ success: true });

        await annotationManager.saveAnnotations();

        expect(fetch).toHaveBeenCalledWith(
          '/api/jobs/job123/jd-annotations',
          expect.objectContaining({
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
          })
        );
      });

      test('includes annotations in request body', async () => {
        annotationManager.annotations = [{ id: 'ann1', text: 'Python' }];
        mockFetchResponse({ success: true });

        await annotationManager.saveAnnotations();

        const lastCall = fetch.mock.calls[0];
        const body = JSON.parse(lastCall[1].body);

        expect(body.annotations).toEqual([{ id: 'ann1', text: 'Python' }]);
      });

      test('dispatches annotations:updated event on success', async () => {
        const eventHandler = jest.fn();
        window.addEventListener('annotations:updated', eventHandler);

        annotationManager.annotations = [{ id: 'ann1' }];
        mockFetchResponse({ success: true });

        await annotationManager.saveAnnotations();

        expect(eventHandler).toHaveBeenCalled();
        expect(eventHandler.mock.calls[0][0].detail).toEqual({
          jobId: 'job123',
          hasAnnotations: true,
          annotationCount: 1,
        });

        window.removeEventListener('annotations:updated', eventHandler);
      });
    });

    describe('scheduleSave', () => {
      beforeEach(() => {
        jest.useFakeTimers();
      });

      afterEach(() => {
        jest.useRealTimers();
      });

      test('schedules save after debounce delay', () => {
        const saveSpy = jest.spyOn(annotationManager, 'saveAnnotations').mockImplementation(() => {});

        annotationManager.scheduleSave();

        expect(saveSpy).not.toHaveBeenCalled();

        jest.advanceTimersByTime(1000);

        expect(saveSpy).toHaveBeenCalled();
      });

      test('clears previous timeout on rapid calls', () => {
        const saveSpy = jest.spyOn(annotationManager, 'saveAnnotations').mockImplementation(() => {});

        annotationManager.scheduleSave();
        jest.advanceTimersByTime(500);
        annotationManager.scheduleSave();
        jest.advanceTimersByTime(500);
        annotationManager.scheduleSave();
        jest.advanceTimersByTime(1000);

        expect(saveSpy).toHaveBeenCalledTimes(1);
      });
    });

    describe('showRawJd', () => {
      test('renders raw JD in content element', () => {
        annotationManager.showRawJd('Test job description');

        const contentEl = document.getElementById('jd-processed-content');
        expect(contentEl.innerHTML).toContain('Test job description');
      });

      test('escapes HTML entities', () => {
        annotationManager.showRawJd('<script>alert("xss")</script>');

        const contentEl = document.getElementById('jd-processed-content');
        expect(contentEl.innerHTML).toContain('&lt;script&gt;');
        expect(contentEl.innerHTML).not.toContain('<script>');
      });

      test('handles non-string input gracefully', () => {
        const showEmptySpy = jest.spyOn(annotationManager, 'showEmptyState');

        annotationManager.showRawJd({ invalid: 'object' });

        expect(showEmptySpy).toHaveBeenCalled();
      });
    });

    describe('showEmptyState', () => {
      test('hides loading and content, shows empty', () => {
        annotationManager.showEmptyState();

        const loadingEl = document.getElementById('jd-loading');
        const contentEl = document.getElementById('jd-processed-content');
        const emptyEl = document.getElementById('jd-empty');

        expect(loadingEl.classList.contains('hidden')).toBe(true);
        expect(contentEl.classList.contains('hidden')).toBe(true);
        expect(emptyEl.classList.contains('hidden')).toBe(false);
      });
    });

    describe('undo / redo', () => {
      beforeEach(() => {
        annotationManager.annotations = [
          { id: 'ann1', text: 'Python' },
        ];
        // Mock methods that undo/redo calls
        annotationManager.applyHighlights = jest.fn();
        annotationManager.renderAnnotations = jest.fn();
        annotationManager.updateStats = jest.fn();
        annotationManager.scheduleSave = jest.fn();
        annotationManager.updateUndoRedoButtons = jest.fn();
      });

      test('undo add action removes annotation', () => {
        annotationManager.undoManager.push({
          type: 'add',
          annotation: { id: 'ann1', text: 'Python' },
        });

        annotationManager.undo();

        expect(annotationManager.annotations).toHaveLength(0);
      });

      test('undo delete action restores annotation', () => {
        annotationManager.annotations = [];
        annotationManager.undoManager.push({
          type: 'delete',
          annotation: { id: 'ann1', text: 'Python' },
        });

        annotationManager.undo();

        expect(annotationManager.annotations).toHaveLength(1);
        expect(annotationManager.annotations[0].id).toBe('ann1');
      });

      test('undo update action restores previous state', () => {
        annotationManager.annotations = [
          { id: 'ann1', relevance: 'high' },
        ];
        annotationManager.undoManager.push({
          type: 'update',
          annotation: { id: 'ann1', relevance: 'high' },
          previousState: { id: 'ann1', relevance: 'low' },
        });

        annotationManager.undo();

        expect(annotationManager.annotations[0].relevance).toBe('low');
      });

      test('redo add action adds annotation back', () => {
        annotationManager.annotations = [];
        annotationManager.undoManager.push({
          type: 'add',
          annotation: { id: 'ann1', text: 'Python' },
        });
        annotationManager.undo();

        annotationManager.redo();

        expect(annotationManager.annotations).toHaveLength(1);
      });
    });

    describe('updateUndoRedoButtons', () => {
      test('disables undo button when no undo available', () => {
        const undoBtn = document.getElementById('undo-btn');

        annotationManager.updateUndoRedoButtons();

        expect(undoBtn.disabled).toBe(true);
      });

      test('enables undo button when undo available', () => {
        const undoBtn = document.getElementById('undo-btn');
        annotationManager.undoManager.push({ type: 'add', annotation: { id: '1' } });

        annotationManager.updateUndoRedoButtons();

        expect(undoBtn.disabled).toBe(false);
      });
    });

    describe('checkIdentityAnnotations', () => {
      test('sets hasIdentityAnnotations for core_identity', () => {
        annotationManager.annotations = [
          { identity: 'core_identity', is_active: true },
        ];

        annotationManager.checkIdentityAnnotations();

        expect(annotationManager.personaState.hasIdentityAnnotations).toBe(true);
      });

      test('sets hasIdentityAnnotations for love_it passion', () => {
        annotationManager.annotations = [
          { passion: 'love_it', is_active: true },
        ];

        annotationManager.checkIdentityAnnotations();

        expect(annotationManager.personaState.hasIdentityAnnotations).toBe(true);
      });

      test('ignores inactive annotations', () => {
        annotationManager.annotations = [
          { identity: 'core_identity', is_active: false },
        ];

        annotationManager.checkIdentityAnnotations();

        expect(annotationManager.personaState.hasIdentityAnnotations).toBe(false);
      });
    });

    describe('savePersona', () => {
      beforeEach(() => {
        annotationManager.personaState.statement = 'Test persona statement';
        annotationManager.personaState.isEditing = true;
        annotationManager.renderPersonaPanel = jest.fn();
      });

      test('calls correct API endpoint', async () => {
        mockFetchResponse({ success: true });

        await annotationManager.savePersona();

        expect(fetch).toHaveBeenCalledWith(
          '/api/jobs/job123/save-persona',
          expect.objectContaining({
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
          })
        );
      });

      test('sends persona statement and is_edited flag in request body', async () => {
        mockFetchResponse({ success: true });

        await annotationManager.savePersona();

        const lastCall = fetch.mock.calls[0];
        const body = JSON.parse(lastCall[1].body);

        expect(body.persona).toBe('Test persona statement');
        expect(body.is_edited).toBe(true);
      });

      test('dispatches persona:updated event on success', async () => {
        const eventHandler = jest.fn();
        window.addEventListener('persona:updated', eventHandler);

        mockFetchResponse({ success: true });

        await annotationManager.savePersona();

        expect(eventHandler).toHaveBeenCalledTimes(1);
        expect(eventHandler.mock.calls[0][0].detail).toEqual({
          jobId: 'job123',
          hasPersona: true
        });

        window.removeEventListener('persona:updated', eventHandler);
      });

      test('does not dispatch event on API failure', async () => {
        const eventHandler = jest.fn();
        window.addEventListener('persona:updated', eventHandler);

        mockFetchResponse({ success: false }, { ok: false, status: 500 });

        await annotationManager.savePersona();

        expect(eventHandler).not.toHaveBeenCalled();

        window.removeEventListener('persona:updated', eventHandler);
      });

      test('updates personaState flags on success', async () => {
        mockFetchResponse({ success: true });

        await annotationManager.savePersona();

        expect(annotationManager.personaState.isEditing).toBe(false);
        expect(annotationManager.personaState.isUserEdited).toBe(true);
      });

      test('calls renderPersonaPanel after save', async () => {
        mockFetchResponse({ success: true });

        await annotationManager.savePersona();

        expect(annotationManager.renderPersonaPanel).toHaveBeenCalled();
      });

      test('does not save when statement is empty', async () => {
        annotationManager.personaState.statement = '';

        await annotationManager.savePersona();

        expect(fetch).not.toHaveBeenCalled();
      });

      test('does not save when statement is whitespace only', async () => {
        annotationManager.personaState.statement = '   \n\t  ';

        await annotationManager.savePersona();

        expect(fetch).not.toHaveBeenCalled();
      });

      test('does not save when statement is null', async () => {
        annotationManager.personaState.statement = null;

        await annotationManager.savePersona();

        expect(fetch).not.toHaveBeenCalled();
      });

      test('handles network errors gracefully', async () => {
        mockFetchError(new Error('Network error'));

        // Should not throw
        await expect(annotationManager.savePersona()).resolves.toBeUndefined();
      });

      test('trims persona statement before saving', async () => {
        annotationManager.personaState.statement = '  Test persona with spaces  ';
        mockFetchResponse({ success: true });

        await annotationManager.savePersona();

        const lastCall = fetch.mock.calls[0];
        const body = JSON.parse(lastCall[1].body);

        expect(body.persona).toBe('Test persona with spaces');
      });
    });

    describe('savePersonaToDb', () => {
      test('dispatches persona:updated event on success', async () => {
        const eventHandler = jest.fn();
        window.addEventListener('persona:updated', eventHandler);

        mockFetchResponse({ success: true }, { ok: true });

        await annotationManager.savePersonaToDb('Test persona', false);

        expect(eventHandler).toHaveBeenCalledTimes(1);
        expect(eventHandler.mock.calls[0][0].detail).toEqual({
          jobId: 'job123',
          hasPersona: true
        });

        window.removeEventListener('persona:updated', eventHandler);
      });

      test('calls correct API endpoint', async () => {
        mockFetchResponse({ success: true }, { ok: true });

        await annotationManager.savePersonaToDb('Test persona', false);

        expect(fetch).toHaveBeenCalledWith(
          '/api/jobs/job123/save-persona',
          expect.objectContaining({
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
          })
        );
      });

      test('sends persona and is_edited in request body', async () => {
        mockFetchResponse({ success: true }, { ok: true });

        await annotationManager.savePersonaToDb('My persona', true);

        const lastCall = fetch.mock.calls[0];
        const body = JSON.parse(lastCall[1].body);

        expect(body.persona).toBe('My persona');
        expect(body.is_edited).toBe(true);
      });

      test('does not dispatch event if response is not ok', async () => {
        const eventHandler = jest.fn();
        window.addEventListener('persona:updated', eventHandler);

        mockFetchResponse({ success: false }, { ok: false, status: 500 });

        await annotationManager.savePersonaToDb('Test persona', false);

        expect(eventHandler).not.toHaveBeenCalled();

        window.removeEventListener('persona:updated', eventHandler);
      });

      test('handles network errors gracefully', async () => {
        mockFetchError(new Error('Network error'));

        // Should not throw
        await expect(annotationManager.savePersonaToDb('Test', false)).resolves.toBeUndefined();
      });
    });
  });

  // =========================================================================
  // Global Function Tests
  // =========================================================================
  describe('Global Functions', () => {
    test('openAnnotationPanel is defined', () => {
      expect(typeof window.openAnnotationPanel).toBe('function');
    });

    test('closeAnnotationPanel is defined', () => {
      expect(typeof window.closeAnnotationPanel).toBe('function');
    });

    test('hideAnnotationPopover is defined', () => {
      expect(typeof window.hideAnnotationPopover).toBe('function');
    });

    test('getActiveAnnotationManager is defined', () => {
      expect(typeof window.getActiveAnnotationManager).toBe('function');
    });

    test('processJDForAnnotation is defined', () => {
      expect(typeof window.processJDForAnnotation).toBe('function');
    });

    test('generateAnnotations is defined', () => {
      expect(typeof window.generateAnnotations).toBe('function');
    });

    test('generateSuggestions is defined', () => {
      expect(typeof window.generateSuggestions).toBe('function');
    });

    test('filterAnnotations is defined', () => {
      expect(typeof window.filterAnnotations).toBe('function');
    });

    test('toggleAnnotationView is defined', () => {
      expect(typeof window.toggleAnnotationView).toBe('function');
    });
  });

  // =========================================================================
  // Constants Tests
  // =========================================================================
  describe('Constants', () => {
    test('RELEVANCE_COLORS has expected keys', () => {
      expect(typeof RELEVANCE_COLORS).toBe('object');
      expect(RELEVANCE_COLORS).toHaveProperty('core_strength');
      expect(RELEVANCE_COLORS).toHaveProperty('extremely_relevant');
      expect(RELEVANCE_COLORS).toHaveProperty('relevant');
      expect(RELEVANCE_COLORS).toHaveProperty('tangential');
      expect(RELEVANCE_COLORS).toHaveProperty('gap');
    });

    test('REQUIREMENT_COLORS has expected keys', () => {
      expect(typeof REQUIREMENT_COLORS).toBe('object');
      expect(REQUIREMENT_COLORS).toHaveProperty('must_have');
      expect(REQUIREMENT_COLORS).toHaveProperty('nice_to_have');
      expect(REQUIREMENT_COLORS).toHaveProperty('neutral');
      expect(REQUIREMENT_COLORS).toHaveProperty('disqualifier');
    });
  });
});
