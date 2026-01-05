import { Card, Container } from "@/components/ui";

export const metadata = {
  title: "Security",
};

export default function SecurityPage() {
  return (
    <Container className="py-14">
      <div className="max-w-2xl">
        <h1 className="text-3xl font-semibold tracking-tight text-white">
          Security
        </h1>
        <p className="mt-3 text-zinc-300">
          This starter app is designed to be deployed behind your controls. The
          defaults are conservative, but you should align to your program’s
          ATO/authorization requirements.
        </p>
      </div>

      <div className="mt-10 grid gap-6 md:grid-cols-3">
        <Card title="Network boundary">
          Deploy in your VPC/VNet, route outbound model calls through an
          approved gateway, and enforce egress controls. Use `OPENAI_BASE_URL`
          to point to your gateway.
        </Card>
        <Card title="Identity & access">
          Add your IdP (OIDC/SAML), enforce MFA, and implement RBAC for admin
          functions (keys, logs, policies). This starter does not include auth
          yet.
        </Card>
        <Card title="Audit & retention">
          Implement structured audit events for model requests and admin
          actions. Apply retention and redaction policies according to your
          requirements.
        </Card>
      </div>

      <div className="mt-10 rounded-2xl border border-white/10 bg-white/[0.03] p-6">
        <div className="text-sm font-semibold text-white">
          Recommended hardening checklist
        </div>
        <ul className="mt-3 space-y-2 text-sm text-zinc-300">
          <li>- Add authentication and authorization before production use.</li>
          <li>- Add request size limits and abuse protection (rate limiting).</li>
          <li>- Add allowlisted upstream hosts and pinned TLS where required.</li>
          <li>- Add logging with redaction + retention policy configuration.</li>
        </ul>
      </div>
    </Container>
  );
}

