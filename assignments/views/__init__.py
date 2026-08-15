"""
Assignments Views sub-package.
"""
from .assignment_views import (
    classroom_assignments,
    create_assignment,
    edit_assignment,
    assignment_detail,
    submit_assignment,
    evaluate_submission,
    delete_question_file,
)
from .quiz_views import (
    classroom_quizzes,
    create_quiz,
    edit_quiz,
    quiz_detail,
    add_question,
    delete_question,
    take_quiz,
    quiz_time_status,
    evaluate_quiz_submission,
)
