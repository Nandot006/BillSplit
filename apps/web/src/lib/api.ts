// Every backend endpoint the web app uses, as one typed function each. All
// of them go through apiFetch (the single client module, CLAUDE.md §11);
// components import these instead of building URLs themselves.

import type {
  AddPersonToGroup,
  Bill,
  BillCreate,
  BillDetail,
  BillImageUrl,
  BillItem,
  BillItemCreate,
  BillItemUpdate,
  BillUpdate,
  Group,
  GroupDetail,
  PayerSuggestion,
  Person,
  PersonSplit,
  PersonTaxonomyScore,
  PersonUpdate,
  QuestionnaireSubmission,
  SettlementRow,
  UUID,
} from "@billsplit/shared-types";

import { ApiError, apiFetch } from "./api-client";

export const api = {
  // groups
  listGroups: () => apiFetch<Group[]>("/groups"),
  createGroup: (name: string) => apiFetch<Group>("/groups", { method: "POST", body: { name } }),
  getGroup: (groupId: UUID) => apiFetch<GroupDetail>(`/groups/${groupId}`),
  renameGroup: (groupId: UUID, name: string) =>
    apiFetch<Group>(`/groups/${groupId}`, { method: "PATCH", body: { name } }),
  deleteGroup: (groupId: UUID) => apiFetch<void>(`/groups/${groupId}`, { method: "DELETE" }),
  addPerson: (groupId: UUID, body: AddPersonToGroup) =>
    apiFetch<Person>(`/groups/${groupId}/people`, { method: "POST", body }),
  removePerson: (groupId: UUID, personId: UUID) =>
    apiFetch<void>(`/groups/${groupId}/people/${personId}`, { method: "DELETE" }),

  // people & taste profiles
  getPerson: (personId: UUID) => apiFetch<Person>(`/people/${personId}`),
  updatePerson: (personId: UUID, body: PersonUpdate) =>
    apiFetch<Person>(`/people/${personId}`, { method: "PATCH", body }),
  getTasteScores: (personId: UUID) =>
    apiFetch<PersonTaxonomyScore[]>(`/people/${personId}/taxonomy-scores`),
  submitQuestionnaire: (personId: UUID, body: QuestionnaireSubmission) =>
    apiFetch<PersonTaxonomyScore[]>(`/people/${personId}/questionnaire`, { method: "POST", body }),

  // bills
  listBills: (groupId: UUID) => apiFetch<Bill[]>(`/groups/${groupId}/bills`),
  createBill: (groupId: UUID, body: BillCreate) =>
    apiFetch<Bill>(`/groups/${groupId}/bills`, { method: "POST", body }),
  getBill: (billId: UUID) => apiFetch<BillDetail>(`/bills/${billId}`),
  updateBill: (billId: UUID, body: BillUpdate) =>
    apiFetch<Bill>(`/bills/${billId}`, { method: "PATCH", body }),
  deleteBill: (billId: UUID) => apiFetch<void>(`/bills/${billId}`, { method: "DELETE" }),
  getBillImageUrl: (billId: UUID) => apiFetch<BillImageUrl>(`/bills/${billId}/image-url`),
  switchToManualEntry: (billId: UUID) =>
    apiFetch<Bill>(`/bills/${billId}/switch-to-manual-entry`, { method: "POST" }),
  finalizeManualEntry: (billId: UUID) =>
    apiFetch<Bill>(`/bills/${billId}/finalize-manual-entry`, { method: "POST" }),
  confirmBill: (billId: UUID) => apiFetch<Bill>(`/bills/${billId}/confirm`, { method: "POST" }),
  closeBill: (billId: UUID) => apiFetch<Bill>(`/bills/${billId}/close`, { method: "POST" }),

  // participants
  addParticipant: (billId: UUID, personId: UUID) =>
    apiFetch<Bill>(`/bills/${billId}/participants`, {
      method: "POST",
      body: { person_id: personId },
    }),
  removeParticipant: (billId: UUID, personId: UUID) =>
    apiFetch<Bill>(`/bills/${billId}/participants/${personId}`, { method: "DELETE" }),

  // items
  addItem: (billId: UUID, body: BillItemCreate) =>
    apiFetch<BillItem>(`/bills/${billId}/items`, { method: "POST", body }),
  updateItem: (billId: UUID, itemId: UUID, body: BillItemUpdate) =>
    apiFetch<BillItem>(`/bills/${billId}/items/${itemId}`, { method: "PATCH", body }),
  deleteItem: (billId: UUID, itemId: UUID) =>
    apiFetch<void>(`/bills/${billId}/items/${itemId}`, { method: "DELETE" }),
  /** Who had this item. One person = a correction; several = shared evenly. */
  setItemAssignees: (billId: UUID, itemId: UUID, personIds: UUID[]) =>
    apiFetch<BillItem>(`/bills/${billId}/items/${itemId}/assignees`, {
      method: "PUT",
      body: { person_ids: personIds },
    }),

  // payer, splits, settlement
  getPayerSuggestion: (billId: UUID) =>
    apiFetch<PayerSuggestion>(`/bills/${billId}/payer-suggestion`),
  setPayer: (billId: UUID, personId: UUID | null) =>
    apiFetch<Bill>(`/bills/${billId}/payer`, { method: "PUT", body: { person_id: personId } }),
  getSplits: (billId: UUID) => apiFetch<PersonSplit[]>(`/bills/${billId}/splits`),
  getSettlement: (billId: UUID) => apiFetch<SettlementRow[]>(`/bills/${billId}/settlement`),
  setPaid: (billId: UUID, personId: UUID, isPaid: boolean) =>
    apiFetch<SettlementRow>(`/bills/${billId}/settlement/${personId}/paid`, {
      method: "PUT",
      body: { is_paid: isPaid },
    }),
};

/** A human-readable message for any error thrown by an api.* call. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const detail = (error.body as { detail?: unknown } | undefined)?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      // FastAPI validation errors: [{loc, msg, ...}]
      const first = detail[0] as { msg?: string; loc?: unknown[] };
      const field = first.loc?.[first.loc.length - 1];
      return field ? `${String(field)}: ${first.msg}` : (first.msg ?? "Invalid input.");
    }
    if (error.status === 401) return "Your session expired. Log in again.";
    if (error.status === 404) return "Not found, or you don't have access to it.";
    return `The server returned an error (${error.status}).`;
  }
  if (error instanceof TypeError) {
    // fetch() network failure. On the free Render plan the API sleeps and
    // takes up to a minute to wake, so say that rather than "failed".
    return "Couldn't reach the server. It may be waking up - try again in a moment.";
  }
  return error instanceof Error ? error.message : "Something went wrong.";
}
