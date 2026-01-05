export type ChatRole = "system" | "user" | "assistant";
export type ChatMessage = { role: ChatRole; content: string };

type UpstreamChatResponse = {
  id?: string;
  model?: string;
  choices?: Array<{ message?: { role?: string; content?: string } }>;
  error?: { message?: string; type?: string; code?: string };
};

function getEnv(name: string) {
  const v = process.env[name];
  return v && v.trim() ? v.trim() : undefined;
}

export function getUpstreamConfig() {
  const apiKey =
    getEnv("GOVCODE_AI_OPENAI_API_KEY") ?? getEnv("OPENAI_API_KEY");
  const baseUrl = (getEnv("OPENAI_BASE_URL") ?? "https://api.openai.com").replace(
    /\/$/,
    "",
  );
  const model =
    getEnv("OPENAI_MODEL") ?? getEnv("GOVCODE_AI_MODEL") ?? "gpt-4o-mini";
  return { apiKey, baseUrl, model };
}

export async function callUpstreamChat({
  messages,
  model,
  signal,
}: {
  messages: ChatMessage[];
  model?: string;
  signal?: AbortSignal;
}): Promise<{ id: string; model: string; message: { role: ChatRole; content: string } }> {
  const cfg = getUpstreamConfig();
  if (!cfg.apiKey) {
    throw new Error(
      "Missing OPENAI_API_KEY (or GOVCODE_AI_OPENAI_API_KEY) on the server.",
    );
  }
  const chosenModel = model ?? cfg.model;
  const url = `${cfg.baseUrl}/v1/chat/completions`;

  const res = await fetch(url, {
    method: "POST",
    headers: {
      authorization: `Bearer ${cfg.apiKey}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model: chosenModel,
      messages,
    }),
    signal,
  });

  const json = (await res.json()) as UpstreamChatResponse;
  if (!res.ok) {
    const err = json?.error?.message ?? `Upstream error (${res.status})`;
    throw new Error(err);
  }

  const choice = json.choices?.[0]?.message;
  const content = choice?.content ?? "";
  return {
    id: json.id ?? `gcai_${Date.now()}`,
    model: json.model ?? chosenModel,
    message: { role: "assistant", content },
  };
}

