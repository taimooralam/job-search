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
        timeFilter: '24h',      // Current time filter
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
            hasIdentityAnnotations: false
        },
        annotationSheet: {
            show: false,
            selectedText: '',
            relevance: 'relevant',
            requirement: 'neutral',
            identity: 'peripheral',
            passion: 'neutral',
            saving: false
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
                    limit: '20'
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

            this.isDragging = true;
            this.startX = e.touches[0].clientX;
            this.startY = e.touches[0].clientY;
            this.currentX = this.startX;

            // Add dragging class
            this.$refs.currentCard?.classList.add('dragging');
        },

        onTouchMove(e) {
            if (!this.isDragging) return;

            this.currentX = e.touches[0].clientX;
            const deltaX = this.currentX - this.startX;
            const deltaY = e.touches[0].clientY - this.startY;

            // If vertical movement is greater, allow scroll
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

            this.annotationMode = true;

            // Load existing annotations
            try {
                const response = await fetch(`/api/jobs/${this.currentJob._id}/jd-annotations`);
                if (response.ok) {
                    const data = await response.json();
                    this.annotation.annotations = data.annotations || [];
                    this.annotation.personaStatement = data.synthesized_persona?.persona_statement || null;
                    this.checkIdentityAnnotations();
                }
            } catch (error) {
                console.error('Failed to load annotations:', error);
                this.annotation.annotations = [];
            }
        },

        closeAnnotationMode() {
            this.annotationMode = false;
        },

        checkIdentityAnnotations() {
            const identityLevels = ['core_identity', 'strong_identity', 'developing'];
            const passionLevels = ['love_it', 'enjoy'];
            const strengthLevels = ['core_strength', 'extremely_relevant'];

            this.annotation.hasIdentityAnnotations = this.annotation.annotations.some(a =>
                a.is_active !== false && (
                    identityLevels.includes(a.identity) ||
                    passionLevels.includes(a.passion) ||
                    strengthLevels.includes(a.relevance)
                )
            );
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
            // Get selected text or smart-select sentence
            const selection = window.getSelection();
            let selectedText = '';

            if (selection && !selection.isCollapsed) {
                selectedText = selection.toString().trim();
            } else {
                // Try to get sentence at tap point
                selectedText = this.getSentenceAtPoint(event);
            }

            if (selectedText && selectedText.length > 10) {
                this.annotationSheet.selectedText = selectedText;
                this.annotationSheet.relevance = 'relevant';
                this.annotationSheet.requirement = 'neutral';
                this.annotationSheet.identity = 'peripheral';
                this.annotationSheet.passion = 'neutral';
                this.annotationSheet.show = true;

                // Haptic
                if ('vibrate' in navigator) {
                    navigator.vibrate(30);
                }
            }
        },

        // Get sentence at tap point
        getSentenceAtPoint(event) {
            try {
                const range = document.caretRangeFromPoint(event.clientX, event.clientY);
                if (!range) return '';

                const text = range.startContainer.textContent || '';
                const offset = range.startOffset;

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
            window.getSelection()?.removeAllRanges();
        },

        async saveAnnotation() {
            if (!this.annotationSheet.selectedText || !this.currentJob) return;

            this.annotationSheet.saving = true;

            try {
                // Create annotation
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

                this.annotation.annotations.push(newAnnotation);

                // Save to server
                await fetch(`/api/jobs/${this.currentJob._id}/jd-annotations`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        annotations: this.annotation.annotations,
                        annotation_version: 1
                    })
                });

                this.checkIdentityAnnotations();

                // Haptic
                if ('vibrate' in navigator) {
                    navigator.vibrate([50, 30, 50]);
                }

                window.showToast?.('Annotation saved', 'success');
                this.closeAnnotationSheet();

            } catch (error) {
                console.error('Failed to save annotation:', error);
                window.showToast?.('Failed to save', 'error');
            } finally {
                this.annotationSheet.saving = false;
            }
        },

        async generatePersona() {
            if (!this.currentJob || this.annotation.personaLoading) return;

            this.annotation.personaLoading = true;

            try {
                // Save annotations first
                await fetch(`/api/jobs/${this.currentJob._id}/jd-annotations`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        annotations: this.annotation.annotations,
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
