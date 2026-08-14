# ⚙️ School Project (Core Configuration)

<details open>
<summary><b>1. Core Purpose</b></summary>
The `school_project` directory is the standard Django root configuration folder. It binds all modular apps together, configures the environment, and dictates how the server operates.
</details>

<details>
<summary><b>2. Rationale & Architecture</b></summary>
Standard Django convention. It holds global settings, ASGI/WSGI entry points, and custom middleware that applies to the entire request lifecycle (like handling database locks or enforcing global security headers).
</details>

<details>
<summary><b>3. Usage Instructions</b></summary>

- **Environment**: Do not hardcode secrets here. Always use the `.env` file in the project root.
- **Routing**: To add a new app, register its URLs in `urls.py` and add it to `INSTALLED_APPS` in `settings.py`.
</details>

<details>
<summary><b>4. System Integrations</b></summary>
- **Database**: Configured to point to the centralized `database/db.sqlite3`.
- **Redis/Celery**: Binds the application to the Redis broker via `CELERY_BROKER_URL` and Channels layers.
- **Static/Media**: Routes all file storage to the `database/media/` directory.
</details>

<details>
<summary><b>5. Key Files Breakdown</b></summary>

- `settings.py`: The master configuration file. Contains database paths, security policies, and LiveKit credentials.
- `asgi.py`: The entry point for Daphne/Uvicorn. Configures protocol routers for HTTP and WebSockets (Django Channels).
- `celery.py`: Initializes the Celery application and auto-discovers tasks across all installed apps.
- `middleware.py`: Custom middleware, including `DatabaseErrorMiddleware` which gracefully catches and reports SQLite locking issues.
</details>