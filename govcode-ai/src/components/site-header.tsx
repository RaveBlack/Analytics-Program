import Link from "next/link";
import { Button, Container } from "@/components/ui";

const nav = [
  { href: "/docs", label: "Docs" },
  { href: "/api", label: "API" },
  { href: "/pricing", label: "Pricing" },
  { href: "/security", label: "Security" },
  { href: "/compliance", label: "Compliance" },
];

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-white/10 bg-black/70 backdrop-blur">
      <Container className="flex h-16 items-center justify-between">
        <div className="flex items-center gap-6">
          <Link
            href="/"
            className="inline-flex items-center gap-2 text-sm font-semibold tracking-tight text-white"
          >
            <span className="grid h-7 w-7 place-items-center rounded-lg border border-white/10 bg-white/5">
              GC
            </span>
            <span>GovCode AI</span>
          </Link>
          <nav className="hidden items-center gap-1 md:flex">
            {nav.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="rounded-full px-3 py-2 text-sm text-zinc-300 hover:bg-white/5 hover:text-white"
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-2">
          <Button href="/dashboard" variant="ghost">
            Dashboard
          </Button>
          <Button href="/dashboard/playground" variant="primary">
            Try Playground
          </Button>
        </div>
      </Container>
    </header>
  );
}

