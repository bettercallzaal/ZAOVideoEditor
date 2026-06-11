-- ZAO recordings review schema.
-- Designed for isolation from day one: every row carries `owner`. Today owner is
-- a trusted editor (Zaal / Iman); later, opening to a token-gated community is a
-- change to the RLS policy, not the schema.

create extension if not exists "pgcrypto";

create table if not exists projects (
  id uuid primary key default gen_random_uuid(),
  owner text not null,
  title text not null default '',
  source text,                       -- drive id or url the recording came from
  status text not null default 'new',-- new | transcribed | reviewing | rendered | published
  duration real not null default 0,
  created_at timestamptz not null default now()
);

create table if not exists transcripts (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references projects(id) on delete cascade,
  kind text not null,                -- raw | corrected | readable
  data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists cuts (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references projects(id) on delete cascade,
  start_s real not null,
  end_s real not null,
  type text not null,                -- filler | gap | falsestart | bleed
  source text not null default 'auto',
  enabled boolean not null default true,
  label text not null default ''
);

-- Captions stay editable data (never a one-way burn). Burn happens at export.
create table if not exists captions (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references projects(id) on delete cascade,
  style text not null default 'bold_pop',
  segments jsonb not null default '[]'::jsonb
);

create table if not exists jobs (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references projects(id) on delete cascade,
  stage text not null,               -- transcribe | render | clip | publish
  status text not null default 'pending',
  progress int not null default 0,
  worker_task_id text,
  created_at timestamptz not null default now()
);

create index if not exists cuts_project_idx on cuts(project_id);
create index if not exists transcripts_project_idx on transcripts(project_id);

-- Row-level security. Phase 1 (team): an editor allowlist table gates access.
-- Phase 2 (community): replace the policy body with a token-gate check.
alter table projects enable row level security;
alter table transcripts enable row level security;
alter table cuts enable row level security;
alter table captions enable row level security;
alter table jobs enable row level security;

create table if not exists editors (
  email text primary key
);

-- An authenticated user who is in the editors allowlist can read/write.
-- `auth.jwt() ->> 'email'` is the signed-in user's email.
create policy "editors manage projects" on projects
  for all using (exists (select 1 from editors e where e.email = (auth.jwt() ->> 'email')))
  with check (exists (select 1 from editors e where e.email = (auth.jwt() ->> 'email')));

create policy "editors manage transcripts" on transcripts
  for all using (exists (select 1 from editors e where e.email = (auth.jwt() ->> 'email')))
  with check (exists (select 1 from editors e where e.email = (auth.jwt() ->> 'email')));

create policy "editors manage cuts" on cuts
  for all using (exists (select 1 from editors e where e.email = (auth.jwt() ->> 'email')))
  with check (exists (select 1 from editors e where e.email = (auth.jwt() ->> 'email')));

create policy "editors manage captions" on captions
  for all using (exists (select 1 from editors e where e.email = (auth.jwt() ->> 'email')))
  with check (exists (select 1 from editors e where e.email = (auth.jwt() ->> 'email')));

create policy "editors manage jobs" on jobs
  for all using (exists (select 1 from editors e where e.email = (auth.jwt() ->> 'email')))
  with check (exists (select 1 from editors e where e.email = (auth.jwt() ->> 'email')));

-- Seed the editor allowlist (Zaal + Iman). Add rows to open access.
insert into editors (email) values ('zaal@thezao.com') on conflict do nothing;
