/**
 * Mobile PWA State Management
 *
 * Alpine.js application for mobile job swiping interface
 * Uses global function pattern for reliable Alpine.js integration
 */

// Global function pattern - more reliable than alpine:init event with CDN scripts
window.mobileApp = function() {
    return {
        // State
        mode: 'main',           // 'main' or 'batch'
        timeFilter: '1h',       // Current time filter (default: 1 hour)
        leadershipOnly: false,  // Leadership toggle
        jobs: [],               // Current job stack
        currentIndex: 0,        // Current card index
        isLoading: false,
        cvProgress: null,       // { runId, step, percent }

        // CV Viewer state
        cvViewer: {
            show: false,
            jobId: null,
            cvHtml: null,
            isLoading: false
        },

        // Annotation state
        annotationMode: false,
        annotation: {
            annotations: [],
            personaStatement: null,
            personaLoading: false,
            hasIdentityAnnotations: false,
            processedJdHtml: null  // LLM-structured JD HTML from backend
        },
        annotationSheet: {
            show: false,
            selectedText: '',
            relevance: 'relevant',
            requirement: 'neutral',
            identity: 'peripheral',
            passion: 'neutral',
            saving: false,
            editingId: null  // ID of annotation being edited (null = creating new)
        },

        // Annotation options
        annotationOptions: {
            relevance: [
                { value: 'core_strength', label: 'Core', emoji: '💪', color: 'text-green-400' },
                { value: 'extremely_relevant', label: 'Strong', emoji: '🎯', color: 'text-emerald-400' },
                { value: 'relevant', label: 'Good', emoji: '✓', color: 'text-blue-400' },
                { value: 'tangential', label: 'Weak', emoji: '〰️', color: 'text-yellow-400' },
                { value: 'gap', label: 'Gap', emoji: '❌', color: 'text-red-400' }
            ],
            requirement: [
                { value: 'must_have', label: 'Must', emoji: '⚡' },
                { value: 'nice_to_have', label: 'Nice', emoji: '✨' },
                { value: 'neutral', label: 'Neutral', emoji: '➖' },
                { value: 'disqualifier', label: 'No', emoji: '🚫' }
            ],
            identity: [
                { value: 'core_identity', label: 'Core', emoji: '🌟', color: 'text-purple-400' },
                { value: 'strong_identity', label: 'Strong', emoji: '💜', color: 'text-purple-300' },
                { value: 'developing', label: 'Growing', emoji: '🌱', color: 'text-green-400' },
                { value: 'peripheral', label: 'Minor', emoji: '○', color: 'text-gray-400' },
                { value: 'not_identity', label: 'Not Me', emoji: '✕', color: 'text-red-400' }
            ],
            passion: [
                { value: 'love_it', label: 'Love', emoji: '❤️', color: 'text-red-400' },
                { value: 'enjoy', label: 'Enjoy', emoji: '😊', color: 'text-orange-400' },
                { value: 'neutral', label: 'Meh', emoji: '😐', color: 'text-gray-400' },
                { value: 'tolerate', label: 'Ok', emoji: '😕', color: 'text-yellow-400' },
                { value: 'avoid', label: 'Avoid', emoji: '😣', color: 'text-red-500' }
            ]
        },

        // Swipe state
        isDragging: false,
        startX: 0,
        startY: 0,
        touchInScrollable: false,  // True if touch started in scrollable area
        swipeDecided: false,       // True once we've decided swipe vs scroll
        currentX: 0,
        swipeProgress: 0,       // -1 to 1 (negative = left, positive = right)

        // Time filter options
        timeFilters: [
            { value: '1h', label: '1h' },
            { value: '2h', label: '2h' },
            { value: '3h', label: '3h' },
            { value: '4h', label: '4h' },
            { value: '6h', label: '6h' },
            { value: '12h', label: '12h' },
            { value: '24h', label: '24h' },
            { value: '1w', label: '1w' },
            { value: '2w', label: '2w' },
            { value: '1m', label: '1m' },
            { value: '2m', label: '2m' },
        ],

        // Computed
        get currentJob() {
            return this.jobs[this.currentIndex] || null;
        },

        get cardStyle() {
            if (!this.isDragging) return '';
            const rotation = this.swipeProgress * 15;  // Max 15 degree rotation
            const translateX = this.swipeProgress * 100;  // Pixels
            return `transform: translateX(${translateX}px) rotate(${rotation}deg)`;
        },

        // Lifecycle
        init() {
            // Ensure overlays are closed on init
            this.cvViewer.show = false;
            this.cvViewer.isLoading = false;
            this.cvProgress = null;
            this.annotationMode = false;

            // Check URL for mode
            const path = window.location.pathname;
            if (path.includes('/batch')) {
                this.mode = 'batch';
            } else if (path.includes('/main')) {
                this.mode = 'main';
            }

            // Load jobs
            this.loadJobs();
        },

        // Actions
        setMode(newMode) {
            if (this.mode !== newMode) {
                this.mode = newMode;
                this.loadJobs();
            }
        },

        setTimeFilter(filter) {
            if (this.timeFilter !== filter) {
                this.timeFilter = filter;
                this.loadJobs();
            }
        },

        async loadJobs() {
            this.isLoading = true;
            this.jobs = [];
            this.currentIndex = 0;

            try {
                const params = new URLSearchParams({
                    mode: this.mode,
                    time_filter: this.timeFilter,
                    leadership_only: this.leadershipOnly.toString(),
                    limit: '500'  // No practical limit for mobile - show all jobs
                });

                const response = await fetch(`/api/mobile/jobs?${params}`);
                if (!response.ok) throw new Error('Failed to load jobs');

                const data = await response.json();
                this.jobs = data.jobs || [];

            } catch (error) {
                console.error('Failed to load jobs:', error);
                window.showToast?.('Failed to load jobs', 'error');
            } finally {
                this.isLoading = false;
            }
        },

        // Swipe handlers
        onTouchStart(e) {
            if (!this.currentJob) return;

            // Check if touch started inside a scrollable element
            const target = e.target;
            const scrollableParent = target.closest('.overflow-y-auto, .overflow-auto, [data-no-swipe]');
            this.touchInScrollable = !!scrollableParent;

            this.isDragging = true;
            this.startX = e.touches[0].clientX;
            this.startY = e.touches[0].clientY;
            this.currentX = this.startX;
            this.swipeDecided = false; // Haven't decided swipe vs scroll yet

            // Add dragging class
            this.$refs.currentCard?.classList.add('dragging');
        },

        onTouchMove(e) {
            if (!this.isDragging) return;

            this.currentX = e.touches[0].clientX;
            const deltaX = this.currentX - this.startX;
            const deltaY = e.touches[0].clientY - this.startY;

            // First significant movement decides: swipe or scroll
            if (!this.swipeDecided && (Math.abs(deltaX) > 10 || Math.abs(deltaY) > 10)) {
                this.swipeDecided = true;
                // If inside scrollable and moving vertically, disable swipe entirely
                if (this.touchInScrollable && Math.abs(deltaY) >= Math.abs(deltaX)) {
                    this.isDragging = false;
                    this.$refs.currentCard?.classList.remove('dragging');
                    return;
                }
            }

            // If vertical movement is greater and we haven't committed to swipe, allow scroll
            if (Math.abs(deltaY) > Math.abs(deltaX) && Math.abs(deltaX) < 20) {
                return;
            }

            // Prevent scroll while swiping horizontally
            e.preventDefault();

            // Calculate progress (-1 to 1)
            const cardWidth = this.$refs.currentCard?.offsetWidth || 300;
            this.swipeProgress = Math.max(-1, Math.min(1, deltaX / (cardWidth * 0.4)));
        },

        onTouchEnd(e) {
            if (!this.isDragging) return;

            this.isDragging = false;
            this.$refs.currentCard?.classList.remove('dragging');

            const threshold = 0.4;  // 40% swipe to commit

            if (Math.abs(this.swipeProgress) > threshold) {
                // Commit the swipe
                if (this.swipeProgress < 0) {
                    this.commitSwipeLeft();
                } else {
                    this.commitSwipeRight();
                }
            } else {
                // Snap back
                this.swipeProgress = 0;
            }
        },

        async commitSwipeLeft() {
            // Discard job
            const job = this.currentJob;
            if (!job) return;

            // Animate out
            const card = this.$refs.currentCard;
            if (card) {
                card.classList.add('snapping');
                card.style.transform = 'translateX(-150%) rotate(-30deg)';
            }

            try {
                const response = await fetch('/api/jobs/status', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        job_id: job._id,
                        status: 'discarded'
                    })
                });

                if (!response.ok) throw new Error('Failed to discard');

                // Haptic feedback
                if ('vibrate' in navigator) {
                    navigator.vibrate(50);
                }

                window.showToast?.('Job discarded', 'info');

            } catch (error) {
                console.error('Failed to discard:', error);
                window.showToast?.('Failed to discard job', 'error');
            }

            // Move to next after animation
            setTimeout(() => this.nextCard(), 300);
        },

        async commitSwipeRight() {
            const job = this.currentJob;
            if (!job) return;

            // Animate out
            const card = this.$refs.currentCard;
            if (card) {
                card.classList.add('snapping');
                card.style.transform = 'translateX(150%) rotate(30deg)';
            }

            try {
                if (this.mode === 'main') {
                    // Move to batch
                    const response = await fetch('/api/jobs/move-to-batch', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            job_ids: [job._id],
                            auto_process: true
                        })
                    });

                    if (!response.ok) throw new Error('Failed to move to batch');

                    // Haptic feedback
                    if ('vibrate' in navigator) {
                        navigator.vibrate([50, 30, 50]);
                    }

                    window.showToast?.('Moved to batch & analyzing', 'success');

                } else {
                    // Generate CV
                    const response = await fetch(`/api/runner/jobs/${job._id}/operations/generate-cv/queue`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ tier: 'quality' })
                    });

                    if (!response.ok) throw new Error('Failed to queue CV generation');

                    const data = await response.json();

                    // Haptic feedback
                    if ('vibrate' in navigator) {
                        navigator.vibrate([50, 30, 50, 30, 50]);
                    }

                    // Start polling progress
                    if (data.run_id) {
                        this.cvProgress = {
                            runId: data.run_id,
                            jobId: job._id,  // Track the job ID for CV viewer
                            step: 'Starting...',
                            percent: 0
                        };
                        this.pollCvProgress(data.run_id);
                    }

                    window.showToast?.('CV generation started', 'success');
                }

            } catch (error) {
                console.error('Swipe right action failed:', error);
                window.showToast?.(`Action failed: ${error.message}`, 'error');
            }

            // Move to next after animation
            setTimeout(() => this.nextCard(), 300);
        },

        nextCard() {
            // Reset swipe state
            this.swipeProgress = 0;

            // Remove current job from array
            this.jobs.splice(this.currentIndex, 1);

            // Reset card style
            const card = this.$refs.currentCard;
            if (card) {
                card.classList.remove('snapping');
                card.style.transform = '';

                // Reset scroll position of JD content to top
                const scrollableAreas = card.querySelectorAll('.overflow-y-auto');
                scrollableAreas.forEach(el => el.scrollTop = 0);
            }

            // Load more if running low
            if (this.jobs.length < 5) {
                this.loadMoreJobs();
            }
        },

        async loadMoreJobs() {
            if (this.isLoading) return;

            try {
                const lastJob = this.jobs[this.jobs.length - 1];
                const params = new URLSearchParams({
                    mode: this.mode,
                    time_filter: this.timeFilter,
                    leadership_only: this.leadershipOnly.toString(),
                    limit: '10',
                    cursor: lastJob?._id || ''
                });

                const response = await fetch(`/api/mobile/jobs?${params}`);
                if (!response.ok) return;

                const data = await response.json();
                if (data.jobs?.length) {
                    // Filter out duplicates
                    const existingIds = new Set(this.jobs.map(j => j._id));
                    const newJobs = data.jobs.filter(j => !existingIds.has(j._id));
                    this.jobs.push(...newJobs);
                }

            } catch (error) {
                console.error('Failed to load more jobs:', error);
            }
        },

        async pollCvProgress(runId) {
            try {
                const response = await fetch(`/api/runner/jobs/${runId}/status`);
                if (!response.ok) throw new Error('Failed to get status');

                const data = await response.json();

                if (data.status === 'completed') {
                    const completedJobId = this.cvProgress?.jobId;
                    this.cvProgress = null;
                    window.showToast?.('CV generated successfully!', 'success');
                    // Haptic feedback
                    if ('vibrate' in navigator) {
                        navigator.vibrate([100, 50, 100, 50, 200]);
                    }
                    // Offer to view the CV
                    if (completedJobId) {
                        setTimeout(() => this.openCvViewer(completedJobId), 500);
                    }
                } else if (data.status === 'failed') {
                    this.cvProgress = null;
                    window.showToast?.('CV generation failed', 'error');
                } else {
                    // Update progress and poll again
                    this.cvProgress = {
                        runId,
                        step: data.current_step || 'Processing...',
                        percent: data.progress || Math.min((this.cvProgress?.percent || 0) + 5, 95)
                    };
                    setTimeout(() => this.pollCvProgress(runId), 1000);
                }

            } catch (error) {
                console.error('Failed to poll CV progress:', error);
                // Keep polling
                setTimeout(() => this.pollCvProgress(runId), 2000);
            }
        },

        // =====================================================================
        // Annotation Methods
        // =====================================================================

        async openAnnotationMode() {
            if (!this.currentJob) return;

            // Load existing annotations and processed JD HTML BEFORE showing panel
            // This ensures getAnnotationJdHtml() has the data when panel renders
            try {
                const response = await fetch(`/api/jobs/${this.currentJob._id}/jd-annotations`);

                if (response.ok) {
                    const data = await response.json();
                    // API returns: { annotations: { processed_jd_html, annotations: [], ... }, ... }
                    const jdAnnotations = data.annotations || {};

                    // Debug: Log what we received from API
                    console.log('[Annotation] API response:', {
                        hasProcessedJdHtml: !!jdAnnotations.processed_jd_html,
                        processedJdHtmlLength: jdAnnotations.processed_jd_html?.length || 0,
                        annotationsCount: jdAnnotations.annotations?.length || 0
                    });

                    // The actual annotations array is nested inside
                    const annotationsList = jdAnnotations.annotations;
                    this.annotation.annotations = Array.isArray(annotationsList) ? annotationsList : [];
                    this.annotation.personaStatement = jdAnnotations.synthesized_persona?.persona_statement || null;
                    // Store the LLM-processed JD HTML if available
                    this.annotation.processedJdHtml = jdAnnotations.processed_jd_html || null;

                    // If no processed JD HTML, auto-generate it on-demand
                    if (!this.annotation.processedJdHtml) {
                        await this.generateProcessedJdHtml();
                    }

                    this.checkIdentityAnnotations();
                } else {
                    this.annotation.annotations = [];
                    this.annotation.processedJdHtml = null;
                }
            } catch (error) {
                console.error('Failed to load annotations:', error);
                this.annotation.annotations = [];
                this.annotation.processedJdHtml = null;
            }

            // Show annotation panel AFTER data is loaded
            this.annotationMode = true;
        },

        closeAnnotationMode() {
            this.annotationMode = false;
        },

        checkIdentityAnnotations() {
            const identityLevels = ['core_identity', 'strong_identity', 'developing'];
            const passionLevels = ['love_it', 'enjoy'];
            const strengthLevels = ['core_strength', 'extremely_relevant'];

            // Ensure annotations is an array before calling .some()
            const annotations = Array.isArray(this.annotation.annotations) ? this.annotation.annotations : [];
            this.annotation.hasIdentityAnnotations = annotations.some(a =>
                a.is_active !== false && (
                    identityLevels.includes(a.identity) ||
                    passionLevels.includes(a.passion) ||
                    strengthLevels.includes(a.relevance)
                )
            );
        },

        // Generate processed JD HTML by calling the structure-jd API (on-demand)
        async generateProcessedJdHtml() {
            if (!this.currentJob) return;

            try {
                const response = await fetch(`/api/jobs/${this.currentJob._id}/process-jd`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ use_llm: true })
                });

                if (!response.ok) return;

                const data = await response.json();
                if (data.success && data.processed_jd?.html) {
                    this.annotation.processedJdHtml = data.processed_jd.html;
                }
            } catch (error) {
                console.error('Failed to generate processed JD:', error);
            }
        },

        // Format JD text for annotation display
        formatJdForAnnotation(text) {
            if (!text) return '<p class="text-mobile-dark-500">No description available</p>';

            // Simple formatting: paragraphs and line breaks
            return text
                .split(/\n\n+/)
                .map(para => `<p class="mb-3">${para.replace(/\n/g, '<br>')}</p>`)
                .join('');
        },

        // Handle tap on JD text
        handleAnnotationTap(event) {
            // Prevent if tapping on a link or button
            if (event.target.closest('a, button')) return;

            // Check if tapping on an existing annotation highlight
            const annotationMark = event.target.closest('mark.annotation-highlight');
            if (annotationMark) {
                const annotationId = annotationMark.dataset.annotationId;
                if (annotationId) {
                    this.editAnnotation(annotationId);
                    return;
                }
            }

            // Get selected text or smart-select from tapped element
            const selection = window.getSelection();
            let selectedText = '';

            if (selection && !selection.isCollapsed) {
                selectedText = selection.toString().trim();
            } else {
                // Try to get text from tapped element (list item, paragraph, etc.)
                selectedText = this.getTextFromTappedElement(event);
            }

            if (selectedText && selectedText.length > 10) {
                this.annotationSheet.selectedText = selectedText;
                // Default to Core Strength + Must Have (like desktop Quick Add)
                this.annotationSheet.relevance = 'core_strength';
                this.annotationSheet.requirement = 'must_have';
                this.annotationSheet.identity = 'peripheral';
                this.annotationSheet.passion = 'neutral';
                this.annotationSheet.editingId = null;  // Creating new annotation
                this.annotationSheet.show = true;

                // Haptic
                if ('vibrate' in navigator) {
                    navigator.vibrate(30);
                }
            }
        },

        // Get text from tapped element - works better with structured HTML
        getTextFromTappedElement(event) {
            try {
                // First, try to get specific list item or paragraph
                const target = event.target;

                // If tapped on a list item, get its text
                const listItem = target.closest('li');
                if (listItem) {
                    return listItem.textContent?.trim() || '';
                }

                // If tapped on a paragraph, get its text
                const paragraph = target.closest('p');
                if (paragraph) {
                    const text = paragraph.textContent?.trim() || '';
                    // If paragraph is short enough, use whole thing
                    if (text.length < 500) {
                        return text;
                    }
                    // Otherwise, try to get sentence at tap point
                    return this.getSentenceAtPoint(event, text);
                }

                // If tapped on a span (e.g., highlight), get parent text
                if (target.tagName === 'SPAN') {
                    return target.textContent?.trim() || '';
                }

                // Fallback: try caretRangeFromPoint
                return this.getSentenceAtPoint(event);
            } catch (e) {
                console.error('Error getting tapped text:', e);
                return '';
            }
        },

        // Get sentence at tap point (fallback)
        getSentenceAtPoint(event, providedText = null) {
            try {
                let text = providedText;
                let offset = 0;

                if (!text) {
                    // Try to get position using caretRangeFromPoint
                    const range = document.caretRangeFromPoint?.(event.clientX, event.clientY);
                    if (!range) return '';
                    text = range.startContainer.textContent || '';
                    offset = range.startOffset;
                } else {
                    // For provided text, estimate offset from click position
                    offset = Math.floor(text.length / 2);
                }

                // Find sentence boundaries
                let start = 0;
                let end = text.length;

                for (let i = offset - 1; i >= 0; i--) {
                    if (/[.!?\n]/.test(text[i])) {
                        start = i + 1;
                        break;
                    }
                }

                for (let i = offset; i < text.length; i++) {
                    if (/[.!?\n]/.test(text[i])) {
                        end = i + 1;
                        break;
                    }
                }

                return text.substring(start, end).trim();
            } catch (e) {
                return '';
            }
        },

        closeAnnotationSheet() {
            this.annotationSheet.show = false;
            this.annotationSheet.selectedText = '';
            this.annotationSheet.editingId = null;
            window.getSelection()?.removeAllRanges();
        },

        // Edit an existing annotation
        editAnnotation(annotationId) {
            const annotation = this.annotation.annotations.find(a => a.id === annotationId);
            if (!annotation) return;

            // Load annotation data into the sheet
            this.annotationSheet.selectedText = annotation.target?.text || '';
            this.annotationSheet.relevance = annotation.relevance || 'relevant';
            this.annotationSheet.requirement = annotation.requirement_type || 'neutral';
            this.annotationSheet.identity = annotation.identity || 'peripheral';
            this.annotationSheet.passion = annotation.passion || 'neutral';
            this.annotationSheet.editingId = annotationId;
            this.annotationSheet.show = true;

            // Haptic
            if ('vibrate' in navigator) {
                navigator.vibrate([30, 20, 30]);
            }
        },

        // Delete an annotation (optimistic - instant UI, background save)
        deleteAnnotation() {
            if (!this.annotationSheet.editingId || !this.currentJob) return;

            const jobId = this.currentJob._id;

            // === OPTIMISTIC UPDATE: Update UI immediately ===
            this.annotation.annotations = this.annotation.annotations.filter(
                a => a.id !== this.annotationSheet.editingId
            );

            this.checkIdentityAnnotations();

            // Haptic feedback immediately
            if ('vibrate' in navigator) {
                navigator.vibrate(50);
            }

            // Close sheet immediately
            this.closeAnnotationSheet();

            // === BACKGROUND SAVE ===
            const annotationsToSave = [...this.annotation.annotations];
            const processedJdHtml = this.annotation.processedJdHtml;

            fetch(`/api/jobs/${jobId}/jd-annotations`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    annotations: annotationsToSave,
                    processed_jd_html: processedJdHtml,
                    annotation_version: 1
                })
            }).then(response => {
                if (!response.ok) {
                    console.error('Background delete save failed:', response.status);
                    window.showToast?.('Delete failed - refresh to see actual state', 'error');
                }
            }).catch(error => {
                console.error('Background delete save error:', error);
                window.showToast?.('Delete failed - refresh to see actual state', 'error');
            });
        },

        async saveAnnotation() {
            if (!this.annotationSheet.selectedText || !this.currentJob) return;

            const isEditing = !!this.annotationSheet.editingId;
            const jobId = this.currentJob._id;

            // === OPTIMISTIC UPDATE: Update UI immediately ===
            if (isEditing) {
                // Update existing annotation
                this.annotation.annotations = this.annotation.annotations.map(a => {
                    if (a.id === this.annotationSheet.editingId) {
                        return {
                            ...a,
                            relevance: this.annotationSheet.relevance,
                            requirement_type: this.annotationSheet.requirement,
                            identity: this.annotationSheet.identity,
                            passion: this.annotationSheet.passion,
                            updated_at: new Date().toISOString()
                        };
                    }
                    return a;
                });
            } else {
                // Create new annotation
                const newAnnotation = {
                    id: crypto.randomUUID(),
                    target: {
                        text: this.annotationSheet.selectedText,
                        char_start: 0,
                        char_end: this.annotationSheet.selectedText.length
                    },
                    annotation_type: 'skill_match',
                    relevance: this.annotationSheet.relevance,
                    requirement_type: this.annotationSheet.requirement,
                    identity: this.annotationSheet.identity,
                    passion: this.annotationSheet.passion,
                    is_active: true,
                    status: 'approved',
                    source: 'human',
                    created_at: new Date().toISOString()
                };

                // Use array reassignment to trigger Alpine reactivity
                this.annotation.annotations = [...this.annotation.annotations, newAnnotation];
            }

            this.checkIdentityAnnotations();

            // Haptic feedback immediately
            if ('vibrate' in navigator) {
                navigator.vibrate([50, 30, 50]);
            }

            // Close sheet immediately (optimistic - don't wait for server)
            this.closeAnnotationSheet();

            // === BACKGROUND SAVE: Save to server without blocking UI ===
            // Capture current state for background save
            const annotationsToSave = [...this.annotation.annotations];
            const processedJdHtml = this.annotation.processedJdHtml;

            // Save in background (don't await)
            fetch(`/api/jobs/${jobId}/jd-annotations`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    annotations: annotationsToSave,
                    processed_jd_html: processedJdHtml,
                    annotation_version: 1
                })
            }).then(response => {
                if (!response.ok) {
                    console.error('Background save failed:', response.status);
                    window.showToast?.('Save failed - changes may be lost', 'error');
                }
            }).catch(error => {
                console.error('Background save error:', error);
                window.showToast?.('Save failed - changes may be lost', 'error');
            });
        },

        async generatePersona() {
            if (!this.currentJob || this.annotation.personaLoading) return;

            this.annotation.personaLoading = true;

            try {
                // Save annotations first (include processed_jd_html to avoid overwriting)
                await fetch(`/api/jobs/${this.currentJob._id}/jd-annotations`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        annotations: this.annotation.annotations,
                        processed_jd_html: this.annotation.processedJdHtml,
                        annotation_version: 1
                    })
                });

                // Generate persona
                const response = await fetch(`/api/jobs/${this.currentJob._id}/synthesize-persona`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });

                if (!response.ok) throw new Error('Synthesis failed');

                const data = await response.json();

                if (data.success && data.persona) {
                    this.annotation.personaStatement = data.persona;

                    // Save persona
                    await fetch(`/api/jobs/${this.currentJob._id}/save-persona`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            persona_statement: data.persona,
                            is_user_edited: false
                        })
                    });

                    // Haptic
                    if ('vibrate' in navigator) {
                        navigator.vibrate([100, 50, 100, 50, 200]);
                    }

                    window.showToast?.('Persona generated!', 'success');
                } else {
                    window.showToast?.('Could not generate persona', 'warning');
                }

            } catch (error) {
                console.error('Failed to generate persona:', error);
                window.showToast?.('Persona generation failed', 'error');
            } finally {
                this.annotation.personaLoading = false;
            }
        },

        // =====================================================================
        // CV Viewer Methods
        // =====================================================================

        // Check if a job has a generated CV
        hasGeneratedCv(job) {
            if (!job) return false;
            const cvData = job.generated_cv || job.cv_data;
            return !!(cvData?.html || cvData?.content);
        },

        // Format JD using the JDFormatter (regex-based structuring)
        formatJD(text) {
            if (!text) return '<p class="text-mobile-dark-500 italic">No description available</p>';
            // Use the global JDFormatter if available
            if (window.JDFormatter && typeof window.JDFormatter.format === 'function') {
                return window.JDFormatter.format(text);
            }
            // Fallback: basic formatting with line breaks
            return text.replace(/\n/g, '<br>');
        },

        // Get JD HTML for annotation panel - prefer LLM-processed HTML, fallback to JDFormatter
        // Also applies highlights for existing annotations
        getAnnotationJdHtml() {
            // Get base HTML - prefer LLM-processed, fallback to regex formatter
            let html;
            if (this.annotation.processedJdHtml) {
                console.log('[Annotation] Using LLM-processed JD HTML:', this.annotation.processedJdHtml.length, 'chars');
                html = this.annotation.processedJdHtml;
            } else {
                const rawJd = this.currentJob?.description || this.currentJob?.job_description || '';
                console.log('[Annotation] Falling back to JDFormatter for raw JD:', rawJd.length, 'chars');
                html = this.formatJD(rawJd);
            }

            // Apply highlights for existing annotations
            return this.applyHighlightsToHtml(html);
        },

        // Apply annotation highlights to HTML string
        applyHighlightsToHtml(html) {
            if (!html) return html;

            // Get active annotations
            const annotations = Array.isArray(this.annotation.annotations)
                ? this.annotation.annotations.filter(a => a.is_active !== false)
                : [];

            if (!annotations.length) return html;

            // Apply highlights for each annotation
            // Sort by text length (longest first) to avoid nested replacements
            const sortedAnnotations = [...annotations].sort((a, b) =>
                (b.target?.text?.length || 0) - (a.target?.text?.length || 0)
            );

            for (const annotation of sortedAnnotations) {
                const targetText = annotation.target?.text;
                if (!targetText || targetText.length < 5) continue;

                const relevance = annotation.relevance || 'relevant';

                // Escape special regex characters in target text
                const escapedText = targetText.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

                // Create highlight mark - CSS handles colors via data-relevance attribute
                const highlightMark = `<mark class="annotation-highlight" data-annotation-id="${annotation.id}" data-relevance="${relevance}">$&</mark>`;

                // Replace first occurrence only (to avoid duplicates)
                const regex = new RegExp(escapedText, 'i');
                html = html.replace(regex, highlightMark);
            }

            return html;
        },

        async openCvViewer(jobId) {
            this.cvViewer.jobId = jobId || this.currentJob?._id;
            if (!this.cvViewer.jobId) return;

            this.cvViewer.show = true;
            this.cvViewer.isLoading = true;
            this.cvViewer.cvHtml = null;

            try {
                // Fetch job data including generated CV
                const response = await fetch(`/api/jobs/${this.cvViewer.jobId}`);
                if (!response.ok) throw new Error('Failed to fetch job');

                const job = await response.json();

                // Get CV HTML from job data
                const cvData = job.generated_cv || job.cv_data;
                if (cvData?.html) {
                    this.cvViewer.cvHtml = cvData.html;
                } else if (cvData?.content) {
                    this.cvViewer.cvHtml = cvData.content;
                } else {
                    this.cvViewer.cvHtml = '<div class="text-center py-8 text-mobile-dark-500">No CV generated yet</div>';
                }

            } catch (error) {
                console.error('Failed to load CV:', error);
                this.cvViewer.cvHtml = '<div class="text-center py-8 text-mobile-red-500">Failed to load CV</div>';
            } finally {
                this.cvViewer.isLoading = false;
            }
        },

        closeCvViewer() {
            this.cvViewer.show = false;
            this.cvViewer.cvHtml = null;
        },

        openCvInDesktop() {
            if (this.cvViewer.jobId) {
                window.open(`/job/${this.cvViewer.jobId}`, '_blank');
            }
        }
    };
};
