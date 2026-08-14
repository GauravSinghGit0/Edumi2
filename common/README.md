# 🛠️ Common Module

<details open>
<summary><b>1. Core Purpose</b></summary>
The `common` app provides shared utilities, template tags, custom mixins, and abstract models used across the entire EduMi2 ecosystem.
</details>

<details>
<summary><b>2. Rationale & Architecture</b></summary>
Promotes DRY (Don't Repeat Yourself) principles. Instead of rewriting pagination logic, permission checks, or date-formatting template tags in every single app, they are centralized here and imported as needed.
</details>

<details>
<summary><b>3. Usage Instructions</b></summary>

- **Template Tags**: Load them in HTML using `{% load common_tags %}` to use custom filters (e.g., duration formatting).
- **Models**: Inherit from `TimeStampedModel` to automatically get `created_at` and `updated_at` fields on any new database table.
</details>

<details>
<summary><b>4. System Integrations</b></summary>
- **Global**: Imported by almost every other app in the project. Does not depend on any specific app, ensuring no circular import issues.
</details>

<details>
<summary><b>5. Key Files Breakdown</b></summary>

- `models.py`: Contains abstract base classes.
- `utils.py`: Helper functions for file handling, timezone conversions, and standardizing JSON responses.
- `templatetags/common_tags.py`: Custom Django template filters used in the UI.
</details>