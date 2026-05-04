/**
 * background.js — NEPSE CAGR Extension
 * Handles native messaging to start engine and run calculations.
 */

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {

  // ── Calculate CAGR via native host (starts engine if needed) ─────────────
  if (request.action === 'cagrViaNative') {
    chrome.runtime.sendNativeMessage(
      'com.nepse.cagr',
      { action: 'cagr', payload: request.payload },
      (response) => {
        if (chrome.runtime.lastError) {
          sendResponse({ error: chrome.runtime.lastError.message });
        } else {
          sendResponse(response);
        }
      }
    );
    return true;
  }

  // ── Ping engine ───────────────────────────────────────────────────────────
  if (request.action === 'ping') {
    chrome.runtime.sendNativeMessage(
      'com.nepse.cagr',
      { action: 'ping' },
      (response) => {
        if (chrome.runtime.lastError) {
          sendResponse({ error: chrome.runtime.lastError.message });
        } else {
          sendResponse(response);
        }
      }
    );
    return true;
  }

});
