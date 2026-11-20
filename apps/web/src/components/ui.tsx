// The handful of shared UI pieces every screen uses. Kept deliberately
// small: buttons, fields, notices, a loading state, and a page header.

import Link from "next/link";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "quiet" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-ink text-paper hover:opacity-90",
  secondary: "border border-line-strong bg-surface text-ink hover:border-ink",
  quiet: "text-ink-soft underline-offset-4 hover:text-ink hover:underline",
  danger: "border border-danger/40 bg-surface text-danger hover:bg-danger-soft",
};

export function Button({
  variant = "primary",
  busy = false,
  className = "",
  children,
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; busy?: boolean }) {
  const padding = variant === "quiet" ? "px-1 py-1" : "px-4 py-2.5";
  return (
    <button
      {...rest}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={`inline-flex items-center justify-center gap-2 rounded-lg text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${padding} ${VARIANTS[variant]} ${className}`}
    >
      {children}
    </button>
  );
}

export function ButtonLink({
  href,
  variant = "primary",
  className = "",
  children,
}: {
  href: string;
  variant?: Variant;
  className?: string;
  children: ReactNode;
}) {
  const padding = variant === "quiet" ? "px-1 py-1" : "px-4 py-2.5";
  return (
    <Link
      href={href}
      className={`inline-flex items-center justify-center gap-2 rounded-lg text-sm font-semibold transition ${padding} ${VARIANTS[variant]} ${className}`}
    >
      {children}
    </Link>
  );
}

export function Field({
  label,
  hint,
  className = "",
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string }) {
  return (
    <label className={`flex flex-col gap-1 text-sm ${className}`}>
      <span className="font-medium text-ink-soft">{label}</span>
      <input
        {...rest}
        className="rounded-lg border border-line-strong bg-surface px-3 py-2 text-base text-ink placeholder:text-muted focus:border-ink"
      />
      {hint && <span className="text-xs text-muted">{hint}</span>}
    </label>
  );
}

export const inputClass =
  "rounded-lg border border-line-strong bg-surface px-3 py-2 text-base text-ink placeholder:text-muted focus:border-ink";

export function Notice({
  tone = "info",
  children,
}: {
  tone?: "info" | "error" | "success" | "attention";
  children: ReactNode;
}) {
  const styles = {
    info: "border-line bg-surface text-ink-soft",
    error: "border-danger/30 bg-danger-soft text-danger",
    success: "border-stamp/30 bg-stamp-soft text-stamp",
    attention: "border-highlight bg-highlight/30 text-ink",
  }[tone];
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={`rounded-lg border px-3 py-2 text-sm ${styles}`}
    >
      {children}
    </div>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-3 py-10 text-sm text-muted">
      <span className="size-4 animate-spin rounded-full border-2 border-line-strong border-t-ink motion-reduce:animate-none" />
      {label}…
    </div>
  );
}

export function PageHeader({
  title,
  back,
  actions,
  children,
}: {
  title: ReactNode;
  back?: { href: string; label: string };
  actions?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-col gap-2">
      {back && (
        <Link href={back.href} className="w-fit text-sm text-ink-soft hover:text-ink">
          ‹ {back.label}
        </Link>
      )}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-3xl font-bold">{title}</h1>
        {actions && <div className="flex gap-2">{actions}</div>}
      </div>
      {children}
    </header>
  );
}

export function Section({
  title,
  aside,
  children,
}: {
  title: string;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="mb-8">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h2 className="text-lg font-semibold">{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

/** Initial-letter avatar; color derived from the name so it's stable. */
export function Avatar({ name, size = "md" }: { name: string; size?: "sm" | "md" }) {
  const hue = [...name].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 7);
  const dims = size === "sm" ? "size-6 text-xs" : "size-9 text-sm";
  return (
    <span
      aria-hidden
      className={`inline-flex shrink-0 items-center justify-center rounded-full font-semibold text-white ${dims}`}
      style={{ backgroundColor: `hsl(${hue} 45% 42%)` }}
    >
      {name.trim().charAt(0).toUpperCase() || "?"}
    </span>
  );
}
