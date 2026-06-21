import React from 'react';

/**
 * SuggestedQuestions — displays AI-generated follow-up questions
 * 
 * Props:
 *   - suggestions: array of strings (from LLM's [FOLLOW_UPS] block)
 *   - onSelect: function(question) — fires when user clicks a suggestion
 *   - disabled: boolean — disables buttons while loading
 */
const SuggestedQuestions = ({ suggestions = [], onSelect, disabled = false }) => {
  if (!suggestions || suggestions.length === 0) {
    return null;
  }

  return (
    <div className="suggested-questions">
      <p className="suggestions-label">Follow-up suggestions:</p>
      <div className="suggestions-grid">
        {suggestions.map((question, index) => (
          <button
            key={index}
            className="suggestion-chip"
            onClick={() => onSelect(question)}
            disabled={disabled}
            type="button"
          >
            {question}
          </button>
        ))}
      </div>
    </div>
  );
};

export default SuggestedQuestions;