# 📝 Assignments Module

<details open>
<summary><b>1. Core Purpose</b></summary>
The `assignments` app manages academic coursework creation, student submissions, teacher grading workflows, and automated feedback distribution for the EduMi2 platform.
</details>

<details>
<summary><b>2. Rationale & Architecture</b></summary>
Encapsulates all asynchronous assignment lifecycles. It provides structured schema for deadlines, grade weightage, file attachment uploads, and submission status tracking, allowing teachers to evaluate student progress efficiently.
</details>

<details>
<summary><b>3. Usage Instructions</b></summary>

- **Creating Assignments**: Educators create coursework specifying title, description, due date, maximum score, and optional resource attachments.
- **Submitting Work**: Students upload file submissions or text responses before the deadline timestamp.
- **Grading**: Educators review submissions, assign numerical grades, and provide feedback remarks.
</details>

<details>
<summary><b>4. System Integrations</b></summary>

- **Accounts App**: Links submissions to specific `UserProfile` accounts (Teachers and Students) to enforce role-based access controls.
- **Meetings App**: Can tie assignments directly to specific `Classroom` instances for course syllabus integration.
- **Storage**: Manages attachment files stored securely under `media/assignments/`.
</details>

<details>
<summary><b>5. Key Files Breakdown</b></summary>

- `models.py`: Defines `Assignment`, `AssignmentSubmission`, and `AssignmentAttachment` models.
- `views/`: Module containing views for assignment creation, student submission handling, and grading interfaces.
- `urls/`: URL pattern configurations for assignment routing.
- `admin.py`: Django admin registration for managing coursework entities.
</details>
