-- Plant history (phase B3, spec section 5). Row-level security is the guard: every
-- call from the app runs as the signed-in person. "Expose new tables" is off on the
-- hosted project, so each table is granted to authenticated explicitly; anon gets none.

create or replace function public.account_exists() returns boolean
    language sql stable security definer set search_path = ''
    as $$ select exists (select 1 from auth.users where id = auth.uid()) $$;
revoke all on function public.account_exists() from public, anon;
grant execute on function public.account_exists() to authenticated;

create table public.plants (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
    name text not null check (char_length(name) between 1 and 60),
    species text not null default '',
    genus text not null default '',
    place_lat double precision,
    place_lon double precision,
    created_at timestamptz not null default now()
);

create table public.answers (
    id uuid primary key,
    user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
    plant_id uuid not null references public.plants (id) on delete cascade,
    taken_at timestamptz not null,
    created_at timestamptz not null default now(),
    photo_path text,
    observation jsonb not null,
    evidence jsonb not null,
    answer jsonb,
    told jsonb
);
create index answers_plant_taken on public.answers (plant_id, taken_at desc);

create table public.chat_messages (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
    answer_id uuid not null references public.answers (id) on delete cascade,
    role text not null check (role in ('user', 'assistant')),
    content text not null check (char_length(content) <= 4000),
    tools jsonb,
    created_at timestamptz not null default now()
);

alter table public.plants enable row level security;
alter table public.answers enable row level security;
alter table public.chat_messages enable row level security;

create policy "own plants" on public.plants for all to authenticated
    using (user_id = auth.uid()) with check (user_id = auth.uid());

-- a foreign key check ignores row-level security, so an answer must also point at a
-- plant of the same person, or B could hang rows (and a cascade) off A's plant
create policy "own answers" on public.answers for all to authenticated
    using (user_id = auth.uid())
    with check (
        user_id = auth.uid()
        and exists (select 1 from public.plants p where p.id = plant_id and p.user_id = auth.uid())
    );

create policy "own chat" on public.chat_messages for all to authenticated
    using (user_id = auth.uid())
    with check (
        user_id = auth.uid()
        and exists (select 1 from public.answers a where a.id = answer_id and a.user_id = auth.uid())
    );

grant select, insert, update, delete on public.plants to authenticated;
grant select, insert, update, delete on public.answers to authenticated;
grant select, insert, delete on public.chat_messages to authenticated;
revoke all on public.plants, public.answers, public.chat_messages from anon;

-- photos only (the app stores every photo as JPEG), bounded: a signed-in person holds a
-- token and could otherwise fill the free tier directly
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
    values ('photos', 'photos', false, 15728640, '{image/jpeg}')
    on conflict (id) do update
    set file_size_limit = excluded.file_size_limit, allowed_mime_types = excluded.allowed_mime_types;

create policy "own photos: read" on storage.objects for select to authenticated
    using (bucket_id = 'photos' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "own photos: insert" on storage.objects for insert to authenticated
    with check (bucket_id = 'photos' and (storage.foldername(name))[1] = auth.uid()::text
                and public.account_exists());
create policy "own photos: update" on storage.objects for update to authenticated
    using (bucket_id = 'photos' and (storage.foldername(name))[1] = auth.uid()::text)
    with check (bucket_id = 'photos' and (storage.foldername(name))[1] = auth.uid()::text
                and public.account_exists());
create policy "own photos: delete" on storage.objects for delete to authenticated
    using (bucket_id = 'photos' and (storage.foldername(name))[1] = auth.uid()::text);
