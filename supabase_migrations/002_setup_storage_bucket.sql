-- =====================================================
-- STORAGE BUCKET SETUP - RESUMES
-- This migration configures the 'resumes' storage bucket
-- Run this in Supabase SQL Editor to fix bucket access
-- =====================================================

-- Note: Storage buckets in Supabase are created through the UI, not SQL
-- But RLS policies for storage can be set via SQL

-- Set RLS on the storage bucket to allow downloads for authenticated users
insert into storage.buckets (id, name, public)
values ('resumes', 'resumes', true)
on conflict (id) do update set public = true;

-- Create RLS policy to allow authenticated users to upload
create policy "Authenticated users can upload resumes"
on storage.objects for insert
to authenticated
with check (
  bucket_id = 'resumes'
);

-- Create RLS policy to allow authenticated users to download their own resumes
create policy "Users can download their own resumes"
on storage.objects for select
to authenticated
using (
  bucket_id = 'resumes'
  and (storage.foldername(name))[1] = auth.uid()::text
);

-- Create RLS policy to allow public access to resumes (since they're using public URLs)
create policy "Public can download resumes"
on storage.objects for select
with (public)
using (bucket_id = 'resumes');

-- Create policy to allow deletion of own resumes
create policy "Users can delete their own resumes"
on storage.objects for delete
to authenticated
using (
  bucket_id = 'resumes'
  and (storage.foldername(name))[1] = auth.uid()::text
);
