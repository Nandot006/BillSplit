import { ProfileScreen } from "./profile-screen";

export default async function PersonPage(props: PageProps<"/people/[personId]">) {
  const { personId } = await props.params;
  return <ProfileScreen personId={personId} />;
}
