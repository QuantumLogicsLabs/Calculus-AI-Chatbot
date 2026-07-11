import { useState, useEffect, useRef } from "react";
import ChatWindow from "./ChatWindow";
import { IconClose } from "./Icons";
import "./Chatbot.css";

function Chatbot() {
  const [isOpen, setIsOpen] = useState(false);
  const [hasUnread, setHasUnread] = useState(false);
  const bubbleRef = useRef(null);
  const wasOpenRef = useRef(isOpen);

  useEffect(() => {
    const handler = (e) => {
      if (e.key === "Escape" && isOpen) setIsOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [isOpen]);

  // CB-21: whenever the panel goes from open -> closed (Escape, the
  // in-panel close button, or backdrop click), send keyboard focus back
  // to the trigger bubble instead of letting it fall off the unmounted
  // panel and get lost.
  useEffect(() => {
    if (wasOpenRef.current && !isOpen) {
      bubbleRef.current?.focus();
    }
    wasOpenRef.current = isOpen;
  }, [isOpen]);

  useEffect(() => {
    if (window.innerWidth <= 640) {
      document.body.style.overflow = isOpen ? "hidden" : "";
    }
    return () => { document.body.style.overflow = ""; };
  }, [isOpen]);

  return (
    <>
      {isOpen && <div className="cb-backdrop" onClick={() => setIsOpen(false)} aria-hidden="true" />}
  
      <div className="cb-root">
        {isOpen && (
          <div className="cb-panel-wrapper">
            <ChatWindow
              onClose={() => setIsOpen(false)}
              onActivity={() => !isOpen && setHasUnread(true)}
            />
          </div>
        )}
  
        <button
          ref={bubbleRef}
          type="button"
          className={`cb-bubble${isOpen ? " cb-bubble--open" : ""}`}
          onClick={() => {
            if (isOpen) setIsOpen(false);
            else { setIsOpen(true); setHasUnread(false); }
          }}
          aria-label={isOpen ? "Close calculus tutor" : "Open calculus tutor"}
          aria-expanded={isOpen}
          aria-haspopup="dialog"
        >
          <span className="cb-bubble-icon" aria-hidden="true">{
            isOpen ? <IconClose /> : <span className="cb-bubble-icon">∂</span>}
          </span>
          {!isOpen && hasUnread && <span className="cb-bubble-badge" aria-label="New message" />}
          {!isOpen && <span className="cb-bubble-label">Ask tutor</span>}
        </button>
      </div>
    </>
  );
}

export default Chatbot;
