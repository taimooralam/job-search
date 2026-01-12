/**
 * JD Annotation System - JavaScript Implementation
 *
 * Features:
 * - Text selection and annotation creation
 * - Annotation highlighting with relevance-based colors
 * - Auto-save with 1.5-second debounce
 * - STAR story linking
 * - Validation and boost calculation preview
 *
 * Architecture:
 * - AnnotationManager: Main controller class
 * - State stored in MongoDB via API
 * - Highlight rendering via CSS classes
 */

// ============================================================================
// Constants
// ============================================================================

const RELEVANCE_COLORS = {
    core_strength: { bg: 'bg-teal-100', border: 'border-teal-400', text: 'text-teal-800' },
    extremely_relevant: { bg: 'bg-green-100', border: 'border-green-400', text: 'text-green-800' },
    relevant: { bg: 'bg-amber-100', border: 'border-amber-500', text: 'text-amber-800' },
    tangential: { bg: 'bg-orange-100', border: 'border-orange-400', text: 'text-orange-800' },
    gap: { bg: 'bg-rose-100', border: 'border-rose-400', text: 'text-rose-800' }
};

const REQUIREMENT_COLORS = {
    must_have: { bg: 'bg-blue-100', text: 'text-blue-700' },
    nice_to_have: { bg: 'bg-gray-100', text: 'text-gray-600' },
    neutral: { bg: 'bg-gray-50', text: 'text-gray-500' },
    disqualifier: { bg: 'bg-red-100', text: 'text-red-700' }
};

const AUTOSAVE_DELAY = 1000; // 1 second (reduced for smoother UX)

// ============================================================================
// Undo Manager Class
// ============================================================================

/**
 * UndoManager - Transaction history system for annotation actions.
 *
 * Supports undo/redo for:
 * - add: Adding new annotations
 * - delete: Deleting annotations
 * - update: Modifying existing annotations
 *
 * Usage:
 *   undoManager.push({ type: 'add', annotation: {...} });
 *   undoManager.push({ type: 'delete', annotation: {...} });
 *   undoManager.push({ type: 'update', annotation: {...}, previousState: {...} });
 */
class UndoManager {
    /**
     * Create an UndoManager instance
     * @param {number} maxHistory - Maximum number of actions to keep in history (default: 50)
     */
    constructor(maxHistory = 50) {
        this.undoStack = [];
        this.redoStack = [];
        this.maxHistory = maxHistory;
    }

    /**
     * Record an action for undo capability
     * @param {Object} action - The action to record
     * @param {string} action.type - 'add' | 'delete' | 'update'
     * @param {Object} action.annotation - The annotation object (cloned)
     * @param {Object} [action.previousState] - For 'update' type, the previous annotation state
     */
    push(action) {
        // Deep clone annotation to preserve state at this point in time
        const clonedAction = {
            type: action.type,
            annotation: JSON.parse(JSON.stringify(action.annotation)),
        };
        if (action.previousState) {
            clonedAction.previousState = JSON.parse(JSON.stringify(action.previousState));
        }

        this.undoStack.push(clonedAction);

        // Limit history size
        if (this.undoStack.length > this.maxHistory) {
            this.undoStack.shift();
        }

        // Clear redo stack when new action is performed
        this.redoStack = [];
    }

    /**
     * Undo the last action
     * @returns {Object|null} The action that was undone, or null if nothing to undo
     */
    undo() {
        if (this.undoStack.length === 0) return null;
        const action = this.undoStack.pop();
        this.redoStack.push(action);
        return action;
    }

    /**
     * Redo the last undone action
     * @returns {Object|null} The action that was redone, or null if nothing to redo
     */
    redo() {
        if (this.redoStack.length === 0) return null;
        const action = this.redoStack.pop();
        this.undoStack.push(action);
        return action;
    }

    /**
     * Check if undo is available
     * @returns {boolean} True if there are actions to undo
     */
    canUndo() {
        return this.undoStack.length > 0;
    }

    /**
     * Check if redo is available
     * @returns {boolean} True if there are actions to redo
     */
    canRedo() {
        return this.redoStack.length > 0;
    }

    /**
     * Clear all history
     */
    clear() {
        this.undoStack = [];
        this.redoStack = [];
    }

    /**
     * Get the count of actions that can be undone
     * @returns {number} Number of actions in undo stack
     */
    get undoCount() {
        return this.undoStack.length;
    }

    /**
     * Get the count of actions that can be redone
     * @returns {number} Number of actions in redo stack
     */
    get redoCount() {
        return this.redoStack.length;
    }
}

// ============================================================================
// Annotation Manager Class
// ============================================================================

class AnnotationManager {
    /**
     * Create an AnnotationManager instance
     * @param {string} jobId - The job ID to manage annotations for
     * @param {Object} config - Configuration options with element IDs (for batch page support)
     * @param {string} config.panelId - ID of the annotation panel element (default: 'jd-annotation-panel')
     * @param {string} config.contentId - ID of the JD content element (default: 'jd-processed-content')
     * @param {string} config.popoverId - ID of the popover element (default: 'annotation-popover')
     * @param {string} config.listId - ID of the annotation list element (default: 'annotation-items')
     * @param {string} config.loadingId - ID of the loading indicator element (default: 'jd-loading')
     * @param {string} config.emptyId - ID of the empty state element (default: 'jd-empty')
     * @param {string} config.saveIndicatorId - ID of the save indicator element (default: 'annotation-save-indicator')
     * @param {string} config.overlayId - ID of the overlay element (default: 'jd-annotation-overlay')
     */
    constructor(jobId, config = {}) {
        this.jobId = jobId;
        this.config = {
            panelId: config.panelId || 'jd-annotation-panel',
            contentId: config.contentId || 'jd-processed-content',
            popoverId: config.popoverId || 'annotation-popover',
            listId: config.listId || 'annotation-items',
            loadingId: config.loadingId || 'jd-loading',
            emptyId: config.emptyId || 'jd-empty',
            saveIndicatorId: config.saveIndicatorId || 'annotation-save-indicator',
            overlayId: config.overlayId || 'jd-annotation-overlay',
            listContainerId: config.listContainerId || 'annotation-list',
            listCountId: config.listCountId || 'annotation-list-count',
            listEmptyId: config.listEmptyId || 'annotation-list-empty',
            annotationCountId: config.annotationCountId || 'annotation-count',
            activeAnnotationCountId: config.activeAnnotationCountId || 'active-annotation-count',
            coverageBarId: config.coverageBarId || 'annotation-coverage-bar',
            coveragePctId: config.coveragePctId || 'annotation-coverage-pct',
            boostValueId: config.boostValueId || 'total-boost-value',
            personaPanelId: config.personaPanelId || 'persona-panel-container',
            // Batch suggestion review banner IDs
            reviewBannerId: config.reviewBannerId || 'review-banner',
            pendingCountId: config.pendingCountId || 'pending-count',
            // Undo/Redo button IDs
            undoBtnId: config.undoBtnId || 'undo-btn',
            redoBtnId: config.redoBtnId || 'redo-btn',
            // ID prefix for batch mode (empty string for detail page, 'batch-' for batch)
            idPrefix: config.idPrefix || ''
        };
        this.annotations = [];
        // Initialize undo manager for transaction history
        this.undoManager = new UndoManager();
        this.processedJdHtml = null;
        this.settings = {
            auto_highlight: true,
            show_confidence: true,
            min_confidence_threshold: 0.5
        };
        this.saveTimeout = null;
        this.currentFilter = 'all';
        this.starStories = [];
        // Track the last annotation ID that was edited/created for save pulse animation
        this._lastEditedAnnotationId = null;
        this.popoverState = {
            selectedText: '',
            selectedRange: null,
            // Optimistic defaults - most annotations are core strengths you must have
            relevance: 'core_strength',
            requirement: 'must_have',
            passion: 'enjoy',
            identity: 'strong_identity',
            starIds: [],
            reframeNote: '',
            keywords: '',
            // Track explicit user selections (vs defaults)
            hasExplicitRelevance: false,
            hasExplicitRequirement: false,
            hasExplicitPassion: false,
            hasExplicitIdentity: false
        };
        // Persona synthesis state
        this.personaState = {
            statement: null,
            isLoading: false,
            isEditing: false,
            hasIdentityAnnotations: false,
            isUserEdited: false,
            unavailable: false,  // True when on Vercel (LangChain not available)
            isExpanded: false    // Collapsible state - collapsed by default
        };
        // Track if destroyed
        this._destroyed = false;
    }

    /**
     * Clean up resources when the manager is no longer needed
     * Call this when closing a sidebar or switching jobs in batch view
     */
    destroy() {
        this._destroyed = true;

        // Clear any pending save timeout
        if (this.saveTimeout) {
            clearTimeout(this.saveTimeout);
            this.saveTimeout = null;
        }

        // Clear smart selection state
        if (this.smartSelectionState) {
            this.smartSelectionState.hasSentenceSelected = false;
            this.smartSelectionState.lastSelectedSentence = null;
        }

        // Hide popover if visible
        const popover = document.getElementById(this.config.popoverId);
        if (popover) {
            popover.classList.add('hidden');
        }

        // Clear selection
        if (window.getSelection) {
            window.getSelection().removeAllRanges();
        }

        console.log('AnnotationManager destroyed for job:', this.jobId);
    }

    /**
     * Set up keyboard shortcuts for undo/redo
     * Ctrl+Z (Cmd+Z on Mac): Undo
     * Ctrl+Y or Ctrl+Shift+Z (Cmd+Shift+Z on Mac): Redo
     */
    setupKeyboardShortcuts() {
        this._undoRedoHandler = (e) => {
            if (this._destroyed) return;

            // Only handle if this manager is active (container is visible)
            const container = document.getElementById(this.config.panelId);
            if (!container || container.offsetParent === null) {
                // For batch mode, check if the content container is visible instead
                const contentContainer = document.getElementById(this.config.contentId);
                if (!contentContainer || contentContainer.offsetParent === null) {
                    return;
                }
            }

            // Check for Ctrl+Z (undo) - not Shift
            if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
                e.preventDefault();
                this.undo();
            }
            // Check for Ctrl+Y or Ctrl+Shift+Z (redo)
            else if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.key === 'z' && e.shiftKey) || (e.key === 'Z' && e.shiftKey))) {
                e.preventDefault();
                this.redo();
            }
        };

        document.addEventListener('keydown', this._undoRedoHandler);
    }

    /**
     * Initialize the annotation manager
     */
    async init() {
        console.log('Initializing AnnotationManager for job:', this.jobId);

        // Load existing annotations
        await this.loadAnnotations();

        // Load STAR stories for linking
        await this.loadStarStories();

        // Set up event listeners
        this.setupEventListeners();

        // Set up keyboard shortcuts for undo/redo
        this.setupKeyboardShortcuts();

        // Render initial state
        this.renderAnnotations();
        this.updateStats();

        // Update undo/redo button states
        this.updateUndoRedoButtons();
    }

    /**
     * Load annotations from API
     */
    async loadAnnotations() {
        try {
            // Fetch annotations and raw job data in parallel
            const [annotationsRes, jobRes] = await Promise.all([
                fetch(`/api/jobs/${this.jobId}/jd-annotations`),
                fetch(`/api/jobs/${this.jobId}`)
            ]);

            // Get raw JD from job data (must be a string, not an object)
            let rawJd = null;
            if (jobRes.ok) {
                const jobData = await jobRes.json();
                const job = jobData.job || jobData;
                // extracted_jd is often a structured object, so check type
                // Prefer description or job_description which are raw text strings
                const candidates = [job.description, job.job_description];
                // Only use extracted_jd if it's a string (not structured object)
                if (typeof job.extracted_jd === 'string') {
                    candidates.unshift(job.extracted_jd);
                }
                rawJd = candidates.find(c => typeof c === 'string' && c.trim()) || null;
            }

            if (!annotationsRes.ok) throw new Error('Failed to load annotations');

            const data = await annotationsRes.json();
            if (data.success && data.annotations) {
                // Normalize annotations to ensure is_active defaults to true
                // (for backward compatibility with older annotations)
                // Also auto-approve AI suggestions (Issue 1: auto-apply UX)
                this.annotations = (data.annotations.annotations || []).map(ann => ({
                    ...ann,
                    is_active: ann.is_active !== false,  // Default to true unless explicitly false
                    // Auto-approve auto_generated annotations (user can delete/edit if wrong)
                    status: ann.source === 'auto_generated' && !ann.status ? 'approved' : ann.status
                }));
                this.processedJdHtml = data.annotations.processed_jd_html;
                this.settings = data.annotations.settings || this.settings;

                // Load stored persona if available
                const storedPersona = data.annotations.synthesized_persona;
                if (storedPersona && storedPersona.persona_statement) {
                    this.personaState.statement = storedPersona.persona_statement;
                    this.personaState.isUserEdited = storedPersona.is_user_edited || false;
                }

                // Check for identity annotations
                this.checkIdentityAnnotations();

                // Render processed JD if available
                if (this.processedJdHtml) {
                    this.renderProcessedJd();
                } else if (rawJd) {
                    // No processed JD yet - show raw JD with preserved whitespace
                    this.showRawJd(rawJd);
                } else {
                    // No JD at all - show empty state
                    this.showEmptyState();
                }

                // Apply highlights after content is rendered
                if (this.annotations.length > 0) {
                    this.applyHighlights();
                }

                // Render annotation list in sidebar and update stats
                this.renderAnnotations();
                this.updateStats();

                // Render persona panel (shows Generate Persona button if identity annotations exist)
                this.renderPersonaPanel();
            } else if (rawJd) {
                // No annotations data but have raw JD - show it
                this.showRawJd(rawJd);
            } else {
                // No annotations data and no raw JD - show empty state
                this.showEmptyState();
            }

            this.updateSaveIndicator('saved');
        } catch (error) {
            console.error('Error loading annotations:', error);
            this.updateSaveIndicator('error');
            // Show empty state on error too
            this.showEmptyState();
        }
    }

    /**
     * Show raw JD with preserved whitespace formatting - ready for annotation
     */
    showRawJd(rawJd) {
        const loadingEl = document.getElementById(this.config.loadingId);
        const emptyEl = document.getElementById(this.config.emptyId);
        const contentEl = document.getElementById(this.config.contentId);

        if (loadingEl) loadingEl.classList.add('hidden');
        if (emptyEl) emptyEl.classList.add('hidden');

        // Safety check: ensure rawJd is a string
        if (typeof rawJd !== 'string') {
            console.error('showRawJd called with non-string:', typeof rawJd);
            this.showEmptyState();
            return;
        }

        if (contentEl) {
            // Convert plain text to HTML with preserved whitespace
            // Use CSS white-space: pre-wrap to preserve formatting without <br> tags
            // This ensures clean text selection for annotations
            const escapedJd = rawJd
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;');

            contentEl.innerHTML = `
                <div class="raw-jd-content p-4 text-sm text-gray-700 leading-relaxed select-text cursor-text" style="white-space: pre-wrap; word-wrap: break-word;">
                    <div class="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 text-xs select-none">
                        <strong>Ready to annotate!</strong> Select any text below to add annotations. Use the quick-add buttons above or click "Structure JD" to organize into sections.
                    </div>
                    <div class="jd-text-content">${escapedJd}</div>
                </div>
            `;
            contentEl.classList.remove('hidden');
        }
    }

    /**
     * Show empty state (hides loading, shows empty message)
     */
    showEmptyState() {
        const loadingEl = document.getElementById(this.config.loadingId);
        const emptyEl = document.getElementById(this.config.emptyId);
        const contentEl = document.getElementById(this.config.contentId);

        if (loadingEl) loadingEl.classList.add('hidden');
        if (contentEl) contentEl.classList.add('hidden');
        if (emptyEl) emptyEl.classList.remove('hidden');
    }

    /**
     * Load STAR stories for linking
     */
    async loadStarStories() {
        try {
            // Try to get STAR stories from the job's selected_stars field
            const response = await fetch(`/api/jobs/${this.jobId}`);
            if (response.ok) {
                const data = await response.json();
                const job = data.job || data;

                // Get all_stars or selected_stars
                this.starStories = job.all_stars || job.selected_stars || [];

                // If no stars, try to extract from meta-prompt or other sources
                if (this.starStories.length === 0 && job.star_to_pain_mapping) {
                    // Extract star IDs from mapping
                    const starIds = new Set();
                    Object.values(job.star_to_pain_mapping || {}).forEach(ids => {
                        ids.forEach(id => starIds.add(id));
                    });
                    this.starStories = Array.from(starIds).map(id => ({ id, title: id }));
                }
            }
        } catch (error) {
            console.warn('Could not load STAR stories:', error);
        }

        // Populate STAR selector in popover
        this.renderStarSelector();
    }

    /**
     * Render STAR story checkboxes in popover
     */
    renderStarSelector() {
        const container = document.getElementById('popover-star-selector');
        if (!container) return;

        if (this.starStories.length === 0) {
            container.innerHTML = '<p class="text-xs text-gray-400 italic">No STAR stories available</p>';
            return;
        }

        container.innerHTML = this.starStories.map(star => `
            <label class="flex items-start gap-2 py-1 cursor-pointer hover:bg-gray-100 rounded px-1">
                <input type="checkbox"
                       class="star-checkbox mt-0.5 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                       value="${star.id}"
                       onchange="getActiveAnnotationManager()?.updatePopoverStars()">
                <span class="text-xs text-gray-700">${star.title || star.id}</span>
            </label>
        `).join('');
    }

    /**
     * Save annotations to API
     */
    async saveAnnotations() {
        this.updateSaveIndicator('saving');

        try {
            // Capture feedback for any auto-generated annotations before saving
            for (const annotation of this.annotations) {
                if (annotation.source === 'auto_generated' &&
                    annotation.original_values &&
                    !annotation.feedback_captured) {
                    // Fire and forget - don't block the save
                    this.captureAnnotationFeedback(annotation, 'save');
                }
            }

            const response = await fetch(`/api/jobs/${this.jobId}/jd-annotations`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    annotation_version: 1,
                    processed_jd_html: this.processedJdHtml,
                    annotations: this.annotations,
                    settings: this.settings
                })
            });

            if (!response.ok) {
                // Try to extract actual error message from response
                let errorMsg = 'Failed to save annotations';
                try {
                    const errorData = await response.json();
                    errorMsg = errorData?.error || errorMsg;
                } catch (e) { /* ignore json parse error */ }
                throw new Error(errorMsg);
            }

            this.updateSaveIndicator('saved');
            console.log('Annotations saved successfully');

            // Show save pulse animation on the last edited annotation
            this.showSavePulseAnimation();

            // Dispatch event to update JD badge in job rows (turns green when annotations exist)
            window.dispatchEvent(new CustomEvent('annotations:updated', {
                detail: {
                    jobId: this.jobId,
                    hasAnnotations: this.annotations.length > 0,
                    annotationCount: this.annotations.length
                }
            }));
        } catch (error) {
            console.error('Error saving annotations:', error);
            this.updateSaveIndicator('error');
        }
    }

    /**
     * Show save success pulse animation on the last edited annotation highlight.
     * Adds a brief green shimmer effect to indicate successful save.
     */
    showSavePulseAnimation() {
        if (!this._lastEditedAnnotationId) return;

        const highlightEl = document.querySelector(
            `.annotation-highlight[data-annotation-id="${this._lastEditedAnnotationId}"]`
        );

        if (highlightEl) {
            // Add the pulse class
            highlightEl.classList.add('save-pulse');

            // Remove the class after animation completes (1 second)
            setTimeout(() => {
                highlightEl.classList.remove('save-pulse');
            }, 1000);
        }

        // Clear the tracked annotation ID
        this._lastEditedAnnotationId = null;
    }

    /**
     * Schedule auto-save with debounce
     */
    scheduleSave() {
        if (this.saveTimeout) {
            clearTimeout(this.saveTimeout);
        }
        this.updateSaveIndicator('unsaved');
        this.saveTimeout = setTimeout(() => this.saveAnnotations(), AUTOSAVE_DELAY);
    }

    /**
     * Set up event listeners
     */
    setupEventListeners() {
        const jdViewer = document.getElementById(this.config.contentId);
        if (jdViewer) {
            // Track state for smart selection:
            // - First click: select sentence
            // - Subsequent clicks: toggle popover
            // - Right-click: clear selection, enable manual selection mode
            this.smartSelectionState = {
                hasSentenceSelected: false,
                lastSelectedSentence: null
            };

            // Left click handler
            jdViewer.addEventListener('click', (e) => {
                // Skip if clicking on existing annotation highlights
                if (e.target.closest('.annotation-highlight')) return;

                const popover = document.getElementById('annotation-popover');
                const isPopoverVisible = popover && !popover.classList.contains('hidden');
                const selection = window.getSelection();

                // Check if click is within current selection
                const clickedInsideSelection = this.isClickInsideSelection(e, selection);

                // If we already have a sentence selected AND clicked inside it
                if (this.smartSelectionState.hasSentenceSelected && clickedInsideSelection) {
                    // Toggle popover visibility for SAME selection
                    if (isPopoverVisible) {
                        hideAnnotationPopover({ save: true });
                    } else {
                        // Re-show popover with the same selection
                        if (selection.rangeCount > 0) {
                            const range = selection.getRangeAt(0);
                            const rect = range.getBoundingClientRect();
                            const selectedText = selection.toString().trim();
                            if (selectedText.length >= 3) {
                                this.showAnnotationPopover(rect, selectedText);
                            }
                        }
                    }
                    return;
                }

                // Click OUTSIDE current selection OR no selection yet
                // -> Reset state and select new sentence
                this.smartSelectionState.hasSentenceSelected = false;
                this.smartSelectionState.lastSelectedSentence = null;
                hideAnnotationPopover({ save: true });

                // Select the sentence at the new click location
                this.handleSmartSentenceClick(e);
            });

            // Right-click handler - reset to manual selection mode
            jdViewer.addEventListener('contextmenu', (e) => {
                // Skip if clicking on existing annotation highlights
                if (e.target.closest('.annotation-highlight')) return;

                // Clear selection and reset state
                window.getSelection().removeAllRanges();
                this.smartSelectionState.hasSentenceSelected = false;
                this.smartSelectionState.lastSelectedSentence = null;
                hideAnnotationPopover({ save: false });

                // Don't prevent default - allow normal context menu
                // The user can now manually select text
            });

            // Also handle manual drag selection
            let mouseDownPos = null;
            let isDragging = false;

            jdViewer.addEventListener('mousedown', (e) => {
                if (e.target.closest('.annotation-highlight')) return;
                if (e.button !== 0) return; // Only track left mouse button

                mouseDownPos = { x: e.clientX, y: e.clientY };
                isDragging = false;
            });

            jdViewer.addEventListener('mousemove', (e) => {
                if (mouseDownPos) {
                    const dx = Math.abs(e.clientX - mouseDownPos.x);
                    const dy = Math.abs(e.clientY - mouseDownPos.y);
                    if (dx > 5 || dy > 5) {
                        isDragging = true;
                        // User is manually selecting - reset smart selection state
                        this.smartSelectionState.hasSentenceSelected = false;
                    }
                }
            });

            jdViewer.addEventListener('mouseup', (e) => {
                // Handle click on existing annotation - open for editing
                const highlightEl = e.target.closest('.annotation-highlight');
                if (highlightEl) {
                    mouseDownPos = null;
                    isDragging = false;
                    const annotationId = highlightEl.dataset.annotationId;
                    if (annotationId) {
                        this.editAnnotationFromHighlight(annotationId, highlightEl);
                    }
                    return;
                }

                // If user dragged to select text manually, use that selection
                if (isDragging) {
                    const selection = window.getSelection();
                    const selectedText = selection.toString().trim();
                    if (selectedText.length >= 3) {
                        this.handleTextSelection(e);
                        this.smartSelectionState.hasSentenceSelected = true;
                        this.smartSelectionState.lastSelectedSentence = selectedText;
                    }
                }

                mouseDownPos = null;
                isDragging = false;
            });
        }

        // Store reference for cleanup
        this._keydownHandler = (e) => {
            if (this._destroyed) return;
            if (e.key === 'Escape') {
                hideAnnotationPopover({ save: false, clearSelection: true });
                // Also clear smart selection state
                if (this.smartSelectionState) {
                    this.smartSelectionState.hasSentenceSelected = false;
                    window.getSelection().removeAllRanges();
                }
            }
        };
        document.addEventListener('keydown', this._keydownHandler);

        // Click outside popover to close (but not clear selection)
        this._mousedownHandler = (e) => {
            if (this._destroyed) return;
            const popover = document.getElementById(this.config.popoverId);
            if (!popover || popover.classList.contains('hidden')) return;

            // If clicking inside the popover, don't close
            if (popover.contains(e.target)) return;

            // If clicking on an annotation highlight, let the click handler manage it
            if (e.target.closest('.annotation-highlight')) return;

            // If clicking inside JD viewer, let the viewer handlers manage it
            const jdViewerEl = document.getElementById(this.config.contentId);
            if (jdViewerEl && jdViewerEl.contains(e.target)) return;

            // Close popover for clicks outside - auto-save if valid
            hideAnnotationPopover({ save: true });
        };
        document.addEventListener('mousedown', this._mousedownHandler);
    }

    /**
     * Check if a click event occurred inside the current text selection
     * @param {MouseEvent} event - The click event
     * @param {Selection} selection - The window selection object
     * @returns {boolean} True if click is inside the selection's bounding rect
     */
    isClickInsideSelection(event, selection) {
        if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
            return false;
        }

        const range = selection.getRangeAt(0);
        const rect = range.getBoundingClientRect();

        // Add small padding for easier clicking (5px)
        const padding = 5;
        return (
            event.clientX >= rect.left - padding &&
            event.clientX <= rect.right + padding &&
            event.clientY >= rect.top - padding &&
            event.clientY <= rect.bottom + padding
        );
    }

    /**
     * Handle smart sentence selection on click
     * First click: selects the complete sentence containing the click point
     */
    handleSmartSentenceClick(event) {
        console.log('[SmartSelect] Click detected at', event.clientX, event.clientY);

        // Get the text node at click position - cross-browser support
        let textNode, clickOffset;

        if (document.caretRangeFromPoint) {
            // Chrome, Safari, Edge
            const range = document.caretRangeFromPoint(event.clientX, event.clientY);
            if (!range || !range.startContainer) {
                console.log('[SmartSelect] No range or startContainer found');
                return;
            }
            textNode = range.startContainer;
            clickOffset = range.startOffset;
        } else if (document.caretPositionFromPoint) {
            // Firefox
            const pos = document.caretPositionFromPoint(event.clientX, event.clientY);
            if (!pos || !pos.offsetNode) {
                console.log('[SmartSelect] No caret position found (Firefox)');
                return;
            }
            textNode = pos.offsetNode;
            clickOffset = pos.offset;
        } else {
            console.log('[SmartSelect] Browser does not support caret position APIs');
            return;
        }

        console.log('[SmartSelect] Text node:', textNode, 'nodeType:', textNode.nodeType);

        // Handle both text nodes and element nodes (when clicking on styled text)
        if (textNode.nodeType !== Node.TEXT_NODE) {
            console.log('[SmartSelect] Not a text node, using TreeWalker');
            // If we clicked on an element, find the first text node inside it
            const walker = document.createTreeWalker(
                textNode,
                NodeFilter.SHOW_TEXT,
                null,
                false
            );
            textNode = walker.nextNode();
            if (!textNode) {
                console.log('[SmartSelect] TreeWalker found no text node');
                return;
            }
            clickOffset = 0; // Start from beginning of found text node
            console.log('[SmartSelect] TreeWalker found text node:', textNode.textContent.substring(0, 50));
        }

        const fullText = textNode.textContent;
        console.log('[SmartSelect] Full text:', fullText.substring(0, 100), '... offset:', clickOffset);

        // Find sentence boundaries
        const sentenceBounds = this.findSentenceBounds(fullText, clickOffset);
        if (!sentenceBounds) {
            console.log('[SmartSelect] No sentence bounds found');
            return;
        }
        console.log('[SmartSelect] Sentence bounds:', sentenceBounds);

        // Extract the sentence
        const sentence = fullText.substring(sentenceBounds.start, sentenceBounds.end).trim();
        console.log('[SmartSelect] Extracted sentence:', sentence.substring(0, 80), '... length:', sentence.length);

        // Skip if too short
        if (sentence.length < 5) {
            console.log('[SmartSelect] Sentence too short, skipping');
            return;
        }

        // Create a range for the sentence and select it
        const sentenceRange = document.createRange();
        sentenceRange.setStart(textNode, sentenceBounds.start);
        sentenceRange.setEnd(textNode, sentenceBounds.end);

        // Select the sentence visually
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(sentenceRange);

        // Update smart selection state
        this.smartSelectionState.hasSentenceSelected = true;
        this.smartSelectionState.lastSelectedSentence = sentence;

        // Auto-save immediately with optimistic defaults (no popover)
        console.log('[SmartSelect] Auto-saving annotation for sentence');
        this.autoSaveAnnotation(sentence);
    }

    /**
     * Find sentence boundaries around a position in text
     * Returns { start, end } indices or null if not found
     */
    findSentenceBounds(text, position) {
        if (!text || position < 0 || position > text.length) return null;

        // Sentence terminators: . ! ? and also consider line breaks as boundaries
        const sentenceEndPattern = /[.!?](?:\s|$)|[\n\r]+/g;

        // Find the start of the sentence (look backward)
        let start = 0;
        let match;
        sentenceEndPattern.lastIndex = 0;

        while ((match = sentenceEndPattern.exec(text)) !== null) {
            if (match.index >= position) break;
            start = match.index + match[0].length;
        }

        // Trim leading whitespace
        while (start < position && /\s/.test(text[start])) {
            start++;
        }

        // Find the end of the sentence (look forward)
        sentenceEndPattern.lastIndex = position;
        match = sentenceEndPattern.exec(text);

        let end;
        if (match) {
            end = match.index + 1;
            if (/^[\n\r\s]+$/.test(match[0])) {
                end = match.index;
            }
        } else {
            end = text.length;
        }

        // Trim trailing whitespace
        while (end > start && /\s/.test(text[end - 1])) {
            end--;
        }

        if (end <= start) return null;

        return { start, end };
    }

    /**
     * Handle text selection in JD viewer
     * Auto-saves with optimistic defaults (no popover)
     */
    handleTextSelection(event) {
        const selection = window.getSelection();
        const selectedText = selection.toString().trim();

        if (selectedText.length < 3) {
            return; // Ignore very short selections
        }

        // Auto-save immediately with optimistic defaults (no popover)
        console.log('[TextSelection] Auto-saving annotation for selection');
        this.autoSaveAnnotation(selectedText);
    }

    /**
     * Show annotation popover at position
     */
    showAnnotationPopover(rect, selectedText, editingAnnotation = null) {
        const popover = document.getElementById(this.config.popoverId);
        if (!popover) return;

        // Update header text based on mode
        const titleEl = document.getElementById('popover-title');
        if (titleEl) {
            titleEl.textContent = editingAnnotation ? 'Edit Annotation' : 'Create Annotation';
        }

        // Update save button text
        const saveBtn = document.getElementById('popover-save-btn');
        if (saveBtn) {
            saveBtn.textContent = editingAnnotation ? 'Update Annotation' : 'Add Annotation';
        }

        // Show/hide delete button based on edit mode
        const deleteBtn = document.getElementById('popover-delete-btn');
        if (deleteBtn) {
            if (editingAnnotation) {
                deleteBtn.classList.remove('hidden');
            } else {
                deleteBtn.classList.add('hidden');
            }
        }

        // Update selected text display (textarea uses .value instead of .textContent)
        const textEl = document.getElementById('popover-selected-text');
        if (textEl) {
            textEl.value = selectedText;
            // Add input handler to sync edits back to popoverState
            textEl.oninput = () => {
                this.popoverState.selectedText = textEl.value.trim();
            };
        }

        // Reset form state first (this clears editingAnnotationId)
        this.resetPopoverForm();

        // Store editing state AFTER resetPopoverForm() to avoid being cleared
        // This is critical: resetPopoverForm() sets editingAnnotationId = null
        this.editingAnnotationId = editingAnnotation?.id || null;

        // Auto-select defaults for new annotations (smoother UX)
        if (!editingAnnotation) {
            this.setPopoverRelevance('core_strength');
            this.setPopoverRequirement('must_have');
        }

        // If editing, populate with existing values (overrides defaults)
        if (editingAnnotation) {
            this.populatePopoverWithAnnotation(editingAnnotation);
        }

        // Position popover - account for panel boundaries
        const panel = document.getElementById(this.config.panelId);
        const panelRect = panel ? panel.getBoundingClientRect() : { left: 0, right: window.innerWidth, top: 0, bottom: window.innerHeight };

        const popoverWidth = 320;
        // Force layout to get accurate height
        popover.style.visibility = 'hidden';
        popover.classList.remove('hidden');
        const popoverHeight = popover.offsetHeight || 500;
        popover.classList.add('hidden');
        popover.style.visibility = '';

        // Calculate position relative to viewport
        let left = rect.left + (rect.width / 2) - (popoverWidth / 2);
        let top = rect.bottom + 10;

        // Keep within panel bounds (prefer inside panel if open)
        const padding = 10;
        const rightBound = panel ? panelRect.right : window.innerWidth;
        const leftBound = panel ? panelRect.left : 0;

        // Constrain horizontally
        if (left < leftBound + padding) {
            left = leftBound + padding;
        }
        if (left + popoverWidth > rightBound - padding) {
            left = rightBound - popoverWidth - padding;
        }

        // Constrain vertically - prefer below, fall back to above
        if (top + popoverHeight > window.innerHeight - padding) {
            // Try positioning above the selection
            const aboveTop = rect.top - popoverHeight - 10;
            if (aboveTop > padding) {
                top = aboveTop;
            } else {
                // Center vertically if neither above nor below works
                top = Math.max(padding, (window.innerHeight - popoverHeight) / 2);
            }
        }

        // Final safety clamp
        top = Math.max(padding, Math.min(top, window.innerHeight - popoverHeight - padding));
        left = Math.max(padding, Math.min(left, window.innerWidth - popoverWidth - padding));

        popover.style.left = `${left}px`;
        popover.style.top = `${top}px`;
        popover.classList.remove('hidden');
    }

    /**
     * Populate popover with existing annotation data for editing.
     *
     * IMPORTANT: Sets _isPopulating flag to prevent checkAutoDeleteAnnotation()
     * from being triggered during population. This flag is checked in each
     * setPopover* method to avoid accidental deletion when loading existing
     * annotation values.
     */
    populatePopoverWithAnnotation(annotation) {
        // Set flag to prevent checkAutoDeleteAnnotation during population
        this._isPopulating = true;

        // Set relevance
        if (annotation.relevance) {
            this.setPopoverRelevance(annotation.relevance);
        }

        // Set requirement type
        if (annotation.requirement_type) {
            this.setPopoverRequirement(annotation.requirement_type);
        }

        // Set passion level
        if (annotation.passion) {
            this.setPopoverPassion(annotation.passion);
        }

        // Set identity level
        if (annotation.identity) {
            this.setPopoverIdentity(annotation.identity);
        }

        // Clear populating flag
        this._isPopulating = false;

        // Set STAR stories
        if (annotation.star_ids && annotation.star_ids.length > 0) {
            annotation.star_ids.forEach(starId => {
                const checkbox = document.querySelector(`.star-checkbox[value="${starId}"]`);
                if (checkbox) checkbox.checked = true;
            });
            this.popoverState.starIds = annotation.star_ids;
        }

        // Set reframe note and auto-expand if has content
        const reframeEl = document.getElementById('popover-reframe-note');
        if (reframeEl && annotation.reframe_note) {
            reframeEl.value = annotation.reframe_note;
            this.expandPopoverField('reframe');
        }

        // Set strategic note and auto-expand if has content
        const strategicEl = document.getElementById('popover-strategic-note');
        if (strategicEl && annotation.strategic_note) {
            strategicEl.value = annotation.strategic_note;
            this.expandPopoverField('strategic');
        }

        // Set keywords and auto-expand if has content
        const keywordsEl = document.getElementById('popover-keywords');
        if (keywordsEl && annotation.suggested_keywords && annotation.suggested_keywords.length > 0) {
            keywordsEl.value = annotation.suggested_keywords.join(', ');
            this.expandPopoverField('keywords');
        }

        // Show AI suggestion section for auto-generated annotations
        this.populateAISuggestionSection(annotation);

        // Store state (ensure all values are set after setPopover* calls)
        this.popoverState.selectedText = annotation.target?.text || '';
        this.popoverState.reframeNote = annotation.reframe_note || '';
        this.popoverState.strategicNote = annotation.strategic_note || '';
        this.popoverState.keywords = annotation.suggested_keywords?.join(', ') || '';
    }

    /**
     * Populate the AI suggestion section for auto-generated annotations
     * Shows confidence badge and match explanation in the popover
     * @param {Object} annotation - The annotation object
     */
    populateAISuggestionSection(annotation) {
        const container = document.getElementById('popover-ai-suggestion-container');
        const confidenceBadge = document.getElementById('popover-confidence-badge');
        const matchExplanation = document.getElementById('popover-match-explanation');

        if (!container) return;

        // Only show for auto-generated annotations
        if (annotation.source !== 'auto_generated' || !annotation.original_values?.confidence) {
            container.classList.add('hidden');
            return;
        }

        // Show the container
        container.classList.remove('hidden');

        // Get confidence data
        const conf = annotation.original_values.confidence;
        const pct = Math.round(conf * 100);

        // Set confidence badge with appropriate color
        if (confidenceBadge) {
            let colorClass;
            if (pct >= 85) {
                colorClass = 'confidence-high bg-green-100 text-green-700 border-green-200';
            } else if (pct >= 70) {
                colorClass = 'confidence-medium bg-amber-100 text-amber-700 border-amber-200';
            } else {
                colorClass = 'confidence-low bg-gray-100 text-gray-600 border-gray-200';
            }
            confidenceBadge.className = `confidence-badge px-1.5 py-0.5 rounded text-xs font-medium border ${colorClass}`;
            confidenceBadge.innerHTML = `${pct}% confidence <span class="ai-indicator">&#10024;</span>`;
        }

        // Set match explanation
        if (matchExplanation) {
            const explanation = this.getMatchExplanation(annotation);
            matchExplanation.textContent = explanation || '';
        }

        // Auto-expand the section since it's relevant
        this.expandPopoverField('ai-suggestion');
    }

    /**
     * Expand a collapsible popover field
     */
    expandPopoverField(field) {
        const content = document.getElementById(`${field}-content`);
        const chevron = document.getElementById(`${field}-chevron`);

        if (content) {
            content.classList.remove('hidden');
        }
        if (chevron) {
            chevron.style.transform = 'rotate(90deg)';
        }
    }

    /**
     * Collapse a collapsible popover field
     */
    collapsePopoverField(field) {
        const content = document.getElementById(`${field}-content`);
        const chevron = document.getElementById(`${field}-chevron`);

        if (content) {
            content.classList.add('hidden');
        }
        if (chevron) {
            chevron.style.transform = 'rotate(0deg)';
        }
    }

    /**
     * Reset popover form to default state
     */
    resetPopoverForm() {
        // Clear button selections for all dimension types
        document.querySelectorAll('.relevance-btn').forEach(btn => {
            btn.classList.remove('ring-2', 'ring-indigo-500');
        });
        document.querySelectorAll('.requirement-btn').forEach(btn => {
            btn.classList.remove('ring-2', 'ring-indigo-500');
        });
        document.querySelectorAll('.passion-btn').forEach(btn => {
            btn.classList.remove('ring-2', 'ring-indigo-500');
        });
        document.querySelectorAll('.identity-btn').forEach(btn => {
            btn.classList.remove('ring-2', 'ring-indigo-500');
        });

        // Clear checkboxes
        document.querySelectorAll('.star-checkbox').forEach(cb => {
            cb.checked = false;
        });

        // Clear inputs
        const reframeEl = document.getElementById('popover-reframe-note');
        const keywordsEl = document.getElementById('popover-keywords');
        const strategicEl = document.getElementById('popover-strategic-note');
        if (reframeEl) reframeEl.value = '';
        if (keywordsEl) keywordsEl.value = '';
        if (strategicEl) strategicEl.value = '';

        // Collapse all expandable fields
        this.collapsePopoverField('reframe');
        this.collapsePopoverField('strategic');
        this.collapsePopoverField('keywords');
        this.collapsePopoverField('ai-suggestion');

        // Hide AI suggestion section (only shown for auto-generated annotations)
        const aiSuggestionContainer = document.getElementById('popover-ai-suggestion-container');
        if (aiSuggestionContainer) aiSuggestionContainer.classList.add('hidden');

        // Reset editing state
        this.editingAnnotationId = null;

        // CRITICAL: Reset popoverState to avoid stale values from previous edit sessions.
        // This fixes the bug where editing annotation B after annotation A would
        // trigger auto-delete because the toggle logic detected the same relevance
        // value as "selected" and toggled it off.
        this.popoverState = {
            selectedText: '',
            selectedRange: null,
            relevance: null,
            requirement: null,
            passion: null,
            identity: null,
            starIds: [],
            reframeNote: '',
            keywords: '',
            // Reset explicit selection flags - these track user interactions
            hasExplicitRelevance: false,
            hasExplicitRequirement: false,
            hasExplicitPassion: false,
            hasExplicitIdentity: false
        };

        // Disable save button
        const saveBtn = document.getElementById('popover-save-btn');
        if (saveBtn) saveBtn.disabled = true;

        // Hide delete button
        const deleteBtn = document.getElementById('popover-delete-btn');
        if (deleteBtn) deleteBtn.classList.add('hidden');
    }

    /**
     * Set relevance in popover (with toggle support)
     * Clicking the same value toggles it off
     */
    setPopoverRelevance(relevance) {
        // Toggle off if clicking the same value
        if (this.popoverState.relevance === relevance && this.popoverState.hasExplicitRelevance) {
            this.popoverState.relevance = null;
            this.popoverState.hasExplicitRelevance = false;
        } else {
            this.popoverState.relevance = relevance;
            this.popoverState.hasExplicitRelevance = true;
        }

        // Update button states
        document.querySelectorAll('.relevance-btn').forEach(btn => {
            if (btn.dataset.relevance === this.popoverState.relevance) {
                btn.classList.add('ring-2', 'ring-indigo-500');
            } else {
                btn.classList.remove('ring-2', 'ring-indigo-500');
            }
        });

        this.updatePopoverSaveButton();
        this.checkAutoDeleteAnnotation();
    }

    /**
     * Set requirement type in popover (with toggle support)
     * Clicking the same value toggles it off
     */
    setPopoverRequirement(requirement) {
        // Toggle off if clicking the same value
        if (this.popoverState.requirement === requirement && this.popoverState.hasExplicitRequirement) {
            this.popoverState.requirement = null;
            this.popoverState.hasExplicitRequirement = false;
        } else {
            this.popoverState.requirement = requirement;
            this.popoverState.hasExplicitRequirement = true;
        }

        // Update button states
        document.querySelectorAll('.requirement-btn').forEach(btn => {
            if (btn.dataset.requirement === this.popoverState.requirement) {
                btn.classList.add('ring-2', 'ring-indigo-500');
            } else {
                btn.classList.remove('ring-2', 'ring-indigo-500');
            }
        });

        this.updatePopoverSaveButton();
        this.checkAutoDeleteAnnotation();
    }

    /**
     * Set passion level in popover (with toggle support)
     * Clicking the same value toggles it off
     */
    setPopoverPassion(passion) {
        // Toggle off if clicking the same value
        if (this.popoverState.passion === passion && this.popoverState.hasExplicitPassion) {
            this.popoverState.passion = null;
            this.popoverState.hasExplicitPassion = false;
        } else {
            this.popoverState.passion = passion;
            this.popoverState.hasExplicitPassion = true;
        }

        // Update button states
        document.querySelectorAll('.passion-btn').forEach(btn => {
            if (btn.dataset.passion === this.popoverState.passion) {
                btn.classList.add('ring-2', 'ring-indigo-500');
            } else {
                btn.classList.remove('ring-2', 'ring-indigo-500');
            }
        });

        this.updatePopoverSaveButton();
        this.checkAutoDeleteAnnotation();
    }

    /**
     * Set identity level in popover (with toggle support)
     * Clicking the same value toggles it off
     */
    setPopoverIdentity(identity) {
        // Toggle off if clicking the same value
        if (this.popoverState.identity === identity && this.popoverState.hasExplicitIdentity) {
            this.popoverState.identity = null;
            this.popoverState.hasExplicitIdentity = false;
        } else {
            this.popoverState.identity = identity;
            this.popoverState.hasExplicitIdentity = true;
        }

        // Update button states
        document.querySelectorAll('.identity-btn').forEach(btn => {
            if (btn.dataset.identity === this.popoverState.identity) {
                btn.classList.add('ring-2', 'ring-indigo-500');
            } else {
                btn.classList.remove('ring-2', 'ring-indigo-500');
            }
        });

        this.updatePopoverSaveButton();
        this.checkAutoDeleteAnnotation();
    }

    /**
     * Check if all dimensions are unselected and auto-delete the annotation if editing.
     * Called after each dimension toggle to clean up annotations with no dimensions.
     *
     * IMPORTANT: Skipped during population (_isPopulating flag) to prevent
     * accidental deletion when loading existing annotation values.
     */
    checkAutoDeleteAnnotation() {
        // Skip during population - we're just loading existing values
        if (this._isPopulating) {
            return;
        }

        // Only auto-delete when editing an existing annotation
        if (!this.editingAnnotationId) {
            return;
        }

        // Check if all dimensions are now unselected
        const hasAnySelection =
            this.popoverState.hasExplicitRelevance ||
            this.popoverState.hasExplicitRequirement ||
            this.popoverState.hasExplicitPassion ||
            this.popoverState.hasExplicitIdentity;

        if (!hasAnySelection) {
            // Auto-delete the annotation (no confirmation dialog per GAP-105)
            this.deleteAnnotation(this.editingAnnotationId);

            // Hide the popover without saving
            hideAnnotationPopover({ save: false });
        }
    }

    /**
     * Update selected STAR stories in popover
     */
    updatePopoverStars() {
        const checkboxes = document.querySelectorAll('.star-checkbox:checked');
        this.popoverState.starIds = Array.from(checkboxes).map(cb => cb.value);
        this.updatePopoverSaveButton();
    }

    /**
     * Check if the current popover state can be saved.
     * Requires: (1) text with at least 3 chars, (2) any explicit selection made.
     * @returns {boolean} True if annotation can be saved
     */
    canSaveAnnotation() {
        const textEl = document.getElementById('popover-selected-text');
        const hasText = textEl?.value?.trim().length >= 3;

        const hasAnyExplicitSelection =
            this.popoverState.hasExplicitRelevance ||
            this.popoverState.hasExplicitRequirement ||
            this.popoverState.hasExplicitPassion ||
            this.popoverState.hasExplicitIdentity;

        return hasText && hasAnyExplicitSelection;
    }

    /**
     * Update save button enabled state
     *
     * Uses OR logic: enable when ANY dimension has been explicitly selected.
     * The dimensions are mutually independent - user can annotate based on
     * relevance only, passion only, identity only, or any combination.
     */
    updatePopoverSaveButton() {
        const saveBtn = document.getElementById('popover-save-btn');
        if (saveBtn) {
            // Enable if ANY dimension has been explicitly selected (OR logic)
            const hasAnyExplicitSelection =
                this.popoverState.hasExplicitRelevance ||
                this.popoverState.hasExplicitRequirement ||
                this.popoverState.hasExplicitPassion ||
                this.popoverState.hasExplicitIdentity;

            saveBtn.disabled = !hasAnyExplicitSelection;
        }
    }

    /**
     * Create or update annotation from popover state
     */
    createAnnotationFromPopover() {
        const reframeEl = document.getElementById('popover-reframe-note');
        const keywordsEl = document.getElementById('popover-keywords');
        const strategicEl = document.getElementById('popover-strategic-note');
        const textEl = document.getElementById('popover-selected-text');

        // Read text directly from textarea (more reliable than oninput handler)
        const editedText = textEl?.value?.trim() || this.popoverState.selectedText;
        // Keep original text for highlighting (if user edited, original is different)
        const originalText = this.popoverState.originalText || this.popoverState.selectedText;

        const isEditing = !!this.editingAnnotationId;
        console.log('[createAnnotationFromPopover] isEditing:', isEditing, 'editingAnnotationId:', this.editingAnnotationId);

        if (isEditing) {
            // Update existing annotation
            const index = this.annotations.findIndex(a => a.id === this.editingAnnotationId);
            if (index !== -1) {
                // Record previous state for undo
                const previousState = this.annotations[index];

                // Preserve original_text for highlighting if it exists, otherwise use current target.text
                const existingOriginalText = this.annotations[index].target?.original_text ||
                                              this.annotations[index].target?.text;
                const updatedAnnotation = {
                    ...this.annotations[index],
                    target: {
                        ...this.annotations[index].target,
                        text: editedText,  // User's edited text for display
                        original_text: existingOriginalText,  // Original JD text for highlighting
                        char_end: editedText.length
                    },
                    relevance: this.popoverState.relevance,
                    requirement_type: this.popoverState.requirement || 'neutral',
                    passion: this.popoverState.passion || 'neutral',
                    identity: this.popoverState.identity || 'peripheral',
                    star_ids: this.popoverState.starIds,
                    reframe_note: reframeEl?.value || '',
                    strategic_note: strategicEl?.value || '',
                    suggested_keywords: keywordsEl?.value.split(',').map(k => k.trim()).filter(k => k) || [],
                    updated_at: new Date().toISOString()
                };

                // Record for undo
                this.undoManager.push({
                    type: 'update',
                    annotation: updatedAnnotation,
                    previousState: previousState
                });

                this.annotations[index] = updatedAnnotation;
                console.log('Updated annotation:', this.annotations[index]);
            }
        } else {
            // Create new annotation
            const annotation = {
                id: this.generateId(),
                target: {
                    text: editedText,  // User's edited text for display
                    original_text: originalText,  // Original JD text for highlighting
                    section: this.getSelectedSection(),
                    char_start: 0, // Would need more complex DOM tracking
                    char_end: editedText.length
                },
                annotation_type: 'skill_match',
                relevance: this.popoverState.relevance,
                requirement_type: this.popoverState.requirement || 'neutral',
                passion: this.popoverState.passion || 'neutral',
                identity: this.popoverState.identity || 'peripheral',
                star_ids: this.popoverState.starIds,
                reframe_note: reframeEl?.value || '',
                strategic_note: strategicEl?.value || '',
                suggested_keywords: keywordsEl?.value.split(',').map(k => k.trim()).filter(k => k) || [],
                is_active: true,
                priority: 3,
                source: 'manual',
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString()
            };

            // Record for undo
            this.undoManager.push({
                type: 'add',
                annotation: annotation
            });

            // Add to annotations
            this.annotations.push(annotation);
            console.log('Created annotation:', annotation);
            console.log('[createAnnotationFromPopover] After push, this.annotations.length =', this.annotations.length);
        }

        // Re-render list and stats immediately
        console.log('[createAnnotationFromPopover] Calling renderAnnotations, this.annotations.length =', this.annotations.length);
        this.renderAnnotations();
        this.updateStats();

        // Apply highlights with slight delay to ensure DOM is stable after list re-render
        // This fixes color not updating when changing relevance (e.g., core -> medium)
        // Use force=true since we're saving changes that may affect highlight colors
        requestAnimationFrame(() => {
            this.applyHighlights({ force: true });
        });

        // Track the annotation ID for save pulse animation
        if (isEditing) {
            this._lastEditedAnnotationId = this.editingAnnotationId;
        } else {
            // For new annotations, get the ID of the just-added annotation
            const newAnnotation = this.annotations[this.annotations.length - 1];
            this._lastEditedAnnotationId = newAnnotation?.id || null;
        }

        // Schedule save
        this.scheduleSave();

        // Update undo/redo button states
        this.updateUndoRedoButtons();

        // Issue 3: Capture learning signal for manual annotations
        // Both new creations and edits represent positive user signals
        if (!isEditing) {
            // New annotation created via popover
            const newAnnotation = this.annotations[this.annotations.length - 1];
            if (newAnnotation?.source === 'manual') {
                this.captureManualAnnotationLearning(newAnnotation);
            }
        } else {
            // Edited annotation - capture updated values as positive signal
            const editedIndex = this.annotations.findIndex(a => a.id === this.editingAnnotationId);
            if (editedIndex !== -1) {
                const editedAnnotation = this.annotations[editedIndex];
                if (editedAnnotation?.source === 'manual') {
                    // Reset learning_captured to re-capture with new values
                    editedAnnotation.learning_captured = false;
                    this.captureManualAnnotationLearning(editedAnnotation);
                }
            }
        }

        // Show toast feedback
        if (typeof showToast === 'function') {
            showToast(isEditing ? 'Annotation updated' : 'Annotation saved', 'success');
        }

        // Hide popover and reset editing state
        this.editingAnnotationId = null;
        _hidePopover();
    }

    /**
     * Auto-save annotation immediately with optimistic defaults
     * Called on text selection - creates annotation and shows popover for editing
     * (Issue 2: Panel stays open on non-annotated text click)
     * @param {string} text - The selected text to annotate
     * @param {DOMRect} [selectionRect] - Optional rect for positioning popover
     */
    autoSaveAnnotation(text, selectionRect = null) {
        if (!text || text.length < 3) return;

        // Check if this text is already annotated
        const existingAnnotation = this.annotations.find(
            a => a.target?.text?.toLowerCase() === text.toLowerCase() ||
                 a.target?.original_text?.toLowerCase() === text.toLowerCase()
        );
        if (existingAnnotation) {
            // Already annotated - show edit mode instead
            if (typeof showToast === 'function') {
                showToast('Already annotated - tap highlight to edit', 'info');
            }
            window.getSelection().removeAllRanges();
            return;
        }

        // Create annotation with optimistic defaults (Issue 2: use specified defaults)
        const annotation = {
            id: this.generateId(),
            target: {
                text: text,
                original_text: text,
                section: this.getSelectedSection(),
                char_start: 0,
                char_end: text.length
            },
            annotation_type: 'skill_match',
            relevance: 'core_strength',  // Default per Issue 2
            requirement_type: 'must_have',  // Default per Issue 2
            passion: 'neutral',  // Default per Issue 2 (changed from 'enjoy')
            identity: 'peripheral',  // Default per Issue 2 (changed from 'strong_identity')
            star_ids: [],
            reframe_note: '',
            strategic_note: '',
            suggested_keywords: [],
            is_active: true,
            priority: 3,
            source: 'manual',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString()
        };

        // Record for undo
        this.undoManager.push({
            type: 'add',
            annotation: annotation
        });

        // Add to annotations
        this.annotations.push(annotation);
        console.log('[autoSaveAnnotation] Created annotation:', annotation.id);

        // Render and highlight (before showing popover so highlight exists)
        this.renderAnnotations();
        this.updateStats();

        // Apply highlights with slight delay to ensure DOM is stable
        // Use force=true since we just created a new annotation
        requestAnimationFrame(() => {
            this.applyHighlights({ force: true });

            // Issue 2: Show popover for the newly created annotation
            // Find the highlight element that was just created
            const highlightEl = document.querySelector(`.annotation-highlight[data-annotation-id="${annotation.id}"]`);
            if (highlightEl) {
                const rect = highlightEl.getBoundingClientRect();
                this.showAnnotationPopover(rect, text, annotation);
                this.scrollToAnnotation(annotation.id);
            } else if (selectionRect) {
                // Fallback: use selection rect if highlight not found
                this.showAnnotationPopover(selectionRect, text, annotation);
            }
        });

        // Track the annotation ID for save pulse animation
        this._lastEditedAnnotationId = annotation.id;

        // Schedule save to backend
        this.scheduleSave();

        // Update undo/redo button states
        this.updateUndoRedoButtons();

        // Issue 3: Capture learning signal from manual annotations
        this.captureManualAnnotationLearning(annotation);

        // Show toast feedback with truncated text
        const shortText = text.length > 30 ? text.substring(0, 30) + '...' : text;
        if (typeof showToast === 'function') {
            showToast(`Created - edit below`, 'success');
        }
    }

    /**
     * Generate unique ID
     */
    generateId() {
        return 'ann_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }

    /**
     * Get section from selection
     */
    getSelectedSection() {
        // Try to find parent section element
        const selection = window.getSelection();
        if (!selection.rangeCount) return 'unknown';

        let node = selection.anchorNode;
        while (node && node.nodeType !== Node.ELEMENT_NODE) {
            node = node.parentNode;
        }

        // Look for section data attribute
        while (node) {
            if (node.dataset?.section) {
                return node.dataset.section;
            }
            node = node.parentNode;
        }

        return 'unknown';
    }

    /**
     * Render annotations in list
     * @param {number} retryCount - Internal retry counter for deferred rendering
     */
    renderAnnotations(retryCount = 0) {
        const container = document.getElementById(this.config.listId);
        const emptyState = document.getElementById(this.config.listEmptyId);

        // DEBUG: Log render state with detailed info
        console.log('[renderAnnotations] Called:', {
            containerId: this.config.listId,
            containerFound: !!container,
            containerTagName: container?.tagName,
            containerParentId: container?.parentElement?.id,
            emptyStateFound: !!emptyState,
            annotationsCount: this.annotations.length,
            annotationIds: this.annotations.map(a => a.id?.slice(-8)),
            currentFilter: this.currentFilter,
            retryCount,
            callerStack: new Error().stack?.split('\n').slice(1, 4).join(' <- ')
        });

        if (!container) {
            // Container not found - might be a timing issue with HTMX/fetch content loading
            // Retry up to 3 times with increasing delays to handle async DOM updates
            const maxRetries = 3;
            if (retryCount < maxRetries) {
                const delay = (retryCount + 1) * 50; // 50ms, 100ms, 150ms
                setTimeout(() => this.renderAnnotations(retryCount + 1), delay);
                return;
            }
            // All retries exhausted - log error with diagnostic info
            console.error(`[AnnotationManager] renderAnnotations: Container not found with id="${this.config.listId}" after ${maxRetries} retries. Available IDs containing "annotation":`,
                [...document.querySelectorAll('[id*="annotation"]')].map(el => el.id).slice(0, 10));
            return;
        }

        // Filter annotations
        const filtered = this.getFilteredAnnotations();

        // DEBUG: Log filtered results
        console.log('[renderAnnotations] Filtered:', {
            filteredCount: filtered.length,
            annotations: filtered.map(a => ({ id: a.id, relevance: a.relevance }))
        });

        // Show/hide empty state
        if (emptyState) {
            emptyState.classList.toggle('hidden', filtered.length > 0);
        }

        // Render items
        const renderedHtml = filtered.map(ann => this.renderAnnotationItem(ann)).join('');
        container.innerHTML = renderedHtml;

        // Update count
        const countEl = document.getElementById(this.config.listCountId);
        if (countEl) countEl.textContent = filtered.length;

        // DEBUG: Verify render completed
        console.log('[renderAnnotations] Completed:', {
            renderedHtmlLength: renderedHtml.length,
            containerChildCount: container.children.length,
            countElValue: countEl?.textContent,
            emptyStateHidden: emptyState?.classList.contains('hidden')
        });

        // Update the review banner for pending suggestions
        this.updateReviewBanner();
    }

    /**
     * Get filtered annotations based on current filter
     */
    getFilteredAnnotations() {
        if (this.currentFilter === 'all') return this.annotations;

        return this.annotations.filter(ann => {
            switch (this.currentFilter) {
                // Relevance/Match Strength filters
                case 'core_strength':
                case 'extremely_relevant':
                case 'relevant':
                case 'tangential':
                case 'gap':
                    return ann.relevance === this.currentFilter;

                // Requirement Type filters
                case 'must_have':
                case 'nice_to_have':
                    return ann.requirement_type === this.currentFilter;

                // Passion Level filters
                case 'love_it':
                case 'enjoy':
                case 'neutral_passion':
                case 'tolerate':
                case 'avoid':
                    return ann.passion === this.currentFilter;

                // Identity Level filters
                case 'core_identity':
                case 'strong_identity':
                case 'developing':
                case 'peripheral':
                case 'not_identity':
                    return ann.identity === this.currentFilter;

                // Status filter
                case 'active':
                    return ann.is_active;

                default:
                    return true;
            }
        });
    }

    /**
     * Render single annotation item
     */
    renderAnnotationItem(annotation) {
        const colors = RELEVANCE_COLORS[annotation.relevance] || { bg: 'bg-gray-100', border: 'border-gray-300', text: 'text-gray-500' };
        const reqColors = REQUIREMENT_COLORS[annotation.requirement_type] || REQUIREMENT_COLORS.neutral;

        // Passion badge (only show for non-neutral)
        const passionBadge = this.getPassionBadge(annotation.passion);
        // Identity badge (only show for non-peripheral)
        const identityBadge = this.getIdentityBadge(annotation.identity);
        // Confidence badge (only for auto-generated annotations)
        const confidenceBadge = this.getConfidenceBadge(annotation);
        // Match explanation (only for auto-generated annotations)
        const matchExplanation = this.getMatchExplanation(annotation);

        // Relevance badge - only show if relevance is set (avoid showing "null")
        const relevanceBadge = annotation.relevance
            ? `<span class="px-1.5 py-0.5 rounded text-xs font-medium ${colors.bg} ${colors.text}">
                   ${this.formatRelevance(annotation.relevance)}
               </span>`
            : '';

        // Quick action buttons for AI suggestions
        // Since AI suggestions are now auto-approved (Issue 1: auto-apply UX),
        // we only show the reject/delete button - no accept button needed
        const isAutoGenerated = annotation.source === 'auto_generated';
        const quickActions = '';

        return `
            <div class="annotation-item p-3 border-b border-gray-100 hover:bg-gray-50 cursor-pointer transition ${!annotation.is_active ? 'opacity-50' : ''} ${isAutoGenerated ? 'border-l-2 border-l-purple-300' : ''}"
                 data-annotation-id="${annotation.id}"
                 onclick="getActiveAnnotationManager()?.selectAnnotation('${annotation.id}')">
                <div class="flex items-start justify-between gap-2">
                    <div class="flex-1 min-w-0">
                        <div class="flex items-center flex-wrap gap-1 mb-1">
                            ${relevanceBadge}
                            <span class="px-1.5 py-0.5 rounded text-xs font-medium ${reqColors.bg} ${reqColors.text}">
                                ${this.formatRequirement(annotation.requirement_type)}
                            </span>
                            ${confidenceBadge}
                            ${passionBadge}
                            ${identityBadge}
                        </div>
                        <p class="text-sm text-gray-800 line-clamp-2">${annotation.target?.text || ''}</p>
                        ${matchExplanation ? `<p class="text-xs text-gray-400 mt-1 match-explanation">${matchExplanation}</p>` : ''}
                        ${annotation.reframe_note ? `<p class="text-xs text-gray-500 mt-1 italic line-clamp-1">${annotation.reframe_note}</p>` : ''}
                    </div>
                    <div class="flex items-center gap-1">
                        ${quickActions}
                        <button onclick="event.stopPropagation(); getActiveAnnotationManager()?.toggleActive('${annotation.id}')"
                                class="p-1 rounded hover:bg-gray-200"
                                title="${annotation.is_active ? 'Deactivate' : 'Activate'}">
                            <svg class="w-4 h-4 ${annotation.is_active ? 'text-green-500' : 'text-gray-300'}" fill="currentColor" viewBox="0 0 20 20">
                                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
                            </svg>
                        </button>
                        <button onclick="event.stopPropagation(); getActiveAnnotationManager()?.deleteAnnotation('${annotation.id}')"
                                class="p-1 rounded hover:bg-red-100"
                                title="Delete">
                            <svg class="w-4 h-4 text-gray-400 hover:text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
                            </svg>
                        </button>
                    </div>
                </div>
            </div>
        `;
    }

    /**
     * Get passion badge HTML (only for notable passions)
     */
    getPassionBadge(passion) {
        const badges = {
            love_it: '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-pink-100 text-pink-700" title="Love it">🔥</span>',
            enjoy: '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-rose-50 text-rose-600" title="Enjoy">💜</span>',
            avoid: '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-stone-100 text-stone-600" title="Avoid">🚫</span>',
            tolerate: '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-amber-50 text-amber-600" title="Tolerate">😐</span>'
        };
        return badges[passion] || '';
    }

    /**
     * Get identity badge HTML (only for notable identities)
     */
    getIdentityBadge(identity) {
        const badges = {
            core_identity: '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-indigo-100 text-indigo-700" title="Core Identity">⭐</span>',
            strong_identity: '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-violet-50 text-violet-600" title="Strong Identity">💪</span>',
            developing: '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-sky-50 text-sky-600" title="Developing">📈</span>',
            not_identity: '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-zinc-100 text-zinc-600" title="Not Me">✗</span>'
        };
        return badges[identity] || '';
    }

    /**
     * Get confidence badge HTML for auto-generated annotations
     * Shows AI confidence percentage with color coding based on confidence level
     * @param {Object} annotation - The annotation object
     * @returns {string} HTML string for the confidence badge, or empty string if not applicable
     */
    getConfidenceBadge(annotation) {
        // Only show for auto-generated annotations
        if (annotation.source !== 'auto_generated') return '';

        // Get confidence from original_values (set during auto-generation)
        const conf = annotation.original_values?.confidence;
        if (!conf && conf !== 0) return '';

        // Calculate percentage
        const pct = Math.round(conf * 100);

        // Color coding based on confidence level
        // >= 85%: green (high confidence)
        // >= 70%: amber (medium confidence)
        // < 70%: gray (low confidence)
        let colorClass;
        if (pct >= 85) {
            colorClass = 'confidence-high bg-green-100 text-green-700 border-green-200';
        } else if (pct >= 70) {
            colorClass = 'confidence-medium bg-amber-100 text-amber-700 border-amber-200';
        } else {
            colorClass = 'confidence-low bg-gray-100 text-gray-600 border-gray-200';
        }

        return `<span class="confidence-badge px-1.5 py-0.5 rounded text-xs font-medium border ${colorClass}" title="AI confidence: ${pct}%">
            ${pct}% <span class="ai-indicator">&#10024;</span>
        </span>`;
    }

    /**
     * Get match explanation text for auto-generated annotations
     * Describes why the AI made this suggestion based on match_method and matched_keyword
     * @param {Object} annotation - The annotation object
     * @returns {string|null} Match explanation text, or null if not applicable
     */
    getMatchExplanation(annotation) {
        // Only show for auto-generated annotations
        if (annotation.source !== 'auto_generated') return null;

        const matchMethod = annotation.original_values?.match_method || 'semantic similarity';
        const matchedKeyword = annotation.original_values?.matched_keyword;

        // Format match method for display
        const methodLabels = {
            'sentence_embedding': 'sentence similarity',
            'keyword_match': 'keyword match',
            'skill_prior': 'skill prior',
            'semantic_similarity': 'semantic similarity',
            'exact_match': 'exact match'
        };
        const displayMethod = methodLabels[matchMethod] || matchMethod;

        if (matchedKeyword) {
            return `Matched: "${matchedKeyword}" (${displayMethod})`;
        }
        return `Matched via ${displayMethod}`;
    }

    /**
     * Format relevance for display
     */
    formatRelevance(relevance) {
        const labels = {
            core_strength: 'Core',
            extremely_relevant: 'Strong',
            relevant: 'Medium',
            tangential: 'Weak',
            gap: 'Gap'
        };
        return labels[relevance] || relevance;
    }

    /**
     * Format requirement for display
     */
    formatRequirement(requirement) {
        const labels = {
            must_have: 'Must-Have',
            nice_to_have: 'Nice-to-Have',
            neutral: 'Neutral',
            disqualifier: 'Disqualifier'
        };
        return labels[requirement] || requirement;
    }

    /**
     * Toggle annotation active state
     */
    toggleActive(annotationId) {
        const annotation = this.annotations.find(a => a.id === annotationId);
        if (annotation) {
            annotation.is_active = !annotation.is_active;
            annotation.updated_at = new Date().toISOString();
            this.renderAnnotations();
            this.updateStats();
            // Apply highlights with slight delay to ensure DOM is stable
            // Use force=true since we're modifying annotation state
            requestAnimationFrame(() => {
                this.applyHighlights({ force: true });
            });
            this.scheduleSave();
        }
    }

    /**
     * Delete annotation
     * @param {string} annotationId - ID of the annotation to delete
     * @param {boolean} [skipHistory=false] - If true, don't record in undo history (used by undo/redo)
     */
    deleteAnnotation(annotationId, skipHistory = false) {
        const index = this.annotations.findIndex(a => a.id === annotationId);
        if (index !== -1) {
            const annotation = this.annotations[index];

            // Record for undo (before deletion)
            if (!skipHistory) {
                this.undoManager.push({
                    type: 'delete',
                    annotation: annotation
                });
                this.updateUndoRedoButtons();
            }

            // Capture negative feedback for auto-generated annotations
            if (annotation.source === 'auto_generated' && annotation.original_values) {
                this.captureAnnotationFeedback(annotation, 'delete');
            }

            this.annotations.splice(index, 1);
            this.renderAnnotations();
            this.updateStats();
            // Apply highlights with slight delay to ensure DOM is stable
            // Use force=true since we're modifying annotation list
            requestAnimationFrame(() => {
                this.applyHighlights({ force: true });
            });
            this.scheduleSave();
        }
    }

    /**
     * Undo the last annotation action.
     * Supports undoing add, delete, and update operations.
     */
    undo() {
        const action = this.undoManager.undo();
        if (!action) {
            if (typeof showToast === 'function') {
                showToast('Nothing to undo', 'info');
            }
            return;
        }

        switch (action.type) {
            case 'delete':
                // Restore deleted annotation
                this.annotations.push(action.annotation);
                break;
            case 'add':
                // Remove added annotation (use skipHistory=true to avoid recording)
                this.annotations = this.annotations.filter(a => a.id !== action.annotation.id);
                break;
            case 'update':
                // Restore previous state
                const idx = this.annotations.findIndex(a => a.id === action.annotation.id);
                if (idx !== -1) {
                    this.annotations[idx] = JSON.parse(JSON.stringify(action.previousState));
                }
                break;
        }

        this.renderAnnotations();
        this.updateStats();
        // Use force=true since undo modifies annotation state
        requestAnimationFrame(() => {
            this.applyHighlights({ force: true });
        });
        this.scheduleSave();
        this.updateUndoRedoButtons();

        if (typeof showToast === 'function') {
            showToast('Undone', 'info');
        }
    }

    /**
     * Redo the last undone annotation action.
     * Supports redoing add, delete, and update operations.
     */
    redo() {
        const action = this.undoManager.redo();
        if (!action) {
            if (typeof showToast === 'function') {
                showToast('Nothing to redo', 'info');
            }
            return;
        }

        switch (action.type) {
            case 'delete':
                // Re-delete the annotation
                this.annotations = this.annotations.filter(a => a.id !== action.annotation.id);
                break;
            case 'add':
                // Re-add the annotation
                this.annotations.push(action.annotation);
                break;
            case 'update':
                // Re-apply the update
                const idx = this.annotations.findIndex(a => a.id === action.annotation.id);
                if (idx !== -1) {
                    this.annotations[idx] = JSON.parse(JSON.stringify(action.annotation));
                }
                break;
        }

        this.renderAnnotations();
        this.updateStats();
        // Use force=true since redo modifies annotation state
        requestAnimationFrame(() => {
            this.applyHighlights({ force: true });
        });
        this.scheduleSave();
        this.updateUndoRedoButtons();

        if (typeof showToast === 'function') {
            showToast('Redone', 'info');
        }
    }

    /**
     * Update undo/redo button states based on history availability.
     * Uses ID prefix for batch mode support.
     */
    updateUndoRedoButtons() {
        const prefix = this.config.idPrefix || '';
        const undoBtn = document.getElementById(`${prefix}undo-btn`);
        const redoBtn = document.getElementById(`${prefix}redo-btn`);

        if (undoBtn) {
            const canUndo = this.undoManager.canUndo();
            undoBtn.disabled = !canUndo;
            undoBtn.classList.toggle('opacity-50', !canUndo);
            undoBtn.classList.toggle('cursor-not-allowed', !canUndo);
        }
        if (redoBtn) {
            const canRedo = this.undoManager.canRedo();
            redoBtn.disabled = !canRedo;
            redoBtn.classList.toggle('opacity-50', !canRedo);
            redoBtn.classList.toggle('cursor-not-allowed', !canRedo);
        }
    }

    /**
     * Capture feedback for auto-generated annotations with retry logic.
     * Called when user saves (with potential edits) or deletes an annotation.
     * Uses direct VPS call to bypass Vercel timeout.
     * Implements exponential backoff (1s, 2s, 4s) for resilience against 502/network errors.
     *
     * @param {Object} annotation - The annotation object
     * @param {string} action - "save" or "delete"
     * @param {number} retryCount - Internal retry counter (default: 0)
     */
    async captureAnnotationFeedback(annotation, action, retryCount = 0) {
        const MAX_RETRIES = 3;
        const BASE_DELAY = 1000; // 1 second

        // Only capture feedback for auto-generated annotations
        if (annotation.source !== 'auto_generated') return;
        if (!annotation.original_values) return;
        // Skip if feedback was already captured for this annotation
        if (annotation.feedback_captured && action === 'save') return;

        // Show subtle syncing indicator (only on first attempt)
        if (retryCount === 0) {
            this.showFeedbackSyncing();
        }

        try {
            const payload = {
                annotation_id: annotation.id,
                action: action,
                original_values: annotation.original_values,
                // Include target info for context-aware deletion learning
                target: {
                    section: annotation.target?.section || null,
                    text: annotation.target?.text || null,
                },
            };

            // For save action, include final values for comparison
            if (action === 'save') {
                payload.final_values = {
                    relevance: annotation.relevance,
                    passion: annotation.passion,
                    identity: annotation.identity,
                    requirement_type: annotation.requirement_type,
                };
            }

            // Direct VPS call to bypass Vercel timeout (10s limit)
            const runnerUrl = window.RUNNER_URL || '';
            const runnerToken = window.RUNNER_TOKEN || '';

            const response = await fetch(`${runnerUrl}/user/annotation-feedback`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${runnerToken}`,
                },
                body: JSON.stringify(payload)
            });

            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    // Mark feedback as captured (for save action)
                    if (action === 'save') {
                        annotation.feedback_captured = true;
                    }
                    console.log(`Feedback captured for ${action}:`, data);
                    this.showFeedbackSuccess();
                    return; // Success - exit
                }
            }

            // Non-OK response (502, 503, etc.) - retry if we have attempts left
            if (retryCount < MAX_RETRIES) {
                const delay = BASE_DELAY * Math.pow(2, retryCount); // Exponential backoff
                console.warn(`Feedback capture failed (${response.status}), retrying in ${delay}ms... (attempt ${retryCount + 1}/${MAX_RETRIES})`);
                setTimeout(() => this.captureAnnotationFeedback(annotation, action, retryCount + 1), delay);
                return;
            }

            // All retries exhausted
            console.error(`Feedback capture failed after ${MAX_RETRIES} retries for annotation ${annotation.id}`);
        } catch (error) {
            // Network error - retry if we have attempts left
            if (retryCount < MAX_RETRIES) {
                const delay = BASE_DELAY * Math.pow(2, retryCount);
                console.warn(`Feedback capture error: ${error.message}, retrying in ${delay}ms... (attempt ${retryCount + 1}/${MAX_RETRIES})`);
                setTimeout(() => this.captureAnnotationFeedback(annotation, action, retryCount + 1), delay);
                return;
            }

            // All retries exhausted
            console.error(`Feedback capture failed after ${MAX_RETRIES} retries:`, error);
        } finally {
            // Only hide indicator after all retries exhausted or success
            if (retryCount >= MAX_RETRIES || annotation.feedback_captured) {
                this.hideFeedbackSyncing();
            }
        }
    }

    /**
     * Capture learning signal from manual annotations (Issue 3: Learn from manual annotations)
     * Manual annotations represent positive signals - the user explicitly marked this text as relevant.
     * This helps improve future AI suggestions.
     *
     * @param {Object} annotation - The manual annotation object
     * @param {number} retryCount - Internal retry counter (default: 0)
     */
    async captureManualAnnotationLearning(annotation, retryCount = 0) {
        const MAX_RETRIES = 3;
        const BASE_DELAY = 1000;

        // Only capture for manual annotations
        if (annotation.source !== 'manual') return;
        // Skip if already captured
        if (annotation.learning_captured) return;

        try {
            const payload = {
                annotation_id: annotation.id,
                action: 'manual_create',  // Distinct action type for manual annotations
                target: {
                    section: annotation.target?.section || null,
                    text: annotation.target?.text || null,
                },
                // Positive signal: user explicitly chose these values
                values: {
                    relevance: annotation.relevance,
                    passion: annotation.passion,
                    identity: annotation.identity,
                    requirement_type: annotation.requirement_type,
                },
            };

            const runnerUrl = window.RUNNER_URL || '';
            const runnerToken = window.RUNNER_TOKEN || '';

            const response = await fetch(`${runnerUrl}/user/annotation-feedback`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${runnerToken}`,
                },
                body: JSON.stringify(payload)
            });

            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    annotation.learning_captured = true;
                    console.log('[ManualLearning] Captured positive signal:', annotation.target?.text?.substring(0, 50));
                    return;
                }
            }

            // Retry on failure
            if (retryCount < MAX_RETRIES) {
                const delay = BASE_DELAY * Math.pow(2, retryCount);
                console.warn(`[ManualLearning] Retry ${retryCount + 1}/${MAX_RETRIES} in ${delay}ms`);
                setTimeout(() => this.captureManualAnnotationLearning(annotation, retryCount + 1), delay);
            }
        } catch (error) {
            if (retryCount < MAX_RETRIES) {
                const delay = BASE_DELAY * Math.pow(2, retryCount);
                setTimeout(() => this.captureManualAnnotationLearning(annotation, retryCount + 1), delay);
            } else {
                console.error('[ManualLearning] Failed after retries:', error);
            }
        }
    }

    /**
     * Show subtle syncing indicator for feedback capture
     */
    showFeedbackSyncing() {
        // Use save indicator if available, otherwise just log
        const saveIndicator = document.getElementById(this.config.saveIndicatorId);
        if (saveIndicator) {
            this._previousIndicatorContent = saveIndicator.innerHTML;
            saveIndicator.innerHTML = `
                <span class="text-blue-500 flex items-center gap-1">
                    <svg class="animate-spin h-3 w-3" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    <span class="text-xs">Syncing...</span>
                </span>
            `;
        }
    }

    /**
     * Hide feedback syncing indicator
     */
    hideFeedbackSyncing() {
        const saveIndicator = document.getElementById(this.config.saveIndicatorId);
        if (saveIndicator && this._previousIndicatorContent) {
            saveIndicator.innerHTML = this._previousIndicatorContent;
            this._previousIndicatorContent = null;
        }
    }

    /**
     * Show brief success indicator for feedback capture
     */
    showFeedbackSuccess() {
        const saveIndicator = document.getElementById(this.config.saveIndicatorId);
        if (saveIndicator) {
            const previousContent = saveIndicator.innerHTML;
            saveIndicator.innerHTML = `
                <span class="text-green-500 flex items-center gap-1">
                    <svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                    </svg>
                    <span class="text-xs">Synced</span>
                </span>
            `;
            // Revert after 1 second
            setTimeout(() => {
                if (saveIndicator.innerHTML.includes('Synced')) {
                    saveIndicator.innerHTML = previousContent;
                }
            }, 1000);
        }
    }

    /**
     * Select annotation (scroll to and highlight in JD viewer)
     */
    selectAnnotation(annotationId) {
        console.log('Selected annotation:', annotationId);

        // Find the highlight in the JD content
        const highlight = document.querySelector(`.annotation-highlight[data-annotation-id="${annotationId}"]`);
        if (highlight) {
            // Add temporary pulse animation
            highlight.classList.add('annotation-highlight-pulse');
            setTimeout(() => {
                highlight.classList.remove('annotation-highlight-pulse');
            }, 1500);

            // Scroll into view
            highlight.scrollIntoView({
                behavior: 'smooth',
                block: 'center'
            });
        }

        // Also highlight in the annotation list
        const annotationItem = document.querySelector(`.annotation-item[data-annotation-id="${annotationId}"]`);
        if (annotationItem) {
            document.querySelectorAll('.annotation-item.selected').forEach(item => {
                item.classList.remove('selected');
            });
            annotationItem.classList.add('selected');
        }
    }

    /**
     * Apply highlights to JD content based on active annotations.
     *
     * IMPORTANT: When editing an existing annotation (popover is open for edit),
     * we should NOT clear and recreate highlights as this would destroy the
     * highlight the user just clicked on, causing a jarring UX.
     *
     * @param {Object} options - Options for highlight application
     * @param {boolean} options.force - Force re-application even during edit mode (default: false)
     */
    applyHighlights(options = {}) {
        const { force = false } = options;

        const contentEl = document.getElementById(this.config.contentId);
        if (!contentEl) {
            console.warn('applyHighlights: Content element not found');
            return;
        }

        // Skip if we're currently editing an annotation (popover is open for edit)
        // This prevents destroying the highlight the user just clicked on
        // Use force=true to override this guard (e.g., when relevance color changes)
        if (!force && this.editingAnnotationId) {
            const popover = document.getElementById(this.config.popoverId);
            const isPopoverVisible = popover && !popover.classList.contains('hidden');
            if (isPopoverVisible) {
                console.log('applyHighlights: Skipping - edit popover is open for annotation:', this.editingAnnotationId);
                return;
            }
        }

        // Clear existing highlights first
        this.clearHighlights(contentEl);

        // Get active annotations only
        const activeAnnotations = this.annotations.filter(a => a.is_active !== false);
        if (!activeAnnotations.length) {
            console.log('applyHighlights: No active annotations to highlight');
            return;
        }

        // Apply highlights for each annotation
        let highlightCount = 0;
        activeAnnotations.forEach(annotation => {
            // Use original_text for highlighting (matches JD), fallback to text
            const targetText = annotation.target?.original_text || annotation.target?.text;
            const relevance = annotation.relevance || 'relevant';

            // Debug: Log the relevance being applied for each annotation
            console.log(`applyHighlights: annotation ${annotation.id?.slice(-6)} relevance=${relevance}`);

            if (targetText && targetText.length > 0) {
                const found = this.highlightTextInElement(contentEl, targetText, relevance, annotation.id);
                if (found) highlightCount++;
            }
        });

        console.log(`applyHighlights: Applied ${highlightCount}/${activeAnnotations.length} highlights`);
    }

    /**
     * Clear all existing highlights from content
     */
    clearHighlights(container) {
        const highlights = container.querySelectorAll('.annotation-highlight');
        highlights.forEach(highlight => {
            const textNode = document.createTextNode(highlight.textContent);
            highlight.parentNode.replaceChild(textNode, highlight);
        });
        // Normalize to merge adjacent text nodes
        container.normalize();
    }

    /**
     * Highlight text within an element using TreeWalker
     */
    highlightTextInElement(container, searchText, relevance, annotationId) {
        if (!searchText || searchText.length < 2) return false;

        const walker = document.createTreeWalker(
            container,
            NodeFilter.SHOW_TEXT,
            {
                acceptNode: (node) => {
                    // Skip nodes inside existing highlights or info boxes
                    if (node.parentElement.closest('.annotation-highlight, .raw-jd-content > div:first-child')) {
                        return NodeFilter.FILTER_REJECT;
                    }
                    return NodeFilter.FILTER_ACCEPT;
                }
            }
        );

        let node;
        let found = false;

        while ((node = walker.nextNode()) && !found) {
            const text = node.textContent;
            const index = text.indexOf(searchText);

            if (index !== -1) {
                // Split the text node and wrap the matched portion
                const beforeText = text.substring(0, index);
                const matchText = text.substring(index, index + searchText.length);
                const afterText = text.substring(index + searchText.length);

                const parent = node.parentNode;
                const fragment = document.createDocumentFragment();

                if (beforeText) {
                    fragment.appendChild(document.createTextNode(beforeText));
                }

                // Create highlight span
                const highlight = document.createElement('span');
                highlight.className = `annotation-highlight annotation-highlight-${relevance}`;
                highlight.dataset.annotationId = annotationId || '';
                highlight.dataset.relevance = relevance;
                highlight.dataset.relevanceLabel = this.getRelevanceLabel(relevance);
                highlight.textContent = matchText;
                highlight.style.cursor = 'pointer';
                highlight.onclick = (e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    // Open popover for editing this annotation
                    this.editAnnotationFromHighlight(annotationId, highlight);
                };
                fragment.appendChild(highlight);

                if (afterText) {
                    fragment.appendChild(document.createTextNode(afterText));
                }

                parent.replaceChild(fragment, node);
                found = true;
            }
        }

        return found;
    }

    /**
     * Get human-readable label for relevance level
     */
    getRelevanceLabel(relevance) {
        const labels = {
            'core_strength': 'Core (3.0x)',
            'extremely_relevant': 'Strong (2.0x)',
            'relevant': 'Medium (1.5x)',
            'tangential': 'Weak (1.0x)',
            'gap': 'Gap (0.3x)'
        };
        return labels[relevance] || relevance;
    }

    /**
     * Edit annotation from highlight click.
     *
     * Guards against:
     * - Duplicate calls (from both mouseup and onclick handlers)
     * - Calling applyHighlights while popover is open for edit
     */
    editAnnotationFromHighlight(annotationId, highlightEl) {
        if (!annotationId) return;

        // Guard: If already editing this annotation, don't re-trigger
        // This prevents issues from duplicate event handlers (mouseup + onclick)
        if (this.editingAnnotationId === annotationId) {
            console.log('editAnnotationFromHighlight: Already editing this annotation, skipping');
            return;
        }

        // Find the annotation data
        const annotation = this.annotations.find(a => a.id === annotationId);
        if (!annotation) {
            console.warn('Annotation not found:', annotationId);
            return;
        }

        // Get position from highlight element
        const rect = highlightEl.getBoundingClientRect();

        // Show popover in edit mode
        // This sets editingAnnotationId which guards applyHighlights from clearing this highlight
        this.showAnnotationPopover(rect, annotation.target?.text || '', annotation);

        // Also highlight in the list
        this.scrollToAnnotation(annotationId);
    }

    /**
     * Scroll to annotation in the list and highlight it
     */
    scrollToAnnotation(annotationId) {
        if (!annotationId) return;

        // Find the annotation item in the list
        const annotationItem = document.querySelector(`.annotation-item[data-annotation-id="${annotationId}"]`);
        if (annotationItem) {
            // Remove previous selection
            document.querySelectorAll('.annotation-item.selected').forEach(item => {
                item.classList.remove('selected');
            });

            // Add selection to current item
            annotationItem.classList.add('selected');

            // Scroll into view smoothly
            annotationItem.scrollIntoView({
                behavior: 'smooth',
                block: 'center'
            });
        }
    }

    /**
     * Render processed JD HTML
     */
    renderProcessedJd() {
        const loadingEl = document.getElementById(this.config.loadingId);
        const emptyEl = document.getElementById(this.config.emptyId);
        const contentEl = document.getElementById(this.config.contentId);

        if (loadingEl) loadingEl.classList.add('hidden');
        if (emptyEl) emptyEl.classList.add('hidden');

        if (contentEl && this.processedJdHtml) {
            contentEl.innerHTML = this.processedJdHtml;
            contentEl.classList.remove('hidden');
        }
    }

    /**
     * Update statistics displays
     */
    updateStats() {
        // Update annotation counts
        const countEl = document.getElementById(this.config.annotationCountId);
        const activeCountEl = document.getElementById(this.config.activeAnnotationCountId);

        if (countEl) countEl.textContent = `${this.annotations.length} annotations`;
        if (activeCountEl) {
            const activeCount = this.annotations.filter(a => a.is_active).length;
            activeCountEl.textContent = `${activeCount} active`;
        }

        // Update coverage
        this.updateCoverage();

        // Update boost preview
        this.updateBoostPreview();

        // Phase 11: Update review queue if container exists
        this.renderReviewQueue();

        // Update persona panel
        this.renderPersonaPanel();
    }

    // ============================================================================
    // Persona Methods
    // ============================================================================

    /**
     * Check if there are any annotations relevant for persona synthesis.
     * Includes: identity (core_identity, strong_identity, developing),
     *           passion (love_it, enjoy),
     *           strength (core_strength, extremely_relevant)
     */
    checkIdentityAnnotations() {
        const identityLevels = ['core_identity', 'strong_identity', 'developing'];
        const passionLevels = ['love_it', 'enjoy'];
        const strengthLevels = ['core_strength', 'extremely_relevant'];

        this.personaState.hasIdentityAnnotations = this.annotations.some(
            a => a.is_active && (
                identityLevels.includes(a.identity) ||
                passionLevels.includes(a.passion) ||
                strengthLevels.includes(a.relevance)
            )
        );
    }

    /**
     * Synthesize persona from identity annotations using LLM
     */
    async synthesizePersona() {
        if (this.personaState.isLoading) return;

        // Check for identity annotations first
        this.checkIdentityAnnotations();
        if (!this.personaState.hasIdentityAnnotations) {
            console.log('No identity annotations found, skipping synthesis');
            return;
        }

        this.personaState.isLoading = true;
        this.renderPersonaPanel();

        try {
            // First, ensure annotations are saved to MongoDB so the API has latest data
            await this.saveAnnotations();

            const response = await fetch(`/api/jobs/${this.jobId}/synthesize-persona`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });

            const data = await response.json();

            if (data.unavailable) {
                // Expected on Vercel - LangChain not available
                this.personaState.unavailable = true;
                console.info('Persona synthesis unavailable on this deployment:', data.message);
            } else if (data.success && data.persona) {
                this.personaState.statement = data.persona;
                this.personaState.isUserEdited = false;
                this.personaState.unavailable = false;
                console.log('Synthesized persona:', data.persona);

                // Auto-save the synthesized persona to MongoDB
                await this.savePersonaToDb(data.persona, false);
            } else {
                console.warn('Persona synthesis returned no result:', data.message || data.error);
            }
        } catch (error) {
            console.error('Error synthesizing persona:', error);
        } finally {
            this.personaState.isLoading = false;
            this.renderPersonaPanel();
        }
    }

    /**
     * Save persona to database (without triggering UI updates)
     */
    async savePersonaToDb(persona, isEdited) {
        try {
            await fetch(`/api/jobs/${this.jobId}/save-persona`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    persona: persona,
                    is_edited: isEdited
                })
            });
        } catch (error) {
            console.error('Error saving persona to DB:', error);
        }
    }

    /**
     * Save persona (after user edit)
     */
    async savePersona() {
        const statement = this.personaState.statement?.trim();
        if (!statement) return;

        try {
            const response = await fetch(`/api/jobs/${this.jobId}/save-persona`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    persona: statement,
                    is_edited: true
                })
            });

            const data = await response.json();
            if (data.success) {
                this.personaState.isEditing = false;
                this.personaState.isUserEdited = true;
                console.log('Persona saved successfully');
            }
        } catch (error) {
            console.error('Error saving persona:', error);
        }

        this.renderPersonaPanel();
    }

    /**
     * Enter persona edit mode
     */
    startEditingPersona() {
        this.personaState.isEditing = true;
        this.renderPersonaPanel();
    }

    /**
     * Start manual persona entry (when synthesis unavailable)
     */
    startManualPersonaEntry() {
        this.personaState.statement = '';  // Start with empty statement
        this.personaState.isEditing = true;
        this.personaState.unavailable = false;  // Clear unavailable state
        this.renderPersonaPanel();
    }

    /**
     * Cancel persona edit mode
     */
    cancelEditingPersona() {
        this.personaState.isEditing = false;
        this.renderPersonaPanel();
    }

    /**
     * Update persona statement (called from textarea input)
     */
    updatePersonaText(text) {
        this.personaState.statement = text;
    }

    /**
     * Toggle persona panel expanded/collapsed state
     */
    togglePersonaExpanded() {
        this.personaState.isExpanded = !this.personaState.isExpanded;
        this.renderPersonaPanel();
    }

    /**
     * Render the persona panel UI - Compact, collapsible design
     */
    renderPersonaPanel() {
        const container = document.getElementById(this.config.personaPanelId);
        if (!container) return;

        // Check for identity annotations
        this.checkIdentityAnnotations();

        // Hide completely if no identity annotations
        if (!this.personaState.hasIdentityAnnotations) {
            container.innerHTML = '';
            container.classList.add('hidden');
            return;
        }

        container.classList.remove('hidden');
        const { statement, isLoading, isEditing, isUserEdited, unavailable, isExpanded } = this.personaState;

        // Loading state - compact inline
        if (isLoading) {
            container.innerHTML = `
                <div class="flex items-center gap-2 py-1.5 px-2 bg-indigo-50 dark:bg-indigo-900/20 rounded border border-indigo-200 dark:border-indigo-800">
                    <svg class="animate-spin h-3.5 w-3.5 text-indigo-600 dark:text-indigo-400 flex-shrink-0" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    <span class="text-xs text-indigo-700 dark:text-indigo-300">Synthesizing persona...</span>
                </div>
            `;
            return;
        }

        // Unavailable on Vercel - compact button
        if (unavailable && !statement) {
            container.innerHTML = `
                <button onclick="getActiveAnnotationManager()?.startManualPersonaEntry()"
                        class="persona-generate-btn bg-amber-100 text-amber-700 hover:bg-amber-200 dark:bg-amber-900/30 dark:text-amber-300 dark:hover:bg-amber-900/50 border border-amber-300 dark:border-amber-700">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/>
                    </svg>
                    Enter Persona Manually
                </button>
            `;
            return;
        }

        // No persona yet - compact generate button
        if (!statement) {
            container.innerHTML = `
                <button onclick="getActiveAnnotationManager()?.synthesizePersona()"
                        class="persona-generate-btn bg-indigo-100 text-indigo-700 hover:bg-indigo-200 dark:bg-indigo-900/30 dark:text-indigo-300 dark:hover:bg-indigo-900/50 border border-indigo-300 dark:border-indigo-700">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z"/>
                    </svg>
                    Generate Persona
                </button>
            `;
            return;
        }

        // Edit mode - compact
        if (isEditing) {
            container.innerHTML = `
                <div class="p-2 bg-indigo-50 dark:bg-indigo-900/20 rounded border border-indigo-200 dark:border-indigo-800">
                    <textarea id="persona-edit-textarea"
                              class="w-full p-2 border border-indigo-300 dark:border-indigo-600 rounded text-xs bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                              rows="2"
                              oninput="getActiveAnnotationManager()?.updatePersonaText(this.value)"
                    >${statement}</textarea>
                    <div class="flex gap-1.5 mt-1.5">
                        <button onclick="getActiveAnnotationManager()?.savePersona()"
                                class="px-2 py-1 bg-indigo-600 text-white rounded text-xs font-medium hover:bg-indigo-700">
                            Save
                        </button>
                        <button onclick="getActiveAnnotationManager()?.cancelEditingPersona()"
                                class="px-2 py-1 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded text-xs font-medium hover:bg-gray-50 dark:hover:bg-gray-600">
                            Cancel
                        </button>
                    </div>
                </div>
            `;
            return;
        }

        // Display mode - collapsible card
        const expandedClass = isExpanded ? 'persona-panel-expanded' : 'persona-panel-collapsed';
        const editedBadge = isUserEdited
            ? '<span class="text-[10px] bg-indigo-200 dark:bg-indigo-800 text-indigo-700 dark:text-indigo-300 px-1.5 py-0.5 rounded-full">edited</span>'
            : '';
        const chevronRotation = isExpanded ? 'rotate-180' : '';

        container.innerHTML = `
            <div class="persona-panel ${expandedClass} bg-indigo-50 dark:bg-indigo-900/20 rounded border border-indigo-200 dark:border-indigo-800">
                <!-- Collapsed header - always visible -->
                <div class="flex items-center justify-between py-1.5 px-2 cursor-pointer hover:bg-indigo-100 dark:hover:bg-indigo-900/30 rounded-t transition"
                     onclick="getActiveAnnotationManager()?.togglePersonaExpanded()">
                    <div class="flex items-center gap-1.5 min-w-0">
                        <svg class="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/>
                        </svg>
                        <span class="text-xs font-medium text-indigo-900 dark:text-indigo-200">Persona</span>
                        ${editedBadge}
                        ${!isExpanded ? `<span class="text-xs text-indigo-600 dark:text-indigo-400 truncate ml-1 italic">"${this.truncateText(statement, 40)}"</span>` : ''}
                    </div>
                    <div class="flex items-center gap-1 flex-shrink-0">
                        <button onclick="event.stopPropagation(); getActiveAnnotationManager()?.startEditingPersona()"
                                class="p-1 text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-200 rounded hover:bg-indigo-200 dark:hover:bg-indigo-800"
                                title="Edit persona">
                            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/>
                            </svg>
                        </button>
                        <button onclick="event.stopPropagation(); getActiveAnnotationManager()?.synthesizePersona()"
                                class="p-1 text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-200 rounded hover:bg-indigo-200 dark:hover:bg-indigo-800"
                                title="Regenerate persona">
                            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
                            </svg>
                        </button>
                        <svg class="persona-toggle-btn w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400 ${chevronRotation} transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
                        </svg>
                    </div>
                </div>
                <!-- Expanded content -->
                <div class="persona-content ${isExpanded ? 'px-2 pb-2 pt-1' : ''}">
                    <p class="text-xs text-indigo-800 dark:text-indigo-200 italic leading-relaxed">"${statement}"</p>
                </div>
            </div>
        `;
    }

    /**
     * Helper to truncate text for collapsed state preview
     */
    truncateText(text, maxLength) {
        if (!text || text.length <= maxLength) return text || '';
        return text.substring(0, maxLength).trim() + '...';
    }

    /**
     * Update coverage progress bar
     */
    updateCoverage() {
        // Calculate coverage based on section targets
        const sectionTargets = {
            responsibilities: 5,
            qualifications: 5,
            technical_skills: 4,
            nice_to_have: 2
        };

        let annotatedSections = {};
        this.annotations.forEach(ann => {
            const section = ann.target?.section || 'unknown';
            annotatedSections[section] = (annotatedSections[section] || 0) + 1;
        });

        let totalTarget = 0;
        let totalAnnotated = 0;

        Object.entries(sectionTargets).forEach(([section, target]) => {
            totalTarget += target;
            totalAnnotated += Math.min(annotatedSections[section] || 0, target);
        });

        const coverage = totalTarget > 0 ? Math.round((totalAnnotated / totalTarget) * 100) : 0;

        const barEl = document.getElementById(this.config.coverageBarId);
        const pctEl = document.getElementById(this.config.coveragePctId);

        if (barEl) barEl.style.width = `${coverage}%`;
        if (pctEl) pctEl.textContent = `${coverage}%`;

        // Update section coverage list with actual counts
        const sectionCoverageList = document.getElementById('section-coverage-list');
        if (sectionCoverageList) {
            Object.entries(sectionTargets).forEach(([section, target]) => {
                const count = annotatedSections[section] || 0;
                const span = sectionCoverageList.querySelector(`[data-section="${section}"]`);
                if (span) {
                    span.textContent = `${count}/${target}`;
                    // Color based on coverage: green=complete, orange=partial, gray=none
                    span.classList.remove('text-gray-500', 'text-orange-500', 'text-green-500');
                    if (count >= target) {
                        span.classList.add('text-green-500');
                    } else if (count > 0) {
                        span.classList.add('text-orange-500');
                    } else {
                        span.classList.add('text-gray-500');
                    }
                }
            });
        }

        // Phase 10 (GAP-093): Update coverage warning display
        const warningsEl = document.getElementById('coverage-warnings');
        if (warningsEl) {
            const warnings = this.validateCoverage();
            if (warnings.length > 0) {
                warningsEl.innerHTML = warnings.map(w =>
                    `<div class="text-orange-600 text-sm">⚠ ${w}</div>`
                ).join('');
                warningsEl.classList.remove('hidden');
            } else {
                warningsEl.innerHTML = '';
                warningsEl.classList.add('hidden');
            }
        }
    }

    /**
     * Phase 10 (GAP-093): Validate section coverage before generation.
     *
     * Checks that all JD sections have adequate annotation coverage.
     * Returns warnings for sections below target.
     *
     * @returns {string[]} Array of warning messages
     */
    validateCoverage() {
        const sectionTargets = {
            responsibilities: { target: 5, label: 'Responsibilities' },
            qualifications: { target: 5, label: 'Qualifications' },
            technical_skills: { target: 4, label: 'Technical Skills' },
            nice_to_have: { target: 2, label: 'Nice to Have' }
        };

        // Count annotations per section
        const sectionCounts = {};
        this.annotations.forEach(ann => {
            if (!ann.is_active) return;
            const section = ann.target?.section || 'unknown';
            sectionCounts[section] = (sectionCounts[section] || 0) + 1;
        });

        const warnings = [];
        for (const [section, config] of Object.entries(sectionTargets)) {
            const count = sectionCounts[section] || 0;
            if (count < config.target) {
                warnings.push(`${config.label}: ${count}/${config.target} annotations`);
            }
        }

        return warnings;
    }

    // ============================================================================
    // Phase 11 (GAP-094): Review Workflow
    // ============================================================================

    /**
     * Get annotations pending review (draft or needs_review status).
     *
     * @returns {Array} Annotations needing review
     */
    getPendingReviewAnnotations() {
        return this.annotations.filter(ann =>
            ann.status === 'needs_review' ||
            (ann.status === 'draft' && ann.created_by === 'pipeline_suggestion')
        );
    }

    /**
     * Approve an annotation (mark as human-reviewed).
     *
     * @param {string} annotationId - ID of annotation to approve
     */
    approveAnnotation(annotationId) {
        const annotation = this.annotations.find(a => a.id === annotationId);
        if (annotation) {
            annotation.status = 'approved';
            annotation.last_reviewed_by = 'human';
            annotation.reviewed_at = new Date().toISOString();
            console.log(`Annotation ${annotationId} approved`);
            this.renderAnnotations();
            this.scheduleSave();
        }
    }

    /**
     * Reject an annotation with optional note.
     *
     * @param {string} annotationId - ID of annotation to reject
     * @param {string} note - Optional rejection note
     */
    rejectAnnotation(annotationId, note = '') {
        const annotation = this.annotations.find(a => a.id === annotationId);
        if (annotation) {
            annotation.status = 'rejected';
            annotation.is_active = false;
            annotation.review_note = note;
            annotation.last_reviewed_by = 'human';
            annotation.reviewed_at = new Date().toISOString();
            console.log(`Annotation ${annotationId} rejected${note ? ': ' + note : ''}`);
            this.renderAnnotations();
            // Use force=true since we're modifying annotation state
            this.applyHighlights({ force: true });
            this.updateStats();
            this.scheduleSave();
        }
    }

    /**
     * Bulk approve all pending review annotations.
     */
    bulkApprove() {
        const pending = this.getPendingReviewAnnotations();
        pending.forEach(ann => {
            ann.status = 'approved';
            ann.last_reviewed_by = 'human';
            ann.reviewed_at = new Date().toISOString();
        });
        console.log(`Bulk approved ${pending.length} annotations`);
        this.renderAnnotations();
        this.scheduleSave();
    }

    /**
     * Bulk reject all pending review annotations.
     *
     * @param {string} note - Optional rejection note
     */
    bulkReject(note = '') {
        const pending = this.getPendingReviewAnnotations();
        pending.forEach(ann => {
            ann.status = 'rejected';
            ann.is_active = false;
            ann.review_note = note;
            ann.last_reviewed_by = 'human';
            ann.reviewed_at = new Date().toISOString();
        });
        console.log(`Bulk rejected ${pending.length} annotations`);
        this.renderAnnotations();
        // Use force=true since we're modifying annotation state
        this.applyHighlights({ force: true });
        this.updateStats();
        this.scheduleSave();
    }

    /**
     * Filter annotations by status.
     *
     * @param {string} status - 'all', 'approved', 'pending', 'rejected'
     * @returns {Array} Filtered annotations
     */
    filterByStatus(status) {
        if (status === 'all') {
            return this.annotations;
        } else if (status === 'pending') {
            return this.getPendingReviewAnnotations();
        } else {
            return this.annotations.filter(ann => ann.status === status);
        }
    }

    /**
     * Render review queue UI element (if container exists).
     */
    renderReviewQueue() {
        const container = document.getElementById('review-queue-container');
        if (!container) return;

        const pending = this.getPendingReviewAnnotations();

        if (pending.length === 0) {
            container.innerHTML = `
                <div class="text-gray-500 text-sm p-4">
                    ✓ No annotations pending review
                </div>
            `;
            return;
        }

        const cards = pending.map(ann => {
            const text = ann.target?.text || 'Unknown text';
            const truncated = text.length > 50 ? text.substring(0, 50) + '...' : text;
            return `
                <div class="border rounded p-3 mb-2 bg-yellow-50" data-ann-id="${ann.id}">
                    <div class="text-sm font-medium">${truncated}</div>
                    <div class="text-xs text-gray-600 mt-1">
                        ${ann.relevance || 'unset'} | ${ann.requirement_type || 'unset'}
                    </div>
                    <div class="mt-2 flex gap-2">
                        <button onclick="window.annotationManager?.approveAnnotation('${ann.id}')"
                                class="px-2 py-1 text-xs bg-green-500 text-white rounded hover:bg-green-600">
                            Approve
                        </button>
                        <button onclick="window.annotationManager?.rejectAnnotation('${ann.id}')"
                                class="px-2 py-1 text-xs bg-red-500 text-white rounded hover:bg-red-600">
                            Reject
                        </button>
                    </div>
                </div>
            `;
        }).join('');

        container.innerHTML = `
            <div class="mb-2 text-sm font-semibold">
                ${pending.length} annotations pending review
            </div>
            ${cards}
            <div class="mt-3 flex gap-2">
                <button onclick="window.annotationManager?.bulkApprove()"
                        class="px-3 py-1 text-sm bg-green-600 text-white rounded hover:bg-green-700">
                    Approve All
                </button>
                <button onclick="window.annotationManager?.bulkReject()"
                        class="px-3 py-1 text-sm bg-red-600 text-white rounded hover:bg-red-700">
                    Reject All
                </button>
            </div>
        `;
    }

    /**
     * Update boost preview
     */
    updateBoostPreview() {
        const boostEl = document.getElementById(this.config.boostValueId);
        if (!boostEl) return;

        // Calculate aggregate boost from active annotations
        const RELEVANCE_MULTIPLIERS = {
            core_strength: 3.0,
            extremely_relevant: 2.0,
            relevant: 1.5,
            tangential: 1.0,
            gap: 0.3
        };

        const REQUIREMENT_MULTIPLIERS = {
            must_have: 1.5,
            nice_to_have: 1.0,
            neutral: 1.0,
            disqualifier: 0.0
        };

        let totalBoost = 1.0;
        const activeAnnotations = this.annotations.filter(a => a.is_active);

        activeAnnotations.forEach(ann => {
            const relMult = RELEVANCE_MULTIPLIERS[ann.relevance] || 1.0;
            const reqMult = REQUIREMENT_MULTIPLIERS[ann.requirement_type] || 1.0;
            totalBoost *= (relMult * reqMult) ** 0.1; // Dampen effect of multiple annotations
        });

        boostEl.textContent = `${totalBoost.toFixed(2)}x`;
    }

    /**
     * Update save indicator
     */
    updateSaveIndicator(status) {
        const indicator = document.getElementById(this.config.saveIndicatorId);
        if (!indicator) return;

        switch (status) {
            case 'saved':
                indicator.innerHTML = '<span class="text-green-500">● Saved</span>';
                break;
            case 'saving':
                indicator.innerHTML = '<span class="text-yellow-500">● Saving...</span>';
                break;
            case 'unsaved':
                indicator.innerHTML = '<span class="text-yellow-500">● Unsaved</span>';
                break;
            case 'error':
                indicator.innerHTML = '<span class="text-red-500">● Error</span>';
                break;
        }
    }

    /**
     * Filter annotations
     */
    setFilter(filter) {
        this.currentFilter = filter;

        // Update filter button states
        document.querySelectorAll('.annotation-filter-btn').forEach(btn => {
            if (btn.dataset.filter === filter) {
                btn.classList.remove('bg-gray-100', 'text-gray-600');
                btn.classList.add('bg-indigo-100', 'text-indigo-800');
            } else {
                btn.classList.remove('bg-indigo-100', 'text-indigo-800');
                btn.classList.add('bg-gray-100', 'text-gray-600');
            }
        });

        this.renderAnnotations();
    }

    // ============================================================================
    // Batch Suggestion Review (Phase 2)
    // ============================================================================

    /**
     * Get pending AI-generated suggestions that haven't been approved or rejected.
     * NOTE: Since Issue 1 auto-apply UX change, AI suggestions are auto-approved on load.
     * This function now returns an empty array for backward compatibility.
     * @returns {Array} Always returns empty array (pending suggestions are auto-approved)
     */
    getPendingSuggestions() {
        // AI suggestions are now auto-approved on load (Issue 1: auto-apply UX)
        // Return empty array for backward compatibility with review banner
        return [];
    }

    /**
     * Accept all pending AI suggestions at once.
     * Marks each suggestion as approved and triggers re-render.
     */
    acceptAllSuggestions() {
        const pending = this.getPendingSuggestions();
        if (pending.length === 0) return;

        pending.forEach(a => {
            a.status = 'approved';
            a.reviewed_at = new Date().toISOString();
        });

        this.renderAnnotations();
        this.updateStats();
        this.scheduleSave();

        if (typeof showToast === 'function') {
            showToast(`Accepted ${pending.length} suggestions`, 'success');
        }
    }

    /**
     * Quickly accept a single AI suggestion.
     * @param {string} annotationId - ID of the annotation to accept
     */
    quickAcceptSuggestion(annotationId) {
        const ann = this.annotations.find(a => a.id === annotationId);
        if (ann) {
            // Record previous state for undo
            const previousState = JSON.parse(JSON.stringify(ann));

            ann.status = 'approved';
            ann.reviewed_at = new Date().toISOString();

            // Record for undo
            this.undoManager.push({
                type: 'update',
                annotation: ann,
                previousState: previousState
            });

            this.renderAnnotations();
            this.updateStats();
            this.scheduleSave();
            this.updateUndoRedoButtons();

            if (typeof showToast === 'function') {
                showToast('Suggestion accepted', 'success');
            }
        }
    }

    /**
     * Quickly reject (delete) a single AI suggestion.
     * Captures feedback before removing for learning purposes.
     * @param {string} annotationId - ID of the annotation to reject
     */
    quickRejectSuggestion(annotationId) {
        const ann = this.annotations.find(a => a.id === annotationId);
        if (!ann) return;

        // Record for undo (before deletion)
        this.undoManager.push({
            type: 'delete',
            annotation: ann
        });

        // Capture feedback for auto-generated annotations before removing
        if (ann.source === 'auto_generated' && ann.original_values) {
            this.captureAnnotationFeedback(ann, 'delete');
        }

        // Remove the annotation
        this.annotations = this.annotations.filter(a => a.id !== annotationId);
        this.renderAnnotations();
        this.updateStats();
        // Use force=true since we're modifying annotation list
        requestAnimationFrame(() => {
            this.applyHighlights({ force: true });
        });
        this.scheduleSave();
        this.updateUndoRedoButtons();

        if (typeof showToast === 'function') {
            showToast('Suggestion rejected', 'info');
        }
    }

    /**
     * Update the review banner visibility based on pending suggestions count.
     * Called after renderAnnotations to show/hide the banner.
     */
    updateReviewBanner() {
        const pending = this.getPendingSuggestions();

        // Get the banner using configured ID
        const banner = document.getElementById(this.config.reviewBannerId);
        const countEl = document.getElementById(this.config.pendingCountId);

        if (banner) {
            if (pending.length > 0) {
                banner.classList.remove('hidden');
                if (countEl) countEl.textContent = pending.length;
            } else {
                banner.classList.add('hidden');
            }
        }
    }
}

// ============================================================================
// Global Functions (called from HTML)
// ============================================================================

let annotationManager = null;

/**
 * Open annotation panel
 */
function openAnnotationPanel(jobId) {
    const panel = document.getElementById('jd-annotation-panel');
    const overlay = document.getElementById('jd-annotation-overlay');

    if (!panel || !overlay) {
        console.error('Annotation panel elements not found');
        return;
    }

    // Read jobId from panel data attribute if not provided
    if (!jobId) {
        jobId = panel.dataset.jobId;
    }

    if (!jobId) {
        console.error('No jobId provided and none found in panel data attribute');
        return;
    }

    // Initialize manager if needed
    if (!annotationManager || annotationManager.jobId !== jobId) {
        annotationManager = new AnnotationManager(jobId);
        annotationManager.init();
    }

    // Show panel
    overlay.classList.remove('hidden');
    panel.classList.remove('translate-x-full');

    // Focus trap
    panel.focus();
}

/**
 * Close annotation panel
 */
function closeAnnotationPanel() {
    const panel = document.getElementById('jd-annotation-panel');
    const overlay = document.getElementById('jd-annotation-overlay');

    if (panel) panel.classList.add('translate-x-full');
    if (overlay) overlay.classList.add('hidden');

    // Hide popover - auto-save if valid before closing panel
    hideAnnotationPopover({ save: true });
}

/**
 * Private helper to hide the popover DOM element only (no save logic)
 */
function _hidePopover() {
    const popover = document.getElementById('annotation-popover');
    if (popover) popover.classList.add('hidden');
}

/**
 * Hide annotation popover with optional auto-save
 * @param {Object} options - Options for hiding behavior
 * @param {boolean} options.save - Whether to auto-save if valid (default: true)
 * @param {boolean} options.clearSelection - Whether to clear text selection (default: false)
 */
function hideAnnotationPopover(options = {}) {
    const { save = true, clearSelection = false } = options;

    const popover = document.getElementById('annotation-popover');
    if (!popover || popover.classList.contains('hidden')) return;

    const manager = getActiveAnnotationManager();
    if (save && manager?.canSaveAnnotation()) {
        manager.createAnnotationFromPopover();
        return; // createAnnotationFromPopover will call _hidePopover()
    }

    _hidePopover();

    if (clearSelection) {
        window.getSelection().removeAllRanges();
    }
}

/**
 * Toggle collapsible popover field visibility
 * Used for Reframe Note, Strategic Note, and ATS Keywords fields
 */
function togglePopoverField(field) {
    const content = document.getElementById(`${field}-content`);
    const chevron = document.getElementById(`${field}-chevron`);

    if (!content) return;

    if (content.classList.contains('hidden')) {
        // Expand
        content.classList.remove('hidden');
        if (chevron) {
            chevron.style.transform = 'rotate(90deg)';
        }
    } else {
        // Collapse
        content.classList.add('hidden');
        if (chevron) {
            chevron.style.transform = 'rotate(0deg)';
        }
    }
}

// NOTE: getActiveAnnotationManager() is defined later in this file (line ~2727)
// to support both batch and job detail contexts

/**
 * Set quick annotation (from toolbar)
 */
function setQuickAnnotation(relevance) {
    const manager = getActiveAnnotationManager();
    if (manager) {
        manager.setPopoverRelevance(relevance);
    }
}

/**
 * Set requirement type (from toolbar)
 */
function setRequirementType(requirement) {
    const manager = getActiveAnnotationManager();
    if (manager) {
        manager.setPopoverRequirement(requirement);
    }
}

/**
 * Set passion level (from toolbar)
 */
function setQuickPassion(passion) {
    const manager = getActiveAnnotationManager();
    if (manager) {
        manager.setPopoverPassion(passion);
    }
}

/**
 * Set identity level (from toolbar)
 */
function setQuickIdentity(identity) {
    const manager = getActiveAnnotationManager();
    if (manager) {
        manager.setPopoverIdentity(identity);
    }
}

/**
 * Set relevance in popover
 */
function setPopoverRelevance(relevance) {
    const manager = getActiveAnnotationManager();
    if (manager) {
        manager.setPopoverRelevance(relevance);
    }
}

/**
 * Set requirement in popover
 */
function setPopoverRequirement(requirement) {
    const manager = getActiveAnnotationManager();
    if (manager) {
        manager.setPopoverRequirement(requirement);
    }
}

/**
 * Set passion level in popover
 */
function setPopoverPassion(passion) {
    const manager = getActiveAnnotationManager();
    if (manager) {
        manager.setPopoverPassion(passion);
    }
}

/**
 * Set identity level in popover
 */
function setPopoverIdentity(identity) {
    const manager = getActiveAnnotationManager();
    if (manager) {
        manager.setPopoverIdentity(identity);
    }
}

/**
 * Save annotation from popover
 */
function saveAnnotationFromPopover() {
    const manager = getActiveAnnotationManager();
    if (manager) {
        manager.createAnnotationFromPopover();
    }
}

/**
 * Delete annotation from popover (when editing existing annotation)
 */
function deleteAnnotationFromPopover() {
    const manager = getActiveAnnotationManager();
    if (!manager) return;

    const annotationId = manager.editingAnnotationId;
    if (!annotationId) {
        console.warn('No annotation being edited to delete');
        return;
    }

    // Delete the annotation immediately (Gmail undo pattern - no confirmation needed)
    manager.deleteAnnotation(annotationId);

    // Hide the popover - no save needed since we just deleted
    hideAnnotationPopover({ save: false });
}

// Export to window for HTML onclick handlers
window.deleteAnnotationFromPopover = deleteAnnotationFromPopover;

/**
 * Get the active annotation manager instance.
 * Works in both job detail page (annotationManager) and batch page (batchAnnotationManager) contexts.
 * @returns {AnnotationManager|null} The active annotation manager or null
 */
function getActiveAnnotationManager() {
    // Check batch context first (if batchAnnotationManager exists and is active)
    // IMPORTANT: Use window.batchAnnotationManager since it's defined in batch-sidebars.js
    // and exposed on window for cross-file accessibility. This fixes the critical bug
    // where annotations were disappearing on batch page (variable scope issue).
    if (window.batchAnnotationManager) {
        return window.batchAnnotationManager;
    }
    // Fall back to job detail page context (annotationManager is in same file, so direct access works)
    if (typeof annotationManager !== 'undefined' && annotationManager) {
        return annotationManager;
    }
    return null;
}

// Export for use in onclick handlers
window.getActiveAnnotationManager = getActiveAnnotationManager;

// ============================================================================
// Annotation Suggestion System
// ============================================================================

/**
 * Rebuild annotation priors from all historical annotations.
 *
 * This recomputes the sentence embeddings and skill priors used by
 * the auto-annotation system. Typically takes 15-60 seconds depending
 * on the number of historical annotations (~3000).
 *
 * Use this when:
 * - You've made many new manual annotations
 * - The auto-annotation accuracy seems off
 * - After initial system setup
 */
async function rebuildPriors() {
    // Support both panel mode (no prefix) and sidebar mode (batch- prefix)
    const btn = document.getElementById('rebuild-priors-btn') ||
                document.getElementById('batch-rebuild-priors-btn');
    const originalContent = btn ? btn.innerHTML : '';

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `
            <svg class="animate-spin w-3 h-3 sm:w-4 sm:h-4 sm:mr-1.5" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <span class="hidden sm:inline">Rebuilding...</span>
        `;
    }

    try {
        const response = await fetch('/api/runner/user/annotation-priors/rebuild', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.error || `HTTP ${response.status}`);
        }

        const data = await response.json();

        if (data.success) {
            showToast(`Rebuilt priors: ${data.annotations_indexed} annotations indexed`, 'success');
        } else {
            throw new Error(data.error || 'Unknown error');
        }
    } catch (error) {
        console.error('Error rebuilding priors:', error);
        showToast(`Rebuild failed: ${error.message}`, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalContent;
        }
    }
}

// Export rebuild function to window
window.rebuildPriors = rebuildPriors;

/**
 * Generate annotations automatically using the annotation suggestion system.
 *
 * This function calls the runner service to generate annotations based on:
 * - Sentence embeddings matching against historical annotation patterns
 * - Skill priors learned from user feedback
 * - Master CV skills and responsibilities
 *
 * Only generates annotations for JD items that match the user's profile.
 */
async function generateAnnotations() {
    // Use getActiveAnnotationManager to work in both detail page and batch page contexts
    const manager = getActiveAnnotationManager();
    if (!manager) {
        console.error('Annotation manager not initialized');
        return;
    }

    // Support both panel mode (no prefix) and sidebar mode (batch- prefix)
    const btn = document.getElementById('generate-annotations-btn') ||
                document.getElementById('batch-generate-annotations-btn');
    const originalContent = btn ? btn.innerHTML : '';

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `
            <svg class="animate-spin w-3 h-3 sm:w-4 sm:h-4 sm:mr-1.5" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <span class="hidden sm:inline">Generating...</span>
        `;
    }

    try {
        const response = await fetch(`/api/runner/jobs/${manager.jobId}/generate-annotations`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.error || `HTTP ${response.status}`);
        }

        const data = await response.json();

        if (data.success) {
            // Reload annotations to show the newly created ones
            await manager.loadAnnotations();

            // Show success message
            const msg = `Created ${data.created} annotations (${data.skipped} JD items skipped - no match found)`;
            console.log('Auto-annotation result:', data);

            // Show toast notification if available
            if (window.showToast) {
                window.showToast(msg, 'success');
            } else {
                alert(msg);
            }
        } else {
            throw new Error(data.error || 'Unknown error');
        }
    } catch (error) {
        console.error('Error generating annotations:', error);
        if (window.showToast) {
            window.showToast(`Failed to generate annotations: ${error.message}`, 'error');
        } else {
            alert(`Failed to generate annotations: ${error.message}`);
        }
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalContent;
        }
    }
}
window.generateAnnotations = generateAnnotations;

/**
 * Filter annotations
 */
function filterAnnotations(filter) {
    if (annotationManager) {
        annotationManager.setFilter(filter);
    }
}

/**
 * Toggle annotation view (viewer vs list)
 */
function toggleAnnotationView(view) {
    const viewerBtn = document.getElementById('view-toggle-viewer');
    const listBtn = document.getElementById('view-toggle-list');
    const viewerContainer = document.getElementById('jd-viewer-container');
    const listContainer = document.getElementById('annotation-list-container');

    if (view === 'viewer') {
        viewerBtn?.classList.add('bg-indigo-100', 'text-indigo-800');
        viewerBtn?.classList.remove('bg-gray-100', 'text-gray-600');
        listBtn?.classList.remove('bg-indigo-100', 'text-indigo-800');
        listBtn?.classList.add('bg-gray-100', 'text-gray-600');
        viewerContainer?.classList.remove('hidden');
        listContainer?.classList.add('hidden', 'lg:block');
    } else {
        listBtn?.classList.add('bg-indigo-100', 'text-indigo-800');
        listBtn?.classList.remove('bg-gray-100', 'text-gray-600');
        viewerBtn?.classList.remove('bg-indigo-100', 'text-indigo-800');
        viewerBtn?.classList.add('bg-gray-100', 'text-gray-600');
        viewerContainer?.classList.add('hidden');
        listContainer?.classList.remove('hidden');
        listContainer?.classList.remove('lg:block');
    }
}

/**
 * Process JD for annotation using LLM
 */
async function processJDForAnnotation() {
    if (!annotationManager) return;

    const btn = document.getElementById('process-jd-btn');

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="animate-spin">⏳</span> Structuring...';
    }

    try {
        const response = await fetch(`/api/jobs/${annotationManager.jobId}/process-jd`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ use_llm: true })
        });

        if (!response.ok) throw new Error('Failed to process JD');

        const data = await response.json();
        if (data.success && data.processed_jd) {
            annotationManager.processedJdHtml = data.processed_jd.html;
            annotationManager.renderProcessedJd();
        }
    } catch (error) {
        console.error('Error processing JD:', error);
        alert('Failed to structure job description');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `
                <svg class="w-3 h-3 sm:w-4 sm:h-4 sm:mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16m-7 6h7"/>
                </svg>
                <span class="hidden sm:inline">Structure JD</span>
            `;
        }
    }
}

/**
 * Generate improvement suggestions
 */
async function generateSuggestions() {
    if (!annotationManager) return;

    const btn = document.getElementById('generate-suggestions-btn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="animate-spin">⏳</span> Generating...';
    }

    try {
        const response = await fetch(`/api/jobs/${annotationManager.jobId}/generate-suggestions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        if (!response.ok) throw new Error('Failed to generate suggestions');

        const data = await response.json();
        if (data.success) {
            // TODO: Show suggestions modal with proper UI
            console.log('Generated suggestions:', data.suggestions);
            if (data.gap_count === 0) {
                alert('No gaps found. Add annotations with relevance "Gap" to identify skills you need to address.');
            } else {
                alert(`Generated suggestions: ${data.gap_count} gap${data.gap_count > 1 ? 's' : ''} identified.\n\nCheck the console for details.`);
            }
        }
    } catch (error) {
        console.error('Error generating suggestions:', error);
        alert('Failed to generate suggestions');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `
                <svg class="w-3 h-3 sm:w-4 sm:h-4 sm:mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/>
                </svg>
                <span class="hidden sm:inline">Suggestions</span>
            `;
        }
    }
}
