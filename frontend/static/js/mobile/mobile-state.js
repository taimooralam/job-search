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
        mode: 'batch',          // 'main' or 'batch' - default to batch for CV generation workflow
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
        annotationVersion: 0,  // Version counter to force x-html re-evaluation
        annotation: {
            annotations: [],
            personaStatement: null,
            personaLoading: false,
            hasIdentityAnnotations: false,
            processedJdHtml: null,  // LLM-structured JD HTML from backend
            autoGenerating: false   // Auto-annotation generation in progress
        },
        annotationSheet: {
            show: false,
            selectedText: '',
            // Optimistic defaults - most annotations are strengths you must have
            relevance: 'core_strength',
            requirement: 'must_have',
            identity: 'strong_identity',
            passion: 'enjoy',
            saving: false,
            editingId: null,  // ID of annotation being edited (null = creating new)
            aiInfo: null  // AI suggestion metadata (confidence, match method) when editing
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
                const data = await response.json();

                if (!response.ok) {
                    // Extract actual error message from response
                    const errorMsg = data?.error || `Server error ${response.status}`;
                    throw new Error(errorMsg);
                }
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

        commitSwipeRight() {
            const job = this.currentJob;
            if (!job) return;

            const jobId = job._id;
            const mode = this.mode;

            // Animate out
            const card = this.$refs.currentCard;
            if (card) {
                card.classList.add('snapping');
                card.style.transform = 'translateX(150%) rotate(30deg)';
            }

            // Haptic feedback immediately
            if ('vibrate' in navigator) {
                navigator.vibrate(mode === 'main' ? [50, 30, 50] : [50, 30, 50, 30, 50]);
            }

            // Move to next card immediately (optimistic)
            setTimeout(() => this.nextCard(), 300);

            // === FIRE AND FORGET: API calls in background ===
            if (mode === 'main') {
                // Move to batch (background)
                fetch('/api/jobs/move-to-batch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        job_ids: [jobId],
                        auto_process: true
                    })
                }).then(response => {
                    if (response.ok) {
                        window.showToast?.('Moved to batch & analyzing', 'success');
                    } else {
                        window.showToast?.('Failed to move to batch', 'error');
                    }
                }).catch(error => {
                    console.error('Move to batch failed:', error);
                    window.showToast?.('Failed to move to batch', 'error');
                });

            } else {
                // Batch mode: Check if CV already exists
                if (this.hasGeneratedCv(job)) {
                    // CV exists - just skip to next (already moving via nextCard above)
                    window.showToast?.('CV exists - skipped', 'info');
                } else {
                    // No CV - generate it
                    this.triggerCvGeneration(jobId);
                }
            }
        },

        // Trigger CV generation (fire-and-forget - no blocking, no progress overlay)
        triggerCvGeneration(jobId) {
            fetch(`/api/runner/jobs/${jobId}/operations/generate-cv/queue`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tier: 'quality' })
            }).then(async response => {
                if (!response.ok) {
                    window.showToast?.('Failed to start CV generation', 'error');
                    return;
                }

                const data = await response.json();
                // Show confirmation with run_id - fire and forget, no polling
                const runIdShort = data.run_id ? data.run_id.slice(0, 8) : 'unknown';
                window.showToast?.(`CV queued (${runIdShort})`, 'success');
            }).catch(error => {
                console.error('CV generation failed:', error);
                window.showToast?.('Failed to start CV generation', 'error');
            });
        },

        // Regenerate CV and move to next card (for jobs that already have CV)
        regenerateCvAndNext() {
            const job = this.currentJob;
            if (!job) return;

            const jobId = job._id;

            // Animate out
            const card = this.$refs.currentCard;
            if (card) {
                card.classList.add('snapping');
                card.style.transform = 'translateX(150%) rotate(30deg)';
            }

            // Haptic
            if ('vibrate' in navigator) {
                navigator.vibrate([50, 30, 50, 30, 50]);
            }

            // Move to next
            setTimeout(() => this.nextCard(), 300);

            // Trigger CV generation (will overwrite existing)
            this.triggerCvGeneration(jobId);
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

        /**
         * Auto-generate annotations using the suggestion system.
         * Calls the runner service to generate annotations based on
         * sentence embeddings and skill priors.
         */
        async autoAnnotate() {
            if (!this.currentJob || this.annotation.autoGenerating) return;

            this.annotation.autoGenerating = true;

            try {
                const response = await fetch(`/api/runner/jobs/${this.currentJob._id}/generate-annotations`, {
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
                    await this.reloadAnnotations();

                    // Haptic feedback
                    if ('vibrate' in navigator) {
                        navigator.vibrate([100, 50, 100]);
                    }

                    window.showToast?.(`Created ${data.created} annotations`, 'success');
                } else {
                    throw new Error(data.error || 'Unknown error');
                }

            } catch (error) {
                console.error('Failed to auto-generate annotations:', error);
                window.showToast?.(`Auto-annotate failed: ${error.message}`, 'error');
            } finally {
                this.annotation.autoGenerating = false;
            }
        },

        /**
         * Reload annotations from server (after auto-generate or other changes)
         */
        async reloadAnnotations() {
            if (!this.currentJob) return;

            try {
                const response = await fetch(`/api/jobs/${this.currentJob._id}/jd-annotations`);
                if (!response.ok) return;

                const data = await response.json();
                const jdAnnotations = data.annotations || {};
                const annotationsList = jdAnnotations.annotations;
                this.annotation.annotations = Array.isArray(annotationsList) ? annotationsList : [];
                this.annotation.personaStatement = jdAnnotations.synthesized_persona?.persona_statement || null;
                this.checkIdentityAnnotations();
            } catch (error) {
                console.error('Failed to reload annotations:', error);
            }
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
                // Optimistic defaults - auto-save immediately, user can edit if needed
                this.annotationSheet.relevance = 'core_strength';
                this.annotationSheet.requirement = 'must_have';
                this.annotationSheet.identity = 'strong_identity';
                this.annotationSheet.passion = 'enjoy';
                this.annotationSheet.editingId = null;  // Creating new annotation
                this.annotationSheet.aiInfo = null;  // Clear AI info for new annotations

                // AUTO-SAVE: Save immediately with defaults, show sheet for optional adjustment
                this.autoSaveAnnotation();

                // Haptic feedback for auto-save
                if ('vibrate' in navigator) {
                    navigator.vibrate([20, 10, 20]);  // Double tap feel
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
            this.annotationSheet.aiInfo = null;
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

            // Load AI suggestion metadata if auto-generated
            if (annotation.source === 'auto_generated' && annotation.original_values?.confidence) {
                const conf = annotation.original_values.confidence;
                const pct = Math.round(conf * 100);
                const matchMethod = annotation.original_values.match_method || 'semantic similarity';
                const methodLabels = {
                    'sentence_embedding': 'sentence similarity',
                    'keyword_match': 'keyword match',
                    'skill_prior': 'skill prior',
                    'semantic_similarity': 'semantic similarity',
                    'exact_match': 'exact match'
                };
                this.annotationSheet.aiInfo = {
                    pct: pct,
                    method: methodLabels[matchMethod] || matchMethod,
                    matchedKeyword: annotation.original_values.matched_keyword || null,
                    colorClass: pct >= 85 ? 'text-green-600 bg-green-900/50'
                              : pct >= 70 ? 'text-amber-600 bg-amber-900/50'
                              : 'text-gray-400 bg-gray-800/50'
                };
            } else {
                this.annotationSheet.aiInfo = null;
            }

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

            // Increment version to force x-html re-evaluation (remove highlight)
            this.annotationVersion++;
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

        // Auto-save annotation with defaults (no sheet shown, just toast)
        // User can tap highlight to edit if defaults aren't right
        autoSaveAnnotation() {
            if (!this.annotationSheet.selectedText || !this.currentJob) return;

            const jobId = this.currentJob._id;
            const selectedText = this.annotationSheet.selectedText;

            // Create new annotation with optimistic defaults
            const newAnnotation = {
                id: crypto.randomUUID(),
                target: {
                    text: selectedText,
                    char_start: 0,
                    char_end: selectedText.length
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

            // === OPTIMISTIC UPDATE: Update UI immediately ===
            this.annotation.annotations = [...this.annotation.annotations, newAnnotation];
            this.annotationVersion++;
            this.checkIdentityAnnotations();

            // Show brief toast (not the full sheet)
            const shortText = selectedText.length > 30
                ? selectedText.substring(0, 30) + '...'
                : selectedText;
            window.showToast?.(`✓ "${shortText}"`, 'success');

            // Clear selection
            window.getSelection()?.removeAllRanges();

            // Show save pulse animation on the new annotation highlight
            requestAnimationFrame(() => {
                setTimeout(() => {
                    const highlight = document.querySelector(`.annotation-highlight[data-annotation-id="${newAnnotation.id}"]`);
                    if (highlight) {
                        highlight.classList.add('save-pulse');
                        setTimeout(() => highlight.classList.remove('save-pulse'), 1000);
                    }
                }, 100); // Small delay for x-html to re-render
            });

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
            }).catch(error => {
                console.error('Auto-save failed:', error);
                window.showToast?.('Save failed - tap to retry', 'error');
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

            // Track annotation ID for save pulse animation
            const savedAnnotationId = isEditing
                ? this.annotationSheet.editingId
                : this.annotation.annotations[this.annotation.annotations.length - 1]?.id;

            // Increment version to force x-html re-evaluation with new highlights
            this.annotationVersion++;
            this.checkIdentityAnnotations();

            // Haptic feedback immediately
            if ('vibrate' in navigator) {
                navigator.vibrate([50, 30, 50]);
            }

            // Close sheet immediately (optimistic - don't wait for server)
            this.closeAnnotationSheet();

            // Show save pulse animation on the annotation highlight
            if (savedAnnotationId) {
                requestAnimationFrame(() => {
                    setTimeout(() => {
                        const highlight = document.querySelector(`.annotation-highlight[data-annotation-id="${savedAnnotationId}"]`);
                        if (highlight) {
                            highlight.classList.add('save-pulse');
                            setTimeout(() => highlight.classList.remove('save-pulse'), 1000);
                        }
                    }, 100); // Small delay for x-html to re-render
                });
            }

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
            const jobId = this.currentJob?._id;
            console.log('[Persona] Starting generation for job:', jobId);

            if (!this.currentJob || this.annotation.personaLoading) {
                console.log('[Persona] Aborted - no job or already loading');
                return;
            }

            this.annotation.personaLoading = true;

            try {
                // Step 1: Save annotations first
                console.log('[Persona] Step 1: Saving annotations...', {
                    count: this.annotation.annotations?.length,
                    hasProcessedJdHtml: !!this.annotation.processedJdHtml
                });

                const saveResponse = await fetch(`/api/jobs/${jobId}/jd-annotations`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        annotations: this.annotation.annotations,
                        processed_jd_html: this.annotation.processedJdHtml,
                        annotation_version: 1
                    })
                });

                console.log('[Persona] Step 1 result:', saveResponse.ok ? 'OK' : `FAILED (${saveResponse.status})`);
                if (!saveResponse.ok) {
                    const errText = await saveResponse.text();
                    console.error('[Persona] Save annotations failed:', errText);
                }

                // Step 2: Generate persona
                console.log('[Persona] Step 2: Calling synthesize-persona API...');
                const response = await fetch(`/api/jobs/${jobId}/synthesize-persona`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });

                console.log('[Persona] Step 2 response status:', response.status);
                if (!response.ok) {
                    const errText = await response.text();
                    console.error('[Persona] Synthesis API failed:', errText);
                    throw new Error(`Synthesis failed: ${response.status}`);
                }

                const data = await response.json();
                console.log('[Persona] Step 2 result:', {
                    success: data.success,
                    hasPersona: !!data.persona,
                    personaLength: data.persona?.length || 0
                });

                if (data.success && data.persona) {
                    this.annotation.personaStatement = data.persona;

                    // Step 3: Save persona to database
                    console.log('[Persona] Step 3: Saving persona to database...');
                    const savePersonaResponse = await fetch(`/api/jobs/${jobId}/save-persona`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            persona: data.persona,  // API expects 'persona', not 'persona_statement'
                            is_edited: false        // API expects 'is_edited', not 'is_user_edited'
                        })
                    });

                    console.log('[Persona] Step 3 result:', savePersonaResponse.ok ? 'OK' : `FAILED (${savePersonaResponse.status})`);
                    if (!savePersonaResponse.ok) {
                        const errText = await savePersonaResponse.text();
                        console.error('[Persona] Save persona failed:', errText);
                        window.showToast?.('Persona generated but save failed!', 'warning');
                    } else {
                        console.log('[Persona] ✓ Complete! Persona saved successfully');
                        window.showToast?.('Persona generated!', 'success');
                    }

                    // Haptic
                    if ('vibrate' in navigator) {
                        navigator.vibrate([100, 50, 100, 50, 200]);
                    }
                } else {
                    console.log('[Persona] No persona in response:', data);
                    window.showToast?.('Could not generate persona', 'warning');
                }

            } catch (error) {
                console.error('[Persona] Failed:', error);
                window.showToast?.('Persona generation failed', 'error');
            } finally {
                this.annotation.personaLoading = false;
                console.log('[Persona] Generation complete, loading state reset');
            }
        },

        // =====================================================================
        // CV Viewer Methods
        // =====================================================================

        // Check if a job has a generated CV
        // The CV generation service saves: cv_text (markdown), cv_editor_state (TipTap JSON), generated_cv (boolean)
        hasGeneratedCv(job) {
            if (!job) return false;
            // Check for generated_cv boolean flag (set by CV generation service)
            // OR cv_text markdown content
            return job.generated_cv === true || !!job.cv_text;
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
            // Reference annotationVersion to trigger Alpine re-evaluation when annotations change
            // eslint-disable-next-line no-unused-vars
            const _version = this.annotationVersion;

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
                let escapedText = targetText.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

                // Handle HTML entity encoding: annotation stores plain text but HTML has entities
                // Replace common characters with patterns that match both plain and encoded forms
                // IMPORTANT: ampersand MUST be first to avoid replacing & in patterns we just added
                escapedText = escapedText
                    .replace(/&/g, '(?:&|&amp;)')         // ampersand - MUST BE FIRST
                    .replace(/'/g, "(?:'|&#39;|&apos;)")  // apostrophe
                    .replace(/"/g, '(?:"|&quot;|&#34;)')  // double quote
                    .replace(/</g, '(?:<|&lt;)')          // less than
                    .replace(/>/g, '(?:>|&gt;)');         // greater than

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

                const data = await response.json();
                const job = data.job;  // API returns {"job": {...}}

                if (!job) throw new Error('Job not found in response');

                // CV generation service saves: cv_text (markdown), cv_editor_state (TipTap JSON)
                // Priority: cv_text (markdown) > cv_editor_state > legacy fields
                if (job.cv_text) {
                    // Convert markdown to HTML for display
                    this.cvViewer.cvHtml = this.markdownToHtml(job.cv_text);
                } else if (job.cv_editor_state?.content) {
                    // Convert TipTap JSON to HTML
                    this.cvViewer.cvHtml = this.prosemirrorToHtml(job.cv_editor_state);
                } else {
                    // Legacy fallback
                    const cvData = job.generated_cv || job.cv_data;
                    if (cvData?.html) {
                        this.cvViewer.cvHtml = cvData.html;
                    } else if (cvData?.content) {
                        this.cvViewer.cvHtml = cvData.content;
                    } else {
                        this.cvViewer.cvHtml = '<div class="text-center py-8 text-mobile-dark-500">No CV generated yet</div>';
                    }
                }

            } catch (error) {
                console.error('Failed to load CV:', error);
                this.cvViewer.cvHtml = '<div class="text-center py-8 text-mobile-red-500">Failed to load CV</div>';
            } finally {
                this.cvViewer.isLoading = false;
            }
        },

        // Convert markdown to HTML for CV display (light background)
        markdownToHtml(markdown) {
            if (!markdown) return '';

            // Basic markdown to HTML conversion - using dark text for light background
            let html = markdown
                // Headers (order matters - ### before ## before #)
                .replace(/^### (.+)$/gm, '<h3 class="text-base font-semibold text-gray-700 mt-4 mb-2 uppercase tracking-wide">$1</h3>')
                .replace(/^## (.+)$/gm, '<h2 class="text-lg font-bold text-gray-800 mt-5 mb-2">$1</h2>')
                .replace(/^# (.+)$/gm, '<h1 class="text-2xl font-bold text-purple-700 mb-1">$1</h1>')
                // Bold and italic
                .replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-gray-800">$1</strong>')
                .replace(/\*(.+?)\*/g, '<em class="text-gray-600">$1</em>')
                // Bullet lists
                .replace(/^[\-\•] (.+)$/gm, '<li class="text-gray-700 mb-1">$1</li>')
                // Line breaks and paragraphs
                .replace(/\n\n/g, '</p><p class="mb-3 text-gray-700">')
                .replace(/\n/g, '<br>');

            // Wrap consecutive list items in ul
            html = html.replace(/(<li[^>]*>.*?<\/li>(?:<br>)?)+/g, (match) => {
                // Clean up any <br> between list items
                const cleanedItems = match.replace(/<br>/g, '');
                return `<ul class="list-disc ml-5 mb-4 space-y-1">${cleanedItems}</ul>`;
            });

            // Wrap in paragraph if not already wrapped
            if (!html.startsWith('<')) {
                html = `<p class="mb-3 text-gray-700">${html}</p>`;
            }

            return `<div class="cv-content max-w-none px-6 py-4 text-gray-800 leading-relaxed">${html}</div>`;
        },

        // Convert ProseMirror/TipTap JSON to HTML (light background)
        prosemirrorToHtml(doc) {
            if (!doc?.content) return '';

            const renderNode = (node) => {
                if (!node) return '';

                switch (node.type) {
                    case 'doc':
                        return node.content?.map(renderNode).join('') || '';
                    case 'paragraph':
                        const pText = node.content?.map(renderNode).join('') || '';
                        return `<p class="mb-3 text-gray-700">${pText}</p>`;
                    case 'heading':
                        const level = node.attrs?.level || 2;
                        const hText = node.content?.map(renderNode).join('') || '';
                        const hClasses = {
                            1: 'text-2xl font-bold text-purple-700 mb-1',
                            2: 'text-lg font-bold text-gray-800 mt-5 mb-2',
                            3: 'text-base font-semibold text-gray-700 mt-4 mb-2 uppercase tracking-wide'
                        };
                        return `<h${level} class="${hClasses[level] || hClasses[2]}">${hText}</h${level}>`;
                    case 'bulletList':
                        return `<ul class="list-disc ml-5 mb-4 space-y-1">${node.content?.map(renderNode).join('') || ''}</ul>`;
                    case 'orderedList':
                        return `<ol class="list-decimal ml-5 mb-4 space-y-1">${node.content?.map(renderNode).join('') || ''}</ol>`;
                    case 'listItem':
                        return `<li class="text-gray-700">${node.content?.map(renderNode).join('') || ''}</li>`;
                    case 'text':
                        let text = node.text || '';
                        // Apply marks
                        if (node.marks) {
                            for (const mark of node.marks) {
                                if (mark.type === 'bold') text = `<strong class="font-semibold text-gray-800">${text}</strong>`;
                                if (mark.type === 'italic') text = `<em class="text-gray-600">${text}</em>`;
                            }
                        }
                        return text;
                    case 'hardBreak':
                        return '<br>';
                    default:
                        return node.content?.map(renderNode).join('') || '';
                }
            };

            return `<div class="cv-content max-w-none px-6 py-4 text-gray-800 leading-relaxed">${renderNode(doc)}</div>`;
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
