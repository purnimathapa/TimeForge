# TimeForge — Local Development Setup (macOS)

This guide walks through a clean-machine setup for TimeForge using PostgreSQL on macOS. The project uses **split Django settings**: shared values live in `timeforge/settings/base.py`, and local development loads `timeforge/settings/dev.py`, which requires a `.env` file at the project root.

## Prerequisites

- macOS with Python 3.12+ available
- PostgreSQL installed via [Postgres.app](https://postgresapp.com/) or Homebrew (`brew install postgresql@16`)
- Git

## 1. Clone and enter the project

```bash
git clone <repository-url> TimeForge
cd TimeForge
```

## 2. Create and activate a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

## 3. Install Python dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

Pinned packages: Django, psycopg2-binary, python-decouple, reportlab (PDF export), openpyxl (Excel export).

## 4. Install and start PostgreSQL

### Option A — Postgres.app

1. Download and open Postgres.app.
2. Click **Initialize** if prompted.
3. Ensure the server is running (elephant icon in the menu bar).

### Option B — Homebrew

```bash
brew install postgresql@16
brew services start postgresql@16
```

Add the Homebrew bin directory to your `PATH` if `psql` is not found.

## 5. Create the database and role

Use your macOS username as the PostgreSQL role (Postgres.app and Homebrew often create this automatically).

```bash
# Create the application database
createdb timeforge

# Verify connection (no password needed for local peer/trust auth on many setups)
psql -d timeforge -c "SELECT version();"
```

If you need a dedicated role with a password:

```bash
psql postgres
```

```sql
CREATE USER timeforge_user WITH PASSWORD 'your_password';
CREATE DATABASE timeforge OWNER timeforge_user;
GRANT ALL PRIVILEGES ON DATABASE timeforge TO timeforge_user;
\q
```

## 6. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

| Variable     | Example / notes                                      |
|--------------|------------------------------------------------------|
| `SECRET_KEY` | Long random string (required — no default)           |
| `DEBUG`      | `True` for local dev (`False` if variable is omitted)|
| `ALLOWED_HOSTS` | `localhost,127.0.0.1`                           |
| `TIME_ZONE`  | `Asia/Kathmandu` (institution timezone)              |
| `DB_NAME`    | `timeforge`                                          |
| `DB_USER`    | Your macOS username or dedicated role                |
| `DB_PASSWORD`| Leave empty for local trust auth, or set if required |
| `DB_HOST`    | `localhost`                                          |
| `DB_PORT`    | `5432`                                               |

**Never commit `.env`** — it is listed in `.gitignore`.

If `.env` is missing, Django raises `ImproperlyConfigured` at startup with a pointer to this document. There is no SQLite fallback.

## 7. Run migrations

```bash
python manage.py migrate
```

This creates Django’s built-in tables only (auth, admin, sessions, contenttypes). No TimeForge app models exist yet.

Verify tables in PostgreSQL:

```bash
psql -d timeforge -c "\dt"
```

Expected tables include: `auth_group`, `auth_permission`, `auth_user`, `django_admin_log`, `django_content_type`, `django_migrations`, `django_session`.

## 8. Start the development server

```bash
python manage.py runserver
```

Open http://127.0.0.1:8000/ — you should see the default Django welcome page.

## 9. Quick verification checklist

```bash
# Migrations apply cleanly
python manage.py migrate

# Only built-in apps have migrations
python manage.py showmigrations

# Server starts with .env present
python manage.py check

# Missing .env should fail loudly (rename temporarily to test)
mv .env .env.bak
python manage.py check   # expect ImproperlyConfigured
mv .env.bak .env
```

## Settings layout

| Module                      | Purpose                                      |
|-----------------------------|----------------------------------------------|
| `timeforge/settings/base.py`| Shared settings; `DEBUG` defaults to `False` |
| `timeforge/settings/dev.py` | Local dev; requires `.env` file              |
| `timeforge/settings/__init__.py` | Default import path (`timeforge.settings`) |

`manage.py`, `wsgi.py`, and `asgi.py` all use `DJANGO_SETTINGS_MODULE=timeforge.settings`.

## Troubleshooting

**`FATAL: database "timeforge" does not exist`**  
Run `createdb timeforge` (step 5).

**`connection refused` on port 5432**  
Start Postgres.app or `brew services start postgresql@16`.

**`UndefinedValueError: SECRET_KEY not found`**  
Ensure `.env` exists and contains `SECRET_KEY=...`.

**`ImproperlyConfigured: Missing .env file`**  
Run `cp .env.example .env` and fill in values.

**Password authentication failed**  
Set `DB_USER` and `DB_PASSWORD` in `.env` to match your PostgreSQL role.
