/**
 * LinkedIn Multi-Import Alpine.js Component
 *
 * Provides a hover dropdown for importing multiple LinkedIn jobs at once.
 * Supports pasting job IDs or URLs (one per line or comma-separated).
 */
function linkedinImport() {
    return {
        open: false,
        input: '',
        loading: false,
        progress: '',
        results: [],

        /**
         * Parse input to extract LinkedIn job IDs
         * Handles both job IDs and full URLs
         */
        parseInput(text) {
            return text
                .split(/[\n,]+/)
                .map(s => s.trim())
                .filter(s => s.length > 0)
                .map(s => {
                    // Extract job ID from URL if needed
                    const urlMatch = s.match(/jobs\/view\/(\d+)/);
                    if (urlMatch) {
                        return urlMatch[1];
                    }
                    // Check if it's a plain number
                    if (/^\d+$/.test(s)) {
                        return s;
                    }
                    // Return as-is for API to handle
                    return s;
                });
        },

        /**
         * Import jobs from LinkedIn
         */
        async importJobs() {
            const ids = this.parseInput(this.input);

            if (ids.length === 0) {
                return;
            }

            this.loading = true;
            this.results = [];

            for (let i = 0; i < ids.length; i++) {
                this.progress = `${i + 1}/${ids.length}`;

                try {
                    const resp = await fetch('/api/jobs/import-linkedin', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ job_id_or_url: ids[i] })
                    });

                    const data = await resp.json();

                    this.results.push({
                        id: i,
                        success: data.success,
                        message: data.success
                            ? `Imported: ${data.job?.title || ids[i]}`
                            : `${ids[i]}: ${data.error || 'Unknown error'}`
                    });
                } catch (e) {
                    this.results.push({
                        id: i,
                        success: false,
                        message: `${ids[i]}: ${e.message || 'Network error'}`
                    });
                }
            }

            this.loading = false;
            this.input = '';

            // Calculate success count
            const successCount = this.results.filter(r => r.success).length;
            const totalCount = this.results.length;

            // Refresh page data after imports
            if (typeof htmx !== 'undefined') {
                htmx.trigger(document.body, 'refresh');
            }

            // Show toast notification
            if (typeof showToast === 'function') {
                const status = successCount === totalCount ? 'success' :
                              successCount === 0 ? 'error' : 'warning';
                showToast(`Imported ${successCount}/${totalCount} jobs`, status);
            }

            // Dispatch custom event for other components to react
            document.dispatchEvent(new CustomEvent('linkedin:import-complete', {
                detail: { successCount, totalCount, results: this.results }
            }));
        }
    };
}
