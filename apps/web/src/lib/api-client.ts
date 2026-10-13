// The single typed API client module for the web app (CLAUDE.md SS11: "API
// calls go through a single typed client module per app, not scattered
// fetch calls"). Every request to the FastAPI backend goes through
// `apiFetch` below rather than a bare `fetch()` call somewhere in a
// component.
//
// Auth: the backend expects `Authorization: Bearer <supabase-jwt>` on every
// authenticated route (see backend/app/api/deps.py). In a Client Component,
// apiFetch fetches the current session token itself via the browser
// Supabase client. Server Components/Actions don't have access to that
// client, so they must pass the token explicitly as `accessToken` (get it
// from `(await createClient()).auth.getUser()` / `getSession()` in
// `@/lib/supabase/server`).

import { env } from "./env";

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown) {
    super(`API request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export type ApiFetchOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
  /** Required when calling from a Server Component/Action; see module docs above. */
  accessToken?: string;
};

async function getBrowserAccessToken(): Promise<string | undefined> {
  // Dynamic import so this branch (and its cookie/localStorage access) never
  // gets pulled into a server bundle - only reached when `window` exists.
  const { createClient } = await import("./supabase/client");
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return session?.access_token;
}

/**
 * Typed wrapper around fetch for calls to the FastAPI backend.
 *
 * @param path  Path relative to the API base, e.g. "/groups" or "/bills/123".
 * @param options  Standard fetch options; `body`, if present, is JSON-encoded.
 */
export async function apiFetch<TResponse>(
  path: string,
  options: ApiFetchOptions = {},
): Promise<TResponse> {
  const { body, headers, accessToken, ...rest } = options;

  const token = accessToken ?? (typeof window !== "undefined" ? await getBrowserAccessToken() : undefined);

  const response = await fetch(`${env.apiUrl}${path}`, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => undefined);
    throw new ApiError(response.status, errorBody);
  }

  // 204 No Content etc. - nothing to parse.
  if (response.status === 204) {
    return undefined as TResponse;
  }

  return (await response.json()) as TResponse;
}
