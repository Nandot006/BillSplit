import type { Metadata } from "next";

import { NewBillScreen } from "./new-bill-screen";

export const metadata: Metadata = { title: "New bill · BillSplit" };

export default async function NewBillPage(props: PageProps<"/groups/[groupId]/bills/new">) {
  const { groupId } = await props.params;
  return <NewBillScreen groupId={groupId} />;
}
