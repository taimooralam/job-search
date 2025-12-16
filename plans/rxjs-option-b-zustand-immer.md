# Option B: Zustand + Immer (2-3 weeks)

## Overview

Lightweight state management upgrade keeping Alpine.js for templates but adding Zustand for centralized state and Immer for immutable updates.

---

## Scope

- Keep Alpine.js for templates and reactivity
- Add Zustand for centralized state management
- Use Immer for immutable state updates
- Keep existing WebSocket/SSE code structure
- Smaller learning curve than RxJS

---

## Timeline: 2-3 Weeks

### Week 1: Foundation
- Add Zustand via CDN (UMD bundle)
- Create central store architecture
- Migrate queue-store.js to Zustand

### Week 2: State Migration
- Migrate cli-panel.js state to Zustand
- Add Immer for immutable updates
- Connect Alpine.js stores to Zustand

### Week 3: Integration
- Unify state across components
- Add devtools support
- Testing and documentation

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Alpine.js Templates               │
│        (x-data, x-show, x-for, @click, etc.)       │
└─────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│                    Zustand Store                    │
│  ┌───────────────┬───────────────┬───────────────┐ │
│  │ queue state   │  cli state    │ pipeline state│ │
│  └───────────────┴───────────────┴───────────────┘ │
│                          │                          │
│                    Immer produce()                  │
│              (immutable state updates)              │
└─────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│          Existing WebSocket/SSE Code                │
│     (queue-websocket.js, pipeline-actions.js)       │
└─────────────────────────────────────────────────────┘
```

---

## Key Benefits

| Benefit | Description |
|---------|-------------|
| **Minimal disruption** | Keep Alpine.js templates unchanged |
| **Centralized state** | Single source of truth |
| **Immutable updates** | Immer prevents mutation bugs |
| **DevTools** | Zustand has excellent devtools support |
| **Small bundle** | Zustand: 1KB, Immer: 3KB |
| **No build step** | Works with CDN imports |

---

## Why Not Full RxJS?

| Aspect | Zustand + Immer | RxJS |
|--------|-----------------|------|
| Learning curve | Low (simple API) | High (many operators) |
| Bundle size | ~4KB | ~30KB |
| Debugging | Devtools support | Complex streams |
| Team familiarity | Likely familiar | May need training |

---

## Implementation

### 1. Add CDN Scripts

```html
<!-- In base.html -->
<script src="https://unpkg.com/zustand@4/umd/vanilla.production.js"></script>
<script src="https://unpkg.com/immer@10/dist/immer.umd.production.min.js"></script>
```

### 2. Create Central Store

```javascript
// frontend/static/js/zustand-store.js
const { createStore } = window.zustand;
const { produce } = window.immer;

const useQueueStore = createStore((set, get) => ({
    // State
    pending: [],
    running: [],
    failed: [],
    history: [],
    connected: false,
    error: null,

    // Actions
    setConnected: (connected) => set({ connected }),

    addPending: (item) => set(produce((state) => {
        if (!state.pending.find(i => i.queue_id === item.queue_id)) {
            state.pending.push(item);
        }
    })),

    movePendingToRunning: (queueId) => set(produce((state) => {
        const idx = state.pending.findIndex(i => i.queue_id === queueId);
        if (idx !== -1) {
            const [item] = state.pending.splice(idx, 1);
            state.running.push(item);
        }
    })),

    moveRunningToHistory: (queueId) => set(produce((state) => {
        const idx = state.running.findIndex(i => i.queue_id === queueId);
        if (idx !== -1) {
            const [item] = state.running.splice(idx, 1);
            state.history.unshift(item);
            if (state.history.length > 50) {
                state.history.pop();
            }
        }
    })),

    updateState: (newState) => set({
        pending: newState.pending || [],
        running: newState.running || [],
        failed: newState.failed || [],
        history: newState.history || []
    })
}));

// Make available globally
window.queueStore = useQueueStore;
```

### 3. Create CLI Store

```javascript
// frontend/static/js/cli-zustand-store.js
const { createStore } = window.zustand;
const { produce } = window.immer;

const useCliStore = createStore((set, get) => ({
    // State
    runs: {},
    activeRunId: null,
    _pendingLogs: {},

    // Actions
    startRun: (runId, jobId, operation, jobTitle) => set(produce((state) => {
        state.runs[runId] = {
            id: runId,
            jobId,
            operation,
            jobTitle,
            status: 'running',
            logs: [],
            startedAt: Date.now()
        };
        state.activeRunId = runId;

        // Replay pending logs
        if (state._pendingLogs[runId]) {
            state.runs[runId].logs = state._pendingLogs[runId].logs;
            delete state._pendingLogs[runId];
        }
    })),

    appendLog: (runId, text, logType = 'info') => set(produce((state) => {
        if (state.runs[runId]) {
            state.runs[runId].logs.push({
                ts: Date.now(),
                type: logType,
                text
            });
        } else {
            // Queue for later
            if (!state._pendingLogs[runId]) {
                state._pendingLogs[runId] = { logs: [] };
            }
            state._pendingLogs[runId].logs.push({
                ts: Date.now(),
                type: logType,
                text
            });
        }
    })),

    completeRun: (runId, status = 'completed') => set(produce((state) => {
        if (state.runs[runId]) {
            state.runs[runId].status = status;
            state.runs[runId].completedAt = Date.now();
        }
    })),

    setActiveRun: (runId) => set({ activeRunId: runId })
}));

// Make available globally
window.cliStore = useCliStore;
```

### 4. Connect to Alpine.js

```javascript
// In Alpine.store initialization
document.addEventListener('alpine:init', () => {
    Alpine.store('queue', {
        // Proxy to Zustand
        get pending() { return window.queueStore.getState().pending; },
        get running() { return window.queueStore.getState().running; },
        get failed() { return window.queueStore.getState().failed; },
        get history() { return window.queueStore.getState().history; },
        get connected() { return window.queueStore.getState().connected; }
    });

    // Subscribe to Zustand changes and trigger Alpine reactivity
    window.queueStore.subscribe((state) => {
        // Force Alpine.js to re-render
        Alpine.store('queue')._updated = Date.now();
    });
});
```

---

## Files to Modify

| File | Changes |
|------|---------|
| `frontend/templates/base.html` | Add Zustand + Immer CDN scripts |
| `frontend/static/js/zustand-store.js` | **NEW** - Central queue store |
| `frontend/static/js/cli-zustand-store.js` | **NEW** - CLI panel store |
| `frontend/static/js/queue-store.js` | Migrate to use Zustand |
| `frontend/static/js/cli-panel.js` | Migrate to use Zustand |

---

## Comparison with Option C (RxJS-lite)

| Aspect | Option B (Zustand) | Option C (RxJS-lite) |
|--------|-------------------|----------------------|
| **Primary benefit** | Centralized state | Reactive streams |
| **Solves race conditions** | Partially (via Immer) | Yes (via buffer/race) |
| **Solves reconnection** | No (still manual) | Yes (via retryWhen) |
| **Learning curve** | Very low | Medium |
| **Future extensibility** | Limited | High |
| **Bundle size** | Smaller (~4KB) | Larger (~30KB) |

---

## Decision: Deferred

**Reason**: Option C (RxJS-lite) better addresses the root causes of race conditions and reconnection bugs. Zustand helps with state organization but doesn't solve the timing issues that RxJS operators handle elegantly.

Consider Option B if:
- Team is unfamiliar with reactive programming
- Bundle size is critical
- Only state organization (not timing) is the issue
