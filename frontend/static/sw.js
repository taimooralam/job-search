/**
 * Service Worker for Job Intelligence Pipeline PWA
 *
 * Minimal implementation for PWA installability.
 * No offline caching - app requires live connection for real-time job data.
 */

const SW_VERSION = '1.0.0';

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

// Fetch event - pass through all requests (no caching)
self.addEventListener('fetch', (event) => {
  // Simply fetch from network - no caching strategy
  event.respondWith(fetch(event.request));
});

// Handle messages from main thread
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});
