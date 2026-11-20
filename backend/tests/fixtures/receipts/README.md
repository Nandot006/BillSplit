# Receipt regression fixtures (CLAUDE.md §9 / §11)

Each `*.json` file pins down how one receipt flows through the OCR step:

- `claude_response` — the structured output Claude returns for the receipt
  (the `ReceiptExtraction` schema in `app/services/ocr/claude.py`).
- `expected` — what the pipeline must turn that into: line items (unit price ×
  quantity), merchant, tax, tip, and the bill subtotal.

`tests/test_claude_ocr.py` runs every fixture here through
`receipt_extraction_to_ocr_result` and through the full `process_bill`
pipeline (with a fake Claude client — no network, no API key).

**The two fixtures below are synthetic** (hand-written responses, not
recorded from real photos). They cover the normalization rules: tax lines
summed, service charge → tip, quantity lines, uneven quantity lines,
discount/zero lines dropped. To add a real regression case: save the receipt
photo next to the JSON (e.g. `cafe_2026_12.jpg`), run it once against the
real API, paste the `claude_response`, and write down the `expected` values
you checked by hand against the paper receipt.
