/**
 * Service Worker for Job Intelligence Pipeline PWA
 *
 * Minimal implementation for PWA installability.
 * No offline caching - app requires live connection for real-time job data.
 */

const SW_VERSION = '1.1.0';

// Install event - activate immediately
self.addEventListener('install', (event) => {
  console.log(`[SW ${SW_VERSION}] Installing service worker`);
  self.skipWaiting();
});

// Activate event - claim clients immediately
self.addEventListener('activate', (event) => {
  console.log(`[SW ${SW_VERSION}] Activating service worker`);
  event.waitUntil(clients.claim());
});

// Fetch event - pass through same-origin requests only
// Cross-origin requests (e.g., to runner.uqab.digital) are NOT intercepted
// to avoid CORS issues with service worker fetch handling
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Skip cross-origin requests - let browser handle CORS directly
  // This prevents intermittent CORS failures caused by SW fetch interception
  if (url.origin !== self.location.origin) {
    return; // Don't call respondWith - let browser handle it normally
  }

  // Same-origin requests: pass through to network
  event.respondWith(fetch(event.request));
});

// Handle messages from main thread
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});
