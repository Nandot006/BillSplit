// Landing point for the sign-up confirmation email. Supabase redirects here
// with a one-time `code`; exchanging it sets the session cookie, so the
// person arrives logged in. Without a code (or if it's expired/used), send
// them to log in normally - their email is confirmed either way.

import { NextResponse, type NextRequest } from "next/server";

import { createClient } from "@/lib/supabase/server";

export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get("code");
  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      return NextResponse.redirect(new URL("/dashboard", request.url));
    }
  }
  return NextResponse.redirect(new URL("/login?confirmed=1", request.url));
}
