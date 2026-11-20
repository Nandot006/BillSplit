// Money helpers. The API sends amounts as decimal strings ("12.50"). We do
// arithmetic in integer cents so nothing drifts by a paisa/cent, and never
// add a currency symbol: v1 is single-currency and the currency isn't
// recorded anywhere (multi-currency is a v1 non-goal, CLAUDE.md §1).

export function toCents(value: string | number | null | undefined): number {
  if (value === null || value === undefined || value === "") return 0;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? Math.round(n * 100) : 0;
}

export function formatCents(cents: number): string {
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  const whole = Math.floor(abs / 100).toLocaleString();
  return `${sign}${whole}.${String(abs % 100).padStart(2, "0")}`;
}

export function formatMoney(value: string | number | null | undefined): string {
  return formatCents(toCents(value));
}

/**
 * Validates user-typed money ("12", "12.5", "12.50") and normalizes it to
 * the API's "12.50" form. Returns null if it isn't a non-negative amount
 * with at most two decimal places.
 */
export function parseMoneyInput(raw: string): string | null {
  const trimmed = raw.trim().replace(/,/g, "");
  if (!/^\d+(\.\d{0,2})?$/.test(trimmed)) return null;
  return (toCents(trimmed) / 100).toFixed(2);
}
