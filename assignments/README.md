# 📝 Assignments & Quizzes Module

<details open>
<summary><b>1. Core Purpose</b></summary>
The `assignments` app manages academic coursework creation, student submissions, teacher grading workflows, timed quizzes, and automated anti-cheating surveillance for EduMi.
</details>

<details open>
<summary><b>2. Rationale & Architecture</b></summary>
Encapsulates all asynchronous assignment lifecycles and interactive assessment pipelines:
- **Coursework Management:** Provides structured schemas for deadlines, grade weightage, file attachment uploads, and submission status tracking.
- **Timed Online Quizzes:** Shuffled questions, randomized option order, automated scoring, and detailed performance breakdown.
- **Anti-Cheating Surveillance Engine:** Monitors student browser activity during exams (tab switching via `visibilitychange` API, window blur events, and full-screen exits), logging suspicious behavior with timestamps directly into the exam audit ledger.
- **Security & Integrity:** Uploaded homework attachments pass through strict binary magic-byte validation (`common.validators`) preventing executable malware disguising as document files.
</details>

<details open>
<summary><b>3. Timed Quizzes & Interactive Assessments</b></summary>

- **Question Formats:** Supports multiple-choice questions (MCQs), single-answer questions, and descriptive problem sets.
- **Randomization:** Automatically randomizes question sequence and answer choices per student to prevent peer copying.
- **Real-Time Countdown:** Client-side JavaScript countdown timer synchronized with server-side submission deadlines.
- **Automatic Grading & Instant Scorecards:** Objective questions are graded instantly upon submission, generating visual scorecards and performance metrics for students and teachers.
</details>

<details>
<summary><b>4. Usage Instructions</b></summary>

- **Creating Assignments:** Teachers create coursework specifying title, description, due date, maximum score, and optional resource attachments.
- **Creating Quizzes:** Teachers configure quiz parameters (duration in minutes, passing score, question pool, answer keys).
- **Submitting Work:** Students upload file submissions before the deadline timestamp; suspicious browser tab-switching events during active quizzes are flagged automatically.
- **Grading:** Teachers review submissions, assign numerical grades, and provide feedback remarks.
</details>

<details>
<summary><b>5. System Integrations</b></summary>

- **Accounts App:** Links submissions and quiz attempts to specific `UserProfile` accounts to enforce role-based access controls.
- **Meetings App:** Quizzes can be launched dynamically inside live virtual classrooms for synchronized in-lecture polling.
- **Common App:** Enforces binary magic-byte inspection on all submitted files via `validate_assignment_file()` and generates WebP thumbnails for document resources.
- **Storage:** Stores student submission attachments securely under `database/media/assignments/`.
</details>

<details>
<summary><b>6. Key Files Breakdown</b></summary>

- `models.py`: Defines `Assignment`, `AssignmentSubmission`, `AssignmentAttachment`, `Quiz`, `Question`, `Option`, and `QuizAttempt`.
- `views/`: Module containing views for assignment creation, student submission handling, quiz evaluation, and grading interfaces.
- `urls/`: URL pattern configurations for assignment and quiz routing.
- `admin.py`: Django admin registration for managing coursework and quiz entities.
</details>
