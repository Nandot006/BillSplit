"use client";

import Link from "next/link";
import { useActionState } from "react";

import { Button, Field, Notice } from "@/components/ui";

import { login } from "../actions";

export function LoginForm({
  next,
  confirmSent,
  confirmed,
}: {
  next: string;
  confirmSent: boolean;
  confirmed: boolean;
}) {
  const [state, formAction, pending] = useActionState(login, null);

  return (
    <form action={formAction} className="flex flex-col gap-4">
      <div>
        <h1 className="text-3xl font-bold">Log in</h1>
        <p className="mt-1 text-sm text-ink-soft">
          New here?{" "}
          <Link href="/signup" className="font-semibold text-ink underline underline-offset-2">
            Create an account
          </Link>
        </p>
      </div>

      <input type="hidden" name="next" value={next} />

      {confirmSent && (
        <Notice tone="success">Check your email and confirm your address, then log in here.</Notice>
      )}
      {confirmed && <Notice tone="success">Email confirmed. Log in to continue.</Notice>}

      <Field label="Email" type="email" name="email" required autoComplete="email" />
      <Field
        label="Password"
        type="password"
        name="password"
        required
        autoComplete="current-password"
      />

      {state?.error && <Notice tone="error">{state.error}</Notice>}

      <Button type="submit" busy={pending}>
        {pending ? "Logging in…" : "Log in"}
      </Button>
    </form>
  );
}
