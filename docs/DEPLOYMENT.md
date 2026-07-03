# TimeForge Deployment Runbook

TimeForge is configured for easy deployment on [Render](https://render.com) using its Web Service and Managed PostgreSQL offerings. 

## 1. Prerequisites
- A Render account.
- Your TimeForge code pushed to a GitHub, GitLab, or Bitbucket repository.

## 2. Infrastructure Setup (Render)
TimeForge utilizes Render's Blueprint feature to automatically provision the database and web service.

1. In your Render Dashboard, click **New > Blueprint**.
2. Connect the repository containing this project.
3. Render will read the `render.yaml` file in the root directory and provision:
   - `timeforge-db` (Managed PostgreSQL Database)
   - `timeforge-web` (Web Service running Gunicorn)
4. During provisioning, Render will automatically:
   - Generate a secure `SECRET_KEY`.
   - Inject the `DATABASE_URL` linking the web service to the database.
   - Run the `./build.sh` script to install dependencies, run migrations, and collect static files using WhiteNoise.

## 3. Environment Variables
The blueprint handles most environment variables automatically. If deploying manually or on another platform, ensure the following are set:
- `DJANGO_ENV`: `production` (Activates production settings and `DEBUG=False`).
- `SECRET_KEY`: A strong random string.
- `DATABASE_URL`: Connection string to your PostgreSQL instance.
- `ALLOWED_HOSTS`: Domain names (comma-separated). Render automatically injects `RENDER_EXTERNAL_HOSTNAME`, which the app trusts by default.
- `SECURE_SSL_REDIRECT`: Defaults to `True`.

## 4. Post-Deployment Steps
After the service is live, you must run one-time setup scripts to populate the database and create a superuser.

From the Render Dashboard for your Web Service, navigate to the **Shell** tab:

1. **Create Superuser**:
   ```bash
   python manage.py createsuperuser
   ```
   Follow the prompts to set your admin username, email, and password.

2. **Seed Initial Data** (Optional but recommended):
   If you want to quickly populate the database with default semesters, departments, subjects, and constraints:
   ```bash
   python seed_db.py
   ```
   *Warning*: Do not run this on an actively used database as it flushes current data. Use only on fresh deployments.

3. **Generate First Timetable**:
   Navigate to the deployed site as the Admin, go to the Timetable List, and click **Generate**.

## 5. Rollback Procedure
If a deployment introduces critical bugs:
1. Go to the **Events** tab in your Render Web Service.
2. Find the previous successful deploy.
3. Click the menu (three dots) next to the deploy and select **Rollback to this deploy**.

## Note on Static Files
This project uses [WhiteNoise](http://whitenoise.evans.io/) to serve static files. Collectstatic places them in the `staticfiles/` directory where they are served efficiently by the web server (Gunicorn) with caching headers, completely removing the need for a separate CDN or Node.js infrastructure for static assets.
