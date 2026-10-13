# BillSplit — Project Context

## What this is

BillSplit is a bill-splitting app. Instead of manually working out who owes what, a group uploads a photo of the bill and the app figures out a fair split on its own.

## Core idea

1. **Groups** — Users create a group of people they regularly split bills with (roommates, friends, family, coworkers).
2. **Preferences** — Each person in the group can have their usual preferences recorded (e.g. what they typically order, dietary habits, items they never share).
3. **Bill upload** — A photo of the bill/receipt is uploaded.
4. **Prediction** — A model reads the bill image and predicts which items each person most likely had, based on their stored preferences and the group's activity history.
5. **Learning from history** — Past bills and how they were actually split feed back into the model, so predictions get more accurate for that group over time.
6. **Accurate split** — The app outputs a per-person breakdown (who owes what, including tax/tip handling) based on the predicted assignment of items.

## Status

Early stage — no code in this folder yet. This file is a working reference for what the product is meant to do, to anchor future planning, design, and implementation work.

## Open questions / to define later

- Tech stack (mobile app, web app, or both)
- How bill image parsing/OCR will work
- How the prediction model is trained and how it improves per group
- Data storage for groups, people, preferences, and bill history
- How manual corrections/overrides feed back into learning
