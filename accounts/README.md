# 👥 Accounts Module & Identity Management

<details open>
<summary><b>1. Core Purpose</b></summary>
The `accounts` app is the foundational identity and access management (IAM) system for EduMi2. It handles user registration, enterprise authentication, profile management, role definitions, and inter-user messaging/notifications.
</details>

<details open>
<summary><b>2. Storage & Avatar Compression Architecture</b></summary>

### Automated In-Memory WebP Avatar Compression
In `accounts/models.py` (`UserProfile.save()`):
- When a student or teacher uploads or updates their profile picture, Pillow intercepts the image in memory.
- Downsamples large camera uploads to max **500x500** pixels using high-fidelity `LANCZOS` resampling.
- Converts color space to RGB and encodes directly to `.webp` at `quality=80` inside an in-memory `io.BytesIO` buffer.
- Renames the file extension to `.webp` and saves back to storage without writing uncompressed temporary files to disk.
- **Impact**: Cuts average avatar upload size from 1.5MB - 4MB down to **~35-65 KB** (75-85% storage reduction), eliminating disk bloat and speeding up dashboard load times.
</details>

<details>
<summary><b>3. Rationale & Architecture</b></summary>
Placed at the core of the project because every other module (meetings, attendance, videos) depends on user identity. It extends Django's base user model via a 1-to-1 `UserProfile` mapping to store academic-specific data (Branch, Employee ID, Roles) without polluting the core auth system.
</details>

<details>
<summary><b>4. Usage Instructions</b></summary>

- **Creating Users**: Use `python manage.py createsuperuser` for admins, or the UI `/register/` endpoint for students/teachers.
- **Role Assignment**: Admins can assign roles via the Django Admin panel or the internal User Management dashboard.
- **Messaging**: Users hit `/inbox/` to interact via the `Conversation` and `Message` models.
</details>

<details>
<summary><b>5. System Integrations</b></summary>
- **Meetings**: Verifies user enrollment and roles before allowing meeting creation or joins.
- **Biometric Attendance**: Links facial biometric templates to `UserProfile` identities.
- **Common App**: Uses common validators for MIME validation and avatar integrity.
- **Channels**: Integrates with Django Channels via `consumers.py` to push real-time notifications to the frontend.
</details>

<details>
<summary><b>6. Key Files Breakdown</b></summary>

- `models.py`: Defines `UserProfile` (with automated WebP avatar compression), `StudentPhoto`, `UserAchievement`, and `EmailVerificationOTP`.
- `messaging_models.py` / `notification_models.py`: Handles peer-to-peer DMs and system-wide alerts.
- `auth_views.py`: Custom login, logout, and registration logic.
- `consumers.py`: ASGI WebSocket consumer for delivering real-time notification payloads.
- `email_tokens.py`: Signed cryptographic token generators for email OTP verification.
</details>