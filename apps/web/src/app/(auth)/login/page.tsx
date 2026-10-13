import { LoginForm } from "./login-form";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string; confirm?: string }>;
}) {
  const params = await searchParams;
  return <LoginForm next={params.next ?? "/dashboard"} confirmed={params.confirm === "1"} />;
}
