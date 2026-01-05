import { Button, Card, Container } from "@/components/ui";

export const metadata = {
  title: "Pricing",
};

const tiers = [
  {
    name: "Pilot",
    price: "$0",
    desc: "Local dev + evaluation.",
    bullets: ["Playground", "API route", "Docs pages", "Self-host friendly"],
    cta: { label: "Get started", href: "/dashboard/playground" },
  },
  {
    name: "Program",
    price: "Contact",
    desc: "For production programs and regulated environments.",
    bullets: ["SSO + RBAC", "Audit events", "Model gateway", "Private networking"],
    cta: { label: "Read security", href: "/security" },
  },
  {
    name: "Enterprise",
    price: "Contact",
    desc: "Large deployments with procurement workflows.",
    bullets: ["SCIM", "Tenant isolation", "Custom retention", "Support SLAs"],
    cta: { label: "Compliance overview", href: "/compliance" },
  },
];

export default function PricingPage() {
  return (
    <Container className="py-14">
      <div className="max-w-2xl">
        <h1 className="text-3xl font-semibold tracking-tight text-white">
          Pricing
        </h1>
        <p className="mt-3 text-zinc-300">
          This repo includes a working starter you can extend. Use these tiers
          as placeholders for your real offering.
        </p>
      </div>

      <div className="mt-10 grid gap-6 md:grid-cols-3">
        {tiers.map((t) => (
          <Card key={t.name} className="flex h-full flex-col">
            <div className="flex items-baseline justify-between">
              <div className="text-base font-semibold text-white">{t.name}</div>
              <div className="text-sm text-zinc-300">{t.price}</div>
            </div>
            <div className="mt-2 text-sm text-zinc-400">{t.desc}</div>
            <ul className="mt-5 space-y-2 text-sm text-zinc-300">
              {t.bullets.map((b) => (
                <li key={b}>- {b}</li>
              ))}
            </ul>
            <div className="mt-6">
              <Button href={t.cta.href} variant="secondary">
                {t.cta.label}
              </Button>
            </div>
          </Card>
        ))}
      </div>
    </Container>
  );
}

