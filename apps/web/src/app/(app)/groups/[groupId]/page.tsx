import { GroupScreen } from "./group-screen";

export default async function GroupPage(props: PageProps<"/groups/[groupId]">) {
  const { groupId } = await props.params;
  return <GroupScreen groupId={groupId} />;
}
