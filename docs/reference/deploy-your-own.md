# Deploying your own copy

The live site's own deploy files (its domain, cloud project and registry ids) are not
in this repo. To run your own copy online:

1. **Image.** The `Dockerfile` builds the app with its data; `.gcloudignore` keeps a
   Cloud Build upload to what the image needs. Any container host works. We use Google
   Cloud Run: `gcloud run deploy herbtwin --source . --region <region> --port 8000`.
   One always-on instance (`--min-instances 1 --max-instances 1`, 1 vCPU, 1 GiB) keeps
   answers in memory between requests.
2. **Settings.** Set the same `HERBTWIN_*` values as `.env` (`.env.example` lists them)
   as service settings, and keep the keys in a secret store, never in the image. For a
   public site also set `HERBTWIN_SITE_URL`, `HERBTWIN_CAPS_ENABLED=1` and a
   `HERBTWIN_JUDGE_CODE` if you want a code that skips the caps.
3. **Caps and accounts.** The daily read caps and the model budget count in Supabase:
   run `supabase db push` with `supabase/migrations/` against your project
   ([docs/SUPABASE.md](../SUPABASE.md)). `/health` should then say `"usage": "ok"`.
4. **Edge (optional).** `edge/src/index.js` is a Cloudflare Worker that adds a shared
   secret header and the visitor's IP; with `HERBTWIN_EDGE_SECRET` set, the app refuses
   requests that skip it. Write your own `wrangler.toml` with your route and
   `ORIGIN` (your Cloud Run address), then `npx wrangler deploy` and
   `npx wrangler secret put EDGE_SECRET`.
5. **Reminder emails (optional).** `python -m herbtwin.reminders` sends the day's
   re-photo emails and exits. We run it once a day as a Nebius Serverless Job, started by
   a scheduled GitHub Actions workflow. That workflow file is not in this repo (it names
   our registry and project); it does four things: installs the Nebius CLI, signs in as
   a service account from repository secrets, builds the image on GitHub with BuildKit
   (`linux/amd64`, `provenance: false`) and pushes it to Nebius Container Registry, then
   runs `nebius ai job create --image <your image> --container-command python --args
   "-m herbtwin.reminders" --platform cpu-d3 --preset 2vcpu-8gb --timeout 1h`, with the
   four keys from a MysteryBox secret (`--env-secret`), and waits for the job to finish.
   What the job does and needs: [docs/REMINDERS.md](../REMINDERS.md).
