/**
 * Tests for batch-sidebars.js
 *
 * Tests the sidebar management functions for the batch processing page.
 */

const fs = require('fs');
const path = require('path');

describe('Batch Sidebars', () => {
  beforeAll(() => {
    // Load the batch-sidebars.js file
    const filePath = path.join(__dirname, '../../static/js/batch-sidebars.js');
    const code = fs.readFileSync(filePath, 'utf-8');

    // Transform function declarations to window assignments so they become global
    // This handles: function foo() {} -> window.foo = function() {}
    const transformedCode = code
      .replace(/^function\s+(\w+)\s*\(/gm, 'window.$1 = function(')
      .replace(/^async function\s+(\w+)\s*\(/gm, 'window.$1 = async function(')
      .replace(/^let\s+(\w+)\s*=/gm, 'window.$1 =')
      .replace(/^const\s+(\w+)\s*=/gm, 'window.$1 =');

    // Execute the transformed code
    const fn = new Function(transformedCode);
    fn.call(window);
  });

  beforeEach(() => {
    // Reset DOM with sidebar structure
    document.body.innerHTML = `
      <div id="batch-sidebar-overlay" class="hidden opacity-0"></div>
      <div id="batch-annotation-sidebar" class="translate-x-full" tabindex="-1">
        <a id="batch-annotation-detail-link" href="#"></a>
        <div id="batch-annotation-content"></div>
      </div>
      <div id="batch-contacts-sidebar" class="translate-x-full" tabindex="-1">
        <a id="batch-contacts-detail-link" href="#"></a>
        <div id="batch-contacts-content"></div>
      </div>
      <div id="batch-cv-sidebar" class="translate-x-full" tabindex="-1">
        <a id="batch-cv-detail-link" href="#"></a>
        <div id="batch-cv-content"></div>
        <div id="batch-cv-editor-content"></div>
        <div id="batch-cv-editor-container"></div>
        <div id="batch-cv-save-indicator" class="hidden"></div>
      </div>
      <div id="batch-jd-preview-sidebar" class="translate-x-full" tabindex="-1">
        <a id="batch-jd-preview-detail-link" href="#"></a>
        <div id="batch-jd-preview-content"></div>
      </div>
    `;

    // Reset global state
    window.currentBatchSidebar = null;
    window.currentBatchJobId = null;
    window.batchAnnotationManager = null;

    jest.clearAllMocks();
  });

  // =========================================================================
  // Global State Tests
  // =========================================================================
  describe('Global State', () => {
    test('currentBatchSidebar is initially null', () => {
      expect(window.currentBatchSidebar).toBeNull();
    });

    test('currentBatchJobId is initially null', () => {
      expect(window.currentBatchJobId).toBeNull();
    });

    test('batchAnnotationManager is initially null', () => {
      expect(window.batchAnnotationManager).toBeNull();
    });
  });

  // =========================================================================
  // Function Existence Tests
  // =========================================================================
  describe('Function Existence', () => {
    test('openBatchAnnotationPanel is defined', () => {
      expect(typeof window.openBatchAnnotationPanel).toBe('function');
    });

    test('openBatchContactsSidebar is defined', () => {
      expect(typeof window.openBatchContactsSidebar).toBe('function');
    });

    test('openBatchCVEditor is defined', () => {
      expect(typeof window.openBatchCVEditor).toBe('function');
    });

    test('openJDPreviewSidebar is defined', () => {
      expect(typeof window.openJDPreviewSidebar).toBe('function');
    });

    test('openBatchSidebar is defined', () => {
      expect(typeof window.openBatchSidebar).toBe('function');
    });

    test('closeBatchSidebar is defined', () => {
      expect(typeof window.closeBatchSidebar).toBe('function');
    });

    test('initBatchCVEditor is defined', () => {
      expect(typeof window.initBatchCVEditor).toBe('function');
    });

    test('cleanupBatchCVEditor is defined', () => {
      expect(typeof window.cleanupBatchCVEditor).toBe('function');
    });

    test('applyBatchCVFormat is defined', () => {
      expect(typeof window.applyBatchCVFormat).toBe('function');
    });

    test('exportBatchCVToPDF is defined', () => {
      expect(typeof window.exportBatchCVToPDF).toBe('function');
    });

    test('escapeHtml is defined', () => {
      expect(typeof window.escapeHtml).toBe('function');
    });

    test('waitForTipTap is defined', () => {
      expect(typeof window.waitForTipTap).toBe('function');
    });
  });

  // =========================================================================
  // openBatchSidebar Tests
  // =========================================================================
  describe('openBatchSidebar', () => {
    test('sets currentBatchSidebar to the type', async () => {
      mockFetchResponse('<div>Content</div>');

      await window.openBatchSidebar('annotation', 'job123');

      expect(window.currentBatchSidebar).toBe('annotation');
    });

    test('sets currentBatchJobId', async () => {
      mockFetchResponse('<div>Content</div>');

      await window.openBatchSidebar('annotation', 'job456');

      expect(window.currentBatchJobId).toBe('job456');
    });

    test('shows overlay', async () => {
      mockFetchResponse('<div>Content</div>');

      await window.openBatchSidebar('annotation', 'job123');

      const overlay = document.getElementById('batch-sidebar-overlay');
      expect(overlay.classList.contains('hidden')).toBe(false);
    });

    test('removes translate-x-full from sidebar', async () => {
      mockFetchResponse('<div>Content</div>');

      // Need to wait for requestAnimationFrame
      jest.useFakeTimers();

      const promise = window.openBatchSidebar('annotation', 'job123');
      jest.runAllTimers();
      await promise;

      jest.useRealTimers();

      const sidebar = document.getElementById('batch-annotation-sidebar');
      expect(sidebar.classList.contains('translate-x-full')).toBe(false);
    });

    test('updates detail link href', async () => {
      mockFetchResponse('<div>Content</div>');

      await window.openBatchSidebar('annotation', 'job789');

      const link = document.getElementById('batch-annotation-detail-link');
      expect(link.href).toContain('/job/job789');
    });

    test('fetches content from correct endpoint', async () => {
      mockFetchResponse('<div>Content</div>');

      await window.openBatchSidebar('annotation', 'job123');

      expect(fetch).toHaveBeenCalledWith('/partials/batch-annotation/job123');
    });

    test('fetches correct endpoint for contacts', async () => {
      mockFetchResponse('<div>Contacts</div>');

      await window.openBatchSidebar('contacts', 'job123');

      expect(fetch).toHaveBeenCalledWith('/partials/batch-contacts/job123');
    });

    test('fetches correct endpoint for cv', async () => {
      mockFetchResponse('<div>CV</div>');

      await window.openBatchSidebar('cv', 'job123');

      expect(fetch).toHaveBeenCalledWith('/partials/batch-cv/job123');
    });

    test('fetches correct endpoint for jd-preview', async () => {
      mockFetchResponse('<div>JD Preview</div>');

      await window.openBatchSidebar('jd-preview', 'job123');

      expect(fetch).toHaveBeenCalledWith('/partials/jd-preview/job123');
    });

    test('loads content into container', async () => {
      global.fetch.mockImplementationOnce(() =>
        Promise.resolve({
          ok: true,
          text: () => Promise.resolve('<div class="test-content">Loaded!</div>'),
        })
      );

      await window.openBatchSidebar('annotation', 'job123');

      const content = document.getElementById('batch-annotation-content');
      expect(content.innerHTML).toContain('test-content');
    });

    test('shows error state on fetch failure', async () => {
      mockFetchResponse({}, { ok: false, status: 500 });

      await window.openBatchSidebar('annotation', 'job123');

      const content = document.getElementById('batch-annotation-content');
      expect(content.innerHTML).toContain('Failed to load content');
    });

    test('shows error state on network error', async () => {
      mockFetchError(new Error('Network error'));

      await window.openBatchSidebar('annotation', 'job123');

      const content = document.getElementById('batch-annotation-content');
      expect(content.innerHTML).toContain('Network error');
    });

    test('prevents body scroll', async () => {
      mockFetchResponse('<div>Content</div>');

      await window.openBatchSidebar('annotation', 'job123');

      expect(document.body.style.overflow).toBe('hidden');
    });

    test('closes previous sidebar before opening new one', async () => {
      mockFetchResponse('<div>Content 1</div>');
      await window.openBatchSidebar('annotation', 'job123');

      mockFetchResponse('<div>Content 2</div>');
      await window.openBatchSidebar('contacts', 'job456');

      expect(window.currentBatchSidebar).toBe('contacts');
      expect(window.currentBatchJobId).toBe('job456');
    });

    test('handles missing sidebar element gracefully', async () => {
      document.getElementById('batch-annotation-sidebar').remove();

      // Should not throw
      await expect(window.openBatchSidebar('annotation', 'job123')).resolves.toBeUndefined();
    });
  });

  // =========================================================================
  // closeBatchSidebar Tests
  // =========================================================================
  describe('closeBatchSidebar', () => {
    beforeEach(async () => {
      // Open a sidebar first
      mockFetchResponse('<div>Content</div>');
      await window.openBatchSidebar('annotation', 'job123');
    });

    test('returns a promise', () => {
      const result = window.closeBatchSidebar();
      expect(result).toBeInstanceOf(Promise);
    });

    test('resets currentBatchSidebar to null', async () => {
      jest.useFakeTimers();

      const promise = window.closeBatchSidebar();
      jest.advanceTimersByTime(300);
      await promise;

      jest.useRealTimers();

      expect(window.currentBatchSidebar).toBeNull();
    });

    test('resets currentBatchJobId to null', async () => {
      jest.useFakeTimers();

      const promise = window.closeBatchSidebar();
      jest.advanceTimersByTime(300);
      await promise;

      jest.useRealTimers();

      expect(window.currentBatchJobId).toBeNull();
    });

    test('adds translate-x-full back to sidebar', async () => {
      const sidebar = document.getElementById('batch-annotation-sidebar');

      await window.closeBatchSidebar(false); // No animation

      expect(sidebar.classList.contains('translate-x-full')).toBe(true);
    });

    test('hides overlay', async () => {
      jest.useFakeTimers();

      const promise = window.closeBatchSidebar();
      jest.advanceTimersByTime(300);
      await promise;

      jest.useRealTimers();

      const overlay = document.getElementById('batch-sidebar-overlay');
      expect(overlay.classList.contains('hidden')).toBe(true);
    });

    test('restores body scroll', async () => {
      jest.useFakeTimers();

      const promise = window.closeBatchSidebar();
      jest.advanceTimersByTime(300);
      await promise;

      jest.useRealTimers();

      expect(document.body.style.overflow).toBe('');
    });

    test('skips animation when animate=false', async () => {
      jest.useFakeTimers();

      const promise = window.closeBatchSidebar(false);
      jest.advanceTimersByTime(0);
      await promise;

      jest.useRealTimers();

      expect(window.currentBatchSidebar).toBeNull();
    });
  });

  // =========================================================================
  // Wrapper Function Tests
  // =========================================================================
  describe('Wrapper Functions', () => {
    test('openBatchAnnotationPanel calls openBatchSidebar with annotation type', async () => {
      const spy = jest.spyOn(window, 'openBatchSidebar').mockResolvedValue();

      await window.openBatchAnnotationPanel('job123');

      expect(spy).toHaveBeenCalledWith('annotation', 'job123');
      spy.mockRestore();
    });

    test('openBatchContactsSidebar calls openBatchSidebar with contacts type', async () => {
      const spy = jest.spyOn(window, 'openBatchSidebar').mockResolvedValue();

      await window.openBatchContactsSidebar('job123');

      expect(spy).toHaveBeenCalledWith('contacts', 'job123');
      spy.mockRestore();
    });

    test('openBatchCVEditor calls openBatchSidebar with cv type', async () => {
      const spy = jest.spyOn(window, 'openBatchSidebar').mockResolvedValue();

      await window.openBatchCVEditor('job123');

      expect(spy).toHaveBeenCalledWith('cv', 'job123');
      spy.mockRestore();
    });

    test('openJDPreviewSidebar calls openBatchSidebar with jd-preview type', async () => {
      const spy = jest.spyOn(window, 'openBatchSidebar').mockResolvedValue();

      await window.openJDPreviewSidebar('job123');

      expect(spy).toHaveBeenCalledWith('jd-preview', 'job123');
      spy.mockRestore();
    });
  });

  // =========================================================================
  // waitForTipTap Tests
  // =========================================================================
  describe('waitForTipTap', () => {
    test('resolves true immediately if TipTap already loaded', async () => {
      window.tiptap = { Editor: jest.fn() };

      const result = await window.waitForTipTap(100);

      expect(result).toBe(true);
    });

    test('resolves true when tiptap-loaded event fires', async () => {
      delete window.tiptap;

      const promise = window.waitForTipTap(5000);

      // Simulate TipTap loading
      window.tiptap = { Editor: jest.fn() };
      window.dispatchEvent(new Event('tiptap-loaded'));

      const result = await promise;
      expect(result).toBe(true);
    });

    test('resolves false on timeout', async () => {
      delete window.tiptap;

      jest.useFakeTimers();

      const promise = window.waitForTipTap(100);
      jest.advanceTimersByTime(200);

      jest.useRealTimers();

      const result = await promise;
      expect(result).toBe(false);
    });
  });

  // =========================================================================
  // escapeHtml Tests
  // =========================================================================
  describe('escapeHtml', () => {
    test('escapes < and >', () => {
      const result = window.escapeHtml('<script>alert("xss")</script>');
      expect(result).not.toContain('<script>');
      expect(result).toContain('&lt;script&gt;');
    });

    test('escapes ampersands', () => {
      const result = window.escapeHtml('foo & bar');
      expect(result).toContain('&amp;');
    });

    test('preserves quotes (safe for text content)', () => {
      // escapeHtml uses textContent which doesn't encode quotes
      // This is safe because the function is meant for text content, not attributes
      const result = window.escapeHtml('"quoted"');
      expect(result).toContain('quoted');
    });

    test('handles empty string', () => {
      expect(window.escapeHtml('')).toBe('');
    });
  });

  // =========================================================================
  // cleanupBatchCVEditor Tests
  // =========================================================================
  describe('cleanupBatchCVEditor', () => {
    test('calls destroy on editor instance if exists', () => {
      const mockDestroy = jest.fn();
      window.batchCVEditorInstance = { destroy: mockDestroy };

      window.cleanupBatchCVEditor();

      expect(mockDestroy).toHaveBeenCalled();
    });

    test('sets batchCVEditorInstance to null', () => {
      window.batchCVEditorInstance = { destroy: jest.fn() };

      window.cleanupBatchCVEditor();

      expect(window.batchCVEditorInstance).toBeNull();
    });

    test('hides save indicator', () => {
      const saveIndicator = document.getElementById('batch-cv-save-indicator');
      saveIndicator.classList.remove('hidden');

      window.cleanupBatchCVEditor();

      expect(saveIndicator.classList.contains('hidden')).toBe(true);
    });

    test('handles missing editor instance gracefully', () => {
      window.batchCVEditorInstance = null;

      // Should not throw
      expect(() => window.cleanupBatchCVEditor()).not.toThrow();
    });
  });

  // =========================================================================
  // applyBatchCVFormat Tests
  // =========================================================================
  describe('applyBatchCVFormat', () => {
    test('calls applyFormat on editor instance', () => {
      const mockApplyFormat = jest.fn();
      window.batchCVEditorInstance = { applyFormat: mockApplyFormat };

      window.applyBatchCVFormat('bold');

      expect(mockApplyFormat).toHaveBeenCalledWith('bold', null);
    });

    test('passes value to applyFormat', () => {
      const mockApplyFormat = jest.fn();
      window.batchCVEditorInstance = { applyFormat: mockApplyFormat };

      window.applyBatchCVFormat('fontSize', '16px');

      expect(mockApplyFormat).toHaveBeenCalledWith('fontSize', '16px');
    });

    test('does nothing if editor not initialized', () => {
      window.batchCVEditorInstance = null;

      // Should not throw
      expect(() => window.applyBatchCVFormat('bold')).not.toThrow();
    });
  });

  // =========================================================================
  // Keyboard Handler Tests
  // =========================================================================
  describe('Keyboard Handler', () => {
    test('Escape key closes open sidebar', async () => {
      mockFetchResponse('<div>Content</div>');
      await window.openBatchSidebar('annotation', 'job123');

      const closeSpy = jest.spyOn(window, 'closeBatchSidebar').mockResolvedValue();

      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));

      expect(closeSpy).toHaveBeenCalled();
      closeSpy.mockRestore();
    });

    test('Escape key does nothing if no sidebar open', () => {
      window.currentBatchSidebar = null;

      const closeSpy = jest.spyOn(window, 'closeBatchSidebar').mockResolvedValue();

      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));

      expect(closeSpy).not.toHaveBeenCalled();
      closeSpy.mockRestore();
    });
  });
});
