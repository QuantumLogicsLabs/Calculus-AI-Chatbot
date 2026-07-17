import { useState, useEffect } from "react";
import Header from "./Header";
import Footer from "./Footer";

function Layout(props) {
  const [darkMode, setDarkMode] = useState(() => {
    try {
      return localStorage.getItem("calculus-dark") === "true";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    const root = document.documentElement;
    if (darkMode) {
      root.setAttribute("data-theme", "dark");
      root.classList.add("dark");
    } else {
      root.setAttribute("data-theme", "light");
      root.classList.remove("dark");
    }
    try {
      localStorage.setItem("calculus-dark", String(darkMode));
    } catch {}
  }, [darkMode]);

  const toggle = () => setDarkMode((v) => !v);

  return (
    <>
      <Header darkMode={darkMode} onToggleDark={toggle} />
      {props.body}
      <Footer />
    </>
  );
}

export default Layout;
