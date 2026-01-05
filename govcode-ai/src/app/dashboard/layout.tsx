import Link from "next/link";
import { Container } from "@/components/ui";

export const metadata = {
  title: "Dashboard",
};

const nav = [
  { href: "/dashboard/playground", label: "Playground" },
  { href: "/docs", label: "Docs" },
  { href: "/api", label: "API" },
];

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen">
      <header className="border-b border-white/10 bg-black">
        <Container className="flex h-16 items-center justify-between">
          <Link href="/" className="text-sm font-semibold text-white">
            GovCode AI
          </Link>
          <nav className="flex items-center gap-1">
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
        </Container>
      </header>
      <main>{children}</main>
    </div>
  );
}

