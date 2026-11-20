import { LoginForm } from "./login-form";

export default async function LoginPage(props: PageProps<"/login">) {
  const params = await props.searchParams;
  const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);
  return (
    <LoginForm
      next={one(params.next) ?? "/dashboard"}
      confirmSent={one(params.confirm) === "1"}
      confirmed={one(params.confirmed) === "1"}
    />
  );
}
