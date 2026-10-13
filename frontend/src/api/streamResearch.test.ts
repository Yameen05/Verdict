import { afterEach, expect, it, vi } from "vitest";
import { streamResearch, type StreamEvent } from "./client";
afterEach(() => vi.unstubAllGlobals());
function mock(chunks: string[]) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(new ReadableStream({ start(controller) {
    for (const chunk of chunks) controller.enqueue(new TextEncoder().encode(chunk));
    controller.close();
  }}), {status:200})));
}
it("handles fragmented SSE, concurrent progress, and heartbeats without advancing them", async () => {
  mock([": ping\r\n\r\nevent: prog",'ress\r\ndata: {"kind":"filing_question","index":1}\r\n\r\n', 'event: error\ndata: {"detail":"safe","error_type":"TimeoutError","failure":{"kind":"timeout"}}\n\n']);
  const events: StreamEvent[] = [];
  await streamResearch("AAPL",event => events.push(event));
  expect(events.map(e=>e.event)).toEqual(["progress","error"]);
});
it("rejects a disconnected or malformed stream before a terminal event", async () => {
  mock([": ping\n\nevent: completed\ndata: broken\n\n"]);
  await expect(streamResearch("AAPL",()=>{})).rejects.toThrow("before completion");
});
