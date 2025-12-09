/**
 * JD Annotation System - JavaScript Implementation
 *
 * Features:
 * - Text selection and annotation creation
 * - Annotation highlighting with relevance-based colors
 * - Auto-save with 3-second debounce
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

const AUTOSAVE_DELAY = 3000; // 3 seconds

// ============================================================================
// Annotation Manager Class
// ============================================================================

class AnnotationManager {
    constructor(jobId) {
        this.jobId = jobId;
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
            starIds: [],
            reframeNote: '',
            keywords: ''
        };
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

            // Get raw JD from job data
            let rawJd = null;
            if (jobRes.ok) {
                const jobData = await jobRes.json();
                const job = jobData.job || jobData;
                rawJd = job.extracted_jd || job.description || job.job_description || null;
            }

            if (!annotationsRes.ok) throw new Error('Failed to load annotations');

            const data = await annotationsRes.json();
            if (data.success && data.annotations) {
                this.annotations = data.annotations.annotations || [];
                this.processedJdHtml = data.annotations.processed_jd_html;
                this.settings = data.annotations.settings || this.settings;

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
     * Show raw JD with preserved whitespace formatting
     */
    showRawJd(rawJd) {
        const loadingEl = document.getElementById('jd-loading');
        const emptyEl = document.getElementById('jd-empty');
        const contentEl = document.getElementById('jd-processed-content');

        if (loadingEl) loadingEl.classList.add('hidden');
        if (emptyEl) emptyEl.classList.add('hidden');

        if (contentEl) {
            // Convert plain text to HTML with preserved whitespace
            // - Escape HTML entities
            // - Convert newlines to <br> or use <pre> style
            // - Preserve multiple spaces
            const escapedJd = rawJd
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/\n/g, '<br>');

            contentEl.innerHTML = `
                <div class="raw-jd-content p-4 text-sm text-gray-700 leading-relaxed" style="white-space: pre-wrap; word-wrap: break-word;">
                    <div class="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-lg text-blue-700 text-xs">
                        <strong>Tip:</strong> Click "Process JD" above to parse sections and enable text selection for annotations.
                    </div>
                    ${escapedJd}
                </div>
            `;
            contentEl.classList.remove('hidden');
        }
    }

    /**
     * Show empty state (hides loading, shows empty message)
     */
    showEmptyState() {
        const loadingEl = document.getElementById('jd-loading');
        const emptyEl = document.getElementById('jd-empty');
        const contentEl = document.getElementById('jd-processed-content');

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
                       onchange="annotationManager.updatePopoverStars()">
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
        // Text selection in JD viewer
        const jdViewer = document.getElementById('jd-processed-content');
        if (jdViewer) {
            jdViewer.addEventListener('mouseup', (e) => this.handleTextSelection(e));
        }

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                hideAnnotationPopover();
            }
        });

        // Click outside popover to close
        document.addEventListener('click', (e) => {
            const popover = document.getElementById('annotation-popover');
            const jdViewer = document.getElementById('jd-processed-content');
            if (popover && !popover.classList.contains('hidden') &&
                !popover.contains(e.target) && !jdViewer?.contains(e.target)) {
                hideAnnotationPopover();
            }
        });
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
        this.popoverState.selectedRange = range.cloneRange();

        // Reset popover state
        this.popoverState.relevance = null;
        this.popoverState.requirement = null;
        this.popoverState.starIds = [];
        this.popoverState.reframeNote = '';
        this.popoverState.keywords = '';

        // Show popover
        this.showAnnotationPopover(rect, selectedText);
    }

    /**
     * Show annotation popover at position
     */
    showAnnotationPopover(rect, selectedText) {
        const popover = document.getElementById('annotation-popover');
        if (!popover) return;

        // Update selected text display
        const textEl = document.getElementById('popover-selected-text');
        if (textEl) textEl.textContent = selectedText;

        // Reset form state
        this.resetPopoverForm();

        // Position popover
        const popoverWidth = 320;
        const popoverHeight = popover.offsetHeight || 400;

        let left = rect.left + (rect.width / 2) - (popoverWidth / 2);
        let top = rect.bottom + 10;

        // Keep within viewport
        if (left < 10) left = 10;
        if (left + popoverWidth > window.innerWidth - 10) {
            left = window.innerWidth - popoverWidth - 10;
        }
        if (top + popoverHeight > window.innerHeight - 10) {
            top = rect.top - popoverHeight - 10;
        }

        popover.style.left = `${left}px`;
        popover.style.top = `${top}px`;
        popover.classList.remove('hidden');
    }

    /**
     * Reset popover form to default state
     */
    resetPopoverForm() {
        // Clear button selections
        document.querySelectorAll('.relevance-btn').forEach(btn => {
            btn.classList.remove('ring-2', 'ring-indigo-500');
        });
        document.querySelectorAll('.requirement-btn').forEach(btn => {
            btn.classList.remove('ring-2', 'ring-indigo-500');
        });

        // Clear checkboxes
        document.querySelectorAll('.star-checkbox').forEach(cb => {
            cb.checked = false;
        });

        // Clear inputs
        const reframeEl = document.getElementById('popover-reframe-note');
        const keywordsEl = document.getElementById('popover-keywords');
        if (reframeEl) reframeEl.value = '';
        if (keywordsEl) keywordsEl.value = '';

        // Disable save button
        const saveBtn = document.getElementById('popover-save-btn');
        if (saveBtn) saveBtn.disabled = true;
    }

    /**
     * Set relevance in popover
     */
    setPopoverRelevance(relevance) {
        this.popoverState.relevance = relevance;

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
     * Update selected STAR stories in popover
     */
    updatePopoverStars() {
        const checkboxes = document.querySelectorAll('.star-checkbox:checked');
        this.popoverState.starIds = Array.from(checkboxes).map(cb => cb.value);
        this.updatePopoverSaveButton();
    }

    /**
     * Update save button enabled state
     */
    updatePopoverSaveButton() {
        const saveBtn = document.getElementById('popover-save-btn');
        if (saveBtn) {
            // Enable if relevance is selected (requirement defaults to neutral)
            saveBtn.disabled = !this.popoverState.relevance;
        }
    }

    /**
     * Create annotation from popover state
     */
    createAnnotationFromPopover() {
        const reframeEl = document.getElementById('popover-reframe-note');
        const keywordsEl = document.getElementById('popover-keywords');

        const annotation = {
            id: this.generateId(),
            target: {
                text: this.popoverState.selectedText,
                section: this.getSelectedSection(),
                char_start: 0, // Would need more complex DOM tracking
                char_end: this.popoverState.selectedText.length
            },
            annotation_type: 'skill_match',
            relevance: this.popoverState.relevance,
            requirement_type: this.popoverState.requirement || 'neutral',
            star_ids: this.popoverState.starIds,
            reframe_note: reframeEl?.value || '',
            suggested_keywords: keywordsEl?.value.split(',').map(k => k.trim()).filter(k => k) || [],
            is_active: true,
            priority: 3,
            source: 'manual',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString()
        };

        // Add to annotations
        this.annotations.push(annotation);

        // Re-render
        this.renderAnnotations();
        this.applyHighlights();
        this.updateStats();

        // Schedule save
        this.scheduleSave();

        // Hide popover
        hideAnnotationPopover();

        console.log('Created annotation:', annotation);
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
        const container = document.getElementById('annotation-items');
        const emptyState = document.getElementById('annotation-list-empty');

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
        const countEl = document.getElementById('annotation-list-count');
        if (countEl) countEl.textContent = filtered.length;
    }

    /**
     * Get filtered annotations based on current filter
     */
    getFilteredAnnotations() {
        if (this.currentFilter === 'all') return this.annotations;

        return this.annotations.filter(ann => {
            switch (this.currentFilter) {
                case 'core_strength':
                case 'extremely_relevant':
                case 'relevant':
                case 'tangential':
                case 'gap':
                    return ann.relevance === this.currentFilter;
                case 'must_have':
                case 'nice_to_have':
                    return ann.requirement_type === this.currentFilter;
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
        const colors = RELEVANCE_COLORS[annotation.relevance] || RELEVANCE_COLORS.relevant;
        const reqColors = REQUIREMENT_COLORS[annotation.requirement_type] || REQUIREMENT_COLORS.neutral;

        return `
            <div class="annotation-item p-3 border-b border-gray-100 hover:bg-gray-50 cursor-pointer transition ${!annotation.is_active ? 'opacity-50' : ''}"
                 data-annotation-id="${annotation.id}"
                 onclick="annotationManager.selectAnnotation('${annotation.id}')">
                <div class="flex items-start justify-between gap-2">
                    <div class="flex-1 min-w-0">
                        <div class="flex items-center gap-2 mb-1">
                            <span class="px-1.5 py-0.5 rounded text-xs font-medium ${colors.bg} ${colors.text}">
                                ${this.formatRelevance(annotation.relevance)}
                            </span>
                            <span class="px-1.5 py-0.5 rounded text-xs font-medium ${reqColors.bg} ${reqColors.text}">
                                ${this.formatRequirement(annotation.requirement_type)}
                            </span>
                        </div>
                        <p class="text-sm text-gray-800 line-clamp-2">${annotation.target?.text || ''}</p>
                        ${annotation.reframe_note ? `<p class="text-xs text-gray-500 mt-1 italic line-clamp-1">${annotation.reframe_note}</p>` : ''}
                    </div>
                    <div class="flex items-center gap-1">
                        <button onclick="event.stopPropagation(); annotationManager.toggleActive('${annotation.id}')"
                                class="p-1 rounded hover:bg-gray-200"
                                title="${annotation.is_active ? 'Deactivate' : 'Activate'}">
                            <svg class="w-4 h-4 ${annotation.is_active ? 'text-green-500' : 'text-gray-300'}" fill="currentColor" viewBox="0 0 20 20">
                                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
                            </svg>
                        </button>
                        <button onclick="event.stopPropagation(); annotationManager.deleteAnnotation('${annotation.id}')"
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
            this.applyHighlights();
            this.updateStats();
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
            this.applyHighlights();
            this.updateStats();
            this.scheduleSave();
        }
    }

    /**
     * Select annotation (scroll to and highlight)
     */
    selectAnnotation(annotationId) {
        // TODO: Scroll to highlighted text in JD viewer
        console.log('Selected annotation:', annotationId);
    }

    /**
     * Apply highlights to JD content
     */
    applyHighlights() {
        // TODO: Apply CSS highlight classes to annotated text
        // This requires tracking character offsets in the processed HTML
    }

    /**
     * Render processed JD HTML
     */
    renderProcessedJd() {
        const loadingEl = document.getElementById('jd-loading');
        const emptyEl = document.getElementById('jd-empty');
        const contentEl = document.getElementById('jd-processed-content');

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
        const countEl = document.getElementById('annotation-count');
        const activeCountEl = document.getElementById('active-annotation-count');

        if (countEl) countEl.textContent = `${this.annotations.length} annotations`;
        if (activeCountEl) {
            const activeCount = this.annotations.filter(a => a.is_active).length;
            activeCountEl.textContent = `${activeCount} active`;
        }

        // Update coverage
        this.updateCoverage();

        // Update boost preview
        this.updateBoostPreview();
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

        const barEl = document.getElementById('annotation-coverage-bar');
        const pctEl = document.getElementById('annotation-coverage-pct');

        if (barEl) barEl.style.width = `${coverage}%`;
        if (pctEl) pctEl.textContent = `${coverage}%`;
    }

    /**
     * Update boost preview
     */
    updateBoostPreview() {
        const boostEl = document.getElementById('total-boost-value');
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
        const indicator = document.getElementById('annotation-save-indicator');
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

    // Hide popover
    hideAnnotationPopover();
}

/**
 * Hide annotation popover
 */
function hideAnnotationPopover() {
    const popover = document.getElementById('annotation-popover');
    if (popover) popover.classList.add('hidden');
}

/**
 * Set quick annotation (from toolbar)
 */
function setQuickAnnotation(relevance) {
    if (annotationManager) {
        annotationManager.setPopoverRelevance(relevance);
    }
}

/**
 * Set requirement type (from toolbar)
 */
function setRequirementType(requirement) {
    if (annotationManager) {
        annotationManager.setPopoverRequirement(requirement);
    }
}

/**
 * Set relevance in popover
 */
function setPopoverRelevance(relevance) {
    if (annotationManager) {
        annotationManager.setPopoverRelevance(relevance);
    }
}

/**
 * Set requirement in popover
 */
function setPopoverRequirement(requirement) {
    if (annotationManager) {
        annotationManager.setPopoverRequirement(requirement);
    }
}

/**
 * Save annotation from popover
 */
function saveAnnotationFromPopover() {
    if (annotationManager) {
        annotationManager.createAnnotationFromPopover();
    }
}

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
 * Process JD for annotation
 */
async function processJDForAnnotation() {
    if (!annotationManager) return;

    const btn = document.getElementById('process-jd-btn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="animate-spin">⏳</span> Processing...';
    }

    try {
        const response = await fetch(`/api/jobs/${annotationManager.jobId}/process-jd`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ use_llm: false })
        });

        if (!response.ok) throw new Error('Failed to process JD');

        const data = await response.json();
        if (data.success && data.processed_jd) {
            annotationManager.processedJdHtml = data.processed_jd.html;
            annotationManager.renderProcessedJd();
        }
    } catch (error) {
        console.error('Error processing JD:', error);
        alert('Failed to process job description');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `
                <svg class="w-3 h-3 sm:w-4 sm:h-4 sm:mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16m-7 6h7"/>
                </svg>
                <span class="hidden sm:inline">Process JD</span>
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
            // TODO: Show suggestions modal
            console.log('Generated suggestions:', data.suggestions);
            alert(`Generated suggestions: ${data.gap_count} gaps identified`);
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
