# 👥 Accounts Module

<details open>
<summary><b>1. Core Purpose</b></summary>
The `accounts` app is the foundational identity and access management (IAM) system for EduMi2. It handles user registration, authentication, profiles, role definitions, and inter-user messaging/notifications.
</details>

<details>
<summary><b>2. Rationale & Architecture</b></summary>
Placed at the core of the project because every other module (meetings, attendance, videos) depends on user identity. It extends Django's base user model via a 1-to-1 `UserProfile` mapping to store academic-specific data (Branch, Employee ID, Roles) without polluting the core auth system.
</details>

<details>
<summary><b>3. Usage Instructions</b></summary>

- **Creating Users**: Use `python manage.py createsuperuser` for admins, or the UI `/register/` endpoint for students/teachers.
- **Role Assignment**: Admins can assign roles via the Django Admin panel or the internal User Management dashboard.
- **Messaging**: Users hit `/inbox/` to interact via the `Conversation` and `Message` models.
</details>

<details>
<summary><b>4. System Integrations</b></summary>
- **Internal**: Connects to `meetings` (to verify if a user can join a class) and `attendance` (linking face profiles to accounts).
- **Channels**: Integrates with Django Channels via `consumers.py` to push real-time notifications to the frontend.
</details>

<details>
<summary><b>5. Key Files Breakdown</b></summary>

- `models.py`: Defines `UserProfile`, extending the auth User with `role` (Admin/Teacher/Student), `avatar_url`, and `bio`.
- `messaging_models.py` / `notification_models.py`: Handles peer-to-peer DMs and system-wide alerts.
- `auth_views.py`: Custom login, logout, and registration logic.
- `consumers.py`: ASGI WebSocket consumer for delivering real-time notification payloads.
</details>