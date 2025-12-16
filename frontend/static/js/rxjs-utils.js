/**
 * RxJS Utilities Module
 *
 * This module provides a simplified interface to RxJS for the job-search application.
 * It wraps the global rxjs object (loaded via CDN) and provides common utilities.
 *
 * Usage:
 *   const { Subject, timer, debounceTime, exponentialBackoff } = window.RxUtils;
 */

(function(global) {
    'use strict';

    // Ensure RxJS is loaded
    if (!global.rxjs) {
        console.error('[RxUtils] RxJS not loaded. Make sure rxjs CDN script is loaded before this file.');
        return;
    }

    const rxjs = global.rxjs;
    const operators = rxjs.operators || rxjs; // RxJS 7 has operators in main namespace

    /**
     * Exponential backoff with jitter for reconnection logic.
     *
     * @param {number} maxRetries - Maximum number of retry attempts (default: 5)
     * @param {number} baseDelay - Initial delay in ms (default: 1000)
     * @param {number} maxDelay - Maximum delay cap in ms (default: 30000)
     * @returns {function} Operator function for retryWhen
     *
     * @example
     *   connection$.pipe(
     *       retryWhen(exponentialBackoff(5, 1000, 30000))
     *   ).subscribe();
     */
    function exponentialBackoff(maxRetries = 5, baseDelay = 1000, maxDelay = 30000) {
        return function(errors$) {
            return errors$.pipe(
                operators.scan(function(acc, error) {
                    return { count: acc.count + 1, error: error };
                }, { count: 0, error: null }),
                operators.tap(function(state) {
                    if (state.count > maxRetries) {
                        throw state.error; // Propagate error after max retries
                    }
                }),
                operators.filter(function(state) {
                    return state.count <= maxRetries;
                }),
                operators.delayWhen(function(state) {
                    var delay = Math.min(baseDelay * Math.pow(2, state.count - 1), maxDelay);
                    var jitter = Math.random() * 1000; // Add up to 1s jitter
                    var totalDelay = delay + jitter;
                    console.log('[RxUtils] Reconnect attempt ' + state.count + '/' + maxRetries + ' in ' + Math.round(totalDelay) + 'ms');
                    return rxjs.timer(totalDelay);
                }),
                operators.map(function(state) {
                    return state.error;
                })
            );
        };
    }

    /**
     * Create a WebSocket connection as an observable.
     * Wraps the native WebSocket with RxJS Subject for bidirectional communication.
     *
     * @param {string} url - WebSocket URL
     * @param {object} options - Configuration options
     * @returns {object} { messages$, send, close, connected$ }
     *
     * @example
     *   const ws = createWebSocket('ws://localhost:8080/ws');
     *   ws.messages$.subscribe(msg => console.log(msg));
     *   ws.send({ type: 'ping' });
     */
    function createWebSocket(url, options) {
        options = options || {};

        var messages$ = new rxjs.Subject();
        var connected$ = new rxjs.BehaviorSubject(false);
        var socket = null;
        var messageQueue = [];

        function connect() {
            socket = new WebSocket(url);

            socket.onopen = function() {
                connected$.next(true);
                console.log('[RxUtils] WebSocket connected');

                // Flush queued messages
                while (messageQueue.length > 0) {
                    var msg = messageQueue.shift();
                    socket.send(JSON.stringify(msg));
                }
            };

            socket.onmessage = function(event) {
                try {
                    var data = JSON.parse(event.data);
                    messages$.next(data);
                } catch (e) {
                    messages$.next({ raw: event.data });
                }
            };

            socket.onerror = function(error) {
                console.error('[RxUtils] WebSocket error:', error);
                messages$.error(error);
            };

            socket.onclose = function(event) {
                connected$.next(false);
                console.log('[RxUtils] WebSocket closed:', event.code, event.reason);

                if (!event.wasClean && options.autoReconnect !== false) {
                    messages$.error(new Error('Connection closed unexpectedly'));
                } else {
                    messages$.complete();
                }
            };
        }

        function send(data) {
            if (socket && socket.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify(data));
            } else {
                messageQueue.push(data);
            }
        }

        function close() {
            if (socket) {
                socket.close();
            }
            messages$.complete();
            connected$.complete();
        }

        connect();

        return {
            messages$: messages$.asObservable(),
            connected$: connected$.asObservable(),
            send: send,
            close: close,
            reconnect: connect
        };
    }

    /**
     * Create a debounced save function using RxJS.
     *
     * @param {function} saveFn - The actual save function to call
     * @param {number} delayMs - Debounce delay in milliseconds
     * @returns {object} { trigger, destroy }
     *
     * @example
     *   const debouncedSave = createDebouncedSave(() => saveToStorage(), 500);
     *   // Call trigger() whenever state changes
     *   debouncedSave.trigger();
     *   // Cleanup when done
     *   debouncedSave.destroy();
     */
    function createDebouncedSave(saveFn, delayMs) {
        var subject$ = new rxjs.Subject();
        var destroy$ = new rxjs.Subject();

        subject$.pipe(
            operators.debounceTime(delayMs),
            operators.takeUntil(destroy$)
        ).subscribe(function() {
            try {
                saveFn();
            } catch (e) {
                console.error('[RxUtils] Debounced save error:', e);
            }
        });

        return {
            trigger: function() {
                subject$.next();
            },
            destroy: function() {
                destroy$.next();
                destroy$.complete();
            }
        };
    }

    /**
     * Create a pending buffer that queues items until a trigger fires.
     * Useful for buffering logs until the run is created.
     *
     * @param {number} timeoutMs - Timeout before fallback action
     * @param {function} onTimeout - Function to call on timeout
     * @returns {object} { buffer$, trigger$, add, triggerFlush, getBuffered }
     */
    function createPendingBuffer(timeoutMs, onTimeout) {
        var buffer = [];
        var timeoutHandle = null;
        var flushed = false;

        function startTimeout() {
            if (!timeoutHandle && !flushed) {
                timeoutHandle = setTimeout(function() {
                    if (!flushed && onTimeout) {
                        onTimeout(buffer.slice());
                    }
                }, timeoutMs);
            }
        }

        return {
            add: function(item) {
                if (flushed) return;
                buffer.push(item);
                startTimeout();
            },
            flush: function() {
                if (timeoutHandle) {
                    clearTimeout(timeoutHandle);
                    timeoutHandle = null;
                }
                flushed = true;
                var items = buffer.slice();
                buffer = [];
                return items;
            },
            getBuffered: function() {
                return buffer.slice();
            },
            isFlushed: function() {
                return flushed;
            },
            destroy: function() {
                if (timeoutHandle) {
                    clearTimeout(timeoutHandle);
                }
                buffer = [];
            }
        };
    }

    /**
     * Create an interval with automatic cleanup.
     *
     * @param {number} periodMs - Interval period in milliseconds
     * @param {function} callback - Function to call on each tick
     * @returns {object} { start, stop }
     */
    function createInterval(periodMs, callback) {
        var subscription = null;

        return {
            start: function() {
                if (subscription) return; // Already running
                subscription = rxjs.interval(periodMs).subscribe(function(n) {
                    try {
                        callback(n);
                    } catch (e) {
                        console.error('[RxUtils] Interval callback error:', e);
                    }
                });
            },
            stop: function() {
                if (subscription) {
                    subscription.unsubscribe();
                    subscription = null;
                }
            }
        };
    }

    /**
     * Create a Subject that filters messages by type.
     * Useful for splitting WebSocket messages into typed channels.
     *
     * @param {Observable} source$ - Source observable
     * @returns {function} Function that returns filtered observable for a message type
     *
     * @example
     *   const byType = createMessageRouter(ws.messages$);
     *   byType('queue_state').subscribe(handleQueueState);
     *   byType('queue_update').subscribe(handleUpdate);
     */
    function createMessageRouter(source$) {
        var shared$ = source$.pipe(operators.share());

        return function(messageType) {
            return shared$.pipe(
                operators.filter(function(msg) {
                    return msg && msg.type === messageType;
                }),
                operators.map(function(msg) {
                    return msg.payload !== undefined ? msg.payload : msg;
                })
            );
        };
    }

    // Export utilities
    global.RxUtils = {
        // Re-export commonly used RxJS types
        Subject: rxjs.Subject,
        BehaviorSubject: rxjs.BehaviorSubject,
        ReplaySubject: rxjs.ReplaySubject,
        Observable: rxjs.Observable,

        // Re-export creation functions
        of: rxjs.of,
        from: rxjs.from,
        fromEvent: rxjs.fromEvent,
        timer: rxjs.timer,
        interval: rxjs.interval,
        merge: rxjs.merge,
        race: rxjs.race,
        combineLatest: rxjs.combineLatest,
        concat: rxjs.concat,
        EMPTY: rxjs.EMPTY,
        NEVER: rxjs.NEVER,

        // Re-export operators (flattened for convenience)
        pipe: operators.pipe,
        map: operators.map,
        filter: operators.filter,
        tap: operators.tap,
        switchMap: operators.switchMap,
        mergeMap: operators.mergeMap,
        concatMap: operators.concatMap,
        exhaustMap: operators.exhaustMap,
        scan: operators.scan,
        reduce: operators.reduce,
        pairwise: operators.pairwise,
        distinctUntilChanged: operators.distinctUntilChanged,
        debounceTime: operators.debounceTime,
        throttleTime: operators.throttleTime,
        delay: operators.delay,
        delayWhen: operators.delayWhen,
        timeout: operators.timeout,
        retry: operators.retry,
        retryWhen: operators.retryWhen,
        catchError: operators.catchError,
        finalize: operators.finalize,
        takeUntil: operators.takeUntil,
        takeWhile: operators.takeWhile,
        take: operators.take,
        first: operators.first,
        last: operators.last,
        skip: operators.skip,
        buffer: operators.buffer,
        bufferTime: operators.bufferTime,
        bufferCount: operators.bufferCount,
        share: operators.share,
        shareReplay: operators.shareReplay,
        startWith: operators.startWith,
        withLatestFrom: operators.withLatestFrom,
        groupBy: operators.groupBy,

        // Custom utilities
        exponentialBackoff: exponentialBackoff,
        createWebSocket: createWebSocket,
        createDebouncedSave: createDebouncedSave,
        createPendingBuffer: createPendingBuffer,
        createInterval: createInterval,
        createMessageRouter: createMessageRouter
    };

    console.log('[RxUtils] RxJS utilities loaded successfully');

})(typeof window !== 'undefined' ? window : this);
