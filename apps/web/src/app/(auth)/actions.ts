"use server";

import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";

export type AuthActionState = { error: string } | null;

/**
 * Only same-site paths are allowed as a post-login destination. The `next`
 * value comes from the URL, so without this check a crafted link could
 * bounce someone to another site straight after they log in.
 */
function safeNextPath(next: FormDataEntryValue | null): string {
  const value = String(next ?? "");
  return value.startsWith("/") && !value.startsWith("//") && !value.startsWith("/\\")
    ? value
    : "/dashboard";
}

export async function login(
  _prevState: AuthActionState,
  formData: FormData,
): Promise<AuthActionState> {
  const email = String(formData.get("email") ?? "");
  const password = String(formData.get("password") ?? "");

  const supabase = await createClient();
  const { error } = await supabase.auth.signInWithPassword({ email, password });

  if (error) {
    return { error: error.message };
  }

  redirect(safeNextPath(formData.get("next")));
}

export async function signup(
  _prevState: AuthActionState,
  formData: FormData,
): Promise<AuthActionState> {
  const email = String(formData.get("email") ?? "");
  const password = String(formData.get("password") ?? "");
  const displayName = String(formData.get("displayName") ?? "").trim();

  const origin = (await headers()).get("origin") ?? "";
  const supabase = await createClient();
  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: {
      data: { display_name: displayName },
      // The confirmation email links back here; /auth/callback swaps the
      // code for a session so people land logged in.
      emailRedirectTo: origin ? `${origin}/auth/callback` : undefined,
    },
  });

  if (error) {
    return { error: error.message };
  }

  // If the Supabase project has email confirmation turned off, signUp
  // returns a live session straight away - go in. Otherwise (the default),
  // ask them to confirm first.
  if (data.session) {
    redirect("/dashboard");
  }
  redirect("/login?confirm=1");
}

export async function logout(): Promise<void> {
  const supabase = await createClient();
  await supabase.auth.signOut();
  redirect("/login");
}
