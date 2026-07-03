import { useState, useRef, useEffect, useCallback } from "react";
import { useLocation } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import { sendMessage, sendMessageStream, createChatSession, fetchChatHistory } from "../../services/chatApi";
import { getContextString, getTopicContext, getPageUrl } from "../../utils/routeContext";
import Message from "./Message";
import SuggestedQuestions from "./SuggestedQuestions";
import MathSymbolPicker from "./MathSymbolPicker";

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

  const bottomRef = useRef(null);
  const textareaRef = useRef(null);
  const symbolsRef = useRef(null);

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

  const insertSymbol = (symbolText) => {
    const ta = textareaRef.current;
    if (!ta) return;
    const start = ta.selectionStart;
    const end = ta.selectionEnd;
    const before = input.slice(0, start);
    const after = input.slice(end);
    const newVal = before + symbolText + after;
    setInput(newVal);
    requestAnimationFrame(() => {
      ta.focus();
      const pos = start + symbolText.length;
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
          const data = await sendMessage(historyPayload, context, token, pageUrl);
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
}, [input, isLoading, messages, user, pathname, onActivity]);

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

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
              title="Past conversations"
            >
              ⧖
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
              + New Chat
          </button>
          {/* <button type="button" className="cb-icon-btn cb-icon-btn--close" onClick={onClose} aria-label="Close chat">✕</button> */}
        </div>
      </div>

      <div className="cb-topic-bar">
        <span className="cb-topic-dot" aria-hidden="true" />
        <span className="cb-topic-text">
          Studying: <strong>{topic}</strong>
          <span className="cb-topic-path"> · {pathname}</span>
        </span>
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
              {history.map((session) => (
                <li
                  key={session.id}
                  className="cb-history-item"
                  onClick={() => {
                    if (session.messages?.length) setMessages(session.messages);
                    if (session.id) setSessionId(session.id);
                    setTab("chat");
                  }}
                >
                  <span className="cb-history-preview">{session.preview}</span>
                  <span className="cb-history-time">{session.date}</span>
                </li>
              ))}
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
                return (
                  <div key={msg.id ?? i}>
                    <Message message={{ ...msg, userInitial: user?.username?.[0]?.toUpperCase() }} />
                    {isLastBot && suggestions.length > 0 && (
                      <SuggestedQuestions suggestions={suggestions} onSelect={handleSend} disabled={isLoading} />
                    )}
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
        <div ref={symbolsRef}>
          <MathSymbolPicker activeGroup={activeGroup} onGroupChange={setActiveGroup} onInsert={insertSymbol} />
        </div>
      )}

      {tab === "chat" && (
        <div className="cb-input-area">
          <div className="cb-input-row">
            <button
              type="button"
              className={`cb-sym-toggle${showSymbols ? " active" : ""}`}
              onClick={() => setShowSymbols((v) => !v)}
              aria-label="Math symbols"
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
