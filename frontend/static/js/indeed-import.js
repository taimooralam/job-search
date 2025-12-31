/**
 * Indeed Multi-Import Alpine.js Component
 *
 * Provides a hover dropdown for importing multiple Indeed jobs at once.
 * Supports pasting job keys or URLs (one per line or comma-separated).
 *
 * Indeed URL Formats Supported:
 * - https://indeed.com/viewjob?jk=abc123def4567890
 * - https://indeed.com/rc/clk?jk=abc123def4567890
 * - https://indeed.com/jobs?q=...&vjk=abc123def4567890
 * - Raw key: abc123def4567890 (16-char hex)
 */
function indeedImport() {
    return {
        open: false,
        input: '',
        loading: false,
        progress: '',
        results: [],

        /**
         * Parse input to extract Indeed job keys
         * Handles both job keys and full URLs
         */
        parseInput(text) {
            return text
                .split(/[\n,]+/)
                .map(s => s.trim())
                .filter(s => s.length > 0)
                .map(s => {
                    // Extract job key from jk= parameter (viewjob, clk URLs)
                    const jkMatch = s.match(/[?&]jk=([a-f0-9]{16})/i);
                    if (jkMatch) {
                        return jkMatch[1].toLowerCase();
                    }
                    // Extract job key from vjk= parameter (search results page)
                    const vjkMatch = s.match(/[?&]vjk=([a-f0-9]{16})/i);
                    if (vjkMatch) {
                        return vjkMatch[1].toLowerCase();
                    }
                    // Check if it's a raw 16-char hex key
                    if (/^[a-f0-9]{16}$/i.test(s)) {
                        return s.toLowerCase();
                    }
                    // Return as-is for API to handle
                    return s;
                });
        },

        /**
         * Import jobs from Indeed
         */
        async importJobs() {
            const keys = this.parseInput(this.input);

            if (keys.length === 0) {
                return;
            }

            this.loading = true;
            this.results = [];

            for (let i = 0; i < keys.length; i++) {
                this.progress = `${i + 1}/${keys.length}`;

                try {
                    const resp = await fetch('/api/jobs/import-indeed', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ job_key_or_url: keys[i] })
                    });

                    const data = await resp.json();

                    this.results.push({
                        id: i,
                        success: data.success,
                        message: data.success
                            ? `Imported: ${data.title || keys[i]}`
                            : `${keys[i]}: ${data.error || 'Unknown error'}`
                    });
                } catch (e) {
                    this.results.push({
                        id: i,
                        success: false,
                        message: `${keys[i]}: ${e.message || 'Network error'}`
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
                showToast(`Imported ${successCount}/${totalCount} Indeed jobs`, status);
            }

            // Dispatch custom event for other components to react
            document.dispatchEvent(new CustomEvent('indeed:import-complete', {
                detail: { successCount, totalCount, results: this.results }
            }));
        }
    };
}
