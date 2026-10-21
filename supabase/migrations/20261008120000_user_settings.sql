-- C3: the person's choices (spec section 5). One row per person, owner-only like plants;
-- goes with the account. No row reads as the defaults: not sharing, never asked.
create table public.user_settings (
    user_id uuid primary key default auth.uid() references auth.users (id) on delete cascade,
    share_scored_pairs boolean not null default false,
    asked_at timestamptz
);

alter table public.user_settings enable row level security;

create policy "own settings" on public.user_settings for all to authenticated
    using (user_id = auth.uid()) with check (user_id = auth.uid());

-- an upsert (resolution=merge-duplicates) needs insert and update; delete is the cascade
grant select, insert, update on public.user_settings to authenticated;
revoke all on public.user_settings from anon;

-- the export of opted-in people's scored pairs (scripts/export_scored_pairs.py) reads
-- across people with the admin key. "Expose new tables" is off, so even service_role
-- needs a grant: read only, and only the columns the export reads (never typed questions,
-- advice text or the model's reasons, should the server's secret key leak).
grant select (user_id, share_scored_pairs) on public.user_settings to service_role;
grant select (id, user_id, plant_id, earlier_answer_id, later_answer_id, action, prediction,
              signal, did_it, result) on public.advice_scores to service_role;
grant select (id, species, place_lat, place_lon) on public.plants to service_role;
grant select (id, taken_at, observation) on public.answers to service_role;
