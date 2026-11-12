# Deploying Workbench to Vercel + Supabase

This guide takes Workbench from your Mac to a live site:

- **Vercel** runs the Django app (it detects Django automatically) and serves the CSS/JS from its CDN.
- **Supabase** hosts the PostgreSQL database.
- Only your account can sign in. Visitors can click **Try the demo** to use a sandbox account full of sample data that resets every night.

Allow about 30–45 minutes the first time. Everything here works on the free plans.

---

## 0. Before you start

You'll need:

- The project in a **GitHub repo**. Vercel deploys from GitHub. `.gitignore` already keeps `db.sqlite3`, `.env` files and `.venv/` out of git.
- A **Supabase** account: https://supabase.com
- A **Vercel** account (sign in with GitHub): https://vercel.com

First, upgrade your local copy, since this update added logins:

```bash
cd interview-prep
source .venv/bin/activate
pip install -r requirements.txt     # adds psycopg, the PostgreSQL driver
python manage.py migrate
python manage.py createsuperuser    # your login: pick a username and a strong password
python manage.py claim_data         # gives everything you created before logins to that account
python manage.py runserver
```

Sign in at http://127.0.0.1:8000. Your existing stories, questions and projects should all be there.

---

## 1. Create the Supabase database

1. In Supabase, click **New project**. Pick a name (e.g. `workbench`), generate a **database password** and save it in your password manager, and choose a region near you (e.g. *Canada (Central)*).
2. When it's ready, click **Connect** at the top of the project. You need two connection strings from there. Replace `[YOUR-PASSWORD]` in each with your database password:
   - **Transaction pooler** (port **6543**). This is for Vercel.
   - **Session pooler** (port **5432**). This is for running commands from your Mac. (The *direct* connection is IPv6-only on the free plan, so it may not work from home networks.)
   - If your password has special characters like `@ # ? &`, URL-encode them (e.g. `@` becomes `%40`), or regenerate a password without them.
3. **Turn off Supabase's auto-generated API** for this project. Workbench connects to Postgres directly and doesn't use it, and leaving it on would expose your tables through Supabase's REST API. Find the **Data API** settings (under Project Settings or Integrations, depending on your dashboard version) and disable it, or remove `public` from the exposed schemas.

---

## 2. Set up the database from your Mac

Create `.env.production` from the example and paste in the **session pooler** URI:

```bash
cp .env.production.example .env.production
# edit .env.production → DATABASE_URL=postgresql://postgres.xxxx:PASSWORD@aws-0-....pooler.supabase.com:5432/postgres
```

Prefixing a command with `ENV_FILE=.env.production` runs it against Supabase instead of your local SQLite:

```bash
ENV_FILE=.env.production python manage.py migrate            # create all tables in Supabase
ENV_FILE=.env.production python manage.py createsuperuser    # your login on the live site
```

### Copy your existing data over (optional)

Export from your local database, then import into Supabase. Use the **same username** for `createsuperuser` above as on your Mac, so ownership matches.

```bash
python manage.py dumpdata prep journal --natural-foreign --indent 2 -o mydata.json     # from local SQLite
ENV_FILE=.env.production python manage.py loaddata mydata.json                         # into Supabase
ENV_FILE=.env.production python manage.py claim_data                                   # tidy up any un-owned rows
rm mydata.json
```

### Seed the demo (optional)

The demo seeds itself the first time someone clicks **Try the demo**, but you can do it now:

```bash
ENV_FILE=.env.production python manage.py reset_demo
```

---

## 3. Deploy on Vercel

1. Push the latest code to GitHub.
2. In Vercel, click **Add New → Project**, import the repo, and keep the detected settings. Vercel finds `manage.py`, reads `WSGI_APPLICATION`, installs `requirements.txt`, and runs `collectstatic` for you.
3. Before deploying, open **Environment Variables** and add:

   | Name | Value | Required |
   | --- | --- | --- |
   | `DATABASE_URL` | Supabase **transaction pooler** URI (port **6543**) | yes |
   | `DJANGO_SECRET_KEY` | a long random string, made with `python -c "import secrets; print(secrets.token_urlsafe(50))"` | yes |
   | `CRON_SECRET` | another random string, letters and numbers only, e.g. `python -c "import secrets; print(secrets.token_hex(24))"` | yes, for the nightly demo reset |
   | `GITHUB_TOKEN` | a GitHub fine-grained token with read-only **Contents** access to your repos | for private repos, and to get 5,000 GitHub requests an hour instead of 60 |
   | `ANTHROPIC_API_KEY` | your API key | only for AI feedback in practice mode |
   | `SITE_NAME` | e.g. `Workbench` | no |
   | `OWNER_URL` | your personal website, linked from your name on the landing page | no |
   | `REPO_URL` | this project's GitHub repo, shown as "Source on GitHub" on the landing page (only if the repo is public) | no |

4. Click **Deploy**. When it finishes, open the `*.vercel.app` URL and sign in.

What `vercel.json` sets up:

- The app can run for up to 60 seconds per request (importing a big repo's history can take a while).
- A **cron job** calls `/cron/reset-demo/` once a day around 09:00 UTC (2–3 a.m. in Edmonton) to wipe and re-seed the demo. Vercel sends `CRON_SECRET` with the request, and anyone else gets "Forbidden". On the free plan it runs at some point within that hour. You can see each run under **Schedules → Cron Jobs → View Logs**.

### Getting a GitHub token

GitHub → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**. Choose *Only select repositories* (or all of yours). Under **Repository permissions**, set **Contents: Read-only**; Metadata stays read-only automatically. Copy it into `GITHUB_TOKEN`.

---

## 4. After it's live

- **Projects:** on each project's edit page, set the **GitHub repo link** (e.g. `https://github.com/elaiza-remo/Shelf`). Then click **Import new commits** on its Commits tab. On the live site, commits always come from GitHub. When you run Workbench on your Mac with a local repo folder set, it reads the folder instead.
- **Try the demo yourself:** sign out, click **Try the demo**, and click around. Your own data never appears there, and nothing done there touches yours.
- **Custom domain (optional):** add it in Vercel under **Settings → Domains**, then add two environment variables and redeploy:
  - `DJANGO_ALLOWED_HOSTS` = `localhost,127.0.0.1,workbench.yourdomain.com`
  - `DJANGO_CSRF_TRUSTED_ORIGINS` = `https://workbench.yourdomain.com`

---

## 5. Making changes later

The normal loop:

```bash
# work locally against SQLite, as usual
python manage.py test
git add -A && git commit -m "…" && git push      # Vercel deploys automatically on push to main
```

**If your change includes a new migration** (you edited a model), apply it to Supabase as well:

```bash
ENV_FILE=.env.production python manage.py migrate
```

Do this right before or right after pushing. Migrations that only *add* things (new fields with defaults, new tables) are safe to run first. Old code ignores new columns.

**Pull requests and branches** get their own Vercel preview URLs that use the same database (cron jobs only run on production).

---

## 6. Troubleshooting

| What you see | What to do |
| --- | --- |
| Build fails: `Set DJANGO_SECRET_KEY…` | Add `DJANGO_SECRET_KEY` in Vercel's environment variables and redeploy. |
| `Server Error (500)` | Open the deployment in Vercel → **Logs**. Most often it's a typo in `DATABASE_URL` or a missing `migrate`. |
| `DisallowedHost` / `Bad Request (400)` on a custom domain | Add the domain to `DJANGO_ALLOWED_HOSTS` and redeploy. |
| "CSRF verification failed" when signing in on a custom domain | Add `https://your-domain` to `DJANGO_CSRF_TRUSTED_ORIGINS` and redeploy. |
| `prepared statement … does not exist` | `DATABASE_URL` on Vercel must be the **transaction pooler** URI (port 6543); Workbench switches off prepared statements automatically for it. |
| Can't connect when running `migrate` from your Mac | Use the **session pooler** URI (port 5432) in `.env.production`, not the direct connection (IPv6-only on the free plan). |
| `password authentication failed` | Check the password, and URL-encode special characters (`@` → `%40`, `#` → `%23`). |
| Pages load with no styling | Make sure `STATIC_ROOT` is still set in `config/settings.py`; Vercel only runs `collectstatic` when it is. |
| Commit import: rate limit | Add `GITHUB_TOKEN`. Without it GitHub allows 60 requests an hour, shared with everyone on the same IP. |
| Commit import: "couldn't find that repo" | Check the repo link. For a private repo, the token needs access to it. |
| Demo shows someone else's edits | Expected. The demo is a single shared sandbox, wiped nightly. To reset it now: `ENV_FILE=.env.production python manage.py reset_demo`. |
| Supabase project paused | Free projects pause after a stretch with no activity. The nightly demo reset touches the database every day, which normally keeps it awake. Restore it from the Supabase dashboard if it does pause. |
| Forgot your password | `ENV_FILE=.env.production python manage.py changepassword yourusername` |
