// Session refresh + route protection, called from the top-level
// `proxy.ts` on every request (Next.js 16 renamed the `middleware.ts`
// convention to `proxy.ts` - same mechanism). This is the "middleware.ts
// that redirects unauthenticated requests away from protected routes before
// render" from design.md §14.
//
// Protected routes are everything except the auth pages and Next.js
// internals/static assets. New top-level routes are protected by default -
// add them to PUBLIC_PATHS below if a future block needs a public page.

import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

import { env } from "@/lib/env";

const PUBLIC_PATHS = ["/login", "/signup"];

export async function updateSession(request: NextRequest) {
  let response = NextResponse.next({ request });

  const supabase = createServerClient(env.supabaseUrl, env.supabaseAnonKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet) {
        for (const { name, value } of cookiesToSet) {
          request.cookies.set(name, value);
        }
        response = NextResponse.next({ request });
        for (const { name, value, options } of cookiesToSet) {
          response.cookies.set(name, value, options);
        }
      },
    },
  });

  // Do not add logic between createServerClient and getUser() - it must run
  // on every request so a refreshed token actually gets persisted, and
  // getUser() (not getSession()) is required here because it revalidates
  // the token against Supabase Auth rather than trusting the cookie as-is.
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const isPublicPath = PUBLIC_PATHS.some((path) => request.nextUrl.pathname.startsWith(path));

  if (!user && !isPublicPath) {
    const redirectUrl = new URL("/login", request.url);
    redirectUrl.searchParams.set("next", request.nextUrl.pathname);
    return NextResponse.redirect(redirectUrl);
  }

  if (user && isPublicPath) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  return response;
}
