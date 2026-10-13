# BillSplit — Product Requirements Document (PRD)

## 1. Overview

BillSplit is a mobile-first app that splits group bills automatically by reading an uploaded bill photo, predicting who ordered what (based on each person's saved preferences and the group's past bills), and letting users confirm or correct the prediction before finalizing the split.

## 2. Goals

- Eliminate manual item-by-item tallying after a group meal or purchase.
- Get smarter per group over time, so fewer corrections are needed as bill history builds up.
- Make "who owes what" clear and trackable without requiring payment integration.

## 3. Non-goals (MVP)

- No in-app payments or money movement (paid/unpaid status only).
- No multi-currency or business/expense-report use cases.
- No public or social features (friend discovery, public groups).

## 4. Target users

Any set of two or more people who split bills together — from a duo splitting a dinner once in a while, to recurring roommates, friend circles, couples, or coworkers. A "group" is simply any set of people splitting together; there is no separate flow for one-off vs. recurring — a duo is just a 2-person group.

## 5. Core user flow (MVP)

1. Create or select a group of 2 or more people; add their usual preferences.
2. Upload a photo of the bill.
3. App parses line items via OCR and predicts item-to-person assignment using preferences and history.
4. User reviews the predicted assignment and taps to correct any mismatches.
5. App calculates each person's share (items plus proportional tax/tip).
6. Breakdown is shown; each person's share can be marked paid or unpaid.
7. The confirmed (and any corrected) assignment feeds back into that group's history to improve future predictions.

## 6. Feature list — MVP

- Group and people management (add/edit/remove people, per-person preferences)
- Bill photo upload with OCR line-item extraction
- AI-predicted item assignment based on preferences and history
- Manual review and correction step
- Split calculation (items, tax, tip)
- Paid/unpaid status tracking per person
- Bill history per group, feeding the prediction model

## 7. Feature list — future / post-MVP

- Payment integration (UPI, Venmo, etc.)
- Multi-currency support
- Analytics (e.g. who owes the most over time)
- Recurring bill templates

## 8. Success metrics

- Percentage of items correctly predicted without manual correction (should trend up per group over time)
- Time from bill photo upload to finalized split
- Retention: groups that upload a second bill

## 9. Open technical questions

- OCR approach/provider
- Prediction model design and how per-group learning works
- Data storage schema for groups, people, preferences, and bill history

(See `context.md` for the broader product context these questions were first raised in.)

## 10. Risks

- OCR misreads on messy or handwritten receipts
- Cold-start problem: little to no history means poor predictions for new groups
- Privacy of stored preference and spending data
