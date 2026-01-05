import { Card, Container } from "@/components/ui";

export const metadata = {
  title: "Compliance",
};

export default function CompliancePage() {
  return (
    <Container className="py-14">
      <div className="max-w-2xl">
        <h1 className="text-3xl font-semibold tracking-tight text-white">
          Compliance
        </h1>
        <p className="mt-3 text-zinc-300">
          Use this page as a place to document your control posture (e.g.
          FedRAMP, StateRAMP, CJIS, HIPAA, ISO 27001) once you integrate your
          identity, logging, and deployment pipelines.
        </p>
      </div>

      <div className="mt-10 grid gap-6 md:grid-cols-3">
        <Card title="Deployment model">
          Host in your approved environment. Keep data residency, network
          boundary, and egress controls aligned to your authorizing official’s
          requirements.
        </Card>
        <Card title="Controls mapping (starter)">
          Create a controls matrix mapping each control to: implementation, test
          evidence, and owner. This repo provides a place to build that.
        </Card>
        <Card title="Procurement readiness">
          Add your terms, support model, and security package references. Keep
          this content current to reduce procurement friction.
        </Card>
      </div>

      <div className="mt-10 rounded-2xl border border-white/10 bg-white/[0.03] p-6">
        <div className="text-sm font-semibold text-white">
          Suggested artifacts to add next
        </div>
        <ul className="mt-3 space-y-2 text-sm text-zinc-300">
          <li>- System Security Plan (SSP)</li>
          <li>- Data Flow Diagram (DFD) for model calls</li>
          <li>- Vulnerability management and patch cadence</li>
          <li>- Incident response playbook</li>
          <li>- Privacy impact assessment (PIA)</li>
        </ul>
      </div>
    </Container>
  );
}

