import { redirect } from "next/navigation";

export default function Home() {
  // middleware.ts already sends unauthenticated requests to /login before
  // this renders, so anyone reaching "/" is logged in.
  redirect("/dashboard");
}
