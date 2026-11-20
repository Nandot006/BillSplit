"use client";

import Link from "next/link";
import { useActionState } from "react";

import { Button, Field, Notice } from "@/components/ui";

import { signup } from "../actions";

export function SignupForm() {
  const [state, formAction, pending] = useActionState(signup, null);

  return (
    <form action={formAction} className="flex flex-col gap-4">
      <div>
        <h1 className="text-3xl font-bold">Create your account</h1>
        <p className="mt-1 text-sm text-ink-soft">
          Already have one?{" "}
          <Link href="/login" className="font-semibold text-ink underline underline-offset-2">
            Log in
          </Link>
        </p>
      </div>

      <Field
        label="Your name"
        hint="What your friends will see on bills."
        type="text"
        name="displayName"
        required
        autoComplete="name"
      />
      <Field label="Email" type="email" name="email" required autoComplete="email" />
      <Field
        label="Password"
        hint="At least 8 characters."
        type="password"
        name="password"
        required
        minLength={8}
        autoComplete="new-password"
      />

      {state?.error && <Notice tone="error">{state.error}</Notice>}

      <Button type="submit" busy={pending}>
        {pending ? "Creating account…" : "Create account"}
      </Button>
    </form>
  );
}
