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
            isUserEdited: false
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
                this.annotations = data.annotations.annotations || [];
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
        const loadingEl = document.getElementById('jd-loading');
        const emptyEl = document.getElementById('jd-empty');
        const contentEl = document.getElementById('jd-processed-content');

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

        // Click outside popover to close - use mousedown for better UX
        document.addEventListener('mousedown', (e) => {
            const popover = document.getElementById('annotation-popover');
            if (!popover || popover.classList.contains('hidden')) return;

            // If clicking inside the popover, don't close
            if (popover.contains(e.target)) return;

            // If clicking on an annotation highlight, let the click handler manage it
            if (e.target.closest('.annotation-highlight')) return;

            // Close popover for any other click
            hideAnnotationPopover();
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
        const popover = document.getElementById('annotation-popover');
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

        // Update selected text display
        const textEl = document.getElementById('popover-selected-text');
        if (textEl) textEl.textContent = selectedText;

        // Reset form state first
        this.resetPopoverForm();

        // If editing, populate with existing values
        if (editingAnnotation) {
            this.populatePopoverWithAnnotation(editingAnnotation);
        }

        // Position popover - account for panel boundaries
        const panel = document.getElementById('jd-annotation-panel');
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

        // Set STAR stories
        if (annotation.star_ids && annotation.star_ids.length > 0) {
            annotation.star_ids.forEach(starId => {
                const checkbox = document.querySelector(`.star-checkbox[value="${starId}"]`);
                if (checkbox) checkbox.checked = true;
            });
            this.popoverState.starIds = annotation.star_ids;
        }

        // Set reframe note
        const reframeEl = document.getElementById('popover-reframe-note');
        if (reframeEl && annotation.reframe_note) {
            reframeEl.value = annotation.reframe_note;
        }

        // Set strategic note
        const strategicEl = document.getElementById('popover-strategic-note');
        if (strategicEl && annotation.strategic_note) {
            strategicEl.value = annotation.strategic_note;
        }

        // Set keywords
        const keywordsEl = document.getElementById('popover-keywords');
        if (keywordsEl && annotation.suggested_keywords) {
            keywordsEl.value = annotation.suggested_keywords.join(', ');
        }

        // Store state
        this.popoverState.selectedText = annotation.target?.text || '';
        this.popoverState.relevance = annotation.relevance;
        this.popoverState.requirement = annotation.requirement_type;
        this.popoverState.reframeNote = annotation.reframe_note || '';
        this.popoverState.strategicNote = annotation.strategic_note || '';
        this.popoverState.keywords = annotation.suggested_keywords?.join(', ') || '';
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
        const strategicEl = document.getElementById('popover-strategic-note');
        if (reframeEl) reframeEl.value = '';
        if (keywordsEl) keywordsEl.value = '';
        if (strategicEl) strategicEl.value = '';

        // Reset editing state
        this.editingAnnotationId = null;

        // Disable save button
        const saveBtn = document.getElementById('popover-save-btn');
        if (saveBtn) saveBtn.disabled = true;
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

        const isEditing = !!this.editingAnnotationId;

        if (isEditing) {
            // Update existing annotation
            const index = this.annotations.findIndex(a => a.id === this.editingAnnotationId);
            if (index !== -1) {
                this.annotations[index] = {
                    ...this.annotations[index],
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
                    text: this.popoverState.selectedText,
                    section: this.getSelectedSection(),
                    char_start: 0, // Would need more complex DOM tracking
                    char_end: this.popoverState.selectedText.length
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

        // Re-render
        this.renderAnnotations();
        this.applyHighlights();
        this.updateStats();

        // Schedule save
        this.scheduleSave();

        // Hide popover and reset editing state
        this.editingAnnotationId = null;
        hideAnnotationPopover();
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
        const colors = RELEVANCE_COLORS[annotation.relevance] || RELEVANCE_COLORS.relevant;
        const reqColors = REQUIREMENT_COLORS[annotation.requirement_type] || REQUIREMENT_COLORS.neutral;

        // Passion badge (only show for non-neutral)
        const passionBadge = this.getPassionBadge(annotation.passion);
        // Identity badge (only show for non-peripheral)
        const identityBadge = this.getIdentityBadge(annotation.identity);

        return `
            <div class="annotation-item p-3 border-b border-gray-100 hover:bg-gray-50 cursor-pointer transition ${!annotation.is_active ? 'opacity-50' : ''}"
                 data-annotation-id="${annotation.id}"
                 onclick="annotationManager.selectAnnotation('${annotation.id}')">
                <div class="flex items-start justify-between gap-2">
                    <div class="flex-1 min-w-0">
                        <div class="flex items-center flex-wrap gap-1 mb-1">
                            <span class="px-1.5 py-0.5 rounded text-xs font-medium ${colors.bg} ${colors.text}">
                                ${this.formatRelevance(annotation.relevance)}
                            </span>
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
        const contentEl = document.getElementById('jd-processed-content');
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
            const targetText = annotation.target?.text;
            const relevance = annotation.relevance || 'relevant';

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

            if (data.success && data.persona) {
                this.personaState.statement = data.persona;
                this.personaState.isUserEdited = false;
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
        const container = document.getElementById('persona-panel-container');
        if (!container) return;

        // Check for identity annotations
        this.checkIdentityAnnotations();

        // Hide if no identity annotations
        if (!this.personaState.hasIdentityAnnotations) {
            container.innerHTML = '';
            return;
        }

        const { statement, isLoading, isEditing, isUserEdited } = this.personaState;

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

        // No persona yet - show generate button
        if (!statement) {
            container.innerHTML = `
                <div class="p-4 bg-gray-50 rounded-lg border border-gray-200">
                    <h4 class="font-semibold text-gray-700 mb-2">Professional Persona</h4>
                    <p class="text-sm text-gray-600 mb-3">
                        You have identity annotations. Generate a synthesized persona to use in CV, cover letter, and outreach.
                    </p>
                    <button onclick="annotationManager.synthesizePersona()"
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
                              oninput="annotationManager.updatePersonaText(this.value)"
                    >${statement}</textarea>
                    <div class="flex gap-2 mt-3">
                        <button onclick="annotationManager.savePersona()"
                                class="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 text-sm font-medium">
                            Save
                        </button>
                        <button onclick="annotationManager.cancelEditingPersona()"
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
                        <button onclick="annotationManager.startEditingPersona()"
                                class="text-sm text-indigo-600 hover:text-indigo-800 hover:underline">
                            Edit
                        </button>
                        <button onclick="annotationManager.synthesizePersona()"
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

        const barEl = document.getElementById('annotation-coverage-bar');
        const pctEl = document.getElementById('annotation-coverage-pct');

        if (barEl) barEl.style.width = `${coverage}%`;
        if (pctEl) pctEl.textContent = `${coverage}%`;

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
 * Set passion level in popover
 */
function setPopoverPassion(passion) {
    if (annotationManager) {
        annotationManager.setPopoverPassion(passion);
    }
}

/**
 * Set identity level in popover
 */
function setPopoverIdentity(identity) {
    if (annotationManager) {
        annotationManager.setPopoverIdentity(identity);
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
