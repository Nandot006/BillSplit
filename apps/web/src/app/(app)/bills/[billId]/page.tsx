import { BillScreen } from "./bill-screen";

export default async function BillPage(props: PageProps<"/bills/[billId]">) {
  const { billId } = await props.params;
  return <BillScreen billId={billId} />;
}
