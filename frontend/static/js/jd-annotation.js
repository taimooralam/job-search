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
    core_strength: { bg: 'bg-green-200', border: 'border-green-400', text: 'text-green-800' },
    extremely_relevant: { bg: 'bg-emerald-200', border: 'border-emerald-400', text: 'text-emerald-800' },
    relevant: { bg: 'bg-yellow-200', border: 'border-yellow-400', text: 'text-yellow-800' },
    tangential: { bg: 'bg-orange-200', border: 'border-orange-400', text: 'text-orange-800' },
    gap: { bg: 'bg-red-200', border: 'border-red-400', text: 'text-red-800' }
};

const REQUIREMENT_COLORS = {
    must_have: { bg: 'bg-blue-100', text: 'text-blue-700' },
    nice_to_have: { bg: 'bg-gray-100', text: 'text-gray-600' },
    neutral: { bg: 'bg-gray-50', text: 'text-gray-500' },
    disqualifier: { bg: 'bg-red-100', text: 'text-red-700' }
};

const AUTOSAVE_DELAY = 1000; // 1 second (reduced for smoother UX)

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
            personaPanelId: config.personaPanelId || 'persona-panel-container'
        };
        this.annotations = [];
        this.processedJdHtml = null;
        this.settings = {
            auto_highlight: true,
            show_confidence: true,
            min_confidence_threshold: 0.5
        };
        this.saveTimeout = null;
        this.currentFilter = 'all';
        this.starStories = [];
        this.popoverState = {
            selectedText: '',
            selectedRange: null,
            relevance: null,
            requirement: null,
            passion: 'neutral',      // Default to neutral passion
            identity: 'peripheral',  // Default to peripheral identity
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
            unavailable: false  // True when on Vercel (LangChain not available)
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

        // Render initial state
        this.renderAnnotations();
        this.updateStats();
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
                this.annotations = (data.annotations.annotations || []).map(ann => ({
                    ...ann,
                    is_active: ann.is_active !== false  // Default to true unless explicitly false
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

            if (!response.ok) throw new Error('Failed to save annotations');

            this.updateSaveIndicator('saved');
            console.log('Annotations saved successfully');

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
                if (e.target.closest('.annotation-highlight')) {
                    mouseDownPos = null;
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

        // Get position for popover
        const rect = sentenceRange.getBoundingClientRect();

        // Store selection state
        this.popoverState.selectedText = sentence;
        this.popoverState.originalText = sentence;  // Original JD text for highlighting
        this.popoverState.selectedRange = sentenceRange.cloneRange();

        // Reset popover state
        this.popoverState.relevance = null;
        this.popoverState.requirement = null;
        this.popoverState.passion = 'neutral';
        this.popoverState.identity = 'peripheral';
        this.popoverState.starIds = [];
        this.popoverState.reframeNote = '';
        this.popoverState.keywords = '';
        this.popoverState.hasExplicitRelevance = false;
        this.popoverState.hasExplicitRequirement = false;
        this.popoverState.hasExplicitPassion = false;
        this.popoverState.hasExplicitIdentity = false;

        // Show popover
        console.log('[SmartSelect] Showing popover for sentence');
        this.showAnnotationPopover(rect, sentence);
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
     */
    handleTextSelection(event) {
        const selection = window.getSelection();
        const selectedText = selection.toString().trim();

        if (selectedText.length < 3) {
            return; // Ignore very short selections
        }

        // Get selection position for popover
        const range = selection.getRangeAt(0);
        const rect = range.getBoundingClientRect();

        // Store selection state
        this.popoverState.selectedText = selectedText;
        this.popoverState.originalText = selectedText;  // Original JD text for highlighting
        this.popoverState.selectedRange = range.cloneRange();

        // Reset popover state
        this.popoverState.relevance = null;
        this.popoverState.requirement = null;
        this.popoverState.passion = 'neutral';
        this.popoverState.identity = 'peripheral';
        this.popoverState.starIds = [];
        this.popoverState.reframeNote = '';
        this.popoverState.keywords = '';
        // Reset explicit selection flags
        this.popoverState.hasExplicitRelevance = false;
        this.popoverState.hasExplicitRequirement = false;
        this.popoverState.hasExplicitPassion = false;
        this.popoverState.hasExplicitIdentity = false;

        // Show popover
        this.showAnnotationPopover(rect, selectedText);
    }

    /**
     * Show annotation popover at position
     */
    showAnnotationPopover(rect, selectedText, editingAnnotation = null) {
        const popover = document.getElementById(this.config.popoverId);
        if (!popover) return;

        // Store editing state
        this.editingAnnotationId = editingAnnotation?.id || null;

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

        // Reset form state first
        this.resetPopoverForm();

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
     * Populate popover with existing annotation data for editing
     */
    populatePopoverWithAnnotation(annotation) {
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

        // Store state
        this.popoverState.selectedText = annotation.target?.text || '';
        this.popoverState.relevance = annotation.relevance;
        this.popoverState.requirement = annotation.requirement_type;
        this.popoverState.passion = annotation.passion || 'neutral';
        this.popoverState.identity = annotation.identity || 'peripheral';
        this.popoverState.reframeNote = annotation.reframe_note || '';
        this.popoverState.strategicNote = annotation.strategic_note || '';
        this.popoverState.keywords = annotation.suggested_keywords?.join(', ') || '';
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

        // Reset editing state
        this.editingAnnotationId = null;

        // Disable save button
        const saveBtn = document.getElementById('popover-save-btn');
        if (saveBtn) saveBtn.disabled = true;

        // Hide delete button
        const deleteBtn = document.getElementById('popover-delete-btn');
        if (deleteBtn) deleteBtn.classList.add('hidden');
    }

    /**
     * Set relevance in popover
     */
    setPopoverRelevance(relevance) {
        this.popoverState.relevance = relevance;
        this.popoverState.hasExplicitRelevance = true;

        // Update button states
        document.querySelectorAll('.relevance-btn').forEach(btn => {
            if (btn.dataset.relevance === relevance) {
                btn.classList.add('ring-2', 'ring-indigo-500');
            } else {
                btn.classList.remove('ring-2', 'ring-indigo-500');
            }
        });

        this.updatePopoverSaveButton();
    }

    /**
     * Set requirement type in popover
     */
    setPopoverRequirement(requirement) {
        this.popoverState.requirement = requirement;
        this.popoverState.hasExplicitRequirement = true;

        // Update button states
        document.querySelectorAll('.requirement-btn').forEach(btn => {
            if (btn.dataset.requirement === requirement) {
                btn.classList.add('ring-2', 'ring-indigo-500');
            } else {
                btn.classList.remove('ring-2', 'ring-indigo-500');
            }
        });

        this.updatePopoverSaveButton();
    }

    /**
     * Set passion level in popover
     */
    setPopoverPassion(passion) {
        this.popoverState.passion = passion;
        this.popoverState.hasExplicitPassion = true;

        // Update button states
        document.querySelectorAll('.passion-btn').forEach(btn => {
            if (btn.dataset.passion === passion) {
                btn.classList.add('ring-2', 'ring-indigo-500');
            } else {
                btn.classList.remove('ring-2', 'ring-indigo-500');
            }
        });

        this.updatePopoverSaveButton();
    }

    /**
     * Set identity level in popover
     */
    setPopoverIdentity(identity) {
        this.popoverState.identity = identity;
        this.popoverState.hasExplicitIdentity = true;

        // Update button states
        document.querySelectorAll('.identity-btn').forEach(btn => {
            if (btn.dataset.identity === identity) {
                btn.classList.add('ring-2', 'ring-indigo-500');
            } else {
                btn.classList.remove('ring-2', 'ring-indigo-500');
            }
        });

        this.updatePopoverSaveButton();
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

        if (isEditing) {
            // Update existing annotation
            const index = this.annotations.findIndex(a => a.id === this.editingAnnotationId);
            if (index !== -1) {
                // Preserve original_text for highlighting if it exists, otherwise use current target.text
                const existingOriginalText = this.annotations[index].target?.original_text ||
                                              this.annotations[index].target?.text;
                this.annotations[index] = {
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

            // Add to annotations
            this.annotations.push(annotation);
            console.log('Created annotation:', annotation);
        }

        // Re-render list and stats immediately
        this.renderAnnotations();
        this.updateStats();

        // Apply highlights with slight delay to ensure DOM is stable after list re-render
        // This fixes color not updating when changing relevance (e.g., core -> medium)
        requestAnimationFrame(() => {
            this.applyHighlights();
        });

        // Schedule save
        this.scheduleSave();

        // Show toast feedback
        if (typeof showToast === 'function') {
            showToast(isEditing ? 'Annotation updated' : 'Annotation saved', 'success');
        }

        // Hide popover and reset editing state
        this.editingAnnotationId = null;
        _hidePopover();
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
     */
    renderAnnotations() {
        const container = document.getElementById(this.config.listId);
        const emptyState = document.getElementById(this.config.listEmptyId);

        if (!container) return;

        // Filter annotations
        const filtered = this.getFilteredAnnotations();

        // Show/hide empty state
        if (emptyState) {
            emptyState.classList.toggle('hidden', filtered.length > 0);
        }

        // Render items
        container.innerHTML = filtered.map(ann => this.renderAnnotationItem(ann)).join('');

        // Update count
        const countEl = document.getElementById(this.config.listCountId);
        if (countEl) countEl.textContent = filtered.length;
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

        // Relevance badge - only show if relevance is set (avoid showing "null")
        const relevanceBadge = annotation.relevance
            ? `<span class="px-1.5 py-0.5 rounded text-xs font-medium ${colors.bg} ${colors.text}">
                   ${this.formatRelevance(annotation.relevance)}
               </span>`
            : '';

        return `
            <div class="annotation-item p-3 border-b border-gray-100 hover:bg-gray-50 cursor-pointer transition ${!annotation.is_active ? 'opacity-50' : ''}"
                 data-annotation-id="${annotation.id}"
                 onclick="getActiveAnnotationManager()?.selectAnnotation('${annotation.id}')">
                <div class="flex items-start justify-between gap-2">
                    <div class="flex-1 min-w-0">
                        <div class="flex items-center flex-wrap gap-1 mb-1">
                            ${relevanceBadge}
                            <span class="px-1.5 py-0.5 rounded text-xs font-medium ${reqColors.bg} ${reqColors.text}">
                                ${this.formatRequirement(annotation.requirement_type)}
                            </span>
                            ${passionBadge}
                            ${identityBadge}
                        </div>
                        <p class="text-sm text-gray-800 line-clamp-2">${annotation.target?.text || ''}</p>
                        ${annotation.reframe_note ? `<p class="text-xs text-gray-500 mt-1 italic line-clamp-1">${annotation.reframe_note}</p>` : ''}
                    </div>
                    <div class="flex items-center gap-1">
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
            requestAnimationFrame(() => {
                this.applyHighlights();
            });
            this.scheduleSave();
        }
    }

    /**
     * Delete annotation
     */
    deleteAnnotation(annotationId) {
        const index = this.annotations.findIndex(a => a.id === annotationId);
        if (index !== -1) {
            this.annotations.splice(index, 1);
            this.renderAnnotations();
            this.updateStats();
            // Apply highlights with slight delay to ensure DOM is stable
            requestAnimationFrame(() => {
                this.applyHighlights();
            });
            this.scheduleSave();
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
     * Apply highlights to JD content based on active annotations
     */
    applyHighlights() {
        const contentEl = document.getElementById(this.config.contentId);
        if (!contentEl) {
            console.warn('applyHighlights: Content element not found');
            return;
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
     * Edit annotation from highlight click
     */
    editAnnotationFromHighlight(annotationId, highlightEl) {
        if (!annotationId) return;

        // Find the annotation data
        const annotation = this.annotations.find(a => a.id === annotationId);
        if (!annotation) {
            console.warn('Annotation not found:', annotationId);
            return;
        }

        // Get position from highlight element
        const rect = highlightEl.getBoundingClientRect();

        // Show popover in edit mode
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
     * Render the persona panel UI
     */
    renderPersonaPanel() {
        const container = document.getElementById(this.config.personaPanelId);
        if (!container) return;

        // Check for identity annotations
        this.checkIdentityAnnotations();

        // Hide if no identity annotations
        if (!this.personaState.hasIdentityAnnotations) {
            container.innerHTML = '';
            return;
        }

        const { statement, isLoading, isEditing, isUserEdited, unavailable } = this.personaState;

        // Loading state
        if (isLoading) {
            container.innerHTML = `
                <div class="p-4 bg-indigo-50 rounded-lg border border-indigo-200">
                    <h4 class="font-semibold text-indigo-900 mb-2 flex items-center gap-2">
                        <svg class="animate-spin h-4 w-4 text-indigo-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        Synthesizing Persona...
                    </h4>
                    <p class="text-sm text-indigo-700">Analyzing identity annotations to create your professional positioning...</p>
                </div>
            `;
            return;
        }

        // Unavailable on Vercel - show manual entry option
        if (unavailable && !statement) {
            container.innerHTML = `
                <div class="p-4 bg-amber-50 rounded-lg border border-amber-200">
                    <h4 class="font-semibold text-amber-800 mb-2">Professional Persona</h4>
                    <p class="text-sm text-amber-700 mb-3">
                        AI-powered persona synthesis is not available on this deployment.
                        You can enter your persona statement manually.
                    </p>
                    <button onclick="getActiveAnnotationManager()?.startManualPersonaEntry()"
                            class="px-4 py-2 bg-amber-600 text-white rounded-md hover:bg-amber-700 text-sm font-medium">
                        Enter Persona Manually
                    </button>
                </div>
            `;
            return;
        }

        // No persona yet - show generate button
        if (!statement) {
            container.innerHTML = `
                <div class="p-4 bg-gray-50 rounded-lg border border-gray-200">
                    <h4 class="font-semibold text-gray-700 mb-2">Professional Persona</h4>
                    <p class="text-sm text-gray-600 mb-3">
                        You have identity annotations. Generate a synthesized persona to use in CV, cover letter, and outreach.
                    </p>
                    <button onclick="getActiveAnnotationManager()?.synthesizePersona()"
                            class="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 text-sm font-medium">
                        Generate Persona
                    </button>
                </div>
            `;
            return;
        }

        // Edit mode
        if (isEditing) {
            container.innerHTML = `
                <div class="p-4 bg-indigo-50 rounded-lg border border-indigo-200">
                    <h4 class="font-semibold text-indigo-900 mb-2">Edit Persona</h4>
                    <textarea id="persona-edit-textarea"
                              class="w-full p-3 border border-indigo-300 rounded-md text-sm"
                              rows="3"
                              oninput="getActiveAnnotationManager()?.updatePersonaText(this.value)"
                    >${statement}</textarea>
                    <div class="flex gap-2 mt-3">
                        <button onclick="getActiveAnnotationManager()?.savePersona()"
                                class="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 text-sm font-medium">
                            Save
                        </button>
                        <button onclick="getActiveAnnotationManager()?.cancelEditingPersona()"
                                class="px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-md hover:bg-gray-50 text-sm font-medium">
                            Cancel
                        </button>
                    </div>
                </div>
            `;
            return;
        }

        // Display mode
        const editedBadge = isUserEdited
            ? '<span class="text-xs bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded-full ml-2">edited</span>'
            : '';

        container.innerHTML = `
            <div class="p-4 bg-indigo-50 rounded-lg border border-indigo-200">
                <div class="flex items-center justify-between mb-2">
                    <h4 class="font-semibold text-indigo-900 flex items-center">
                        Synthesized Persona ${editedBadge}
                    </h4>
                    <div class="flex gap-2">
                        <button onclick="getActiveAnnotationManager()?.startEditingPersona()"
                                class="text-sm text-indigo-600 hover:text-indigo-800 hover:underline">
                            Edit
                        </button>
                        <button onclick="getActiveAnnotationManager()?.synthesizePersona()"
                                class="text-sm text-indigo-600 hover:text-indigo-800 hover:underline">
                            Regenerate
                        </button>
                    </div>
                </div>
                <p class="text-indigo-800 italic">"${statement}"</p>
                <p class="text-xs text-indigo-600 mt-2">
                    This persona will be used to frame your CV profile, cover letter opening, and outreach messages.
                </p>
            </div>
        `;
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
            this.applyHighlights();
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
        this.applyHighlights();
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

/**
 * Get the active annotation manager (batch or job detail)
 * Batch annotation manager takes priority when the batch sidebar is open
 */
function getActiveAnnotationManager() {
    // Check for batch annotation manager first (set by batch-sidebars.js)
    if (typeof batchAnnotationManager !== 'undefined' && batchAnnotationManager) {
        return batchAnnotationManager;
    }
    // Fall back to job detail annotation manager
    return annotationManager;
}

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

    // Confirm deletion
    if (!confirm('Are you sure you want to delete this annotation?')) {
        return;
    }

    // Delete the annotation
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
    if (typeof batchAnnotationManager !== 'undefined' && batchAnnotationManager) {
        return batchAnnotationManager;
    }
    // Fall back to job detail page context
    if (typeof annotationManager !== 'undefined' && annotationManager) {
        return annotationManager;
    }
    return null;
}

// Export for use in onclick handlers
window.getActiveAnnotationManager = getActiveAnnotationManager;

// ============================================================================
// Strength Suggestions Feature
// ============================================================================

/**
 * Generate strength suggestions via LLM analysis
 * This identifies skills the candidate HAS that match the JD.
 */
async function generateStrengthSuggestions() {
    if (!annotationManager) {
        console.error('Annotation manager not initialized');
        return;
    }

    const btn = document.getElementById('suggest-strengths-btn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `
            <svg class="animate-spin w-4 h-4 mr-1" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            Analyzing...
        `;
    }

    try {
        const response = await fetch(
            `/api/jobs/${annotationManager.jobId}/suggest-strengths`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    include_identity: true,
                    include_passion: true,
                    include_defaults: true,
                    tier: 'balanced'
                })
            }
        );

        const data = await response.json();

        if (data.unavailable) {
            showToast('Strength suggestion requires the runner service.', 'info');
            return;
        }

        if (!data.success) {
            showToast(data.error || 'Failed to generate suggestions', 'error');
            return;
        }

        if (data.suggestions && data.suggestions.length > 0) {
            showStrengthSuggestionsModal(data.suggestions);
        } else {
            showToast('No strength matches found. Your skills may already be annotated, or try manual annotation.', 'info');
        }
    } catch (error) {
        console.error('Error generating strength suggestions:', error);
        showToast('Failed to generate suggestions', 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `
                <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
                </svg>
                Strengths
            `;
        }
    }
}

/**
 * Display strength suggestions in a modal for review and acceptance
 */
function showStrengthSuggestionsModal(suggestions) {
    // Remove any existing modal
    const existingModal = document.getElementById('strength-suggestions-modal');
    if (existingModal) existingModal.remove();

    const modal = document.createElement('div');
    modal.id = 'strength-suggestions-modal';
    modal.className = 'fixed inset-0 z-50 overflow-y-auto';
    modal.innerHTML = `
        <div class="flex items-center justify-center min-h-screen px-4 pt-4 pb-20 text-center sm:p-0">
            <div class="fixed inset-0 transition-opacity bg-gray-500 bg-opacity-75" onclick="closeStrengthSuggestionsModal()"></div>

            <div class="relative inline-block w-full max-w-3xl p-6 my-8 overflow-hidden text-left align-middle transition-all transform bg-white shadow-xl rounded-xl">
                <div class="flex items-center justify-between mb-4">
                    <h3 class="text-lg font-semibold text-gray-900">
                        <span class="text-green-600">&#10003;</span> Strength Suggestions (${suggestions.length})
                    </h3>
                    <button onclick="closeStrengthSuggestionsModal()" class="text-gray-400 hover:text-gray-600">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                        </svg>
                    </button>
                </div>

                <p class="text-sm text-gray-600 mb-4">
                    These are skills you have that match the job description. Accept to create annotations.
                </p>

                <div class="space-y-3 max-h-96 overflow-y-auto" id="suggestions-list">
                    ${suggestions.map((s, i) => renderSuggestionCard(s, i)).join('')}
                </div>

                <div class="mt-6 flex justify-between items-center">
                    <span class="text-sm text-gray-500" id="accepted-count">0 accepted</span>
                    <div class="space-x-3">
                        <button onclick="closeStrengthSuggestionsModal()"
                                class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50">
                            Close
                        </button>
                        <button onclick="acceptAllStrengthSuggestions()"
                                class="px-4 py-2 text-sm font-medium text-white bg-green-600 rounded-md hover:bg-green-700">
                            Accept All
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    // Store suggestions for later access
    window._strengthSuggestions = suggestions;
    window._acceptedSuggestions = new Set();
}

/**
 * Render a single suggestion card
 */
function renderSuggestionCard(suggestion, index) {
    const relevanceColors = {
        'core_strength': 'bg-green-100 text-green-800',
        'extremely_relevant': 'bg-teal-100 text-teal-800',
        'relevant': 'bg-blue-100 text-blue-800',
        'tangential': 'bg-yellow-100 text-yellow-800',
    };

    const relevanceColor = relevanceColors[suggestion.suggested_relevance] || 'bg-gray-100 text-gray-800';
    const confidencePercent = Math.round(suggestion.confidence * 100);

    return `
        <div class="p-4 border rounded-lg hover:border-green-300 transition-colors" id="suggestion-card-${index}">
            <div class="flex items-start justify-between">
                <div class="flex-1">
                    <div class="flex items-center gap-2 mb-2">
                        <span class="px-2 py-0.5 text-xs font-medium rounded ${relevanceColor}">
                            ${(suggestion.suggested_relevance || '').replace('_', ' ')}
                        </span>
                        <span class="text-xs text-gray-500">${confidencePercent}% confidence</span>
                        ${suggestion.source === 'hardcoded_default' ?
                            '<span class="text-xs text-purple-600">Quick match</span>' :
                            '<span class="text-xs text-blue-600">AI match</span>'}
                    </div>
                    <p class="text-sm text-gray-800 font-medium mb-1">${escapeHtmlForSuggestions(suggestion.matching_skill)}</p>
                    <p class="text-xs text-gray-600 line-clamp-2">"${escapeHtmlForSuggestions(suggestion.target_text.substring(0, 150))}${suggestion.target_text.length > 150 ? '...' : ''}"</p>
                    ${suggestion.suggested_keywords?.length > 0 ?
                        `<div class="flex flex-wrap gap-1 mt-2">
                            ${suggestion.suggested_keywords.slice(0, 4).map(kw =>
                                `<span class="px-1.5 py-0.5 text-xs bg-gray-100 text-gray-600 rounded">${escapeHtmlForSuggestions(kw)}</span>`
                            ).join('')}
                        </div>` : ''}
                </div>
                <div class="flex gap-2 ml-4">
                    <button onclick="acceptStrengthSuggestion(${index})"
                            class="p-2 text-green-600 hover:bg-green-50 rounded-md transition-colors"
                            title="Accept">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
                        </svg>
                    </button>
                    <button onclick="skipStrengthSuggestion(${index})"
                            class="p-2 text-gray-400 hover:bg-gray-50 rounded-md transition-colors"
                            title="Skip">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                        </svg>
                    </button>
                </div>
            </div>
        </div>
    `;
}

/**
 * Accept a single strength suggestion and create annotation
 */
function acceptStrengthSuggestion(index) {
    const suggestion = window._strengthSuggestions[index];
    if (!suggestion || !annotationManager) return;

    // Create annotation from suggestion
    const annotation = {
        id: annotationManager.generateId(),
        target: {
            text: suggestion.target_text,
            section: suggestion.target_section || 'unknown',
            index: 0,
            char_start: 0,
            char_end: suggestion.target_text.length
        },
        annotation_type: 'skill_match',
        relevance: suggestion.suggested_relevance,
        requirement_type: suggestion.suggested_requirement || 'neutral',
        passion: suggestion.suggested_passion || 'neutral',
        identity: suggestion.suggested_identity || 'peripheral',
        matching_skill: suggestion.matching_skill,
        suggested_keywords: suggestion.suggested_keywords || [],
        ats_variants: [],
        reframe_note: suggestion.reframe_note || '',
        has_reframe: !!suggestion.reframe_note,
        star_ids: [],
        evidence_summary: suggestion.evidence_summary || '',
        is_active: true,
        priority: 3,
        confidence: suggestion.confidence,
        created_by: 'pipeline_suggestion',
        status: 'needs_review',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
    };

    annotationManager.annotations.push(annotation);
    window._acceptedSuggestions.add(index);

    // Update UI
    const card = document.getElementById(`suggestion-card-${index}`);
    if (card) {
        card.classList.add('bg-green-50', 'border-green-300');
        const acceptBtn = card.querySelector('button[title="Accept"]');
        if (acceptBtn) {
            acceptBtn.disabled = true;
            acceptBtn.classList.add('opacity-50');
        }
    }

    // Update count
    const countEl = document.getElementById('accepted-count');
    if (countEl) {
        countEl.textContent = `${window._acceptedSuggestions.size} accepted`;
    }

    showToast(`Added: ${suggestion.matching_skill}`, 'success');
}

/**
 * Skip a suggestion (just hide the card)
 */
function skipStrengthSuggestion(index) {
    const card = document.getElementById(`suggestion-card-${index}`);
    if (card) {
        card.style.display = 'none';
    }
}

/**
 * Accept all suggestions at once
 */
function acceptAllStrengthSuggestions() {
    if (!window._strengthSuggestions) return;

    window._strengthSuggestions.forEach((_, index) => {
        if (!window._acceptedSuggestions.has(index)) {
            acceptStrengthSuggestion(index);
        }
    });

    // Close modal and save
    closeStrengthSuggestionsModal();
}

/**
 * Close the suggestions modal and save annotations
 */
function closeStrengthSuggestionsModal() {
    const modal = document.getElementById('strength-suggestions-modal');
    if (modal) {
        modal.remove();
    }

    // Save and refresh if any suggestions were accepted
    if (window._acceptedSuggestions && window._acceptedSuggestions.size > 0) {
        annotationManager.renderAnnotations();
        annotationManager.applyHighlights();
        annotationManager.updateStats();
        annotationManager.scheduleSave();
        showToast(`${window._acceptedSuggestions.size} annotations added`, 'success');
    }

    // Cleanup
    window._strengthSuggestions = null;
    window._acceptedSuggestions = null;
}

/**
 * Helper to escape HTML for suggestion rendering
 */
function escapeHtmlForSuggestions(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Export strength suggestion functions to window
window.generateStrengthSuggestions = generateStrengthSuggestions;
window.showStrengthSuggestionsModal = showStrengthSuggestionsModal;
window.acceptStrengthSuggestion = acceptStrengthSuggestion;
window.skipStrengthSuggestion = skipStrengthSuggestion;
window.acceptAllStrengthSuggestions = acceptAllStrengthSuggestions;
window.closeStrengthSuggestionsModal = closeStrengthSuggestionsModal;

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
