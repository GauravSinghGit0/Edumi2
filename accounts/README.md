# 👥 Accounts Module & Identity Management

<details open>
<summary><b>1. Core Purpose</b></summary>
The `accounts` app is the foundational identity and access management (IAM) system for EduMi. It handles user registration, enterprise authentication, profile management, granular role definitions (RBAC), executive administration, bulk user onboarding, and inter-user messaging/notifications.
</details>

<details open>
<summary><b>2. Executive Administration & Granular RBAC</b></summary>

### 1. Granular Role-Based Access Control (RBAC)
- Replaces legacy binary admin checks with a modular 7-flag capability matrix defined in `common.models.AdminRole`:
  - `manage_users`, `manage_courses`, `manage_sessions`, `view_audit`, `manage_settings`, `manage_cameras`, `export_data`.
- Enforced on all administrative endpoints using the `@admin_permission_required(perm)` decorator in `accounts/permissions.py`.
- **Pre-Configured Seed Roles**: *Super Admin*, *Academic Admin*, *Attendance Auditor*, and *IT Admin*.
- **Denial Protection**: Unauthorized browser visits render a stylized `403.html` shield, while AJAX/Fetch calls receive a standard `{ status: 'error', message: '...' }` with HTTP 403.
- **Dynamic Template Context**: Exposed globally via `accounts.context_processors.admin_permissions_context` to conditionally show/hide sidebar navigation items and action buttons.

### 2. Upgraded User Directory
- **Unified Tabs**: *All*, *Students*, *Teachers*, *Admins*, and *Suspended* with real-time unfiltered pill counts.
- **Merged Faculty View**: The Teacher Roster is consolidated directly into the *Teachers* tab (with legacy `/admin/teachers/` redirecting seamlessly).
- **Role-Specific Data Columns**:
  - *Students*: Enrolled courses count, face-recognition biometric attendance %.
  - *Teachers*: Department, courses taught, and total sessions hosted.
  - *Admins*: Privilege level and last login timestamp.
- **"Paginate First, Enrich Second" High-Performance Pipeline**: Database querysets are filtered and sliced by the Paginator *first* ($K = 10$ records per page) before calculating attendance percentages and course counts. This eliminated $O(N)$ query loops and reduced server tab latency from **6,694ms to 99.6ms** (a **98.5% server latency reduction**).
- **Client-Side In-Memory Map Pre-Rendering & Caching (`tabCache`)**: Rendered tab HTML fragments are stored in an in-memory `Map`, enabling instantaneous **< 1ms** tab switching when returning to previously loaded tabs.
- **60-Second Server Counter Caching**: Role tab badge counts (`all`, `active`, `suspended`, `teachers`, `students`, `admins`) are cached in Redis/LocMem for 60 seconds with atomic cache invalidation whenever user accounts are created, activated, or suspended.
- **Unified Navigation Breadcrumbs**: Centralized breadcrumbs across all admin sub-views via `templates/components/admin/breadcrumbs.html` with Lucide chevron dividers and automatic title fallbacks.
- **Floating Bulk Action Toolbar**: Multi-row checkboxes trigger a bottom slide-up toolbar to *Suspend*, *Activate*, *Change role*, or *Export selected* users with an `EdumiConfirm` impact summary modal.
- **Account Actions**: Includes 1-click password reset link generation and direct links to the student biometric 360° dossier.

### 3. 3-Step Bulk User CSV Importer Wizard
- Modal wizard accessed via `"Import users"` on `/admin/users/`:
  - **Step 1 (Upload)**: Drag-and-drop CSV uploader with downloadable sample template (`edumi_user_import_template.csv`).
  - **Step 2 (Preview & Validate)**: Real-time row-by-row validation checking for missing emails, duplicate usernames, and invalid role definitions.
  - **Step 3 (Asynchronous Import)**: Dispatches Celery task `admin_import_users_task` with real-time polling progress bar, downloadable failed-rows CSV, invitation email dispatch, and single-entry `BULK_ACTION` audit logging.

### 4. Global Command Palette (`Ctrl+K` / `Cmd+K`)
- Spotlight-style modal accessible globally across all admin pages.
- Real-time debounced backend search across Quick Actions, Users, Courses, and Live Sessions.
- Deep-links directly to actions like *Add User*, *Import Users*, *Create Course*, and *Live Monitor*.

### 5. High-Fidelity Demo Seed Data
- Management command `python manage.py seed_demo_data --clean-test-users`:
  - Seeds 3 Admins (`rajesh.sharma`, `priya.patel`, `vikram.singh`), 8 Faculty Teachers, 60 Students with realistic Indian names, 10 Courses, 30 Sessions, attendance records, submissions, and 45 audit logs. Default password: `Demo@1234`.
</details>

<details open>
<summary><b>3. Storage & Avatar Compression Architecture</b></summary>

### Automated In-Memory WebP Avatar Compression
In `accounts/models.py` (`UserProfile.save()`):
- When a student or teacher uploads or updates their profile picture, Pillow intercepts the image in memory.
- Downsamples large camera uploads to max **500x500** pixels using high-fidelity `LANCZOS` resampling.
- Converts color space to RGB and encodes directly to `.webp` at `quality=80` inside an in-memory `io.BytesIO` buffer.
- Renames the file extension to `.webp` and saves back to storage without writing uncompressed temporary files to disk.
- **Impact**: Cuts average avatar upload size from 1.5MB - 4MB down to **~35-65 KB** (75-85% storage reduction), eliminating disk bloat and speeding up dashboard load times.
</details>

<details>
<summary><b>4. Rationale & Architecture</b></summary>
Placing identity and governance at the core ensures that all dependent modules (meetings, attendance, cameras, assignments) operate under uniform authorization and security policies. It extends Django's base user model via a 1-to-1 `UserProfile` mapping to store academic-specific data (Branch, Employee ID, Roles) without polluting the core auth system.
</details>

<details>
<summary><b>5. Key Files Breakdown</b></summary>

- `models.py`: Defines `UserProfile` (with automated WebP avatar compression and `admin_role` foreign key), `StudentPhoto`, `UserAchievement`, and `EmailVerificationOTP`.
- `permissions.py`: Implements `@admin_permission_required` and `has_admin_permission` RBAC logic.
- `context_processors.py`: Provides `admin_perms` dictionary to template engines.
- `tasks.py`: Celery workers processing background user CSV imports and notifications.
- `report_services.py`: Aggregators generating CSV and ReportLab PDF reports for attendance and performance.
- `settings_services.py`: Service layer managing dynamic site settings.
- `views/admin_views.py`: Admin panel handlers, command palette API, user management, and roles matrix views.
- `views/admin_list_views.py`: Roster views for classrooms, live meetings, and live monitoring.
- `management/commands/seed_demo_data.py`: High-fidelity Indian dataset seeder.
</details>
