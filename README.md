# CalcVoyager AI Chatbot

An intelligent AI-powered calculus tutoring chatbot designed for the **CalcVoyager** learning platform. The chatbot provides step-by-step explanations, contextual learning assistance, mathematical notation rendering, conversation history, and topic-aware responses to help students master multivariable calculus concepts.

---

## 🚀 Features

### 📚 Calculus Tutoring
- Answers questions related to:
  - Partial Derivatives
  - Vector Calculus
  - Limits & Continuity
  - Gradients
  - Lagrange Multipliers
  - Multivariable Functions
  - Other CalcVoyager topics

### 📝 Step-by-Step Explanations
- Guides students through solutions instead of only providing answers.
- Encourages conceptual understanding and critical thinking.

### 🧮 Mathematical Notation Rendering
- Uses LaTeX for mathematical expressions.
- Frontend renders equations using KaTeX.

Example:

```latex
\nabla f = \left\langle \frac{\partial f}{\partial x}, \frac{\partial f}{\partial y} \right\rangle

💬 Conversation Memory
Maintains context across conversations.
Stores the last 10 conversation turns for improved continuity.
🎯 Topic-Aware Responses
Automatically detects the page/topic the student is studying.
Tailors explanations based on current learning context.
🔄 Suggested Follow-Up Questions

Examples:

Can you show another example?
Why does this step work?
What's the difference between this and a regular derivative?
👤 User Authentication Support
Logged-in users get persistent chat history.
Guest users can chat without account requirements.
⚠ Error Handling
Graceful handling of:
API failures
Slow responses
Network issues
Provides user-friendly fallback messages.
Team Theta

AI Chatbot Team for CalcVoyager

Building an intelligent, educational, and student-focused calculus tutoring experience.