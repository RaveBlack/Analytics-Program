import Link from "next/link";
import { forwardRef } from "react";

type ClassValue = string | false | null | undefined;
function cx(...classes: ClassValue[]) {
  return classes.filter(Boolean).join(" ");
}

export function Container({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cx("mx-auto w-full max-w-6xl px-4 sm:px-6", className)}>
      {children}
    </div>
  );
}

export function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-medium text-zinc-200">
      {children}
    </span>
  );
}

export const Button = forwardRef<
  HTMLAnchorElement,
  {
    href: string;
    children: React.ReactNode;
    variant?: "primary" | "secondary" | "ghost";
    className?: string;
  }
>(function Button(
  { href, children, variant = "primary", className },
  ref,
) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition focus:outline-none focus:ring-2 focus:ring-[var(--color-ring)]";
  const variants: Record<string, string> = {
    primary:
      "bg-white text-black hover:bg-white/90 border border-white/10 shadow-sm",
    secondary:
      "bg-white/5 text-zinc-100 hover:bg-white/10 border border-white/10",
    ghost: "text-zinc-200 hover:text-white hover:bg-white/5",
  };
  return (
    <Link ref={ref} href={href} className={cx(base, variants[variant], className)}>
      {children}
    </Link>
  );
});

export function Card({
  title,
  children,
  className,
}: {
  title?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cx(
        "rounded-2xl border border-white/10 bg-white/[0.03] p-5 shadow-sm",
        className,
      )}
    >
      {title ? (
        <div className="mb-3 text-sm font-semibold text-white">{title}</div>
      ) : null}
      <div className="text-sm leading-6 text-zinc-300">{children}</div>
    </div>
  );
}

