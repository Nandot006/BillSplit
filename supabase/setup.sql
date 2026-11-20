-- BillSplit: one-time Supabase setup for receipt photo storage.
-- Run once in the Supabase dashboard -> SQL Editor -> New query -> Run.
-- Safe to run again: the bucket insert is skipped if it exists, and the
-- policy is dropped and recreated.
--
-- Tables are NOT created here - the backend's Alembic migrations create
-- them (and switch on row level security) every time it starts on Render.

-- 1. A PRIVATE bucket for receipt photos (CLAUDE.md §9: bill images can hold
--    sensitive purchase data). Not public: nobody can open a photo by URL.
--    The web app uploads JPEGs (HEIC is converted in the browser first) of
--    at most 10 MB (design.md §14).
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('bill-images', 'bill-images', false, 10485760, array['image/jpeg', 'image/png'])
on conflict (id) do nothing;

-- 2. Logged-in users may upload only into their own folder: "<their user id>/...".
--    The backend also refuses to create a bill pointing outside the
--    uploader's folder, so one user can't read another's receipt through it.
drop policy if exists "billsplit: upload receipts to own folder" on storage.objects;
create policy "billsplit: upload receipts to own folder"
  on storage.objects for insert
  to authenticated
  with check (
    bucket_id = 'bill-images'
    and (storage.foldername(name))[1] = (select auth.uid()::text)
  );

-- No read policy on purpose: users never download photos directly. The
-- backend reads them with the service-role key (for OCR) and hands out
-- 10-minute signed links to members of the bill's group.
