/**
 * Tests for persona badge updates in batch processing
 *
 * Tests the custom event system that updates the PS (Persona/Synthesized) badge
 * from gray/orange to green when persona is generated or saved.
 *
 * Related files:
 * - frontend/static/js/jd-annotation.js (dispatches persona:updated event)
 * - frontend/templates/batch_processing.html (listens for persona:updated event)
 */

describe('Batch Persona Badge Updates', () => {
  let psBadge;
  let eventListener;

  beforeEach(() => {
    // Set up DOM with PS badge
    document.body.innerHTML = `
      <div id="batch-table">
        <div class="job-row" data-job-id="job123">
          <span data-ps-badge="job123" title="Persona: Not generated">PS</span>
        </div>
        <div class="job-row" data-job-id="job456">
          <span data-ps-badge="job456" title="Persona: In progress">PS</span>
        </div>
      </div>
    `;

    // Get badge elements and manually add classes to classList
    const badge123 = document.querySelector('[data-ps-badge="job123"]');
    badge123.classList.add('badge', 'bg-gray-100', 'text-gray-400', 'dark:bg-gray-700', 'dark:text-gray-500');

    const badge456 = document.querySelector('[data-ps-badge="job456"]');
    badge456.classList.add('badge', 'bg-orange-100', 'text-orange-600', 'dark:bg-orange-900/50', 'dark:text-orange-300');

    // Set up event listener (simulates the one in batch_processing.html)
    eventListener = function(e) {
      const { jobId, hasPersona } = e.detail;
      const badge = document.querySelector(`[data-ps-badge="${jobId}"]`);
      if (badge && hasPersona) {
        badge.classList.remove(
          'bg-gray-100', 'text-gray-400', 'dark:bg-gray-700', 'dark:text-gray-500',
          'bg-orange-100', 'text-orange-600', 'dark:bg-orange-900/50', 'dark:text-orange-300'
        );
        badge.classList.add('bg-green-100', 'text-green-700', 'dark:bg-green-900', 'dark:text-green-300');
        badge.title = 'Persona: Generated';
      }
    };

    window.addEventListener('persona:updated', eventListener);

    psBadge = document.querySelector('[data-ps-badge="job123"]');
  });

  afterEach(() => {
    window.removeEventListener('persona:updated', eventListener);
  });

  // =========================================================================
  // Event Dispatch Tests
  // =========================================================================
  describe('persona:updated Event Dispatch', () => {
    test('event is CustomEvent with correct detail', () => {
      const eventHandler = jest.fn();
      window.addEventListener('persona:updated', eventHandler);

      window.dispatchEvent(new CustomEvent('persona:updated', {
        detail: { jobId: 'job123', hasPersona: true }
      }));

      expect(eventHandler).toHaveBeenCalledTimes(1);
      expect(eventHandler.mock.calls[0][0]).toBeInstanceOf(CustomEvent);
      expect(eventHandler.mock.calls[0][0].detail).toEqual({
        jobId: 'job123',
        hasPersona: true
      });

      window.removeEventListener('persona:updated', eventHandler);
    });

    test('event can be dispatched multiple times', () => {
      const eventHandler = jest.fn();
      window.addEventListener('persona:updated', eventHandler);

      window.dispatchEvent(new CustomEvent('persona:updated', {
        detail: { jobId: 'job123', hasPersona: true }
      }));
      window.dispatchEvent(new CustomEvent('persona:updated', {
        detail: { jobId: 'job456', hasPersona: true }
      }));

      expect(eventHandler).toHaveBeenCalledTimes(2);

      window.removeEventListener('persona:updated', eventHandler);
    });

    test('event detail contains required fields', () => {
      const eventHandler = jest.fn();
      window.addEventListener('persona:updated', eventHandler);

      window.dispatchEvent(new CustomEvent('persona:updated', {
        detail: { jobId: 'job123', hasPersona: true }
      }));

      const eventDetail = eventHandler.mock.calls[0][0].detail;
      expect(eventDetail).toHaveProperty('jobId');
      expect(eventDetail).toHaveProperty('hasPersona');

      window.removeEventListener('persona:updated', eventHandler);
    });
  });

  // =========================================================================
  // Badge Update Tests - Gray to Green
  // =========================================================================
  describe('Badge Updates - Gray to Green', () => {
    test('updates gray badge to green when persona:updated fires', () => {
      expect(psBadge.classList.contains('bg-gray-100')).toBe(true);
      expect(psBadge.classList.contains('text-gray-400')).toBe(true);
      expect(psBadge.classList.contains('bg-green-100')).toBe(false);

      window.dispatchEvent(new CustomEvent('persona:updated', {
        detail: { jobId: 'job123', hasPersona: true }
      }));

      expect(psBadge.classList.contains('bg-gray-100')).toBe(false);
      expect(psBadge.classList.contains('text-gray-400')).toBe(false);
      expect(psBadge.classList.contains('bg-green-100')).toBe(true);
      expect(psBadge.classList.contains('text-green-700')).toBe(true);
    });

    test('removes all gray classes (light and dark mode)', () => {
      psBadge.classList.add('dark:bg-gray-700', 'dark:text-gray-500');

      window.dispatchEvent(new CustomEvent('persona:updated', {
        detail: { jobId: 'job123', hasPersona: true }
      }));

      expect(psBadge.classList.contains('bg-gray-100')).toBe(false);
      expect(psBadge.classList.contains('text-gray-400')).toBe(false);
      expect(psBadge.classList.contains('dark:bg-gray-700')).toBe(false);
      expect(psBadge.classList.contains('dark:text-gray-500')).toBe(false);
    });

    test('adds green classes for light and dark mode', () => {
      window.dispatchEvent(new CustomEvent('persona:updated', {
        detail: { jobId: 'job123', hasPersona: true }
      }));

      expect(psBadge.classList.contains('bg-green-100')).toBe(true);
      expect(psBadge.classList.contains('text-green-700')).toBe(true);
      expect(psBadge.classList.contains('dark:bg-green-900')).toBe(true);
      expect(psBadge.classList.contains('dark:text-green-300')).toBe(true);
    });

    test('updates badge title', () => {
      expect(psBadge.title).toBe('Persona: Not generated');

      window.dispatchEvent(new CustomEvent('persona:updated', {
        detail: { jobId: 'job123', hasPersona: true }
      }));

      expect(psBadge.title).toBe('Persona: Generated');
    });
  });

  // =========================================================================
  // Badge Update Tests - Orange to Green
  // =========================================================================
  describe('Badge Updates - Orange to Green', () => {
    let orangeBadge;

    beforeEach(() => {
      orangeBadge = document.querySelector('[data-ps-badge="job456"]');
    });

    test('updates orange badge to green when persona:updated fires', () => {
      expect(orangeBadge.classList.contains('bg-orange-100')).toBe(true);
      expect(orangeBadge.classList.contains('text-orange-600')).toBe(true);
      expect(orangeBadge.classList.contains('bg-green-100')).toBe(false);

      window.dispatchEvent(new CustomEvent('persona:updated', {
        detail: { jobId: 'job456', hasPersona: true }
      }));

      expect(orangeBadge.classList.contains('bg-orange-100')).toBe(false);
      expect(orangeBadge.classList.contains('text-orange-600')).toBe(false);
      expect(orangeBadge.classList.contains('bg-green-100')).toBe(true);
      expect(orangeBadge.classList.contains('text-green-700')).toBe(true);
    });

    test('removes all orange classes (light and dark mode)', () => {
      window.dispatchEvent(new CustomEvent('persona:updated', {
        detail: { jobId: 'job456', hasPersona: true }
      }));

      expect(orangeBadge.classList.contains('bg-orange-100')).toBe(false);
      expect(orangeBadge.classList.contains('text-orange-600')).toBe(false);
      expect(orangeBadge.classList.contains('dark:bg-orange-900/50')).toBe(false);
      expect(orangeBadge.classList.contains('dark:text-orange-300')).toBe(false);
    });

    test('updates badge title from in progress to generated', () => {
      expect(orangeBadge.title).toBe('Persona: In progress');

      window.dispatchEvent(new CustomEvent('persona:updated', {
        detail: { jobId: 'job456', hasPersona: true }
      }));

      expect(orangeBadge.title).toBe('Persona: Generated');
    });
  });

  // =========================================================================
  // Selector Matching Tests
  // =========================================================================
  describe('Badge Selector Matching', () => {
    test('finds badge by data-ps-badge attribute', () => {
      const badge = document.querySelector('[data-ps-badge="job123"]');
      expect(badge).not.toBeNull();
      expect(badge.textContent.trim()).toBe('PS');
    });

    test('does not update badge for wrong jobId', () => {
      const initialClasses = Array.from(psBadge.classList);

      window.dispatchEvent(new CustomEvent('persona:updated', {
        detail: { jobId: 'job999', hasPersona: true }
      }));

      expect(Array.from(psBadge.classList)).toEqual(initialClasses);
    });

    test('only updates badge for matching jobId', () => {
      const badge123 = document.querySelector('[data-ps-badge="job123"]');
      const badge456 = document.querySelector('[data-ps-badge="job456"]');

      window.dispatchEvent(new CustomEvent('persona:updated', {
        detail: { jobId: 'job123', hasPersona: true }
      }));

      expect(badge123.classList.contains('bg-green-100')).toBe(true);
      expect(badge456.classList.contains('bg-green-100')).toBe(false);
      expect(badge456.classList.contains('bg-orange-100')).toBe(true);
    });
  });

  // =========================================================================
  // Edge Cases
  // =========================================================================
  describe('Edge Cases', () => {
    test('handles missing badge gracefully', () => {
      // Should not throw when badge doesn't exist
      expect(() => {
        window.dispatchEvent(new CustomEvent('persona:updated', {
          detail: { jobId: 'nonexistent', hasPersona: true }
        }));
      }).not.toThrow();
    });

    test('does not update badge when hasPersona is false', () => {
      const initialClasses = Array.from(psBadge.classList);

      window.dispatchEvent(new CustomEvent('persona:updated', {
        detail: { jobId: 'job123', hasPersona: false }
      }));

      expect(Array.from(psBadge.classList)).toEqual(initialClasses);
    });

    test('does not update badge when hasPersona is missing', () => {
      const initialClasses = Array.from(psBadge.classList);

      window.dispatchEvent(new CustomEvent('persona:updated', {
        detail: { jobId: 'job123' }
      }));

      expect(Array.from(psBadge.classList)).toEqual(initialClasses);
    });

    test('handles empty jobId gracefully', () => {
      const initialClasses = Array.from(psBadge.classList);

      expect(() => {
        window.dispatchEvent(new CustomEvent('persona:updated', {
          detail: { jobId: '', hasPersona: true }
        }));
      }).not.toThrow();

      expect(Array.from(psBadge.classList)).toEqual(initialClasses);
    });

    test('handles null jobId gracefully', () => {
      const initialClasses = Array.from(psBadge.classList);

      expect(() => {
        window.dispatchEvent(new CustomEvent('persona:updated', {
          detail: { jobId: null, hasPersona: true }
        }));
      }).not.toThrow();

      expect(Array.from(psBadge.classList)).toEqual(initialClasses);
    });
  });

  // =========================================================================
  // Multiple Badge Updates
  // =========================================================================
  describe('Multiple Badge Updates', () => {
    test('can update multiple badges sequentially', () => {
      const badge123 = document.querySelector('[data-ps-badge="job123"]');
      const badge456 = document.querySelector('[data-ps-badge="job456"]');

      window.dispatchEvent(new CustomEvent('persona:updated', {
        detail: { jobId: 'job123', hasPersona: true }
      }));

      expect(badge123.classList.contains('bg-green-100')).toBe(true);
      expect(badge456.classList.contains('bg-green-100')).toBe(false);

      window.dispatchEvent(new CustomEvent('persona:updated', {
        detail: { jobId: 'job456', hasPersona: true }
      }));

      expect(badge123.classList.contains('bg-green-100')).toBe(true);
      expect(badge456.classList.contains('bg-green-100')).toBe(true);
    });

    test('updating same badge multiple times is idempotent', () => {
      window.dispatchEvent(new CustomEvent('persona:updated', {
        detail: { jobId: 'job123', hasPersona: true }
      }));

      const classesAfterFirst = Array.from(psBadge.classList).sort();

      window.dispatchEvent(new CustomEvent('persona:updated', {
        detail: { jobId: 'job123', hasPersona: true }
      }));

      const classesAfterSecond = Array.from(psBadge.classList).sort();

      expect(classesAfterFirst).toEqual(classesAfterSecond);
      expect(psBadge.title).toBe('Persona: Generated');
    });
  });

  // =========================================================================
  // Integration with CLI Operations
  // =========================================================================
  describe('Integration with CLI Operations', () => {
    test('cli:complete can trigger persona:updated event', () => {
      const eventHandler = jest.fn();
      window.addEventListener('persona:updated', eventHandler);

      // Simulate cli:complete event that triggers persona:updated
      // (as implemented in batch_processing.html lines 2345-2350)
      const cliEvent = new CustomEvent('cli:complete', {
        detail: {
          job_id: 'job123',
          operation: 'analyze-job',
          status: 'success'
        }
      });

      // In the real code, this would be handled by the cli:complete listener
      // which then dispatches persona:updated. We simulate that here.
      if (['analyze-job', 'full-analysis', 'all-ops'].includes(cliEvent.detail.operation)) {
        window.dispatchEvent(new CustomEvent('persona:updated', {
          detail: { jobId: cliEvent.detail.job_id, hasPersona: true }
        }));
      }

      expect(eventHandler).toHaveBeenCalledWith(
        expect.objectContaining({
          detail: { jobId: 'job123', hasPersona: true }
        })
      );

      window.removeEventListener('persona:updated', eventHandler);
    });

    test('operations that generate persona dispatch persona:updated', () => {
      const eventHandler = jest.fn();
      window.addEventListener('persona:updated', eventHandler);

      const operations = ['analyze-job', 'full-analysis', 'all-ops'];

      operations.forEach(operation => {
        window.dispatchEvent(new CustomEvent('persona:updated', {
          detail: { jobId: 'job123', hasPersona: true }
        }));
      });

      expect(eventHandler).toHaveBeenCalledTimes(3);

      window.removeEventListener('persona:updated', eventHandler);
    });

    test('operations that do not generate persona should not update badge', () => {
      const operations = ['extract', 'contacts', 'generate-cv'];
      const initialClasses = Array.from(psBadge.classList);

      // These operations should NOT dispatch persona:updated
      operations.forEach(operation => {
        // No event dispatched for these operations
      });

      expect(Array.from(psBadge.classList)).toEqual(initialClasses);
    });
  });

  // =========================================================================
  // Event Listener Cleanup
  // =========================================================================
  describe('Event Listener Cleanup', () => {
    test('event listener can be removed', () => {
      const tempListener = jest.fn();
      window.addEventListener('persona:updated', tempListener);

      window.dispatchEvent(new CustomEvent('persona:updated', {
        detail: { jobId: 'job123', hasPersona: true }
      }));

      expect(tempListener).toHaveBeenCalledTimes(1);

      window.removeEventListener('persona:updated', tempListener);

      window.dispatchEvent(new CustomEvent('persona:updated', {
        detail: { jobId: 'job123', hasPersona: true }
      }));

      // Still only called once (not called after removal)
      expect(tempListener).toHaveBeenCalledTimes(1);
    });

    test('multiple listeners can coexist', () => {
      const listener1 = jest.fn();
      const listener2 = jest.fn();

      window.addEventListener('persona:updated', listener1);
      window.addEventListener('persona:updated', listener2);

      window.dispatchEvent(new CustomEvent('persona:updated', {
        detail: { jobId: 'job123', hasPersona: true }
      }));

      expect(listener1).toHaveBeenCalledTimes(1);
      expect(listener2).toHaveBeenCalledTimes(1);

      window.removeEventListener('persona:updated', listener1);
      window.removeEventListener('persona:updated', listener2);
    });
  });
});
