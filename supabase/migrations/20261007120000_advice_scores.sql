-- C2: how the earlier answer's main action turned out on the next photo (spec section 4).
-- Owner-only like plants and answers; goes with the account, the plant and either answer.
create table public.advice_scores (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
    plant_id uuid not null references public.plants (id) on delete cascade,
    earlier_answer_id uuid not null references public.answers (id) on delete cascade,
    later_answer_id uuid not null references public.answers (id) on delete cascade,
    action text not null,
    prediction jsonb not null,
    signal text not null check (signal in ('posture', 'tissue', 'colour')),
    did_it text not null check (did_it in ('yes', 'partly', 'no', 'skip')),
    result text not null check (
        result in ('improved', 'no_clear_change', 'worse', 'cant_tell', 'not_done', 'not_scored_yet')
    ),
    reason text,
    comparison jsonb,  -- the four looks and their raw replies
    prompt_version text,
    model text,
    scored_at timestamptz not null default now(),
    unique (earlier_answer_id, later_answer_id)
);
create index advice_scores_plant on public.advice_scores (plant_id, scored_at desc);

alter table public.advice_scores enable row level security;

-- a foreign key check ignores row-level security: both answers and the plant must be the
-- same person's, and both answers on that plant
create policy "own scores" on public.advice_scores for all to authenticated
    using (user_id = auth.uid())
    with check (
        user_id = auth.uid()
        and exists (select 1 from public.plants p where p.id = plant_id and p.user_id = auth.uid())
        and exists (
            select 1 from public.answers a
            where a.id = earlier_answer_id and a.user_id = auth.uid()
              and a.plant_id = advice_scores.plant_id
        )
        and exists (
            select 1 from public.answers a
            where a.id = later_answer_id and a.user_id = auth.uid()
              and a.plant_id = advice_scores.plant_id
        )
    );

grant select, insert, delete on public.advice_scores to authenticated;
revoke all on public.advice_scores from anon;
