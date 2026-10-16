import React, { act } from "react";
import { createRoot } from "react-dom/client";
import Message from "./Message";

test("display math renders without invalid paragraph nesting", async () => {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  const errors = jest.spyOn(console, "error").mockImplementation(() => {});
  try {
    await act(async () => root.render(<Message message={{
      role: "assistant", content: "The derivative is\n\n$$x^2$$", timestamp: new Date().toISOString(),
    }} />));
    expect(container.querySelector(".cb-math-block")).not.toBeNull();
    expect(container.querySelector("p div")).toBeNull();
    expect(errors).not.toHaveBeenCalled();
  } finally {
    await act(async () => root.unmount());
    errors.mockRestore();
    container.remove();
  }
});
