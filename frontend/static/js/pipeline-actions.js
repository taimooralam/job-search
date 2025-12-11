/**
 * Pipeline Actions - Alpine.js State Management and API Functions
 *
 * Provides:
 * - Per-action tier selection (stored in localStorage)
 * - Loading states per action
 * - API execution with cost tracking
 * - Toast notifications for success/error
 * - HTMX integration for partial page updates
 *
 * Actions supported:
 * - structure-jd: Structure/parse job description (Layer 1.4 only)
 * - full-extraction: Full extraction (Layer 1.4 + Layer 2 + Layer 4)
 * - research-company: Research company and role
 * - generate-cv: Generate tailored CV
 */

/* ============================================================================
   Configuration
   ============================================================================ */

const PIPELINE_CONFIG = {
    // Default tiers per action
    defaultTiers: {
        'structure-jd': 'balanced',
        'full-extraction': 'balanced',
        'research-company': 'balanced',
        'generate-cv': 'quality'
    },

    // Actions that support SSE streaming (via runner service)
    streamingActions: ['research-company', 'generate-cv', 'full-extraction'],

    // Streaming endpoints (via Flask proxy)
    streamingEndpoints: {
        'research-company': '/api/runner/operations/{jobId}/research-company/stream',
        'generate-cv': '/api/runner/operations/{jobId}/generate-cv/stream',
        'full-extraction': '/api/runner/operations/{jobId}/full-extraction/stream'
    },

    // Model mappings per tier per action
    models: {
        'structure-jd': {
            fast: 'gpt-4o-mini',
            balanced: 'gpt-4o-mini',
            quality: 'gpt-4o'
        },
        'full-extraction': {
            fast: 'gpt-4o-mini',
            balanced: 'gpt-4o-mini',
            quality: 'gpt-4o'
        },
        'research-company': {
            fast: 'gpt-4o-mini',
            balanced: 'gpt-4o-mini',
            quality: 'gpt-4o'
        },
        'generate-cv': {
            fast: 'claude-haiku',
            balanced: 'claude-sonnet',
            quality: 'claude-opus-4.5'  // Opus 4.5 for highest quality CV generation
        }
    },

    // Estimated costs per tier (in USD)
    costs: {
        fast: 0.02,
        balanced: 0.05,
        quality: 0.50  // Higher due to Opus 4.5
    },

    // API endpoints (relative to /api/jobs/{jobId}/)
    endpoints: {
        'structure-jd': '/api/jobs/{jobId}/process-jd',
        'full-extraction': '/api/jobs/{jobId}/full-extraction',
        'research-company': '/api/jobs/{jobId}/research-company',
        'generate-cv': '/api/jobs/{jobId}/generate-cv'
    },

    // Display labels
    labels: {
        'structure-jd': 'Structure JD',
        'full-extraction': 'Extract JD',
        'research-company': 'Research',
        'generate-cv': 'Generate CV'
    },

    // Tier display info
    tierInfo: {
        fast: {
            label: 'Fast',
            icon: '\u26A1', // Lightning bolt
            description: 'Quick processing, lower cost'
        },
        balanced: {
            label: 'Balanced',
            icon: '\u2696\uFE0F', // Balance scale
            description: 'Good quality/cost balance'
        },
        quality: {
            label: 'High-Quality',
            icon: '\u2728', // Sparkles
            description: 'Best results, higher cost'
        }
    }
};

/* ============================================================================
   Alpine.js Store Initialization
   ============================================================================ */

document.addEventListener('alpine:init', () => {
    // Global pipeline action state store
    Alpine.store('pipeline', {
        // Per-action tier selections
        tiers: { ...PIPELINE_CONFIG.defaultTiers },

        // Loading states per action
        loading: {
            'structure-jd': false,
            'full-extraction': false,
            'research-company': false,
            'generate-cv': false
        },

        // Last execution results per action
        lastResults: {
            'structure-jd': null,
            'full-extraction': null,
            'research-company': null,
            'generate-cv': null
        },

        // Accumulated costs for current session
        sessionCosts: {
            'structure-jd': 0,
            'full-extraction': 0,
            'research-company': 0,
            'generate-cv': 0
        },

        /**
         * Set tier for an action and persist to localStorage
         */
        setTier(action, tier) {
            if (!['fast', 'balanced', 'quality'].includes(tier)) {
                console.warn(`Invalid tier: ${tier}`);
                return;
            }
            this.tiers[action] = tier;
            localStorage.setItem(`pipeline_tier_${action}`, tier);
        },

        /**
         * Get current tier for an action
         */
        getTier(action) {
            return this.tiers[action] || 'balanced';
        },

        /**
         * Get model name for current tier of an action
         */
        getModel(action) {
            const tier = this.getTier(action);
            return PIPELINE_CONFIG.models[action]?.[tier] || 'gpt-4o-mini';
        },

        /**
         * Get estimated cost for a tier
         */
        getCost(tier) {
            return PIPELINE_CONFIG.costs[tier] || PIPELINE_CONFIG.costs.balanced;
        },

        /**
         * Get formatted cost string
         */
        getFormattedCost(tier) {
            const cost = this.getCost(tier);
            return `~$${cost.toFixed(2)}`;
        },

        /**
         * Get tier info (label, icon, description)
         */
        getTierInfo(tier) {
            return PIPELINE_CONFIG.tierInfo[tier] || PIPELINE_CONFIG.tierInfo.balanced;
        },

        /**
         * Check if any action is currently loading
         */
        isAnyLoading() {
            return Object.values(this.loading).some(v => v);
        },

        /**
         * Execute a pipeline action
         * @param {string} action - Action name (structure-jd, research-company, generate-cv)
         * @param {string} jobId - MongoDB job ID
         * @param {Object} options - Additional options
         * @returns {Promise<Object>} Result from API
         */
        async execute(action, jobId, options = {}) {
            // Use SSE streaming for supported actions
            if (PIPELINE_CONFIG.streamingActions.includes(action)) {
                return this.executeWithSSE(action, jobId, options);
            }

            // Fall back to synchronous execution for other actions
            return this.executeSynchronous(action, jobId, options);
        },

        /**
         * Execute a pipeline action with SSE streaming (real-time progress)
         * @param {string} action - Action name
         * @param {string} jobId - MongoDB job ID
         * @param {Object} options - Additional options
         * @returns {Promise<Object>} Result from API
         */
        async executeWithSSE(action, jobId, options = {}) {
            if (this.loading[action]) {
                console.log(`Action ${action} already running`);
                return { success: false, error: 'Action already running' };
            }

            const tier = this.getTier(action);
            const streamEndpoint = PIPELINE_CONFIG.streamingEndpoints[action]?.replace('{jobId}', jobId);

            if (!streamEndpoint) {
                console.warn(`No streaming endpoint for ${action}, falling back to sync`);
                return this.executeSynchronous(action, jobId, options);
            }

            this.loading[action] = true;

            // Show starting toast
            const actionLabel = PIPELINE_CONFIG.labels[action] || action;
            const tierInfo = this.getTierInfo(tier);
            showToast(`Starting ${actionLabel} (${tierInfo.label}) with real-time progress...`, 'info');

            // Show pipeline log panel immediately with pending states
            this.showLayerStatusPanel(action, {}, {}, true);

            try {
                // Step 1: Start the operation and get run_id
                const startResponse = await fetch(streamEndpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ tier, ...options })
                });

                if (!startResponse.ok) {
                    const errorData = await startResponse.json().catch(() => ({}));
                    throw new Error(errorData.error || `Failed to start operation: ${startResponse.status}`);
                }

                const startResult = await startResponse.json();
                const runId = startResult.run_id;

                if (!runId) {
                    throw new Error('No run_id returned from streaming endpoint');
                }

                console.log(`[${action}] Started with run_id: ${runId}`);

                // Step 2: Connect to SSE stream for real-time updates
                return new Promise((resolve) => {
                    const logStreamUrl = `/api/runner/operations/${runId}/logs`;
                    const eventSource = new EventSource(logStreamUrl);

                    let lastLayerStatus = {};
                    let finalResult = null;

                    // Handle regular log messages
                    eventSource.onmessage = (event) => {
                        console.log(`[${action}] Log: ${event.data}`);
                        // Append log to the pipeline log panel's terminal section
                        if (typeof window.appendLogToPipelinePanel === 'function') {
                            window.appendLogToPipelinePanel(event.data);
                        }
                    };

                    // Handle layer status updates
                    eventSource.addEventListener('layer_status', (event) => {
                        try {
                            lastLayerStatus = JSON.parse(event.data);
                            console.log(`[${action}] Layer status:`, lastLayerStatus);
                            // Update the panel with real-time layer progress
                            if (typeof window.showPipelineLogPanel === 'function') {
                                window.showPipelineLogPanel(action, lastLayerStatus, {}, true);
                            }
                        } catch (e) {
                            console.error('Failed to parse layer_status:', e);
                        }
                    });

                    // Handle final result
                    eventSource.addEventListener('result', (event) => {
                        try {
                            finalResult = JSON.parse(event.data);
                            console.log(`[${action}] Result:`, finalResult);
                        } catch (e) {
                            console.error('Failed to parse result:', e);
                        }
                    });

                    // Handle completion/failure
                    eventSource.addEventListener('end', (event) => {
                        const status = event.data;
                        console.log(`[${action}] Ended with status: ${status}`);

                        eventSource.close();
                        this.loading[action] = false;

                        if (status === 'completed' && finalResult) {
                            // Store result
                            this.lastResults[action] = {
                                success: finalResult.success,
                                timestamp: new Date().toISOString(),
                                cost: finalResult.cost_usd || this.getCost(tier),
                                data: finalResult
                            };

                            // Update session costs
                            this.sessionCosts[action] += finalResult.cost_usd || this.getCost(tier);

                            // Show final layer status panel
                            if (finalResult.data?.layer_status || Object.keys(lastLayerStatus).length > 0) {
                                this.showLayerStatusPanel(
                                    action,
                                    finalResult.data?.layer_status || lastLayerStatus,
                                    finalResult.data || {}
                                );
                            } else {
                                showToast(`${actionLabel} completed successfully. Refreshing page...`, 'success');
                            }

                            // Dispatch custom event
                            document.dispatchEvent(new CustomEvent('pipeline-action-complete', {
                                detail: { action, jobId, result: finalResult }
                            }));

                            // Reload page after delay
                            setTimeout(() => window.location.reload(), 3000);

                            resolve(finalResult);
                        } else {
                            // Failed
                            const errorMsg = finalResult?.error || 'Operation failed';
                            showToast(`${actionLabel} failed: ${errorMsg}`, 'error');

                            this.lastResults[action] = {
                                success: false,
                                timestamp: new Date().toISOString(),
                                error: errorMsg
                            };

                            resolve({ success: false, error: errorMsg });
                        }
                    });

                    // Handle SSE errors
                    eventSource.addEventListener('error', (event) => {
                        console.warn(`[${action}] SSE error, falling back to polling`);
                        eventSource.close();

                        // Fall back to polling for status
                        this.pollOperationStatus(action, jobId, runId, actionLabel, tier, resolve);
                    });

                    eventSource.onerror = (err) => {
                        console.error(`[${action}] SSE connection error:`, err);
                        // The 'error' event listener should handle this
                    };
                });

            } catch (error) {
                console.error(`${action} failed:`, error);
                showToast(`${actionLabel} failed: ${error.message}`, 'error');

                this.loading[action] = false;
                this.lastResults[action] = {
                    success: false,
                    timestamp: new Date().toISOString(),
                    error: error.message
                };

                return { success: false, error: error.message };
            }
        },

        /**
         * Poll operation status (fallback when SSE fails)
         */
        async pollOperationStatus(action, jobId, runId, actionLabel, tier, resolve) {
            const maxAttempts = 120;  // 2 minutes max
            let attempts = 0;

            const poll = async () => {
                attempts++;

                try {
                    const statusResponse = await fetch(`/api/runner/operations/${runId}/status`);
                    const statusData = await statusResponse.json();

                    if (statusData.status === 'completed') {
                        this.loading[action] = false;

                        const result = statusData.result || { success: true };
                        this.lastResults[action] = {
                            success: result.success,
                            timestamp: new Date().toISOString(),
                            cost: result.cost_usd || this.getCost(tier),
                            data: result
                        };

                        if (result.success !== false) {
                            this.sessionCosts[action] += result.cost_usd || this.getCost(tier);
                            showToast(`${actionLabel} completed successfully. Refreshing page...`, 'success');
                            setTimeout(() => window.location.reload(), 3000);
                        }

                        resolve(result);
                        return;
                    }

                    if (statusData.status === 'failed') {
                        this.loading[action] = false;
                        const errorMsg = statusData.error || 'Operation failed';
                        showToast(`${actionLabel} failed: ${errorMsg}`, 'error');
                        resolve({ success: false, error: errorMsg });
                        return;
                    }

                    // Still running, poll again
                    if (attempts < maxAttempts) {
                        setTimeout(poll, 1000);
                    } else {
                        this.loading[action] = false;
                        showToast(`${actionLabel} timed out`, 'error');
                        resolve({ success: false, error: 'Operation timed out' });
                    }

                } catch (error) {
                    console.error('Polling error:', error);
                    if (attempts < maxAttempts) {
                        setTimeout(poll, 2000);
                    } else {
                        this.loading[action] = false;
                        showToast(`${actionLabel} failed: ${error.message}`, 'error');
                        resolve({ success: false, error: error.message });
                    }
                }
            };

            poll();
        },

        /**
         * Execute a pipeline action synchronously (original behavior)
         * @param {string} action - Action name (structure-jd, research-company, generate-cv)
         * @param {string} jobId - MongoDB job ID
         * @param {Object} options - Additional options
         * @returns {Promise<Object>} Result from API
         */
        async executeSynchronous(action, jobId, options = {}) {
            if (this.loading[action]) {
                console.log(`Action ${action} already running`);
                return { success: false, error: 'Action already running' };
            }

            const tier = this.getTier(action);
            const model = this.getModel(action);
            const endpoint = PIPELINE_CONFIG.endpoints[action]?.replace('{jobId}', jobId);

            if (!endpoint) {
                console.error(`Unknown action: ${action}`);
                showToast(`Unknown action: ${action}`, 'error');
                return { success: false, error: 'Unknown action' };
            }

            this.loading[action] = true;

            // Show starting toast
            const actionLabel = PIPELINE_CONFIG.labels[action] || action;
            const tierInfo = this.getTierInfo(tier);
            showToast(`Starting ${actionLabel} (${tierInfo.label})...`, 'info');

            // Show pipeline log panel immediately with pending states
            this.showLayerStatusPanel(action, {}, {}, true);  // true = isPending

            try {
                const response = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        tier,
                        model,
                        ...options
                    })
                });

                const result = await response.json();

                // Store result
                this.lastResults[action] = {
                    success: result.success,
                    timestamp: new Date().toISOString(),
                    cost: result.cost_usd || this.getCost(tier),
                    data: result
                };

                if (result.success) {
                    // Update session costs
                    this.sessionCosts[action] += result.cost_usd || this.getCost(tier);

                    // Show detailed layer status panel for all actions that return layer_status
                    if (result.data?.layer_status) {
                        this.showLayerStatusPanel(action, result.data.layer_status, result.data);
                    } else {
                        showToast(`${actionLabel} completed successfully. Refreshing page...`, 'success');
                    }

                    // Dispatch custom event for other components
                    document.dispatchEvent(new CustomEvent('pipeline-action-complete', {
                        detail: { action, jobId, result }
                    }));

                    // Reload page after short delay to show updated data
                    setTimeout(() => {
                        window.location.reload();
                    }, 3000);  // Longer delay to read layer status panel
                } else {
                    showToast(result.error || `${actionLabel} failed`, 'error');
                }

                return result;
            } catch (error) {
                console.error(`${action} failed:`, error);
                showToast(`${actionLabel} failed: ${error.message}`, 'error');

                this.lastResults[action] = {
                    success: false,
                    timestamp: new Date().toISOString(),
                    error: error.message
                };

                return { success: false, error: error.message };
            } finally {
                this.loading[action] = false;
            }
        },

        /**
         * Trigger HTMX refresh for relevant page sections after action completes
         */
        triggerRefresh(action, jobId) {
            // Use HTMX to refresh specific sections based on action
            const refreshTargets = {
                'structure-jd': ['#jd-structured-content', '#jd-viewer-content'],
                'full-extraction': ['#jd-structured-content', '#jd-viewer-content', '#pain-points-section', '#fit-score-section'],
                'research-company': ['#company-research-section', '#research-panel'],
                'generate-cv': ['#cv-preview-section', '#cv-editor-content']
            };

            const targets = refreshTargets[action] || [];
            targets.forEach(selector => {
                const element = document.querySelector(selector);
                if (element) {
                    htmx.trigger(element, 'refresh');
                }
            });

            // Also trigger a general refresh event
            htmx.trigger(document.body, 'pipeline-action-complete', { action, jobId });
        },

        /**
         * Get total session cost across all actions
         */
        getTotalSessionCost() {
            return Object.values(this.sessionCosts).reduce((sum, cost) => sum + cost, 0);
        },

        /**
         * Reset session costs
         */
        resetSessionCosts() {
            Object.keys(this.sessionCosts).forEach(key => {
                this.sessionCosts[key] = 0;
            });
        },

        /**
         * Show detailed layer status panel for pipeline actions
         * @param {string} action - Action name
         * @param {Object} layerStatus - Per-layer status from backend
         * @param {Object} data - Full response data
         * @param {boolean} isPending - If true, show as "in progress" with spinning icons
         */
        showLayerStatusPanel(action, layerStatus, data, isPending = false) {
            // Use the global showPipelineLogPanel if available
            if (typeof window.showPipelineLogPanel === 'function') {
                window.showPipelineLogPanel(action, layerStatus, data, isPending);
            } else {
                // Fallback to simple toast
                const actionLabel = PIPELINE_CONFIG.labels[action] || action;
                if (isPending) {
                    showToast(`${actionLabel} in progress...`, 'info');
                } else {
                    showToast(`${actionLabel} completed successfully. Refreshing page...`, 'success');
                }
            }

            // Also log to console for debugging
            if (!isPending) {
                console.log(`${action} Results:`, { layerStatus, data });
            }
        }
    });

    // Initialize tiers from localStorage
    const actions = Object.keys(PIPELINE_CONFIG.defaultTiers);
    actions.forEach(action => {
        const saved = localStorage.getItem(`pipeline_tier_${action}`);
        if (saved && ['fast', 'balanced', 'quality'].includes(saved)) {
            Alpine.store('pipeline').tiers[action] = saved;
        }
    });
});

/* ============================================================================
   TieredActionButton Alpine.js Component
   ============================================================================ */

/**
 * Alpine.js component for a tiered action button with dropdown
 *
 * Usage:
 * <div x-data="tieredActionButton({ action: 'structure-jd', jobId: '123' })">
 *   <div class="pipeline-action-wrapper">
 *     <div class="btn-action-group" :class="{ 'btn-action-loading': loading }">
 *       <button @click="execute()" class="btn-action-main btn-action-primary">
 *         <span x-text="label"></span>
 *         <span class="tier-badge" :class="tier" x-text="tierIcon"></span>
 *       </button>
 *       <button @click="open = !open" class="btn-action-dropdown btn-action-primary">
 *         <svg>...</svg>
 *       </button>
 *     </div>
 *     <div x-show="open" @click.away="open = false" class="tier-dropdown-menu">
 *       <!-- Tier options -->
 *     </div>
 *   </div>
 * </div>
 */
function tieredActionButton(config) {
    return {
        action: config.action,
        jobId: config.jobId,
        open: false,
        customLabel: config.label || null,

        // Computed properties
        get label() {
            return this.customLabel || PIPELINE_CONFIG.labels[this.action] || this.action;
        },

        get tier() {
            return Alpine.store('pipeline').getTier(this.action);
        },

        get model() {
            return Alpine.store('pipeline').getModel(this.action);
        },

        get cost() {
            return Alpine.store('pipeline').getCost(this.tier);
        },

        get formattedCost() {
            return Alpine.store('pipeline').getFormattedCost(this.tier);
        },

        get loading() {
            return Alpine.store('pipeline').loading[this.action];
        },

        get tierInfo() {
            return Alpine.store('pipeline').getTierInfo(this.tier);
        },

        get tierIcon() {
            return this.tierInfo.icon;
        },

        get tierLabel() {
            return this.tierInfo.label;
        },

        get models() {
            return PIPELINE_CONFIG.models[this.action] || {};
        },

        get allTiers() {
            return ['fast', 'balanced', 'quality'];
        },

        // Methods
        setTier(tier) {
            Alpine.store('pipeline').setTier(this.action, tier);
            this.open = false;
        },

        async execute() {
            if (this.loading) return;
            await Alpine.store('pipeline').execute(this.action, this.jobId);
        },

        getTierIcon(tier) {
            return PIPELINE_CONFIG.tierInfo[tier]?.icon || '\u2022';
        },

        getTierLabel(tier) {
            return PIPELINE_CONFIG.tierInfo[tier]?.label || tier;
        },

        getTierModel(tier) {
            return PIPELINE_CONFIG.models[this.action]?.[tier] || 'gpt-4o-mini';
        },

        getTierCost(tier) {
            return Alpine.store('pipeline').getFormattedCost(tier);
        },

        isTierSelected(tier) {
            return this.tier === tier;
        },

        // Keyboard navigation for dropdown
        handleKeydown(event) {
            if (!this.open) return;

            const tiers = this.allTiers;
            const currentIndex = tiers.indexOf(this.tier);

            switch (event.key) {
                case 'ArrowDown':
                    event.preventDefault();
                    const nextIndex = (currentIndex + 1) % tiers.length;
                    this.setTier(tiers[nextIndex]);
                    break;
                case 'ArrowUp':
                    event.preventDefault();
                    const prevIndex = (currentIndex - 1 + tiers.length) % tiers.length;
                    this.setTier(tiers[prevIndex]);
                    break;
                case 'Escape':
                    this.open = false;
                    break;
                case 'Enter':
                    this.open = false;
                    break;
            }
        }
    };
}

// Make component available globally
window.tieredActionButton = tieredActionButton;

/* ============================================================================
   Direct API Functions (for non-Alpine usage)
   ============================================================================ */

/**
 * Structure job description (Layer 1.4 only)
 * @param {string} jobId - MongoDB job ID
 * @param {Object} options - Options including tier
 */
async function structureJD(jobId, options = {}) {
    const tier = options.tier || localStorage.getItem('pipeline_tier_structure-jd') || 'balanced';
    const model = PIPELINE_CONFIG.models['structure-jd']?.[tier] || 'gpt-4o-mini';

    try {
        const response = await fetch(`/api/jobs/${jobId}/process-jd`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tier, model, ...options })
        });
        return await response.json();
    } catch (error) {
        console.error('Structure JD failed:', error);
        throw error;
    }
}

/**
 * Full JD extraction (Layer 1.4 + Layer 2 + Layer 4)
 * @param {string} jobId - MongoDB job ID
 * @param {Object} options - Options including tier
 */
async function fullExtraction(jobId, options = {}) {
    const tier = options.tier || localStorage.getItem('pipeline_tier_full-extraction') || 'balanced';
    const model = PIPELINE_CONFIG.models['full-extraction']?.[tier] || 'gpt-4o-mini';

    try {
        const response = await fetch(`/api/jobs/${jobId}/full-extraction`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tier, model, ...options })
        });
        return await response.json();
    } catch (error) {
        console.error('Full extraction failed:', error);
        throw error;
    }
}

/**
 * Research company
 * @param {string} jobId - MongoDB job ID
 * @param {Object} options - Options including tier
 */
async function researchCompany(jobId, options = {}) {
    const tier = options.tier || localStorage.getItem('pipeline_tier_research-company') || 'balanced';
    const model = PIPELINE_CONFIG.models['research-company']?.[tier] || 'gpt-4o-mini';

    try {
        const response = await fetch(`/api/jobs/${jobId}/research-company`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tier, model, ...options })
        });
        return await response.json();
    } catch (error) {
        console.error('Research company failed:', error);
        throw error;
    }
}

/**
 * Generate tailored CV
 * @param {string} jobId - MongoDB job ID
 * @param {Object} options - Options including tier
 */
async function generateCV(jobId, options = {}) {
    const tier = options.tier || localStorage.getItem('pipeline_tier_generate-cv') || 'quality';
    const model = PIPELINE_CONFIG.models['generate-cv']?.[tier] || 'claude-sonnet';

    try {
        const response = await fetch(`/api/jobs/${jobId}/generate-cv`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tier, model, ...options })
        });
        return await response.json();
    } catch (error) {
        console.error('Generate CV failed:', error);
        throw error;
    }
}

// Export direct functions for non-Alpine usage
window.structureJD = structureJD;
window.fullExtraction = fullExtraction;
window.researchCompany = researchCompany;
window.generateCV = generateCV;

/* ============================================================================
   Cost Display Component
   ============================================================================ */

/**
 * Alpine.js component for displaying session costs
 *
 * Usage:
 * <div x-data="pipelineCostDisplay()">
 *   <span class="cost-display">
 *     <span class="cost-display-value" x-text="formattedTotal"></span>
 *     <span class="cost-display-label">session cost</span>
 *   </span>
 * </div>
 */
function pipelineCostDisplay() {
    return {
        get total() {
            return Alpine.store('pipeline')?.getTotalSessionCost() || 0;
        },

        get formattedTotal() {
            return `$${this.total.toFixed(4)}`;
        },

        get hasSpending() {
            return this.total > 0;
        },

        reset() {
            Alpine.store('pipeline')?.resetSessionCosts();
        }
    };
}

window.pipelineCostDisplay = pipelineCostDisplay;

/* ============================================================================
   Helper: Toast Notification (uses global showToast if available)
   ============================================================================ */

/**
 * Show toast notification
 * Falls back to console.log if showToast is not available
 */
function showToastSafe(message, type = 'success') {
    if (typeof window.showToast === 'function') {
        window.showToast(message, type);
    } else {
        // Fallback to console
        const logMethod = type === 'error' ? 'error' : type === 'warning' ? 'warn' : 'log';
        console[logMethod](`[${type.toUpperCase()}] ${message}`);
    }
}

// Use showToast from global scope (defined in base.html or job-detail.js)
// This just aliases for consistency in this module
if (typeof showToast === 'undefined') {
    var showToast = showToastSafe;
}

/* ============================================================================
   Event Listeners
   ============================================================================ */

// Close dropdowns when clicking outside
document.addEventListener('click', (event) => {
    // Close tier dropdowns when clicking outside
    if (!event.target.closest('.pipeline-action-wrapper')) {
        // Let Alpine handle this via @click.away
    }
});

// Handle keyboard shortcuts for pipeline actions
document.addEventListener('keydown', (event) => {
    // Alt+1: Structure JD (Layer 1.4 only)
    // Alt+2: Full Extraction (Layer 1.4 + 2 + 4)
    // Alt+3: Research Company
    // Alt+4: Generate CV
    if (event.altKey && !event.ctrlKey && !event.metaKey) {
        const jobId = document.querySelector('[data-job-id]')?.dataset.jobId;
        if (!jobId) return;

        const store = Alpine.store('pipeline');
        if (!store) return;

        switch (event.key) {
            case '1':
                event.preventDefault();
                store.execute('structure-jd', jobId);
                break;
            case '2':
                event.preventDefault();
                store.execute('full-extraction', jobId);
                break;
            case '3':
                event.preventDefault();
                store.execute('research-company', jobId);
                break;
            case '4':
                event.preventDefault();
                store.execute('generate-cv', jobId);
                break;
        }
    }
});

/* ============================================================================
   HTMX Integration
   ============================================================================ */

// Listen for HTMX events to update UI after pipeline actions
document.body.addEventListener('htmx:afterSwap', (event) => {
    // Re-initialize Alpine components in swapped content if needed
    if (event.detail.target.querySelector('[x-data]')) {
        // Alpine should auto-init, but we can force it if needed
    }
});

// Expose configuration for debugging
window.PIPELINE_CONFIG = PIPELINE_CONFIG;
