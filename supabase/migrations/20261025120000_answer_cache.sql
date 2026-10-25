-- Answers kept for 24 hours (25 Oct, Kash), so an answer link survives a deploy or a restart
-- and a signed-out person can still ask about it or make it surer. Written and read only by
-- the server with the secret key, through the functions below; no person can read or change
-- a row. No photo is kept here: `record` and `reading` hold what the AI read from the photo
-- (text and numbers), with the place already rounded to about 1 km. The browser's claim key
-- is kept only as its SHA-256. Reads never see a row past 24 hours; the daily job
-- (purge_answer_cache) deletes them.
create table public.answer_cache (
    id text primary key check (length(id) between 8 and 64),
    owner uuid references auth.users (id) on delete cascade,  -- null: signed out
    claim_hash text check (claim_hash is null or claim_hash ~ '^[0-9a-f]{64}$'),
    record jsonb not null,         -- the answer as it stands, after any refine
    reading jsonb,                 -- evidence for refines; null when the run stopped early
    first_headline text,           -- the photo-only answer, for "what changed"
    last_decline integer,          -- days since the plant last declined, for the asks
    chat jsonb not null default '[]'::jsonb check (jsonb_typeof(chat) = 'array'),
    created_at timestamptz not null default now()
);
create index answer_cache_created on public.answer_cache (created_at);

alter table public.answer_cache enable row level security;
revoke all on public.answer_cache from anon, authenticated;
grant select, insert, update, delete on public.answer_cache to service_role;

-- Keep a signed-out answer for `p_owner`, once: only while it is unowned, under 24 hours old
-- and made for the browser whose claim key hashes to `p_claim_hash`. True when it was kept.
create function public.claim_answer(p_id text, p_claim_hash text, p_owner uuid)
returns boolean language sql set search_path = '' as $$
    with kept as (
        update public.answer_cache set owner = p_owner
        where id = p_id and owner is null and claim_hash = p_claim_hash
          and created_at > now() - interval '24 hours'
        returning 1
    )
    select exists (select 1 from kept);
$$;

-- Add one chat message to an answer still under 24 hours old, in one statement, so two
-- messages at once never lose one. True when it was added.
create function public.add_answer_chat(p_id text, p_msg jsonb)
returns boolean language sql set search_path = '' as $$
    with added as (
        update public.answer_cache set chat = chat || jsonb_build_array(p_msg)
        where id = p_id and created_at > now() - interval '24 hours'
        returning 1
    )
    select exists (select 1 from added);
$$;

-- Delete every answer older than 24 hours; returns how many went. The daily job calls it.
create function public.purge_answer_cache()
returns integer language sql set search_path = '' as $$
    with gone as (
        delete from public.answer_cache where created_at < now() - interval '24 hours'
        returning 1
    )
    select count(*)::integer from gone;
$$;

revoke all on function public.claim_answer(text, text, uuid),
    public.add_answer_chat(text, jsonb), public.purge_answer_cache()
    from public, anon, authenticated;
grant execute on function public.claim_answer(text, text, uuid),
    public.add_answer_chat(text, jsonb), public.purge_answer_cache() to service_role;
