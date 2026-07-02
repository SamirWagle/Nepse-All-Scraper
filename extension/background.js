/**
 * background.js — NEPSE CAGR Extension
 * Handles native messaging to start engine and run calculations.
 */

const NATIVE_HOST = 'com.nepse.cagr';
const NATIVE_ACTIONS = { cagrViaNative: 'cagr', ping: 'ping' };

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  const nativeAction = NATIVE_ACTIONS[request.action];
  if (!nativeAction) return;

  chrome.runtime.sendNativeMessage(
    NATIVE_HOST,
    { action: nativeAction, payload: request.payload },
    (response) => {
      if (chrome.runtime.lastError) {
        sendResponse({ error: chrome.runtime.lastError.message });
      } else {
        sendResponse(response);
      }
    }
  );
  return true;
});
