import { NextResponse } from "next/server";
import { callUpstreamChat, type ChatMessage } from "@/lib/openai-compatible";

type RequestBody = {
  model?: string;
  messages?: ChatMessage[];
};

function badRequest(message: string, status = 400) {
  return NextResponse.json({ error: message }, { status });
}

export async function POST(req: Request) {
  let body: RequestBody;
  try {
    body = (await req.json()) as RequestBody;
  } catch {
    return badRequest("Invalid JSON body.");
  }

  const messages = body.messages;
  if (!Array.isArray(messages) || messages.length === 0) {
    return badRequest("`messages` must be a non-empty array.");
  }
  if (messages.length > 64) {
    return badRequest("Too many messages (max 64).", 413);
  }
  for (const m of messages) {
    if (
      !m ||
      (m.role !== "system" && m.role !== "user" && m.role !== "assistant") ||
      typeof m.content !== "string"
    ) {
      return badRequest("Each message must have `role` and `content`.");
    }
    if (m.content.length > 20_000) {
      return badRequest("Message content too large.", 413);
    }
  }

  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), 45_000);
  try {
    const result = await callUpstreamChat({
      model: body.model,
      messages,
      signal: controller.signal,
    });
    return NextResponse.json(result, { status: 200 });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Unknown error";
    const status = msg.includes("Missing OPENAI_API_KEY") ? 500 : 502;
    return NextResponse.json({ error: msg }, { status });
  } finally {
    clearTimeout(t);
  }
}

