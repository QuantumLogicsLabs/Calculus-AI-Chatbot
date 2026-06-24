import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import Chatbot from "./components/Chatbot/Chatbot";
import "./index.css";
import Dashboard from "./components/Dashboard/Dashboard";


function DemoPage({ title }) {
    return (
      <main style={{ padding: "2rem", maxWidth: 720, margin: "0 auto" }}>
        <h1 style={{ marginTop: 0 }}>{title}</h1>
        <nav style={{ display: "flex", gap: "1rem", flexWrap: "wrap", marginTop: "1.5rem" }}>
          <Link to="/">Home</Link>
          <Link to="/partial-derivatives/1">Partial Derivatives</Link>
          <Link to="/vector-calculus/1">Vector Calculus</Link>
          <Link to="/limits-continuity/1">Limits</Link>
          <Link to="/ai-solver">AI Solver</Link>
          <Link to="/dashboard">Dashboard</Link>
        </nav>
        <p style={{ marginTop: "2rem", fontSize: "0.85rem", color: "var(--muted)" }}>
          Change page → topic bar in chat should update (CB-5).
        </p>
      </main>
    );
  }

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<DemoPage title="Home — CalcVoyager Demo" />} />
          <Route path="/partial-derivatives/1" element={<DemoPage title="Partial Derivatives Part 1" />} />
          <Route path="/vector-calculus/1" element={<DemoPage title="Vector Calculus Part 1" />} />
          <Route path="/limits-continuity/1" element={<DemoPage title="Limits & Continuity Part 1" />} />
          <Route path="/ai-solver" element={<DemoPage title="AI Solver" />} />
          <Route path="/dashboard" element={<Dashboard />} />
        </Routes>
        <Chatbot />
      </BrowserRouter>
    </AuthProvider>
  );
}