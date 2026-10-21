-- Spot answers ("What can I grow here?", spot spec D70). Owner-only like plants and
-- answers; goes with the account. The place is the app's rounded location (2 decimal
-- places, about 1 km): the checks refuse anything finer, so raw GPS can never be stored.
create table public.spots (
    id uuid primary key,
    user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
    taken_at timestamptz not null,
    place_lat double precision
        check (place_lat between -90 and 90 and place_lat = round(place_lat::numeric, 2)::double precision),
    place_lon double precision
        check (place_lon between -180 and 180 and place_lon = round(place_lon::numeric, 2)::double precision),
    aspect jsonb,
    spot jsonb not null,
    grow jsonb,
    created_at timestamptz not null default now()
);
create index spots_place on public.spots (user_id, place_lat, place_lon, taken_at desc);

alter table public.spots enable row level security;

create policy "own spots" on public.spots for all to authenticated
    using (user_id = auth.uid()) with check (user_id = auth.uid());

grant select, insert, update, delete on public.spots to authenticated;
revoke all on public.spots from anon;
