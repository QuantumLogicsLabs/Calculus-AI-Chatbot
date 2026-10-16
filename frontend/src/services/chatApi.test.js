import { sendMessageStream } from "./chatApi";

const encode = (text) => new TextEncoder().encode(text);
const messages = [{ role: "user", content: "Explain derivatives" }];

function streamed(parts, status = 200) {
  let index = 0;
  const reader = {
    read: jest.fn(async () => index < parts.length ? { done: false, value: encode(parts[index++]) } : { done: true }),
    cancel: jest.fn(async () => {}), releaseLock: jest.fn(),
  };
  return { ok: status === 200, status, body: { getReader: () => reader },
           json: async () => ({ detail: "The tutor is unavailable." }), reader };
}

async function run(response) {
  global.fetch = jest.fn(async () => response);
  const token = jest.fn(), done = jest.fn(), error = jest.fn();
  await sendMessageStream(messages, "", null, "/", "", token, done, error);
  return { token, done, error };
}

afterEach(() => jest.restoreAllMocks());

test("parses fragmented CRLF events and passes source metadata", async () => {
  const response = streamed(['data: {"delta":"Hel', 'lo"}\r\n\r\ndata: {"done":true,"mode":"live","source":"primary"}\r\n\r\n']);
  const { token, done, error } = await run(response);
  expect(token).toHaveBeenCalledWith("Hello");
  expect(done).toHaveBeenCalledTimes(1);
  expect(done).toHaveBeenCalledWith(expect.objectContaining({ mode: "live", source: "primary" }));
  expect(error).not.toHaveBeenCalled();
  expect(response.reader.cancel).toHaveBeenCalled();
});

test.each([
  ['event: error\ndata: {"error":"provider details","code":"ai_unavailable"}\n\n'],
  ['data: {"delta":"Partial"}\n\ndata: {"error":"failed"}\n\n'],
  ['data: {"delta":"Partial"}\n\n'],
  ['data: {"delta":'],
  ['data: {"done":true}\n\n'],
])("reports failed, empty or truncated streams without completion", async (data) => {
  const { done, error } = await run(streamed([data]));
  expect(done).not.toHaveBeenCalled();
  expect(error).toHaveBeenCalledTimes(1);
  expect(error.mock.calls[0][0].canFallback).not.toBe(true);
});

test.each([429, 500, 503, 504])("does not allow automatic retry for HTTP %s", async (status) => {
  const { done, error } = await run(streamed([], status));
  expect(done).not.toHaveBeenCalled();
  expect(error.mock.calls[0][0]).toMatchObject({ code: status, canFallback: false });
  expect(fetch).toHaveBeenCalledTimes(1);
});

test.each([404, 405, 501])("permits a legacy JSON fallback for unsupported stream HTTP %s", async (status) => {
  const { error } = await run(streamed([], status));
  expect(error.mock.calls[0][0].canFallback).toBe(true);
});

test("awaits async error handling", async () => {
  global.fetch = jest.fn(async () => streamed([], 404));
  let handled = false;
  await sendMessageStream(messages, "", null, "/", "", jest.fn(), jest.fn(), async () => {
    await Promise.resolve(); handled = true;
  });
  expect(handled).toBe(true);
});

test("request deadline aborts a hung stream", async () => {
  jest.useFakeTimers();
  global.fetch = jest.fn((url, options) => new Promise((resolve, reject) => {
    options.signal.addEventListener("abort", () => reject(Object.assign(new Error(), { name: "AbortError" })));
  }));
  const error = jest.fn();
  const pending = sendMessageStream(messages, "", null, "/", "", jest.fn(), jest.fn(), error);
  jest.advanceTimersByTime(45000);
  await pending;
  expect(error).toHaveBeenCalledWith(expect.objectContaining({ message: expect.stringContaining("too long") }));
  jest.useRealTimers();
});
