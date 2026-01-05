import Link from "next/link";
import { Container } from "@/components/ui";

export function SiteFooter() {
  return (
    <footer className="border-t border-white/10">
      <Container className="flex flex-col gap-6 py-10 md:flex-row md:items-center md:justify-between">
        <div className="text-sm text-zinc-400">
          <div className="font-semibold text-white">GovCode AI</div>
          <div className="mt-1">
            Deployable AI for public-sector software and policy workflows.
          </div>
        </div>
        <div className="flex flex-wrap gap-x-5 gap-y-3 text-sm">
          <Link className="text-zinc-300 hover:text-white" href="/docs">
            Docs
          </Link>
          <Link className="text-zinc-300 hover:text-white" href="/api">
            API
          </Link>
          <Link className="text-zinc-300 hover:text-white" href="/security">
            Security
          </Link>
          <Link className="text-zinc-300 hover:text-white" href="/compliance">
            Compliance
          </Link>
          <Link className="text-zinc-300 hover:text-white" href="/pricing">
            Pricing
          </Link>
        </div>
      </Container>
    </footer>
  );
}

