import { useState, useRef, useEffect, useCallback } from "react";
import { useLocation } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import {
  sendMessage,
  sendMessageStream,
  createChatSession,
  fetchChatHistory,
  fetchTopicProgress,
  exportSession,
} from "../../services/chatApi";
import { getContextString, getTopicContext, getPageUrl } from "../../utils/routeContext";
import Message, { MessageFeedback, renderLatexSegments } from "./Message";
import SuggestedQuestions from "./SuggestedQuestions";
import MathSymbolPicker from "./MathSymbolPicker";
import { IconClose, IconHistory, IconSigma, IconPlus, IconSend, IconDownload } from "./Icons";

const WELCOME_PROMPTS = [
  "How do I find ∂f/∂x?",
  "Explain the gradient geometrically",
  "What is the chain rule here?",
];

const DEMO_BOT_REPLY =
  "[STEP 1 of 2]\n\n" +
  "Great question! The partial derivative $\\frac{\\partial f}{\\partial x}$ measures how $f$ changes when only $x$ changes.\n\n" +
  "Step 1: Treat other variables as constants.\n" +
  "Step 2: Differentiate with respect to $x$.\n\n" +
  "For example, if $f(x,y) = x^2 y$, then $\\frac{\\partial f}{\\partial x} = 2xy$.";

const DEMO_SUGGESTIONS = [
  "Can you show me another example?",
  "What about ∂f/∂y?",
  "Explain the gradient geometrically",
];

const DIFFICULTY_LABELS = {
  beginner: { emoji: "🌱", label: "Beginner" },
  intermediate: { emoji: "📈", label: "Intermediate" },
  advanced: { emoji: "🚀", label: "Advanced" },
};

function TypingIndicator() {
  return (
    <div className="cb-msg-row cb-msg-row--bot">
      <div className="cb-msg-avatar cb-msg-avatar--bot" aria-hidden="true">∂</div>
      <div className="cb-msg-bubble cb-msg-bubble--bot cb-msg-bubble--typing" aria-label="Tutor is thinking">
        <span className="cb-dot" /><span className="cb-dot" /><span className="cb-dot" />
      </div>
    </div>
  );
}

function WelcomeScreen({ topic, onSelect }) {
  return (
    <div className="cb-welcome">
      <div className="cb-welcome-icon" aria-hidden="true">∂</div>
      <h3 className="cb-welcome-title">Calculus Tutor</h3>
      <p className="cb-welcome-sub">
        Ask me anything about <strong>{topic}</strong>.<br />
        I explain step-by-step with proper notation.
      </p>
      <div className="cb-welcome-hints">
        {WELCOME_PROMPTS.map((q) => (
          <button key={q} type="button" className="cb-hint-chip" onClick={() => onSelect(q)}>
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
// History items function
function formatHistoryItems(raw) {
  if (!raw?.length) return [];
  if (raw[0]?.preview) return raw;

  return raw
    .filter((m) => m.role === "user")
    .map((m, i) => ({
      preview: (m.content || "").slice(0, 72) + ((m.content || "").length > 72 ? "…" : ""),
      date: m.timestamp ? new Date(m.timestamp).toLocaleDateString() : "",
      messages: raw.slice(Math.max(0, i * 2 - 1), i * 2 + 3),
      id: m.id || i,
    }));
}

function ChatWindow({ onClose, onActivity }) {
  const { user } = useAuth();
  const location = useLocation();
  const pathname = location.pathname;
  const { topic } = getTopicContext(pathname);

  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [showSymbols, setShowSymbols] = useState(false);
  const [activeGroup, setActiveGroup] = useState(0);
  const [tab, setTab] = useState("chat");
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [difficulty, setDifficulty] = useState(null); // CB-18
  const [exporting, setExporting] = useState(false); // CB-19

  const bottomRef = useRef(null);
  const textareaRef = useRef(null);
  const symbolsRef = useRef(null);
  const symToggleRef = useRef(null); // CB-21: refocus target when picker closes

  // CB-21: move keyboard focus into the panel as soon as it opens, so a
  // keyboard-only user isn't left with focus stranded on the (now hidden)
  // trigger bubble.
  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading, suggestions]);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 120)}px`;
  }, [input]);

  useEffect(() => {
    if (!showSymbols) return;
    const handler = (e) => {
      if (symbolsRef.current && !symbolsRef.current.contains(e.target)) setShowSymbols(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showSymbols]);

  // CB-21: Escape should close the math symbol picker first, not the whole
  // chat panel. Registered on the capture phase so it runs before
  // Chatbot.jsx's document-level Escape handler (which closes the entire
  // panel) ever sees the event — stopPropagation here prevents that.
  useEffect(() => {
    if (!showSymbols) return;
    const handler = (e) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        setShowSymbols(false);
        symToggleRef.current?.focus();
      }
    };
    document.addEventListener("keydown", handler, true);
    return () => document.removeEventListener("keydown", handler, true);
  }, [showSymbols]);

  const loadHistory = useCallback(async () => {
    if (!user?.accessToken) return;
    setHistoryLoading(true);
    try {
      const h = await fetchChatHistory(user.accessToken);
      setHistory(formatHistoryItems(h));
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { id: Date.now(), role: "error", content: err.message, timestamp: new Date().toISOString() },
      ]);
      setTab("chat");
    } finally {
      setHistoryLoading(false);
    }
  }, [user]);

  useEffect(() => {
    if (tab === "history") loadHistory();
  }, [tab, loadHistory]);

  // CB-18: refresh the difficulty badge whenever the topic changes or a
  // response just finished (message_count on the server may have moved).
  useEffect(() => {
    if (isLoading || !user?.accessToken) {
      if (!user?.accessToken) setDifficulty(null);
      return;
    }
    let cancelled = false;
    fetchTopicProgress(user.accessToken, topic).then((progress) => {
      if (!cancelled) setDifficulty(progress?.difficulty_level || null);
    });
    return () => {
      cancelled = true;
    };
  }, [isLoading, user, topic]);

  // const insertSymbol = (symbolText) => {
  //   const ta = textareaRef.current;
  //   if (!ta) return;
  //   const start = ta.selectionStart;
  //   const end = ta.selectionEnd;
  //   const before = input.slice(0, start);
  //   const after = input.slice(end);
  //   const newVal = before + symbolText + after;
  //   setInput(newVal);
  //   requestAnimationFrame(() => {
  //     ta.focus();
  //     const pos = start + symbolText.length;
  //     ta.setSelectionRange(pos, pos);
  //   });
  // };
  const insertSymbol = (symbolText, placeholder) => {
    const ta = textareaRef.current;
    if (!ta) return;
    const wrapped = `$${symbolText}$`;
    const start = ta.selectionStart;
    const end = ta.selectionEnd;
    const before = input.slice(0, start);
    const after = input.slice(end);
    const newVal = before + wrapped + after;
    setInput(newVal);

    requestAnimationFrame(() => {
      ta.focus();
      if (placeholder) {
        // lastIndexOf handles cases like \vec{v} where the letter
        // also appears in the command name itself ("vec")
        const localIdx = symbolText.lastIndexOf(placeholder);
        if (localIdx !== -1) {
          const selStart = start + 1 + localIdx; // +1 for the leading "$"
          const selEnd = selStart + placeholder.length;
          ta.setSelectionRange(selStart, selEnd);
          return;
        }
      }
      const pos = start + wrapped.length;
      ta.setSelectionRange(pos, pos);
    });
  };
  const buildHistory = (msgs) =>
    msgs
      .slice(-20)
      .filter((m) => m.role === "user" || m.role === "assistant")
      .map((m) => ({ role: m.role, content: m.content }));

  const handleSend = useCallback(async (text) => {
  const trimmed = (text ?? input).trim();
  if (!trimmed || isLoading) return;

  const userMsg = {
    id: Date.now(),
    role: "user",
    content: trimmed,
    timestamp: new Date().toISOString(),
    userInitial: user?.username?.[0]?.toUpperCase() || "Y",
  };

  setMessages((prev) => [...prev, userMsg]);
  setInput("");
  setSuggestions([]);
  setIsLoading(true);

  const context = getContextString(pathname);
  const pageUrl = getPageUrl();
  const token = user?.accessToken || null;
  const historyPayload = buildHistory([...messages, userMsg]);

  const botMsgId = Date.now() + 1;
  let streamedAny = false;

  // Placeholder bot message that fills in as tokens arrive
  const startBotMessage = () => {
    setMessages((prev) => [
      ...prev,
      { id: botMsgId, role: "assistant", content: "", timestamp: new Date().toISOString(), streaming: true },
    ]);
  };

  const appendToken = (chunk) => {
    if (!streamedAny) {
      streamedAny = true;
      startBotMessage();
    }
    setMessages((prev) =>
      prev.map((m) => (m.id === botMsgId ? { ...m, content: m.content + chunk } : m))
    );
  };

  try {
    await sendMessageStream(
      historyPayload,
      context,
      token,
      pageUrl,
      appendToken,
      ({ suggestions: finalSuggestions }) => {
        setMessages((prev) => {
          const exists = prev.some((m) => m.id === botMsgId);
          if (!exists) {
            return [
              ...prev,
              {
                id: botMsgId,
                role: "assistant",
                content: "Sorry, I didn't get a response. Please try again.",
                timestamp: new Date().toISOString(),
              },
            ];
          }
          return prev.map((m) => (m.id === botMsgId ? { ...m, streaming: false } : m));
        });
        setSuggestions(finalSuggestions || []);
        setIsLoading(false);
        onActivity?.();
      },
      async () => {
        // Streaming failed/unavailable — fall back to the original non-streaming call
        try {
          const data = await sendMessage(historyPayload, context, token, pageUrl, topic);
          setMessages((prev) => {
            const withoutPlaceholder = prev.filter((m) => m.id !== botMsgId);
            return [
              ...withoutPlaceholder,
              {
                id: botMsgId,
                role: "assistant",
                content: data.reply || "Sorry, I didn't get a response. Please try again.",
                timestamp: new Date().toISOString(),
              },
            ];
          });
          setSuggestions(data.suggestions || []);
          if (data.difficulty) setDifficulty(data.difficulty); // CB-18
        } catch (err) {
          setMessages((prev) => {
            const withoutPlaceholder = prev.filter((m) => m.id !== botMsgId);
            return [
              ...withoutPlaceholder,
              {
                id: botMsgId,
                role: "assistant",
                content: DEMO_BOT_REPLY,
                timestamp: new Date().toISOString(),
              },
            ];
          });
          setSuggestions(DEMO_SUGGESTIONS);
        } finally {
          setIsLoading(false);
          onActivity?.();
        }
      }
    );
  } catch (err) {
    setIsLoading(false);
  }
}, [input, isLoading, messages, user, pathname, onActivity, topic]);

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // CB-19: exports the active session as a downloadable study sheet
  const handleExport = useCallback(async () => {
    if (exporting) return;
    setExporting(true);
    try {
      const { blob, filename } = await exportSession(user?.accessToken, sessionId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { id: Date.now(), role: "error", content: err.message, timestamp: new Date().toISOString() },
      ]);
    } finally {
      setExporting(false);
    }
  }, [user, sessionId, exporting]);

  return (
    <div className="cb-window" role="dialog" aria-label="Calculus Tutor Chat" aria-modal="true">
      <div className="cb-window-header">
        <div className="cb-header-brand">
          <div className="cb-header-icon" aria-hidden="true">∂</div>
          <div className="cb-header-info">
            <span className="cb-header-title">Calculus Tutor</span>
            <span className="cb-header-topic" title={pathname}>{topic}</span>
          </div>
        </div>
        <div className="cb-header-actions">
          {user && (
            <button
              type="button"
              className={`cb-tab-btn${tab === "history" ? " cb-tab-btn--active" : ""}`}
              onClick={() => setTab(tab === "history" ? "chat" : "history")}
              aria-label="Chat history"
              aria-pressed={tab === "history"}
              title="Past conversations"
            >
              ⧖
            </button>
          )}
          {user && (
            <button
              type="button"
              className="cb-icon-btn"
              onClick={handleExport}
              disabled={exporting || !sessionId}
              aria-label="Export study sheet"
              title={sessionId ? "Export this session as a study sheet" : "Send a message first to create a session"}
            >
              <IconDownload />
            </button>
          )}
          <button
              type="button"
              className="cb-icon-btn cb-new-chat-btn"
              onClick={async () => {
                if (user?.accessToken) {
                  const newId = await createChatSession(user.accessToken);
                  setSessionId(newId);
                } else {
                  setSessionId(null);
                }
                setMessages([]);
                setSuggestions([]);
                setInput("");
              }}
              title="New Chat"
              aria-label="Start a new chat"
            >
            <span className="cb-new-chat-icon" aria-hidden="true">+</span>
            <span>New Chat</span>
          </button>
          <button type="button" className="cb-icon-btn cb-icon-btn--close" onClick={onClose} aria-label="Close chat">✕</button>
        </div>
      </div>

      <div className="cb-topic-bar">
        <span className="cb-topic-dot" aria-hidden="true" />
        <span className="cb-topic-text">
          Studying: <strong>{topic}</strong>
          <span className="cb-topic-path"> · {pathname}</span>
        </span>
        {user && difficulty && DIFFICULTY_LABELS[difficulty] && (
          <span
            className={`cb-difficulty-badge cb-difficulty-badge--${difficulty}`}
            title="Adaptive difficulty level for this topic, based on your history (CB-18)"
          >
            {DIFFICULTY_LABELS[difficulty].emoji} {DIFFICULTY_LABELS[difficulty].label}
          </span>
        )}
        {!user && <span className="cb-guest-note">Guest — history won't be saved</span>}
      </div>

      {tab === "history" ? (
        <div className="cb-body">
          {historyLoading ? (
            <div className="cb-loading-history">Loading history…</div>
          ) : history.length === 0 ? (
            <p className="cb-history-empty">No past conversations yet.</p>
          ) : (
            <ul className="cb-history-list">
              {history.map((session) => {
                const selectSession = () => {
                  if (session.messages?.length) setMessages(session.messages);
                  if (session.id) setSessionId(session.id);
                  setTab("chat");
                };
                return (
                  <li
                    key={session.id}
                    className="cb-history-item"
                    role="button"
                    tabIndex={0}
                    onClick={selectSession}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        selectSession();
                      }
                    }}
                    aria-label={`Open conversation: ${session.preview}${session.date ? `, ${session.date}` : ""}`}
                  >
                    <span className="cb-history-preview">{session.preview}</span>
                    <span className="cb-history-time">{session.date}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      ) : (
        <div className="cb-body" role="log" aria-live="polite" aria-label="Conversation">
          {messages.length === 0 ? (
            <WelcomeScreen topic={topic} onSelect={handleSend} />
          ) : (
            <>
              {messages.map((msg, i) => {
                const isLast = i === messages.length - 1;
                const isLastBot = isLast && msg.role === "assistant";
                const showSuggestions = isLastBot && suggestions.length > 0;
                return (
                  <div
                    key={msg.id ?? i}
                    className={`cb-turn${showSuggestions ? " cb-turn--with-suggestions" : ""}`}
                  >
                    <Message
                      message={{ ...msg, userInitial: user?.username?.[0]?.toUpperCase() }}
                      showFeedback={!showSuggestions}
                    />
                    {showSuggestions && (
                      <SuggestedQuestions suggestions={suggestions} onSelect={handleSend} disabled={isLoading} />
                    )}
                    {showSuggestions && <MessageFeedback className="cb-msg-feedback--after-suggestions" />}
                  </div>
                );
              })}
              {isLoading && <TypingIndicator />}
            </>
          )}
          <div ref={bottomRef} />
        </div>
      )}

      {showSymbols && tab === "chat" && (
        <div ref={symbolsRef} id="cb-symbol-picker" role="region" aria-label="Math symbol picker">
          <MathSymbolPicker activeGroup={activeGroup} onGroupChange={setActiveGroup} onInsert={insertSymbol} />
        </div>
      )}

      {tab === "chat" && (
          <div className="cb-input-area">
            {input.trim() && (
              <div className="cb-input-preview">
                <span className="cb-input-preview-label">Preview</span>
                <div className="cb-input-preview-content">
                  {renderLatexSegments(input, "preview")}
                </div>
              </div>
            )}
            <div className="cb-input-row">
              {/* ...unchanged... */}
            <button
              ref={symToggleRef}
              type="button"
              className={`cb-sym-toggle${showSymbols ? " active" : ""}`}
              onClick={() => setShowSymbols((v) => !v)}
              aria-label="Math symbols"
              aria-expanded={showSymbols}
              aria-controls="cb-symbol-picker"
              title="Calculus symbols"
            >
              ∑
            </button>
            <textarea
              ref={textareaRef}
              className="cb-textarea"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a calculus question…"
              rows={1}
              disabled={isLoading}
              aria-label="Message input"
            />
            <button
              type="button"
              className="cb-send-btn"
              onClick={() => handleSend()}
              disabled={isLoading || !input.trim()}
              aria-label="Send message"
            >
              ↑
            </button>
          </div>
          <div className="cb-input-hint">
            <kbd>$…$</kbd> inline math · <kbd>$$…$$</kbd> block · tap <strong>∑</strong> for symbols
          </div>
        </div>
      )}
    </div>
  );
}

export default ChatWindow;
