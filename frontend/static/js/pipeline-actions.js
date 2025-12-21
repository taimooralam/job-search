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
    // ============================================================================
    // Operation Aliases (backward compatibility: old name -> new name)
    // ============================================================================
    operationAliases: {
        'full-extraction': 'analyze-job',
        'structure-jd': 'prepare-annotations',
        'all-ops': 'full-analysis',
        'process-jd': 'analyze-job'  // Remove duplicate
    },

    // Reverse aliases (new name -> old name for backend compatibility)
    reverseAliases: {
        'analyze-job': 'full-extraction',
        'prepare-annotations': 'structure-jd',
        'full-analysis': 'all-ops',
        'discover-contacts': 'research-company',  // Temporarily map to parent
        'generate-cover-letter': 'generate-cv',   // Temporarily map to parent
        'generate-outreach': 'research-company'   // Temporarily map to parent
    },

    // Default tiers per action (using new operation names)
    defaultTiers: {
        'analyze-job': 'balanced',
        'prepare-annotations': 'balanced',
        'research-company': 'balanced',
        'discover-contacts': 'balanced',
        'generate-cv': 'quality',
        'generate-cover-letter': 'quality',
        'generate-outreach': 'balanced',
        'full-analysis': 'balanced',
        // Legacy aliases (for backward compatibility)
        'structure-jd': 'balanced',
        'full-extraction': 'balanced',
        'all-ops': 'balanced'
    },

    // Actions that support background execution (via runner service)
    // NOTE: These don't actually use SSE streaming - they initiate background operations
    // and return a run_id for HTTP polling at 200ms intervals
    streamingActions: ['research-company', 'generate-cv', 'analyze-job', 'full-analysis', 'discover-contacts', 'generate-cover-letter', 'generate-outreach',
        // Legacy aliases
        'full-extraction', 'all-ops'],

    // Start endpoints (via Flask proxy) - using new /start naming (replaces /stream)
    // NOTE: The name "streaming" is misleading - these endpoints just start background
    // operations and return a run_id. Actual progress comes via HTTP polling.
    streamingEndpoints: {
        'research-company': '/api/runner/operations/{jobId}/research-company/start',
        'generate-cv': '/api/runner/operations/{jobId}/generate-cv/start',
        'analyze-job': '/api/runner/operations/{jobId}/full-extraction/start',
        'prepare-annotations': '/api/runner/operations/{jobId}/structure-jd/start',
        'full-analysis': '/api/runner/jobs/{jobId}/all-ops/start',
        'discover-contacts': '/api/runner/operations/{jobId}/research-company/start',  // Maps to research-company for now
        'generate-cover-letter': '/api/runner/operations/{jobId}/generate-cv/start',   // Maps to generate-cv for now
        'generate-outreach': '/api/runner/operations/{jobId}/research-company/start',  // Maps to research-company for now
        // Legacy aliases
        'full-extraction': '/api/runner/operations/{jobId}/full-extraction/start',
        'structure-jd': '/api/runner/operations/{jobId}/structure-jd/start',
        'all-ops': '/api/runner/jobs/{jobId}/all-ops/start'
    },

    // Queue endpoints (for queue-first approach on detail page)
    queueEndpoints: {
        'analyze-job': '/api/runner/jobs/{jobId}/operations/full-extraction/queue',
        'prepare-annotations': '/api/runner/jobs/{jobId}/operations/structure-jd/queue',
        'research-company': '/api/runner/jobs/{jobId}/operations/research-company/queue',
        'discover-contacts': '/api/runner/jobs/{jobId}/operations/research-company/queue',  // Maps to research-company for now
        'generate-cv': '/api/runner/jobs/{jobId}/operations/generate-cv/queue',
        'generate-cover-letter': '/api/runner/jobs/{jobId}/operations/generate-cv/queue',   // Maps to generate-cv for now
        'generate-outreach': '/api/runner/jobs/{jobId}/operations/research-company/queue',  // Maps to research-company for now
        'full-analysis': '/api/runner/jobs/{jobId}/all-ops/start',  // Use /start (not /stream)
        // Legacy aliases
        'structure-jd': '/api/runner/jobs/{jobId}/operations/structure-jd/queue',
        'full-extraction': '/api/runner/jobs/{jobId}/operations/full-extraction/queue',
        'all-ops': '/api/runner/jobs/{jobId}/all-ops/start'  // Use /start (not /stream)
    },

    // Model mappings per tier per action
    models: {
        'analyze-job': {
            fast: 'gpt-4o-mini',
            balanced: 'gpt-4o',
            quality: 'claude-opus-4.5'
        },
        'prepare-annotations': {
            fast: 'gpt-4o-mini',
            balanced: 'gpt-4o-mini',
            quality: 'gpt-4o'
        },
        'research-company': {
            fast: 'gpt-4o-mini',
            balanced: 'gpt-4o-mini',
            quality: 'gpt-4o'
        },
        'discover-contacts': {
            fast: 'gpt-4o-mini',
            balanced: 'gpt-4o-mini',
            quality: 'gpt-4o'
        },
        'generate-cv': {
            fast: 'claude-haiku',
            balanced: 'claude-sonnet',
            quality: 'claude-opus-4.5'
        },
        'generate-cover-letter': {
            fast: 'claude-haiku',
            balanced: 'claude-sonnet',
            quality: 'claude-opus-4.5'
        },
        'generate-outreach': {
            fast: 'gpt-4o-mini',
            balanced: 'gpt-4o-mini',
            quality: 'gpt-4o'
        },
        'full-analysis': {
            fast: 'gpt-4o-mini + claude-haiku',
            balanced: 'gpt-4o-mini + claude-sonnet',
            quality: 'gpt-4o + claude-opus-4.5'
        },
        // Legacy aliases
        'structure-jd': {
            fast: 'gpt-4o-mini',
            balanced: 'gpt-4o-mini',
            quality: 'gpt-4o'
        },
        'full-extraction': {
            fast: 'gpt-4o-mini',
            balanced: 'gpt-4o',
            quality: 'claude-opus-4.5'
        },
        'all-ops': {
            fast: 'gpt-4o-mini + claude-haiku',
            balanced: 'gpt-4o-mini + claude-sonnet',
            quality: 'gpt-4o + claude-opus-4.5'
        }
    },

    // Estimated costs per tier (in USD)
    costs: {
        fast: 0.02,
        balanced: 0.05,
        quality: 0.50
    },

    // API endpoints (relative to /api/jobs/{jobId}/)
    endpoints: {
        'analyze-job': '/api/jobs/{jobId}/full-extraction',
        'prepare-annotations': '/api/jobs/{jobId}/process-jd',
        'research-company': '/api/jobs/{jobId}/research-company',
        'discover-contacts': '/api/jobs/{jobId}/research-company',  // Maps to research-company for now
        'generate-cv': '/api/jobs/{jobId}/generate-cv',
        'generate-cover-letter': '/api/jobs/{jobId}/generate-cv',   // Maps to generate-cv for now
        'generate-outreach': '/api/jobs/{jobId}/research-company',  // Maps to research-company for now
        'full-analysis': '/api/runner/jobs/{jobId}/all-ops/start',  // Use /start (not /stream)
        // Legacy aliases
        'structure-jd': '/api/jobs/{jobId}/process-jd',
        'full-extraction': '/api/jobs/{jobId}/full-extraction',
        'all-ops': '/api/runner/jobs/{jobId}/all-ops/start'  // Use /start (not /stream)
    },

    // Display labels (new unified names)
    labels: {
        'analyze-job': 'Analyze Job',
        'prepare-annotations': 'Prepare Annotations',
        'research-company': 'Research Company',
        'discover-contacts': 'Discover Contacts',
        'generate-cv': 'Generate CV',
        'generate-cover-letter': 'Generate Cover Letter',
        'generate-outreach': 'Generate Outreach',
        'full-analysis': 'Full Analysis',
        // Legacy aliases for backward compatibility
        'structure-jd': 'Prepare Annotations',
        'full-extraction': 'Analyze Job',
        'all-ops': 'Full Analysis'
    },

    // Operation descriptions (for menu tooltips - short form)
    descriptions: {
        'analyze-job': 'JD + pain points + fit score',
        'prepare-annotations': 'For annotation editor',
        'research-company': 'Company + role intel',
        'discover-contacts': 'Find hiring team',
        'generate-cv': 'Tailored CV',
        'generate-cover-letter': 'Standalone letter',
        'generate-outreach': 'Contact messages',
        'full-analysis': 'Complete job analysis'
    },

    // Operation subtext (for learning curve - longer descriptions)
    subtext: {
        'full-analysis': 'Run all analysis steps in parallel',
        'analyze-job': 'Extract JD, identify pain points, calculate fit score',
        'prepare-annotations': 'Structure JD into sections for annotation editor',
        'research-company': 'Gather company signals, funding, news, and role context',
        'discover-contacts': 'Find hiring managers, recruiters, and relevant peers',
        'generate-cv': 'Create tailored CV matched to job requirements',
        'generate-cover-letter': 'Write personalized cover letter for this role',
        'generate-outreach': 'Create LinkedIn and email messages for contacts'
    },

    // Operation categories for menu grouping
    categories: {
        'ANALYSIS': ['analyze-job', 'prepare-annotations'],
        'RESEARCH': ['research-company', 'discover-contacts'],
        'GENERATION': ['generate-cv', 'generate-cover-letter', 'generate-outreach']
    },

    // Operation icons (emoji)
    icons: {
        'analyze-job': '\uD83D\uDCC4',           // Document
        'prepare-annotations': '\u270F\uFE0F',    // Pencil
        'research-company': '\uD83C\uDFE2',       // Building
        'discover-contacts': '\uD83D\uDC65',      // People
        'generate-cv': '\uD83D\uDCDD',            // Memo
        'generate-cover-letter': '\uD83D\uDC8C',  // Love letter
        'generate-outreach': '\uD83D\uDCE8',      // Envelope with arrow
        'full-analysis': '\u26A1'                 // Lightning
    },

    // Tier display info (unified naming: fast/balanced/quality)
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
            label: 'Quality',
            icon: '\u2728', // Sparkles
            description: 'Best results, higher cost'
        }
    },

    // Tier code mappings (for backward compatibility with A/B/C/D)
    tierAliases: {
        'A': 'quality',
        'B': 'balanced',
        'C': 'fast',
        'D': 'fast',
        'auto': 'balanced',
        'Gold': 'quality',
        'Silver': 'balanced',
        'Bronze': 'fast'
    }
};

/* ============================================================================
   Helper Functions
   ============================================================================ */

/**
 * Normalize tier value to standard format (fast/balanced/quality)
 * Handles legacy A/B/C/D and Gold/Silver/Bronze formats
 * @param {string} tier - Input tier value
 * @returns {string} Normalized tier (fast, balanced, or quality)
 */
function normalizeTier(tier) {
    if (!tier) return 'balanced';
    const normalized = PIPELINE_CONFIG.tierAliases[tier];
    if (normalized) return normalized;
    if (['fast', 'balanced', 'quality'].includes(tier)) return tier;
    return 'balanced';
}

/**
 * Get operation name, resolving any aliases
 * @param {string} operation - Operation name (may be old or new)
 * @returns {string} Canonical operation name
 */
function resolveOperation(operation) {
    return PIPELINE_CONFIG.operationAliases[operation] || operation;
}

/**
 * Get backend operation name for API calls
 * @param {string} operation - Operation name (new format)
 * @returns {string} Backend operation name
 */
function getBackendOperation(operation) {
    return PIPELINE_CONFIG.reverseAliases[operation] || operation;
}

// Export helpers for global use
window.normalizeTier = normalizeTier;
window.resolveOperation = resolveOperation;
window.getBackendOperation = getBackendOperation;

/* ============================================================================
   Alpine.js Store Initialization
   ============================================================================ */

document.addEventListener('alpine:init', () => {
    // Global pipeline action state store
    Alpine.store('pipeline', {
        // Per-action tier selections
        tiers: { ...PIPELINE_CONFIG.defaultTiers },

        // Loading states per action (includes both new and legacy names)
        loading: {
            // New operation names
            'analyze-job': false,
            'prepare-annotations': false,
            'research-company': false,
            'discover-contacts': false,
            'generate-cv': false,
            'generate-cover-letter': false,
            'generate-outreach': false,
            'full-analysis': false,
            // Legacy aliases
            'structure-jd': false,
            'full-extraction': false,
            'all-ops': false
        },

        // Last execution results per action
        lastResults: {
            // New operation names
            'analyze-job': null,
            'prepare-annotations': null,
            'research-company': null,
            'discover-contacts': null,
            'generate-cv': null,
            'generate-cover-letter': null,
            'generate-outreach': null,
            'full-analysis': null,
            // Legacy aliases
            'structure-jd': null,
            'full-extraction': null,
            'all-ops': null
        },

        // Accumulated costs for current session
        sessionCosts: {
            // New operation names
            'analyze-job': 0,
            'prepare-annotations': 0,
            'research-company': 0,
            'discover-contacts': 0,
            'generate-cv': 0,
            'generate-cover-letter': 0,
            'generate-outreach': 0,
            'full-analysis': 0,
            // Legacy aliases
            'structure-jd': 0,
            'full-extraction': 0,
            'all-ops': 0
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
         * Queue a pipeline action for background execution (queue-first approach)
         *
         * This is the new queue-based execution for the job detail page:
         * - Adds operation to Redis queue
         * - Status updates via WebSocket
         * - User can view logs on-demand via CLI panel
         *
         * @param {string} action - Action name (structure-jd, full-extraction, research-company, generate-cv)
         * @param {string} jobId - MongoDB job ID
         * @param {Object} options - Additional options (force_refresh, use_llm, use_annotations)
         * @returns {Promise<Object>} Queue response
         */
        async queueExecution(action, jobId, options = {}) {
            if (this.loading[action]) {
                console.log(`Action ${action} already running/queued`);
                return { success: false, error: 'Action already running' };
            }

            const tier = this.getTier(action);
            const queueEndpoint = PIPELINE_CONFIG.queueEndpoints[action]?.replace('{jobId}', jobId);

            if (!queueEndpoint) {
                console.warn(`No queue endpoint for ${action}, falling back to SSE`);
                return this.executeWithSSE(action, jobId, options);
            }

            this.loading[action] = true;

            const actionLabel = PIPELINE_CONFIG.labels[action] || action;
            const tierInfo = this.getTierInfo(tier);

            showToast(`Queuing ${actionLabel} (${tierInfo.label})...`, 'info');

            try {
                const response = await fetch(queueEndpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        tier,
                        force_refresh: options.force_refresh || false,
                        use_llm: options.use_llm !== undefined ? options.use_llm : true,
                        use_annotations: options.use_annotations !== undefined ? options.use_annotations : true,
                    })
                });

                const result = await response.json();

                // Handle HTTP error responses (4xx, 5xx)
                if (!response.ok) {
                    // Extract error from FastAPI format (detail) or Flask proxy format (error)
                    const errorMsg = result.detail || result.error || `Server error (${response.status})`;
                    console.error(`Queue endpoint returned ${response.status}:`, result);

                    this.lastResults[action] = {
                        success: false,
                        timestamp: new Date().toISOString(),
                        error: errorMsg
                    };

                    showToast(errorMsg, 'error');
                    return { success: false, error: errorMsg };
                }

                // Handle both QueueOperationResponse (has success) and
                // StreamingOperationResponse (has run_id but no success)
                if (result.success || (result.run_id && result.success !== false)) {
                    // Store result
                    this.lastResults[action] = {
                        success: true,
                        timestamp: new Date().toISOString(),
                        queued: true,
                        queue_id: result.queue_id,
                        run_id: result.run_id,
                        position: result.position
                    };

                    // Show success toast with position
                    const waitMsg = result.estimated_wait_seconds > 0
                        ? ` (est. ${Math.round(result.estimated_wait_seconds / 60)} min wait)`
                        : '';
                    showToast(`${actionLabel} queued at position #${result.position}${waitMsg}`, 'success');

                    // Update detail pipelines panel if available
                    const pipelinesStore = Alpine.store('detailPipelines');
                    if (pipelinesStore) {
                        pipelinesStore.operations[action] = {
                            status: 'pending',
                            queue_id: result.queue_id,
                            run_id: result.run_id || null,
                            position: result.position,
                            started_at: null,
                            completed_at: null,
                            error: null
                        };
                    }

                    // If run_id is returned, connect to SSE for log streaming
                    if (result.run_id) {
                        const jobTitle = options.jobTitle || 'Unknown Job';

                        // Dispatch CLI start event to create a tab in CLI panel
                        window.dispatchEvent(new CustomEvent('cli:start-run', {
                            detail: {
                                runId: result.run_id,
                                jobId,
                                jobTitle,
                                action: action.replace('-', '_')
                            }
                        }));

                        // NOTE: CLI panel handles log subscription via startRun() -> subscribeToLogs()
                        // Do NOT call _connectToOperationLogs() here - it creates a duplicate LogPoller
                    }

                    return result;

                } else {
                    // Queuing failed
                    this.lastResults[action] = {
                        success: false,
                        timestamp: new Date().toISOString(),
                        error: result.error
                    };

                    showToast(result.error || `Failed to queue ${actionLabel}`, 'error');
                    return result;
                }

            } catch (error) {
                console.error(`Failed to queue ${action}:`, error);
                showToast(`Failed to queue: ${error.message}`, 'error');

                this.lastResults[action] = {
                    success: false,
                    timestamp: new Date().toISOString(),
                    error: error.message
                };

                return { success: false, error: error.message };

            } finally {
                // Reset loading state after a short delay to show queued status
                setTimeout(() => {
                    this.loading[action] = false;
                }, 500);
            }
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
            const jobTitle = options.jobTitle || 'Unknown Job';
            showToast(`Starting ${actionLabel} (${tierInfo.label})...`, 'info');

            // NOTE: We no longer generate cliRunId locally - we use server's run_id
            // This prevents run ID mismatch between client and server

            try {
                // Step 1: Start the operation and get run_id (with timeout to prevent infinite hang)
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 60000); // 60s timeout

                console.log(`[${action}] Sending POST to ${streamEndpoint}`);

                const startResponse = await fetch(streamEndpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ tier, ...options }),
                    signal: controller.signal
                });

                clearTimeout(timeoutId);

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

                // Dispatch CLI start event AFTER we have the server's run_id
                // This ensures the CLI panel uses the same ID as the server
                window.dispatchEvent(new CustomEvent('cli:start-run', {
                    detail: {
                        runId: runId,  // Use server's run_id, not local cliRunId
                        jobId,
                        jobTitle,
                        action: action.replace('-', '_')
                    }
                }));

                // Step 2: Connect to log polling for real-time updates
                return new Promise((resolve) => {
                    console.log(`[${action}] Creating LogPoller for run: ${runId}`);

                    // Check if LogPoller is available
                    if (typeof window.LogPoller === 'undefined') {
                        console.error(`[${action}] LogPoller not available, falling back to status polling`);
                        this.pollOperationStatus(action, jobId, runId, actionLabel, tier, resolve);
                        return;
                    }

                    let poller;
                    try {
                        poller = new window.LogPoller(runId, {
                            pollInterval: 200,  // 200ms for near-instant feel
                            debug: false,
                        });
                        console.log(`[${action}] LogPoller created`);
                    } catch (e) {
                        console.error(`[${action}] Failed to create LogPoller:`, e);
                        // Fall back to polling immediately
                        this.pollOperationStatus(action, jobId, runId, actionLabel, tier, resolve);
                        return;
                    }

                    let lastLayerStatus = {};

                    // Handle regular log messages
                    poller.onLog((log) => {
                        console.log(`[${action}] Log: ${log.message}`);
                        // Dispatch CLI log event
                        const logType = window.cliDetectLogType ? window.cliDetectLogType(log.message) : 'info';
                        window.dispatchEvent(new CustomEvent('cli:log', {
                            detail: {
                                runId: runId,
                                text: log.message,
                                logType
                            }
                        }));
                    });

                    // Handle layer status updates
                    poller.onLayerStatus((layerStatus) => {
                        lastLayerStatus = layerStatus;
                        console.log(`[${action}] Layer status:`, lastLayerStatus);
                        // Dispatch CLI layer status event
                        window.dispatchEvent(new CustomEvent('cli:layer-status', {
                            detail: {
                                runId: runId,
                                layerStatus: lastLayerStatus
                            }
                        }));
                    });

                    // Handle completion/failure
                    poller.onComplete((status, error) => {
                        console.log(`[${action}] Ended with status: ${status}`);
                        this.loading[action] = false;

                        if (status === 'completed') {
                            // Fetch final result from status endpoint
                            this._fetchFinalResult(runId).then(finalResult => {
                                // Store result
                                this.lastResults[action] = {
                                    success: true,
                                    timestamp: new Date().toISOString(),
                                    cost: finalResult?.cost_usd || this.getCost(tier),
                                    data: finalResult
                                };

                                // Update session costs
                                this.sessionCosts[action] += finalResult?.cost_usd || this.getCost(tier);

                                // Dispatch CLI complete event
                                window.dispatchEvent(new CustomEvent('cli:complete', {
                                    detail: {
                                        runId: runId,
                                        status: 'success',
                                        result: finalResult
                                    }
                                }));

                                // Dispatch UI refresh event
                                window.dispatchEvent(new CustomEvent('ui:refresh-job', {
                                    detail: {
                                        jobId,
                                        sections: this._getRefreshSections(action)
                                    }
                                }));

                                // Dispatch custom event for other listeners
                                document.dispatchEvent(new CustomEvent('pipeline-action-complete', {
                                    detail: { action, jobId, result: finalResult }
                                }));

                                resolve(finalResult || { success: true });
                            });
                        } else {
                            // Failed
                            const errorMsg = error || 'Operation failed';

                            // Dispatch CLI complete with error
                            window.dispatchEvent(new CustomEvent('cli:complete', {
                                detail: {
                                    runId: runId,
                                    status: 'error',
                                    error: errorMsg
                                }
                            }));

                            this.lastResults[action] = {
                                success: false,
                                timestamp: new Date().toISOString(),
                                error: errorMsg
                            };

                            resolve({ success: false, error: errorMsg });
                        }
                    });

                    // Handle polling errors (LogPoller auto-retries)
                    poller.onError((err) => {
                        console.warn(`[${action}] Log polling error:`, err);
                        // LogPoller auto-retries, so we just log
                    });

                    // Start the poller (fire-and-forget with error handling)
                    poller.start().catch(err => console.error('[LogPoller] Polling failed:', err));
                });

            } catch (error) {
                console.error(`${action} failed:`, error);

                // Stop simulated progress to prevent misleading UI
                if (typeof window.stopSimulatedProgress === 'function') {
                    window.stopSimulatedProgress();
                }

                // Remove the pipeline log panel on error
                const existingPanel = document.getElementById('pipeline-log-panel');
                if (existingPanel) existingPanel.remove();

                // Show appropriate error message
                const errorMessage = error.name === 'AbortError'
                    ? `${actionLabel} timed out. Runner service may be unavailable.`
                    : `${actionLabel} failed: ${error.message}`;
                showToast(errorMessage, 'error');

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
         * @param {string} action - Action name
         * @param {string} jobId - Job ID
         * @param {string} runId - Runner operation run ID (used for both API and CLI events)
         * @param {string} actionLabel - Display label for action
         * @param {string} tier - Selected tier
         * @param {Function} resolve - Promise resolve function
         */
        async pollOperationStatus(action, jobId, runId, actionLabel, tier, resolve) {
            const maxAttempts = 120;  // 2 minutes max
            let attempts = 0;
            let lastLogIndex = 0;  // Track which logs we've already displayed
            let lastLayerStatus = {};

            const poll = async () => {
                attempts++;

                try {
                    const statusResponse = await fetch(`/api/runner/operations/${runId}/status`);
                    const statusData = await statusResponse.json();

                    // Update CLI panel with layer status from polling
                    if (statusData.layer_status && Object.keys(statusData.layer_status).length > 0) {
                        lastLayerStatus = statusData.layer_status;
                        // Dispatch CLI layer status event
                        window.dispatchEvent(new CustomEvent('cli:layer-status', {
                            detail: {
                                runId: runId,  // Use server's run_id
                                layerStatus: lastLayerStatus
                            }
                        }));
                    }

                    // Display new logs from polling via CLI events
                    if (statusData.logs && statusData.logs.length > lastLogIndex) {
                        const newLogs = statusData.logs.slice(lastLogIndex);
                        newLogs.forEach(log => {
                            const logType = window.cliDetectLogType ? window.cliDetectLogType(log) : 'info';
                            window.dispatchEvent(new CustomEvent('cli:log', {
                                detail: {
                                    runId: runId,  // Use server's run_id
                                    text: log,
                                    logType
                                }
                            }));
                        });
                        lastLogIndex = statusData.logs.length;
                    }

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

                            // Dispatch CLI complete event
                            window.dispatchEvent(new CustomEvent('cli:complete', {
                                detail: {
                                    runId: runId,  // Use server's run_id
                                    status: 'success',
                                    result: result
                                }
                            }));

                            // Dispatch UI refresh event (replaces page reload)
                            window.dispatchEvent(new CustomEvent('ui:refresh-job', {
                                detail: {
                                    jobId,
                                    sections: this._getRefreshSections(action)
                                }
                            }));

                            // Dispatch custom event for other listeners
                            document.dispatchEvent(new CustomEvent('pipeline-action-complete', {
                                detail: { action, jobId, result }
                            }));
                        } else {
                            // Success=false means it completed but had issues
                            window.dispatchEvent(new CustomEvent('cli:complete', {
                                detail: {
                                    runId: runId,  // Use server's run_id
                                    status: 'error',
                                    error: result.error || 'Operation completed with errors'
                                }
                            }));
                        }

                        resolve(result);
                        return;
                    }

                    if (statusData.status === 'failed') {
                        this.loading[action] = false;
                        const errorMsg = statusData.error || 'Operation failed';

                        // Dispatch CLI complete with error
                        window.dispatchEvent(new CustomEvent('cli:complete', {
                            detail: {
                                runId: runId,  // Use server's run_id
                                status: 'error',
                                error: errorMsg
                            }
                        }));

                        this.lastResults[action] = {
                            success: false,
                            timestamp: new Date().toISOString(),
                            error: errorMsg
                        };

                        resolve({ success: false, error: errorMsg });
                        return;
                    }

                    // Still running, poll again
                    if (attempts < maxAttempts) {
                        setTimeout(poll, 1000);
                    } else {
                        this.loading[action] = false;

                        // Dispatch CLI complete with timeout error
                        window.dispatchEvent(new CustomEvent('cli:complete', {
                            detail: {
                                runId: runId,  // Use server's run_id
                                status: 'error',
                                error: 'Operation timed out'
                            }
                        }));

                        resolve({ success: false, error: 'Operation timed out' });
                    }

                } catch (error) {
                    console.error('Polling error:', error);
                    if (attempts < maxAttempts) {
                        setTimeout(poll, 2000);
                    } else {
                        this.loading[action] = false;

                        // Dispatch CLI complete with error
                        window.dispatchEvent(new CustomEvent('cli:complete', {
                            detail: {
                                runId: runId,  // Use server's run_id
                                status: 'error',
                                error: error.message
                            }
                        }));

                        resolve({ success: false, error: error.message });
                    }
                }
            };

            poll();
        },

        /**
         * Connect to log polling for operation logs (used by queueExecution)
         *
         * This method connects to the log polling endpoint after an operation
         * has been queued. Unlike executeWithSSE() which waits for completion,
         * this is fire-and-forget - logs are streamed to CLI panel but we don't
         * block on completion (the queue handles that).
         *
         * Uses LogPoller for reliable streaming during long operations.
         *
         * @param {string} runId - The operation run ID from the queue response
         * @param {string} action - Action name (e.g., 'research-company')
         * @param {string} jobId - MongoDB job ID
         */
        _connectToOperationLogs(runId, action, jobId) {
            console.log(`[${action}] Connecting to log polling for queued operation: ${runId}`);

            // Check if LogPoller is available
            if (typeof window.LogPoller === 'undefined') {
                console.warn(`[${action}] LogPoller not available, skipping log connection`);
                // Logs are persisted on server, CLI panel should handle subscription
                return;
            }

            let poller;
            try {
                poller = new window.LogPoller(runId, {
                    pollInterval: 200,  // 200ms for near-instant feel
                    debug: false,
                });
                console.log(`[${action}] LogPoller created for queued op`);
            } catch (e) {
                console.error(`[${action}] Failed to create LogPoller for queued operation:`, e);
                // Logs are persisted on server, user can fetch via status endpoint
                return;
            }

            // Handle regular log messages
            poller.onLog((log) => {
                console.log(`[${action}] Queued log: ${log.message}`);
                const logType = window.cliDetectLogType ? window.cliDetectLogType(log.message) : 'info';
                window.dispatchEvent(new CustomEvent('cli:log', {
                    detail: {
                        runId: runId,
                        text: log.message,
                        logType
                    }
                }));
            });

            // Handle layer status updates
            poller.onLayerStatus((layerStatus) => {
                console.log(`[${action}] Queued layer status:`, layerStatus);
                window.dispatchEvent(new CustomEvent('cli:layer-status', {
                    detail: {
                        runId: runId,
                        layerStatus: layerStatus
                    }
                }));
            });

            // Handle completion/failure
            poller.onComplete((status, error) => {
                console.log(`[${action}] Queued operation ended with status: ${status}`);

                // Dispatch CLI complete event
                window.dispatchEvent(new CustomEvent('cli:complete', {
                    detail: {
                        runId: runId,
                        status: status === 'completed' ? 'success' : 'error',
                        error: status !== 'completed' ? error || `Operation ${status}` : null
                    }
                }));

                // If completed successfully, trigger UI refresh
                if (status === 'completed') {
                    window.dispatchEvent(new CustomEvent('ui:refresh-job', {
                        detail: {
                            jobId,
                            sections: this._getRefreshSections(action)
                        }
                    }));

                    // Dispatch custom event for other listeners
                    document.dispatchEvent(new CustomEvent('pipeline-action-complete', {
                        detail: { action, jobId, result: { success: true } }
                    }));
                }
            });

            // Handle errors (LogPoller auto-retries, so just log)
            poller.onError((err) => {
                console.warn(`[${action}] Log polling error for queued operation:`, err);
                // Don't dispatch error - poller will retry and logs are persisted
            });

            // Start polling (fire-and-forget with error handling)
            poller.start().catch(err => console.error('[LogPoller] Polling failed:', err));
        },

        /**
         * Execute a pipeline action synchronously (original behavior)
         * Used for non-streaming actions like structure-jd
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
            const jobTitle = options.jobTitle || 'Unknown Job';
            showToast(`Starting ${actionLabel} (${tierInfo.label})...`, 'info');

            // Generate a unique run ID for CLI tracking
            const cliRunId = `run-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

            // Dispatch CLI start event
            window.dispatchEvent(new CustomEvent('cli:start-run', {
                detail: {
                    runId: cliRunId,
                    jobId,
                    jobTitle,
                    action: action.replace('-', '_')
                }
            }));

            // Log starting message
            window.dispatchEvent(new CustomEvent('cli:log', {
                detail: {
                    runId: cliRunId,
                    text: `Starting ${actionLabel} with ${tierInfo.label} tier...`,
                    logType: 'info'
                }
            }));

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

                    // Log success message
                    window.dispatchEvent(new CustomEvent('cli:log', {
                        detail: {
                            runId: cliRunId,
                            text: `${actionLabel} completed successfully`,
                            logType: 'success'
                        }
                    }));

                    // Update layer status if available
                    if (result.data?.layer_status) {
                        window.dispatchEvent(new CustomEvent('cli:layer-status', {
                            detail: {
                                runId: cliRunId,
                                layerStatus: result.data.layer_status
                            }
                        }));
                    }

                    // Dispatch CLI complete event
                    window.dispatchEvent(new CustomEvent('cli:complete', {
                        detail: {
                            runId: cliRunId,
                            status: 'success',
                            result: result
                        }
                    }));

                    // Dispatch UI refresh event (replaces page reload)
                    window.dispatchEvent(new CustomEvent('ui:refresh-job', {
                        detail: {
                            jobId,
                            sections: this._getRefreshSections(action)
                        }
                    }));

                    // Dispatch custom event for other components
                    document.dispatchEvent(new CustomEvent('pipeline-action-complete', {
                        detail: { action, jobId, result }
                    }));
                } else {
                    // Log error message
                    window.dispatchEvent(new CustomEvent('cli:log', {
                        detail: {
                            runId: cliRunId,
                            text: result.error || `${actionLabel} failed`,
                            logType: 'error'
                        }
                    }));

                    // Dispatch CLI complete with error
                    window.dispatchEvent(new CustomEvent('cli:complete', {
                        detail: {
                            runId: cliRunId,
                            status: 'error',
                            error: result.error || `${actionLabel} failed`
                        }
                    }));
                }

                return result;
            } catch (error) {
                console.error(`${action} failed:`, error);

                // Log error message
                window.dispatchEvent(new CustomEvent('cli:log', {
                    detail: {
                        runId: cliRunId,
                        text: `${actionLabel} failed: ${error.message}`,
                        logType: 'error'
                    }
                }));

                // Dispatch CLI complete with error
                window.dispatchEvent(new CustomEvent('cli:complete', {
                    detail: {
                        runId: cliRunId,
                        status: 'error',
                        error: error.message
                    }
                }));

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
         * Get sections to refresh based on completed action
         * @param {string} action - Completed action name
         * @returns {string[]} Array of section names to refresh
         */
        _getRefreshSections(action) {
            const sectionMap = {
                // New operation names
                'analyze-job': ['jd-structured', 'jd-viewer', 'pain-points', 'fit-score', 'action-buttons'],
                'prepare-annotations': ['jd-structured', 'jd-viewer'],
                'research-company': ['company-research', 'role-research', 'action-buttons'],
                'discover-contacts': ['company-research', 'role-research', 'contacts', 'action-buttons'],
                'generate-cv': ['cv-preview', 'action-buttons', 'outcome-tracker'],
                'generate-cover-letter': ['cover-letter', 'action-buttons', 'outcome-tracker'],
                'generate-outreach': ['outreach', 'contacts', 'action-buttons'],
                'full-analysis': ['jd-structured', 'jd-viewer', 'pain-points', 'fit-score', 'company-research', 'role-research', 'cv-preview', 'action-buttons', 'outcome-tracker'],
                // Legacy operation names
                'structure-jd': ['jd-structured', 'jd-viewer'],
                'full-extraction': ['jd-structured', 'jd-viewer', 'pain-points', 'fit-score', 'action-buttons'],
                'all-ops': ['jd-structured', 'jd-viewer', 'pain-points', 'fit-score', 'company-research', 'role-research', 'cv-preview', 'action-buttons', 'outcome-tracker']
            };
            return sectionMap[action] || ['action-buttons'];
        },

        /**
         * Fetch final result from log status endpoint
         *
         * Called when LogPoller completes to get the final operation result.
         * This replaces the need to parse SSE 'result' events.
         *
         * @param {string} runId - The operation run ID
         * @returns {Promise<Object|null>} Final result object or null on error
         */
        async _fetchFinalResult(runId) {
            try {
                const response = await fetch(`/api/runner/logs/${runId}/status`);
                if (!response.ok) {
                    console.warn(`[pipeline-actions] Failed to fetch final result: ${response.status}`);
                    return null;
                }

                const data = await response.json();

                // The status endpoint returns the full operation state
                // We extract relevant result data
                return {
                    success: data.status === 'completed',
                    status: data.status,
                    error: data.error,
                    cost_usd: data.cost_usd,
                    langsmith_url: data.langsmith_url,
                    layer_status: data.layer_status,
                    total_logs: data.total_count,
                    // Include result data if present in meta
                    ...(data.result || {})
                };
            } catch (error) {
                console.error('[pipeline-actions] Error fetching final result:', error);
                return null;
            }
        },

        /**
         * Show detailed layer status panel for pipeline actions
         * @deprecated Use CLI panel events instead
         * @param {string} action - Action name
         * @param {Object} layerStatus - Per-layer status from backend
         * @param {Object} data - Full response data
         * @param {boolean} isPending - If true, show as "in progress" with spinning icons
         */
        showLayerStatusPanel(action, layerStatus, data, isPending = false) {
            // Legacy method - now handled by CLI panel
            const actionLabel = PIPELINE_CONFIG.labels[action] || action;
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
        jobTitle: config.jobTitle || 'Unknown Job',  // Job title for CLI panel display
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
            await Alpine.store('pipeline').execute(this.action, this.jobId, { jobTitle: this.jobTitle });
        },

        /**
         * Queue execution for background processing (queue-first approach)
         * Uses queueExecution instead of execute for job detail page
         */
        async queueExecute() {
            if (this.loading) return;
            await Alpine.store('pipeline').queueExecution(this.action, this.jobId, { jobTitle: this.jobTitle });
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

// Handle keyboard shortcuts for pipeline actions (unified operation names)
document.addEventListener('keydown', (event) => {
    // Alt+1: Analyze Job (JD + pain points + fit score)
    // Alt+2: Prepare Annotations
    // Alt+3: Research Company
    // Alt+4: Generate CV
    // Alt+5: Full Analysis (complete pipeline)
    if (event.altKey && !event.ctrlKey && !event.metaKey) {
        const jobId = document.querySelector('[data-job-id]')?.dataset.jobId;
        if (!jobId) return;

        const store = Alpine.store('pipeline');
        if (!store) return;

        switch (event.key) {
            case '1':
                event.preventDefault();
                store.execute('analyze-job', jobId);
                break;
            case '2':
                event.preventDefault();
                store.execute('prepare-annotations', jobId);
                break;
            case '3':
                event.preventDefault();
                store.execute('research-company', jobId);
                break;
            case '4':
                event.preventDefault();
                store.execute('generate-cv', jobId);
                break;
            case '5':
                event.preventDefault();
                store.execute('full-analysis', jobId);
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
