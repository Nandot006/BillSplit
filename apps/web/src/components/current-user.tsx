"use client";

import { createContext, useContext, type ReactNode } from "react";

export interface CurrentUser {
  id: string;
  email: string | null;
}

const CurrentUserContext = createContext<CurrentUser | null>(null);

export function CurrentUserProvider({
  user,
  children,
}: {
  user: CurrentUser;
  children: ReactNode;
}) {
  return <CurrentUserContext.Provider value={user}>{children}</CurrentUserContext.Provider>;
}

/** The logged-in Supabase user. Only usable under the (app) layout. */
export function useCurrentUser(): CurrentUser {
  const user = useContext(CurrentUserContext);
  if (!user) throw new Error("useCurrentUser must be used inside the logged-in app layout.");
  return user;
}
