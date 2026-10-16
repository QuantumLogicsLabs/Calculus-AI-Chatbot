/**
 * chatApi.js — Objectives CB-1, CB-4, CB-18, CB-19
 *
 * Integrated (default):  POST {API_URL}/api/chat
 *                        GET  {API_URL}/api/chat/sessions
 * Standalone (Beanie):   POST {REACT_APP_CHAT_URL}/chat
 */

// react-scripts injects REACT_APP_* variables at start/build time.
// Bundled production builds use the same origin as the page.
const API_URL = process.env.REACT_APP_API_URL || (
  process.env.NODE_ENV === "production" ? "" : "http://127.0.0.1:8002"
);
// Optional direct AI-service mode; leave empty for the integrated backend.
const STANDALONE_CHAT_URL = process.env.REACT_APP_CHAT_URL || "";
const REQUEST_TIMEOUT_MS = 45000;

function getChatEndpoint() {
  if (STANDALONE_CHAT_URL) {
    return `${STANDALONE_CHAT_URL.replace(/\/$/, "")}/chat/`; // was: /chat
  }
  return `${API_URL}/api/chat/`; // was: /api/chat
}

async function fetchWithTimeout(url, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } catch (err) {
    if (err.name === "AbortError") {
      throw new Error("The tutor is taking too long. Please try again in a moment.");
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * @param {Array<{role: string, content: string}>} messages
 * @param {string} context
 * @param {string|null} token
 * @param {string} pageUrl
 * @param {string} topicKey - CB-18: short stable topic label (e.g. "Partial Derivatives Part 2")
 */
export async function sendMessage(messages, context, token = null, pageUrl = "/", topicKey = "") {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;

  let response;
  try {
    response = await fetchWithTimeout(getChatEndpoint(), {
      method: "POST",
      headers,
      body: JSON.stringify({ messages, context, topic_key: topicKey, page_url: pageUrl }),
    });
  } catch (err) {
    if (err.message.includes("taking too long")) throw err;
    throw new Error("Could not reach the chat service. Make sure the backend is running.");
  }

  // CB-11/CB-14: Handle rate limiting (429 Too Many Requests)
  if (response.status === 429) {
    let detail = "Rate limit exceeded. Please try again later.";
    let retryAfter = 60;
    try {
      const err = await response.json();
      detail = err.detail || detail;
      retryAfter = err.retry_after || retryAfter;
    } catch {}
    const error = new Error(detail);
    error.retryAfter = retryAfter;
    error.code = 429;
    throw error;
  }

  if (!response.ok) {
    let detail = "Chat request failed.";
    try {
      const err = await response.json();
      detail = err.detail || err.message || detail;
    } catch {}
    throw new Error(typeof detail === "string" ? detail : "Chat request failed.");
  }

  try {
    const data = await response.json();
    return {
      reply: data.reply || data.response || data.answer || "",
      suggestions: Array.isArray(data.suggestions) ? data.suggestions : [],
      difficulty: data.difficulty || null, // CB-18
      message_id: data.message_id || null,  // CB-12: for feedback submission
      session_id: data.session_id || null,  // CB-12/CB-19: for feedback / export
      mode: data.mode || null,
      source: data.source || null,
    };
  } catch {
    throw new Error("Invalid response from chat service.");
  }
}

/**
 * sendMessageStream — CB-10 (Frontend streaming)
 * Streams tokens from {API_URL}/api/chat/stream (or standalone /chat/stream)
 * via SSE-over-fetch. Reports errors explicitly; only unsupported routes permit fallback.
 *
 * @param {Array<{role: string, content: string}>} messages
 * @param {string} context
 * @param {string|null} token
 * @param {string} pageUrl
 * @param {string} topicKey - CB-18: short stable topic label
 * @param {(chunk: string) => void} onToken - called with each new text chunk
 * @param {(final: {suggestions: string[], message_id?: number, session_id?: string}) => void} onDone - called once stream ends
 * @param {(err: Error) => void} onError
 */
export async function sendMessageStream(
  messages, context, token = null, pageUrl = "/", topicKey = "",
  onToken = () => {}, onDone = () => {}, onError = () => {}
) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const streamUrl = getChatEndpoint().replace(/\/chat\/?$/, "/chat/stream");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  let reader;
  let receivedText = false;
  try {
    const response = await fetch(streamUrl, {
      method: "POST", headers, signal: controller.signal,
      body: JSON.stringify({ messages, context, topic_key: topicKey, page_url: pageUrl }),
    });
    if (!response.ok) {
      let body = {};
      try { body = await response.json(); } catch {}
      const error = new Error(body.detail || "The tutor is temporarily unavailable. Please try again.");
      error.code = response.status;
      error.retryAfter = body.retry_after;
      // Only missing streaming support permits a single non-streaming retry.
      error.canFallback = [404, 405, 501].includes(response.status);
      throw error;
    }
    if (!response.body) throw new Error("The tutor response was incomplete. Please try again.");
    reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let final = { suggestions: [], message_id: null, session_id: null, mode: null, source: null };
    const processFrame = async (frame) => {
      const payload = frame.split(/\r?\n/).filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart()).join("\n");
      if (!payload) return false;
      let parsed;
      if (payload === "[DONE]") parsed = { done: true };
      else {
        try { parsed = JSON.parse(payload); }
        catch { throw new Error("The tutor response was incomplete. Please try again."); }
      }
      if (!parsed || typeof parsed !== "object") throw new Error("Invalid tutor response.");
      if (parsed.error) throw new Error(parsed.code === "ai_timeout"
        ? "The tutor took too long to respond. Please try again."
        : "The tutor could not complete the answer. Please try again.");
      const chunk = parsed.delta || parsed.token || "";
      if (typeof chunk !== "string") throw new Error("Invalid tutor response.");
      if (chunk) { receivedText = true; onToken(chunk); }
      if (Array.isArray(parsed.suggestions)) final.suggestions = parsed.suggestions;
      for (const key of ["message_id", "session_id", "mode", "source", "difficulty"]) {
        if (parsed[key] != null) final[key] = parsed[key];
      }
      if (parsed.done) {
        if (!receivedText) throw new Error("The tutor returned an empty answer. Please try again.");
        await onDone(final);
        return true;
      }
      return false;
    };
    while (true) {
      const { done, value } = await reader.read();
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
      const frames = buffer.split(/\r?\n\r?\n/);
      buffer = frames.pop();
      for (const frame of frames) if (await processFrame(frame)) return;
      if (done) {
        if (buffer.trim() && await processFrame(buffer)) return;
        throw new Error("The tutor response was interrupted. Please try again.");
      }
    }
  } catch (error) {
    if (error.name === "AbortError") error = new Error("The tutor took too long to respond. Please try again.");
    if (error instanceof TypeError) error = new Error("Could not connect to the tutor. Please try again.");
    if (receivedText) error.canFallback = false;
    await onError(error);
  } finally {
    clearTimeout(timer);
    if (reader) {
      try { await reader.cancel(); } catch {}
      reader.releaseLock?.();
    }
  }
}

/**
 * fetchTopicProgress — CB-18
 * Fetches the student's currently-tracked difficulty level for a topic.
 * Returns null for guests or on any failure (caller should treat that as
 * "no badge to show" rather than an error).
 */
export async function fetchTopicProgress(token, topic) {
  if (!token || !topic) return null;
  try {
    const response = await fetchWithTimeout(
      `${API_URL}/api/chat/progress/${encodeURIComponent(topic)}`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    if (!response.ok) return null;
    const data = await response.json();
    return data.data || null;
  } catch {
    return null;
  }
}

/**
 * fetchAllProgress — CB-18
 * Fetches every topic the student has a tracked difficulty level for.
 * Useful for a Dashboard-style overview of adaptive progress.
 */
export async function fetchAllProgress(token) {
  if (!token) return [];
  try {
    const response = await fetchWithTimeout(`${API_URL}/api/chat/progress`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) return [];
    const data = await response.json();
    return data.data || [];
  } catch {
    return [];
  }
}

/**
 * exportSession — CB-19
 * Downloads the Markdown study sheet for a session. Throws a friendly
 * Error on failure so the caller can surface it in-chat.
 */
export async function exportSession(token, sessionId) {
  if (!token) throw new Error("Sign in to export a session as a study sheet.");
  if (!sessionId) throw new Error("Start chatting first — there's no session to export yet.");

  let response;
  try {
    response = await fetchWithTimeout(`${API_URL}/api/chat/sessions/${sessionId}/export`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch (err) {
    throw new Error("Could not reach the backend server.");
  }

  if (!response.ok) {
    if (response.status === 404) throw new Error("Session not found.");
    throw new Error("Failed to export session.");
  }

  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const filename = match ? match[1] : "study-sheet.md";

  return { blob, filename };
}

/**
 * submitFeedback — CB-12
 * Submits a thumbs-up or thumbs-down rating for a message.
 * For authenticated users only. Guests can still toggle UI locally but
 * the feedback won't be persisted.
 *
 * @param {number} messageId - The message_id from the backend response
 * @param {string} sessionId - The session_id from the backend response
 * @param {string} feedback - "like" or "dislike"
 * @param {string|null} token - JWT auth token (required for authenticated users)
 * @throws {Error} if submission fails
 */
export async function submitFeedback(messageId, sessionId, feedback, token) {
  if (!token) {
    // Guests can't persist feedback, but we return silently so UI still works
    // (they can still toggle the buttons locally and see the visual feedback)
    return;
  }

  if (feedback !== "like" && feedback !== "dislike") {
    throw new Error("Feedback must be 'like' or 'dislike'.");
  }

  try {
    const response = await fetchWithTimeout(`${API_URL}/api/chat/feedback`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        message_id: messageId,
        session_id: sessionId,
        feedback,
      }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to save feedback.");
    }

    return await response.json();
  } catch (err) {
    // Log but don't crash — feedback is optional
    console.warn("Could not save feedback:", err.message);
    throw err;
  }
}

/**
 * createChatSession — CB-13
 * Creates a new backend session for logged-in users. Guests skip this
 * (handled by caller) since guest sessions aren't persisted.
 */
export async function createChatSession(token, title = "New Chat") {
  if (!token) return null;
  try {
    const response = await fetchWithTimeout(`${API_URL}/api/chat/sessions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ title }),
    });
    if (!response.ok) return null;
    const data = await response.json();
    // B-2 fix: the backend actually returns the session id nested under
    // `data`, e.g. { data: { session_id: "..." } } — not at the top
    // level. The old `data.session_id || data.id` check always missed
    // it, so createChatSession() was silently returning null for every
    // logged-in user.
    return data.data?.session_id || null;
  } catch {
    return null; // fail silently — local reset still works
  }
}

export async function fetchChatHistory(token) {
  if (!token) return [];

  let response;
  try {
    // B-2 fix: backend route is /api/chat/sessions, not /api/chat/history
    // (the latter doesn't exist, so this always failed for logged-in users).
    response = await fetchWithTimeout(`${API_URL}/api/chat/sessions`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch (err) {
    if (err.message.includes("taking too long")) throw err;
    throw new Error("Could not reach the backend server.");
  }

  if (!response.ok) {
    if (response.status === 401) throw new Error("Session expired. Please log in again.");
    throw new Error("Failed to load chat history.");
  }

  try {
    const data = await response.json();
    return data.history || data.sessions || data.data || [];
  } catch {
    return [];
  }
}
