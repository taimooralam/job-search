# Option A: Full RxJS Migration (6-8 weeks)

## Overview

Complete architectural overhaul replacing Alpine.js with Vue 3 Composition API + RxJS for state management and reactive streams.

---

## Scope

- Replace Alpine.js with Vue 3 Composition API
- Unify WebSocket + SSE into single connection
- Complete rewrite of state management
- Migrate all frontend JavaScript to TypeScript

---

## Timeline: 6-8 Weeks

### Week 1-2: Foundation
- Set up Vite build system
- Configure Vue 3 + TypeScript
- Create RxJS service layer architecture
- Set up development environment with HMR

### Week 3-4: Core Migration
- Migrate queue-websocket.js → Vue composable with RxJS
- Migrate cli-panel.js → Vue component with RxJS store
- Migrate queue-store.js → Pinia + RxJS integration

### Week 5-6: Feature Migration
- Migrate pipeline-actions.js → Vue composable
- Migrate all Alpine.js templates to Vue SFCs
- Unify SSE + WebSocket into single reactive stream

### Week 7-8: Testing & Polish
- Comprehensive unit tests with marble testing
- E2E tests with Cypress
- Performance optimization
- Documentation

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Vue 3 App                        │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │           Pinia Store (state)                │   │
│  └─────────────────────────────────────────────┘   │
│                       │                             │
│                       ▼                             │
│  ┌─────────────────────────────────────────────┐   │
│  │        RxJS Service Layer                    │   │
│  │  ┌─────────────────────────────────────┐    │   │
│  │  │  connection$  │  messages$  │  state$ │    │   │
│  │  └─────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────┘   │
│                       │                             │
│                       ▼                             │
│  ┌─────────────────────────────────────────────┐   │
│  │     Unified WebSocket + SSE Stream           │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## Key Benefits

| Benefit | Description |
|---------|-------------|
| **Type Safety** | Full TypeScript support with inference |
| **Composition API** | Better code organization and reusability |
| **Pinia + RxJS** | Powerful state management with reactive streams |
| **Single Connection** | Unified WebSocket + SSE reduces complexity |
| **Marble Testing** | Time-based testing with RxJS TestScheduler |
| **Vue DevTools** | Better debugging experience |

---

## Risks

| Risk | Mitigation |
|------|------------|
| Large scope | Phase the migration, keep Alpine.js during transition |
| Learning curve | Vue 3 + RxJS requires team training |
| Flask integration | Create Vue mounting points in Jinja templates |
| Build complexity | Vite simplifies build configuration |

---

## Files to Create/Migrate

### New Files
```
frontend/
├── vite.config.ts
├── tsconfig.json
├── src/
│   ├── main.ts
│   ├── App.vue
│   ├── composables/
│   │   ├── useWebSocket.ts
│   │   ├── useCliPanel.ts
│   │   ├── useQueueStore.ts
│   │   └── usePipelineActions.ts
│   ├── services/
│   │   ├── connection.service.ts
│   │   └── stream.service.ts
│   ├── stores/
│   │   ├── queue.store.ts
│   │   └── cli.store.ts
│   └── components/
│       ├── CliPanel.vue
│       ├── QueueDropdown.vue
│       └── PipelineActions.vue
```

### Files to Remove
```
frontend/static/js/
├── queue-websocket.js    → composables/useWebSocket.ts
├── queue-store.js        → stores/queue.store.ts
├── cli-panel.js          → composables/useCliPanel.ts
├── pipeline-actions.js   → composables/usePipelineActions.ts
```

---

## Example: Vue Composable with RxJS

```typescript
// composables/useWebSocket.ts
import { ref, onMounted, onUnmounted } from 'vue';
import { Subject, BehaviorSubject, timer, interval } from 'rxjs';
import { retryWhen, delay, tap, takeUntil, filter, switchMap } from 'rxjs/operators';
import { webSocket, WebSocketSubject } from 'rxjs/webSocket';

export function useWebSocket(url: string) {
    const connected = ref(false);
    const error = ref<Error | null>(null);
    const destroy$ = new Subject<void>();

    const messages$ = new BehaviorSubject<any>(null);
    let socket$: WebSocketSubject<any>;

    const connect = () => {
        socket$ = webSocket({
            url,
            openObserver: {
                next: () => {
                    connected.value = true;
                    error.value = null;
                }
            },
            closeObserver: {
                next: () => {
                    connected.value = false;
                }
            }
        });

        socket$.pipe(
            retryWhen(errors$ => errors$.pipe(
                tap(err => {
                    error.value = err;
                    console.warn('[WS] Connection error:', err);
                }),
                delay(1000),
                tap(() => console.log('[WS] Reconnecting...'))
            )),
            takeUntil(destroy$)
        ).subscribe({
            next: (msg) => messages$.next(msg),
            error: (err) => error.value = err
        });
    };

    onMounted(() => connect());
    onUnmounted(() => {
        destroy$.next();
        destroy$.complete();
    });

    return {
        connected,
        error,
        messages$,
        send: (msg: any) => socket$.next(msg)
    };
}
```

---

## Decision: Deferred

**Reason**: Option C (RxJS-lite) provides 80% of the benefit with 20% of the effort.

If Option C proves insufficient after 3-6 months, revisit this plan for full migration.
