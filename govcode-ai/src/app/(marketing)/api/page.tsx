import { Container } from "@/components/ui";

export const metadata = {
  title: "API",
};

export default function ApiPage() {
  return (
    <Container className="py-14">
      <div className="max-w-2xl">
        <h1 className="text-3xl font-semibold tracking-tight text-white">API</h1>
        <p className="mt-3 text-zinc-300">
          GovCode AI exposes a simple chat endpoint you can place behind your
          gateway. The server route calls an OpenAI-compatible upstream.
        </p>
      </div>

      <div className="mt-10 grid gap-6 md:grid-cols-2">
        <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-6">
          <div className="text-sm font-semibold text-white">POST /api/chat</div>
          <div className="mt-2 text-sm text-zinc-300">
            Sends chat messages to your configured upstream and returns a single
            assistant message.
          </div>
          <pre className="mt-4 overflow-x-auto rounded-xl border border-white/10 bg-black/40 p-4 text-xs text-zinc-200">
{`curl -s http://localhost:3000/api/chat \\
  -H 'content-type: application/json' \\
  -d '{
    "model": "gpt-4o-mini",
    "messages": [
      {"role":"system","content":"You are a helpful assistant."},
      {"role":"user","content":"Draft a one-paragraph risk summary."}
    ]
  }'`}
          </pre>
        </div>

        <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-6">
          <div className="text-sm font-semibold text-white">Response shape</div>
          <pre className="mt-4 overflow-x-auto rounded-xl border border-white/10 bg-black/40 p-4 text-xs text-zinc-200">
{`{
  "id": "gcai_...",
  "model": "gpt-4o-mini",
  "message": {
    "role": "assistant",
    "content": "..."
  }
}`}
          </pre>
          <div className="mt-3 text-sm text-zinc-300">
            This keeps the surface small; you can add streaming, tool calling,
            logging, and policy enforcement as your program requires.
          </div>
        </div>
      </div>
    </Container>
  );
}

