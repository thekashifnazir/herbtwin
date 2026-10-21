-- D2: re-photo reminders (spec section 7). One row per ticked answer; the due and last
-- days are worked out when the box is ticked. Goes with the answer, the plant and the account.
create table public.reminders (
    answer_id uuid primary key references public.answers (id) on delete cascade,
    user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
    plant_id uuid not null references public.plants (id) on delete cascade,
    plant_name text not null check (char_length(plant_name) between 1 and 60),
    action text not null check (char_length(action) between 1 and 40),
    taken_at timestamptz not null,
    due_on date not null,
    last_on date not null check (last_on >= due_on),
    sent_at timestamptz,
    off_at timestamptz,
    off_reason text check (off_reason in ('unsubscribed', 'followed_up', 'too_late', 'no_account')),
    created_at timestamptz not null default now()
);
create index reminders_due on public.reminders (due_on) where sent_at is null and off_at is null;

alter table public.reminders enable row level security;

-- the answer must be the person's own and on that plant (a foreign key ignores RLS). Name
-- the outer row's columns: inside the subquery a bare plant_id would mean a.plant_id
create policy "read own reminders" on public.reminders for select to authenticated
    using (user_id = auth.uid());
create policy "tick own answers" on public.reminders for insert to authenticated
    with check (
        user_id = auth.uid()
        and exists (select 1 from public.answers a
                    where a.id = reminders.answer_id and a.user_id = auth.uid()
                      and a.plant_id = reminders.plant_id)
    );
create policy "re-tick unsent" on public.reminders for update to authenticated
    using (user_id = auth.uid() and sent_at is null)
    with check (
        user_id = auth.uid()
        and exists (select 1 from public.answers a
                    where a.id = reminders.answer_id and a.user_id = auth.uid()
                      and a.plant_id = reminders.plant_id)
    );
-- one email per answer: a sent reminder stays, so unticking and ticking cannot resend
create policy "untick unsent" on public.reminders for delete to authenticated
    using (user_id = auth.uid() and sent_at is null);

-- the person writes what to send and when; only the job marks sent or off
grant select, delete on public.reminders to authenticated;
grant insert (answer_id, plant_id, plant_name, action, taken_at, due_on, last_on)
    on public.reminders to authenticated;
grant update (answer_id, plant_id, plant_name, action, taken_at, due_on, last_on)
    on public.reminders to authenticated;
revoke all on public.reminders from anon;

-- the daily job (python -m herbtwin.reminders) works across people with the secret key:
-- read the reminder, see whether a later photo exists, mark sent or off. Nothing else.
grant select (answer_id, user_id, plant_id, plant_name, action, taken_at, due_on, last_on,
              sent_at, off_at) on public.reminders to service_role;
grant update (sent_at, off_at, off_reason) on public.reminders to service_role;
grant select (plant_id) on public.answers to service_role;
