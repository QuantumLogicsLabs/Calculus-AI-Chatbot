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

function BotMessageContent({ content }) {
  const cleanedContent = content.replace(
  /\[STEP\s+\d+\s+of\s+\d+\]\s*/i,
  ""
  );

  const segments = parseLatex(cleanedContent);
  
  return (
    <div className="cb-msg-text">
      {segments.map((seg, i) => {
        if (seg.type === "text") {
          return seg.content.split("\n").map((line, j, arr) => (
            <span key={`${i}-${j}`}>
              {line}
              {j < arr.length - 1 && <br />}
            </span>
          ));
        }
        if (seg.type === "inline") return <KatexSpan key={i} latex={seg.content} displayMode={false} />;
        if (seg.type === "block") return <KatexSpan key={i} latex={seg.content} displayMode={true} />;
        return null;
      })}
    </div>
  );
}

function MessageFeedback() {
  const [feedback, setFeedback] = useState(null);

  return (
    <div className="cb-msg-feedback">
      <button
        type="button"
        className={`cb-feedback-btn${feedback === "like" ? " cb-feedback-btn--active-like" : ""}`}
        onClick={() => setFeedback((f) => (f === "like" ? null : "like"))}
        aria-label="Like this response"
        title="Helpful"
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <path d="M7 10v12" /><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z" />
        </svg>
      </button>
      <button
        type="button"
        className={`cb-feedback-btn${feedback === "dislike" ? " cb-feedback-btn--active-dislike" : ""}`}
        onClick={() => setFeedback((f) => (f === "dislike" ? null : "dislike"))}
        aria-label="Dislike this response"
        title="Not helpful"
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <path d="M17 14V2" /><path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-3.88Z" />
        </svg>
      </button>
    </div>
  );
}

function Message({ message }) {
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
          <div className="cb-msg-bubble cb-msg-bubble--error">
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
                  {line}
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
      {isBot && <MessageFeedback />}
    </div>
  );
}

export default Message;