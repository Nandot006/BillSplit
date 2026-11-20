import type { Metadata } from "next";

import { GroupsHome } from "./groups-home";

export const metadata: Metadata = { title: "Your groups · BillSplit" };

export default function DashboardPage() {
  return <GroupsHome />;
}
