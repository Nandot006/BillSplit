// Component tests for the two screens CLAUDE.md §11 names as having
// non-trivial logic: the itemized-breakdown editing UI and the settlement UI.

import type { BillDetail, Person, SettlementRow } from "@billsplit/shared-types";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ReceiptSlip } from "./receipt-slip";
import { SettlementPanel } from "./settlement-panel";

const person = (id: string, name: string): Person => ({
  id,
  group_id: "g",
  supabase_user_id: null,
  display_name: name,
  free_text_preferences: null,
  created_at: "",
});
const people = [person("a", "Asha"), person("b", "Bala"), person("c", "Chitra")];

const bill = (overrides: Partial<BillDetail> = {}): BillDetail => ({
  id: "bill",
  group_id: "g",
  image_storage_path: null,
  merchant_name: "Cafe",
  bill_date: null,
  subtotal: "290.00",
  tax_total: "14.50",
  tip_total: "0.00",
  grand_total: "304.50",
  status: "needs_review",
  payer_person_id: null,
  participant_person_ids: ["a", "b", "c"],
  created_at: "",
  closed_at: null,
  items: [
    {
      id: "dosa",
      bill_id: "bill",
      raw_ocr_text: null,
      parsed_name: "Masala Dosa",
      price: "90.00",
      quantity: 1,
      base_type: "entree",
      flavor_tags: [],
      dietary_flags: [],
      assignments: [
        { id: "x", person_id: "a", is_predicted: true, confidence_score: 0.2, share_fraction: 1 },
      ],
      created_at: "",
    },
    {
      id: "coffee",
      bill_id: "bill",
      raw_ocr_text: null,
      parsed_name: "Filter Coffee",
      price: "40.00",
      quantity: 5,
      base_type: "drink-non-alcoholic",
      flavor_tags: [],
      dietary_flags: [],
      assignments: [],
      created_at: "",
    },
  ],
  ...overrides,
});

describe("ReceiptSlip (itemized breakdown)", () => {
  it("shows line totals and flags unsure and unassigned lines", () => {
    render(<ReceiptSlip bill={bill()} people={people} participants={people} actions={{}} />);
    const coffee = screen.getByText("Filter Coffee").closest("li")!;
    expect(within(coffee).getByText("200.00")).toBeInTheDocument(); // 5 × 40.00
    expect(within(coffee).getByText(/Nobody yet/)).toBeInTheDocument();
    const dosa = screen.getByText("Masala Dosa").closest("li")!;
    expect(within(dosa).getByText(/unsure - check this/)).toBeInTheDocument();
    expect(screen.getByText("304.50")).toBeInTheDocument();
    // read-only: no edit controls
    expect(screen.queryByRole("button", { name: "Change" })).not.toBeInTheDocument();
  });

  it("drops the 'check this' flag once the bill is confirmed", () => {
    render(
      <ReceiptSlip
        bill={bill({ status: "closed" })}
        people={people}
        participants={people}
        actions={{}}
      />,
    );
    expect(screen.queryByText(/check this/)).not.toBeInTheDocument();
    expect(screen.getByText("guessed")).toBeInTheDocument();
  });

  it("tapping one name reassigns the item to that person", async () => {
    const setAssignees = vi.fn().mockResolvedValue(undefined);
    render(
      <ReceiptSlip
        bill={bill()}
        people={people}
        participants={people}
        actions={{ setAssignees }}
      />,
    );
    const dosa = screen.getByText("Masala Dosa").closest("li")!;
    await userEvent.click(within(dosa).getByRole("button", { name: "Change" }));
    await userEvent.click(within(dosa).getByRole("button", { name: /Bala/ }));
    expect(setAssignees).toHaveBeenCalledWith(expect.objectContaining({ id: "dosa" }), ["b"]);
  });

  it("shared mode splits an item between several people", async () => {
    const setAssignees = vi.fn().mockResolvedValue(undefined);
    render(
      <ReceiptSlip
        bill={bill()}
        people={people}
        participants={people}
        actions={{ setAssignees }}
      />,
    );
    const coffee = screen.getByText("Filter Coffee").closest("li")!;
    await userEvent.click(within(coffee).getByRole("button", { name: "Choose who" }));
    await userEvent.click(within(coffee).getByRole("checkbox", { name: "Shared" }));
    await userEvent.click(within(coffee).getByRole("button", { name: /Asha/ }));
    await userEvent.click(within(coffee).getByRole("button", { name: /Chitra/ }));
    await userEvent.click(within(coffee).getByRole("button", { name: "Split between 2" }));
    expect(setAssignees).toHaveBeenCalledWith(expect.objectContaining({ id: "coffee" }), [
      "a",
      "c",
    ]);
  });

  it("only offers participants as assignees", async () => {
    render(
      <ReceiptSlip
        bill={bill()}
        people={people}
        participants={people.slice(0, 2)}
        actions={{ setAssignees: vi.fn() }}
      />,
    );
    const dosa = screen.getByText("Masala Dosa").closest("li")!;
    await userEvent.click(within(dosa).getByRole("button", { name: "Change" }));
    expect(within(dosa).queryByRole("button", { name: /Chitra/ })).not.toBeInTheDocument();
  });

  it("removing a line asks first", async () => {
    const deleteItem = vi.fn().mockResolvedValue(undefined);
    render(
      <ReceiptSlip bill={bill()} people={people} participants={people} actions={{ deleteItem }} />,
    );
    const dosa = screen.getByText("Masala Dosa").closest("li")!;
    await userEvent.click(within(dosa).getByRole("button", { name: "Remove" }));
    expect(deleteItem).not.toHaveBeenCalled();
    await userEvent.click(within(dosa).getByRole("button", { name: "Yes, remove line" }));
    expect(deleteItem).toHaveBeenCalledTimes(1);
  });
});

const settle = (personId: string, name: string, total: string, paid: boolean): SettlementRow => ({
  id: personId,
  bill_id: "bill",
  person_id: personId,
  display_name: name,
  item_subtotal_share: total,
  tax_share: "0.00",
  tip_share: "0.00",
  total_owed: total,
  is_paid: paid,
  paid_at: null,
});

describe("SettlementPanel", () => {
  const handlers = () => ({
    onSetPayer: vi.fn().mockResolvedValue(undefined),
    onSetPaid: vi.fn().mockResolvedValue(undefined),
    onClose: vi.fn().mockResolvedValue(undefined),
  });

  it("prefills the suggested payer and saves it", async () => {
    const h = handlers();
    render(
      <SettlementPanel
        bill={bill({ status: "open" })}
        people={people}
        settlement={[settle("a", "Asha", "100.00", false), settle("b", "Bala", "50.00", false)]}
        suggestion={{ person_id: "b", display_name: "Bala", payment_count: 0, last_paid_at: null }}
        {...h}
      />,
    );
    expect(screen.getByLabelText("Who paid the bill?")).toHaveValue("b");
    expect(screen.getByRole("button", { name: "Close bill" })).toBeDisabled();
    expect(screen.getByText("Choose who paid first.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Set payer" }));
    expect(h.onSetPayer).toHaveBeenCalledWith("b");
  });

  it("lets the payer mark others paid, never themselves, then close", async () => {
    const h = handlers();
    const { rerender } = render(
      <SettlementPanel
        bill={bill({ status: "open", payer_person_id: "a" })}
        people={people}
        settlement={[settle("a", "Asha", "100.00", false), settle("b", "Bala", "50.00", false)]}
        suggestion={null}
        {...h}
      />,
    );
    const asha = screen.getByText("Asha", { selector: ".truncate" }).closest("li")!;
    expect(within(asha).queryByRole("button", { name: "Mark paid" })).not.toBeInTheDocument();
    expect(screen.getByText(/Still owed to Asha/)).toHaveTextContent("50.00");
    expect(screen.getByRole("button", { name: "Close bill" })).toBeDisabled();

    const bala = screen.getByText("Bala", { selector: ".truncate" }).closest("li")!;
    await userEvent.click(within(bala).getByRole("button", { name: "Mark paid" }));
    expect(h.onSetPaid).toHaveBeenCalledWith("b", true);

    rerender(
      <SettlementPanel
        bill={bill({ status: "open", payer_person_id: "a" })}
        people={people}
        settlement={[settle("a", "Asha", "100.00", false), settle("b", "Bala", "50.00", true)]}
        suggestion={null}
        {...h}
      />,
    );
    expect(screen.getByText("PAID")).toBeInTheDocument();
    const close = screen.getByRole("button", { name: "Close bill" });
    expect(close).toBeEnabled();
    await userEvent.click(close);
    expect(h.onClose).toHaveBeenCalledTimes(1);
  });

  it("is read-only once closed", () => {
    render(
      <SettlementPanel
        bill={bill({ status: "closed", payer_person_id: "a" })}
        people={people}
        settlement={[settle("a", "Asha", "100.00", false), settle("b", "Bala", "50.00", true)]}
        suggestion={null}
        {...handlers()}
      />,
    );
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Who paid the bill?")).not.toBeInTheDocument();
    expect(screen.getByText("PAID")).toBeInTheDocument();
  });
});
