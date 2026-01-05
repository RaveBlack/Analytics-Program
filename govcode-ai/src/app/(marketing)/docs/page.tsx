import { Card, Container } from "@/components/ui";

export const metadata = {
  title: "Docs",
};

export default function DocsPage() {
  return (
    <Container className="py-14">
      <div className="max-w-2xl">
        <h1 className="text-3xl font-semibold tracking-tight text-white">
          Docs
        </h1>
        <p className="mt-3 text-zinc-300">
          This is a starter documentation hub for GovCode AI. It’s designed to
          be extended for your environment (IdP, network boundary, retention,
          approvals, and model gateway).
        </p>
      </div>

      <div className="mt-10 grid gap-6 md:grid-cols-3">
        <Card title="Quickstart">
          <ol className="list-decimal space-y-2 pl-5">
            <li>Set `OPENAI_API_KEY` (or your compatible gateway key).</li>
            <li>Run `npm install` then `npm run dev`.</li>
            <li>Open the Playground and send a prompt.</li>
          </ol>
        </Card>
        <Card title="Environment variables">
          <ul className="space-y-2">
            <li>
              <span className="font-semibold text-white">OPENAI_API_KEY</span> —
              required
            </li>
            <li>
              <span className="font-semibold text-white">OPENAI_BASE_URL</span> —
              optional (defaults to OpenAI)
            </li>
            <li>
              <span className="font-semibold text-white">OPENAI_MODEL</span> —
              optional (default set in code)
            </li>
          </ul>
        </Card>
        <Card title="Data handling">
          Prompts are sent server-side from `/api/chat` to your configured
          upstream. Add your logging/redaction/retention policy in that route if
          needed.
        </Card>
      </div>

      <div className="mt-10 rounded-2xl border border-white/10 bg-white/[0.03] p-6">
        <div className="text-sm font-semibold text-white">Next steps</div>
        <ul className="mt-3 space-y-2 text-sm text-zinc-300">
          <li>
            - Add SSO (SAML/OIDC), SCIM, and role-based access controls.
          </li>
          <li>
            - Add audit events (who, what, when) with your retention policy.
          </li>
          <li>
            - Integrate a model gateway (allowlist models, enforce policies).
          </li>
        </ul>
      </div>
    </Container>
  );
}

