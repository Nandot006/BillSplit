"use client";

// A destructive action that asks once, inline, instead of a browser dialog:
// first tap shows "Yes, <action>" / "Cancel" in place.

import { useState } from "react";

import { Button } from "./ui";

export function ConfirmButton({
  label,
  confirmLabel,
  onConfirm,
  busy = false,
  variant = "danger",
}: {
  label: string;
  confirmLabel: string;
  onConfirm: () => void | Promise<void>;
  busy?: boolean;
  variant?: "danger" | "quiet";
}) {
  const [asking, setAsking] = useState(false);
  if (!asking) {
    return (
      <Button type="button" variant={variant} onClick={() => setAsking(true)} busy={busy}>
        {label}
      </Button>
    );
  }
  return (
    <span className="inline-flex items-center gap-2">
      <Button
        type="button"
        variant="danger"
        busy={busy}
        onClick={async () => {
          await onConfirm();
          setAsking(false);
        }}
      >
        {confirmLabel}
      </Button>
      <Button type="button" variant="quiet" onClick={() => setAsking(false)}>
        Cancel
      </Button>
    </span>
  );
}
