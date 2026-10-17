import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "../../context/AuthContext";
import ChatWindow from "./ChatWindow";
import { sendMessage, sendMessageStream } from "../../services/chatApi";

jest.mock("../../services/chatApi");
jest.mock("./Message", () => ({
  __esModule: true,
  default: ({ message }) => <div>{message.content}</div>,
  MessageFeedback: () => null,
  renderLatexSegments: (text) => text,
}));

let container, root;
beforeEach(() => {
  jest.clearAllMocks();
  HTMLElement.prototype.scrollIntoView = jest.fn();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

async function askQuestion() {
  await act(async () => root.render(
    <AuthProvider><MemoryRouter><ChatWindow /></MemoryRouter></AuthProvider>
  ));
  const question = [...container.querySelectorAll("button")].find((b) => b.textContent.includes("How do I find"));
  await act(async () => question.dispatchEvent(new MouseEvent("click", { bubbles: true })));
}

test("partial provider failure displays an error, removes partial answer and never retries", async () => {
  sendMessageStream.mockImplementation(async (...args) => {
    args[5]("UNFINISHED_ANSWER");
    await args[7](new Error("The tutor could not complete the answer. Please try again."));
  });
  await askQuestion();
  expect(container.textContent).toContain("could not complete");
  expect(container.textContent).not.toContain("UNFINISHED_ANSWER");
  expect(sendMessage).not.toHaveBeenCalled();
  expect(container.querySelector("textarea").disabled).toBe(false);
});

test("only unsupported streaming permits a single JSON fallback", async () => {
  sendMessageStream.mockImplementation(async (...args) => {
    await args[7](Object.assign(new Error("Unsupported"), { canFallback: true }));
  });
  sendMessage.mockResolvedValue({ reply: "A complete answer", mode: "live", suggestions: [] });
  await askQuestion();
  expect(sendMessage).toHaveBeenCalledTimes(1);
  expect(container.textContent).toContain("A complete answer");
});

test("explicit mock responses show demo mode", async () => {
  sendMessageStream.mockImplementation(async (...args) => {
    args[5]("A placeholder reply");
    await args[6]({ mode: "mock", suggestions: [] });
  });
  await askQuestion();
  expect(container.textContent).toContain("Demo mode — sample replies only");
});

test("rate limiting is visible and is not retried", async () => {
  sendMessageStream.mockImplementation(async (...args) => {
    await args[7](Object.assign(new Error("Limited"), { code: 429 }));
  });
  await askQuestion();
  expect(container.textContent).toContain("reached the chat limit");
  expect(sendMessage).not.toHaveBeenCalled();
});
