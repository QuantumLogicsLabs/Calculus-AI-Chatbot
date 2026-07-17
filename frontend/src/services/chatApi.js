/**
 * chatApi.js — Objectives CB-1, CB-4, CB-18, CB-19
 *
 * Integrated (default):  POST {API_URL}/api/chat
 *                        GET  {API_URL}/api/chat/history
 * Standalone (Beanie):   POST {REACT_APP_CHAT_URL}/chat
 */

const API_URL = process.env.REACT_APP_API_URL || "http://127.0.0.1:8002";
const STANDALONE_CHAT_URL = process.env.REACT_APP_CHAT_URL || "";
const REQUEST_TIMEOUT_MS = 45000;

function getChatEndpoint() {
  if (STANDALONE_CHAT_URL) {
    return `${STANDALONE_CHAT_URL.replace(/\/$/, "")}/chat`;
  }
  return `${API_URL}/api/chat`;
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
      reply: data.reply || data.response || "",
      suggestions: Array.isArray(data.suggestions) ? data.suggestions : [],
      difficulty: data.difficulty || null, // CB-18
      message_id: data.message_id || null,  // CB-12: for feedback submission
      session_id: data.session_id || null,  // CB-19: for export / CB-12: for feedback
    };
  } catch {
    throw new Error("Invalid response from chat service.");
  }
}
/**
 * sendMessageStream — CB-10 (Frontend streaming)
 * Streams tokens from {API_URL}/api/chat/stream (or standalone /chat/stream)
 * via SSE-over-fetch. Falls back gracefully if the endpoint isn't available yet.
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
  messages,
  context,
  token = null,
  pageUrl = "/",
  topicKey = "",
  onToken = () => {},
  onDone = () => {},
  onError = () => {}
) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;

  const streamUrl = getChatEndpoint().replace(/\/chat$/, "/chat/stream");

  let response;
  try {
    response = await fetch(streamUrl, {
      method: "POST",
      headers,
      body: JSON.stringify({ messages, context, topic_key: topicKey, page_url: pageUrl }),
    });
  } catch (err) {
    onError(new Error("Could not reach the chat service. Make sure the backend is running."));
    return;
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
    onError(error);
    return;
  }

  if (!response.ok || !response.body) {
    onError(new Error("Streaming not available. Falling back."));
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let suggestions = [];
  let message_id = null;  // CB-12: capture for feedback
  let session_id = null;  // CB-12/CB-19: capture for feedback/export

  try {
    // eslint-disable-next-line no-constant-condition
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop(); // keep incomplete chunk for next read

      for (const line of lines) {
        if (!line.startsWith("data:")) continue;
        const payload = line.replace(/^data:\s*/, "");

        if (payload === "[DONE]") {
          onDone({ suggestions, message_id, session_id });
          return;
        }

        try {
          const parsed = JSON.parse(payload);
          if (parsed.token) onToken(parsed.token);
          if (Array.isArray(parsed.suggestions)) suggestions = parsed.suggestions;
          if (parsed.message_id) message_id = parsed.message_id;  // CB-12
          if (parsed.session_id) session_id = parsed.session_id;  // CB-12/CB-19
        } catch {
          // plain-text token fallback (not JSON-wrapped)
          if (payload) onToken(payload);
        }
      }
    }
    onDone({ suggestions, message_id, session_id });
  } catch (err) {
    onError(new Error("Stream interrupted. Please try again."));
  }
}

/**
 * createChatSession — CB-13
 * Creates a new backend session for logged-in users. Guests skip this
 * (handled by caller) since guest sessions aren't persisted.
 * NOTE: relies on POST {API_URL}/api/chat/sessions — confirm with backend
 * owner whether this route exists yet.
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
    return data.session_id || data.id || null;
  } catch {
    return null; // fail silently — local reset still works
  }
}
export async function fetchChatHistory(token) {
  if (!token) return [];

  let response;
  try {
    response = await fetchWithTimeout(`${API_URL}/api/chat/history`, {
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
    return data.history || data.sessions || [];
  } catch {
    return [];
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