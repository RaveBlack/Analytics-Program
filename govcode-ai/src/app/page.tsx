import { Badge, Button, Card, Container } from "@/components/ui";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

export default function Home() {
  return (
    <div className="min-h-screen">
      <SiteHeader />
      <main>
        <section className="relative overflow-hidden">
          <div className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(900px_circle_at_20%_10%,rgba(124,58,237,0.35),transparent_55%),radial-gradient(900px_circle_at_80%_30%,rgba(59,130,246,0.25),transparent_55%)]" />
          <Container className="py-20 sm:py-28">
            <div className="max-w-2xl">
              <Badge>Deployable AI for government & regulated teams</Badge>
              <h1 className="mt-6 text-balance text-4xl font-semibold tracking-tight text-white sm:text-5xl">
                GovCode AI helps teams ship secure software, faster.
              </h1>
              <p className="mt-5 text-pretty text-lg leading-8 text-zinc-300">
                A modern coding and policy copilot platform designed for
                controlled environments: private networking, audit-friendly
                operations, and an API you can own.
              </p>
              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                <Button href="/dashboard/playground" variant="primary">
                  Open Playground
                </Button>
                <Button href="/docs" variant="secondary">
                  Read docs
                </Button>
              </div>
              <p className="mt-4 text-sm text-zinc-400">
                Note: this is a starter implementation for your repo; wire in
                your IdP, network controls, and approvals to match your program.
              </p>
            </div>
          </Container>
        </section>

        <section className="border-t border-white/10">
          <Container className="py-16">
            <div className="grid gap-6 md:grid-cols-3">
              <Card title="Private-by-default">
                Keep prompts and outputs in your boundary. Configure an
                OpenAI-compatible provider (commercial, on-prem, or gateway)
                with environment variables.
              </Card>
              <Card title="Audit-ready workflow">
                Clear request/response boundaries, explicit API keys, and a
                documented data-handling model. Add logging/retention policies
                where your program requires it.
              </Card>
              <Card title="Developer-grade UX">
                A fast Playground, clear docs, and a clean layout meant for
                teams who build and maintain mission software.
              </Card>
            </div>
          </Container>
        </section>

        <section className="border-t border-white/10">
          <Container className="py-16">
            <div className="grid gap-10 md:grid-cols-2 md:items-start">
              <div>
                <h2 className="text-2xl font-semibold text-white">
                  What you get in this repo
                </h2>
                <p className="mt-3 text-zinc-300">
                  A working web app + API surface you can extend into a full
                  platform.
                </p>
                <ul className="mt-6 space-y-3 text-sm text-zinc-300">
                  <li>
                    <span className="font-semibold text-white">Marketing:</span>{" "}
                    Home, Docs, Pricing, Security, Compliance pages
                  </li>
                  <li>
                    <span className="font-semibold text-white">Dashboard:</span>{" "}
                    Playground UI that calls the chat endpoint
                  </li>
                  <li>
                    <span className="font-semibold text-white">API:</span>{" "}
                    `/api/chat` (OpenAI-compatible upstream)
                  </li>
                </ul>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
                <div className="text-sm font-semibold text-white">
                  Example: POST /api/chat
                </div>
                <pre className="mt-3 overflow-x-auto rounded-xl border border-white/10 bg-black/40 p-4 text-xs text-zinc-200">
{`curl -s http://localhost:3000/api/chat \\
  -H 'content-type: application/json' \\
  -d '{"messages":[{"role":"user","content":"Write a short policy memo outline."}]}'`}
                </pre>
              </div>
            </div>
          </Container>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
