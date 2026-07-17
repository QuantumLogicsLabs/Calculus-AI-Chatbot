import { useState, useEffect, useRef } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";


function parseLatex(text) {
  const segments = [];
  const regex = /(\$\$[\s\S]+?\$\$|\$[^$\n]+?\$)/g;
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ type: "text", content: text.slice(lastIndex, match.index) });
    }
    const raw = match[0];
    if (raw.startsWith("$$")) {
      segments.push({ type: "block", content: raw.slice(2, -2).trim() });
    } else {
      segments.push({ type: "inline", content: raw.slice(1, -1).trim() });
    }
    lastIndex = regex.lastIndex;
  }

  if (lastIndex < text.length) {
    segments.push({ type: "text", content: text.slice(lastIndex) });
  }

  return segments;
}

function KatexSpan({ latex, displayMode }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current) return;
    try {
      katex.render(latex, ref.current, { throwOnError: false, strict: false, displayMode });
    } catch {
      ref.current.textContent = latex;
    }
  }, [latex, displayMode]);

  return displayMode
    ? <div ref={ref} className="cb-math-block" />
    : <span ref={ref} className="cb-math-inline" />;
}

const STEP_LINE_RE = /^step\s+\d+[:.)]/i;

function cleanBotContent(content) {
  return content
    .replace(/\[STEP\s+\d+\s+of\s+\d+\]\s*/i, "")
    .replace(/\[FOLLOW_UPS\][\s\S]*?\[\/FOLLOW_UPS\]/gi, "")
    .trim();
}

function renderLatexSegments(text, keyPrefix) {
  return parseLatex(text).map((seg, i) => {
    if (seg.type === "text") return <span key={`${keyPrefix}-${i}`}>{seg.content}</span>;
    if (seg.type === "inline") return <KatexSpan key={`${keyPrefix}-${i}`} latex={seg.content} displayMode={false} />;
    if (seg.type === "block") return <KatexSpan key={`${keyPrefix}-${i}`} latex={seg.content} displayMode={true} />;
    return null;
  });
}

function BotMessageContent({ content }) {
  const cleanedContent = cleanBotContent(content);
  const blocks = cleanedContent.split(/\n\s*\n/).filter((b) => b.trim());

  return (
    <div className="cb-msg-text cb-msg-text--structured">
      {blocks.map((block, bIdx) => {
        const lines = block.split("\n").filter((l) => l.trim());
        const isStepList = lines.length > 1 && lines.every((l) => STEP_LINE_RE.test(l.trim()));

        if (isStepList) {
          return (
            <ol key={bIdx} className="cb-msg-steps">
              {lines.map((line, lIdx) => (
                <li key={lIdx} className="cb-msg-step">
                  {renderLatexSegments(line.replace(/^step\s+\d+[:.)]\s*/i, ""), `b${bIdx}-l${lIdx}`)}
                </li>
              ))}
            </ol>
          );
        }

        return (
          <p key={bIdx} className="cb-msg-paragraph">
            {lines.map((line, lIdx) => (
              <span key={lIdx}>
                {renderLatexSegments(line, `b${bIdx}-l${lIdx}`)}
                {lIdx < lines.length - 1 && <br />}
              </span>
            ))}
          </p>
        );
      })}
    </div>
  );
}

function MessageFeedback({ className = "", messageId = null, sessionId = null, userToken = null }) {
  const [feedback, setFeedback] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleFeedback = async (newFeedback) => {
    // Toggle the local UI state
    setFeedback((f) => (f === newFeedback ? null : newFeedback));

    // For authenticated users, submit to backend (guests get local-only feedback)
    if (userToken && messageId && sessionId && newFeedback !== feedback) {
      setIsSubmitting(true);
      try {
        const { submitFeedback } = await import("../../services/chatApi");
        await submitFeedback(messageId, sessionId, newFeedback === feedback ? null : newFeedback, userToken);
      } catch (err) {
        console.warn("Could not save feedback:", err.message);
        // UI still reflects the toggle; submission failure is non-blocking
      } finally {
        setIsSubmitting(false);
      }
    }
  };

  const likeTitle = userToken ? "Mark as helpful (saved)" : "Mark as helpful (logged out — local only)";
  const dislikeTitle = userToken ? "Mark as not helpful (saved)" : "Mark as not helpful (logged out — local only)";

  return (
    <div className={`cb-msg-feedback${className ? ` ${className}` : ""}`}>
      <button
        type="button"
        className={`cb-feedback-btn${feedback === "like" ? " cb-feedback-btn--active-like" : ""}`}
        onClick={() => handleFeedback("like")}
        disabled={isSubmitting}
        aria-label="Like this response"
        aria-pressed={feedback === "like"}
        title={likeTitle}
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <path d="M7 10v12" /><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z" />
        </svg>
      </button>
      <button
        type="button"
        className={`cb-feedback-btn${feedback === "dislike" ? " cb-feedback-btn--active-dislike" : ""}`}
        onClick={() => handleFeedback("dislike")}
        disabled={isSubmitting}
        aria-label="Dislike this response"
        aria-pressed={feedback === "dislike"}
        title={dislikeTitle}
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <path d="M17 14V2" /><path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-3.88Z" />
        </svg>
      </button>
    </div>
  );
}

function Message({ message, showFeedback = true, messageId = null, sessionId = null, userToken = null }) {
  const isUser = message.role === "user";
  const isError = message.role === "error";
  const isBot = !isUser && !isError;
  const stepMatch =
    message.content?.match(/\[STEP\s+(\d+)\s+of\s+(\d+)\]/i);

  const currentStep = stepMatch
    ? parseInt(stepMatch[1])
    : null;

  const totalSteps = stepMatch
    ? parseInt(stepMatch[2])
    : null;

  if (isError) {
    return (
      <div className="cb-msg-block cb-msg-block--bot">
        <div className="cb-msg-row cb-msg-row--bot">
          <div className="cb-msg-avatar cb-msg-avatar--bot" aria-hidden="true">∂</div>
          <div className="cb-msg-bubble cb-msg-bubble--error" role="alert">
            <span className="cb-error-icon" aria-hidden="true">⚠</span>
            <span className="cb-msg-text">{message.content}</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`cb-msg-block${isUser ? " cb-msg-block--user" : " cb-msg-block--bot"}`}>
      <div className={`cb-msg-row ${isUser ? "cb-msg-row--user" : "cb-msg-row--bot"}`}>
        {isBot && <div className="cb-msg-avatar cb-msg-avatar--bot" aria-hidden="true">∂</div>}
        <div className={`cb-msg-bubble ${isUser ? "cb-msg-bubble--user" : "cb-msg-bubble--bot"}`}>
          {isUser ? (
            <div className="cb-msg-text">
              {message.content.split("\n").map((line, i, arr) => (
                <span key={i}>
                  {renderLatexSegments(line, `u-${i}`)}
                  {i < arr.length - 1 && <br />}
                </span>
              ))}
            </div>
          ) : (
            <>
              {currentStep && totalSteps && (
                <div className="cb-progress-container">
                  <div className="cb-progress-label">
                    Step {currentStep} of {totalSteps}
                  </div>

                  <div className="cb-progress-bar">
                    <div
                      className="cb-progress-fill"
                      style={{
                        width: `${(currentStep / totalSteps) * 100}%`
                      }}
                    />
                  </div>
                </div>
              )}
              <BotMessageContent content={message.content} />
              {currentStep === totalSteps && (
                <div className="cb-complete-badge">
                  🏆 Problem solved!
                </div>
              )}

            </>
        )}
          {message.timestamp && (
            <span className="cb-msg-time">
              {new Date(message.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </span>
          )}
        </div>
        {isUser && (
          <div className="cb-msg-avatar cb-msg-avatar--user" aria-hidden="true">
            {message.userInitial || "U"}
          </div>
        )}
      </div>
      {isBot && showFeedback && <MessageFeedback messageId={messageId} sessionId={sessionId} userToken={userToken} />}
    </div>
  );
}

export { MessageFeedback, renderLatexSegments };
export default Message;
