"use client";

import { useMemo, useRef, useState } from "react";
import { Container } from "@/components/ui";

type Role = "system" | "user" | "assistant";
type ChatMessage = { id: string; role: Role; content: string };

function makeId() {
  return `m_${Math.random().toString(16).slice(2)}`;
}

export default function PlaygroundPage() {
  const [model, setModel] = useState("gpt-4o-mini");
  const [system, setSystem] = useState(
    "You are GovCode AI, a helpful assistant for government and regulated teams.",
  );
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    { id: makeId(), role: "assistant", content: "Ask me to draft, explain, or refactor." },
  ]);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const payloadMessages = useMemo<ChatMessage[]>(() => {
    const userVisible = messages.filter((m) => m.role !== "system");
    return [{ id: "system", role: "system", content: system }, ...userVisible];
  }, [messages, system]);

  async function send() {
    const trimmed = input.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setInput("");
    setMessages((m) => [...m, { id: makeId(), role: "user", content: trimmed }]);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          model,
          messages: [
            ...payloadMessages.map(({ role, content }) => ({ role, content })),
            { role: "user", content: trimmed },
          ],
        }),
      });
      const json = (await res.json()) as
        | { message?: { role: Role; content: string }; error?: string }
        | undefined;
      if (!res.ok) {
        throw new Error(json?.error ?? `Request failed (${res.status})`);
      }
      const reply = json?.message?.content ?? "(empty response)";
      setMessages((m) => [...m, { id: makeId(), role: "assistant", content: reply }]);
      setTimeout(() => scrollRef.current?.scrollIntoView({ behavior: "smooth" }), 0);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setMessages((m) => [
        ...m,
        { id: makeId(), role: "assistant", content: `Error: ${msg}` },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Container className="py-10">
      <div className="flex flex-col gap-6">
        <div className="flex flex-col gap-2">
          <h1 className="text-2xl font-semibold text-white">Playground</h1>
          <p className="text-sm text-zinc-400">
            This is a simple chat UI calling your server-side `/api/chat` route.
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4 md:col-span-1">
            <label className="text-xs font-semibold text-white">Model</label>
            <input
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="mt-2 w-full rounded-xl border border-white/10 bg-black/40 px-3 py-2 text-sm text-zinc-100 outline-none focus:ring-2 focus:ring-[var(--color-ring)]"
              placeholder="gpt-4o-mini"
            />
            <label className="mt-4 block text-xs font-semibold text-white">
              System prompt
            </label>
            <textarea
              value={system}
              onChange={(e) => setSystem(e.target.value)}
              rows={6}
              className="mt-2 w-full resize-none rounded-xl border border-white/10 bg-black/40 px-3 py-2 text-sm text-zinc-100 outline-none focus:ring-2 focus:ring-[var(--color-ring)]"
            />
            <div className="mt-4 text-xs text-zinc-400">
              Tip: point `OPENAI_BASE_URL` to your approved model gateway.
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4 md:col-span-2">
            <div className="h-[46vh] overflow-y-auto rounded-xl border border-white/10 bg-black/40 p-4">
              <div className="space-y-4">
                {messages.map((m) => (
                  <div key={m.id}>
                    <div className="text-xs font-semibold text-white/80">
                      {m.role}
                    </div>
                    <div className="mt-1 whitespace-pre-wrap text-sm leading-6 text-zinc-200">
                      {m.content}
                    </div>
                  </div>
                ))}
                <div ref={scrollRef} />
              </div>
            </div>

            <div className="mt-4 flex gap-2">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) send();
                }}
                className="flex-1 rounded-xl border border-white/10 bg-black/40 px-3 py-2 text-sm text-zinc-100 outline-none focus:ring-2 focus:ring-[var(--color-ring)]"
                placeholder="Write a short policy memo outline..."
              />
              <button
                onClick={send}
                disabled={busy}
                className="inline-flex items-center justify-center rounded-xl border border-white/10 bg-white px-4 py-2 text-sm font-medium text-black hover:bg-white/90 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy ? "Sending…" : "Send"}
              </button>
            </div>

            <div className="mt-2 text-xs text-zinc-400">
              Press <span className="font-semibold text-white">Ctrl</span>+
              <span className="font-semibold text-white">Enter</span> to send.
            </div>
          </div>
        </div>
      </div>
    </Container>
  );
}

