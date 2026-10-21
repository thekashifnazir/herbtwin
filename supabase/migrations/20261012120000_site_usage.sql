-- D1b: the live site's caps and budget (spec section 5). Written only by the server with
-- the secret key, through count_photo_read; no person can read or change them.
create table public.site_usage_days (day date primary key, reads integer not null default 0);
create table public.site_usage_visitors (
    day date not null, visitor text not null, reads integer not null default 0,
    primary key (day, visitor)
);
create table public.site_budget (
    id boolean primary key default true check (id), spent_usd numeric not null default 0,
    warned_at timestamptz
);
insert into public.site_budget default values;
alter table public.site_usage_days enable row level security;
alter table public.site_usage_visitors enable row level security;
alter table public.site_budget enable row level security;
revoke all on public.site_usage_days, public.site_usage_visitors, public.site_budget
    from anon, authenticated;
grant select, insert, update on public.site_usage_days, public.site_usage_visitors,
    public.site_budget to service_role;

create function public.count_photo_read(
    p_day date, p_visitor text, p_cost numeric, p_day_cap integer, p_visitor_cap integer,
    p_budget numeric, p_judge boolean
) returns json language plpgsql set search_path = '' as $$
declare d integer; v integer; s numeric; w timestamptz;
begin
    insert into public.site_usage_days (day) values (p_day) on conflict do nothing;
    insert into public.site_usage_visitors (day, visitor) values (p_day, p_visitor)
        on conflict do nothing;
    select reads into d from public.site_usage_days where day = p_day for update;
    select reads into v from public.site_usage_visitors
        where day = p_day and visitor = p_visitor for update;
    select spent_usd, warned_at into s, w from public.site_budget where id for update;
    if not p_judge then
        if s >= p_budget then
            return json_build_object('allowed', false, 'reason', 'budget', 'spent', s, 'warn', false);
        elsif d >= p_day_cap then
            return json_build_object('allowed', false, 'reason', 'day', 'spent', s, 'warn', false);
        elsif v >= p_visitor_cap then
            return json_build_object('allowed', false, 'reason', 'visitor', 'spent', s, 'warn', false);
        end if;
    end if;
    update public.site_usage_days set reads = reads + 1 where day = p_day;
    update public.site_usage_visitors set reads = reads + 1
        where day = p_day and visitor = p_visitor;
    update public.site_budget set spent_usd = spent_usd + p_cost where id
        returning spent_usd into s;
    return json_build_object('allowed', true, 'reason', 'ok', 'spent', s,
        'warn', w is null and s >= 0.8 * p_budget);
end $$;

create function public.mark_budget_warned() returns void language sql set search_path = '' as $$
    update public.site_budget set warned_at = now() where id and warned_at is null
$$;

-- refines and chat messages: the budget rule only (judges exempt), same lock and reply
create function public.charge_spend(p_cost numeric, p_budget numeric, p_judge boolean)
returns json language plpgsql set search_path = '' as $$
declare s numeric; w timestamptz;
begin
    select spent_usd, warned_at into s, w from public.site_budget where id for update;
    if not p_judge and s >= p_budget then
        return json_build_object('allowed', false, 'reason', 'budget', 'spent', s, 'warn', false);
    end if;
    update public.site_budget set spent_usd = spent_usd + p_cost where id
        returning spent_usd into s;
    return json_build_object('allowed', true, 'reason', 'ok', 'spent', s,
        'warn', w is null and s >= 0.8 * p_budget);
end $$;

-- the health check: true when the counters answer; no amounts
create function public.usage_ping() returns boolean language sql stable set search_path = ''
as $$
    select exists (select 1 from public.site_budget)
$$;

revoke execute on function public.count_photo_read, public.mark_budget_warned,
    public.charge_spend, public.usage_ping from public, anon, authenticated;
grant execute on function public.count_photo_read, public.mark_budget_warned,
    public.charge_spend, public.usage_ping to service_role;
