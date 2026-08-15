"""
Common view mixins and base views used across all apps
"""
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.shortcuts import redirect
from django.contrib import messages
from .utils import is_teacher, is_student, get_user_type


class LoginRequiredMixin:
    """
    Mixin that requires the user to be logged in
    """
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class TeacherRequiredMixin(LoginRequiredMixin):
    """
    Mixin that requires the user to be a teacher
    """
    def dispatch(self, request, *args, **kwargs):
        if not is_teacher(request.user) and not request.user.is_superuser:
            messages.error(request, "You don't have permission to access this page.")
            return redirect('home')
        return super().dispatch(request, *args, **kwargs)


class StudentRequiredMixin(LoginRequiredMixin):
    """
    Mixin that requires the user to be a student
    """
    def dispatch(self, request, *args, **kwargs):
        if not is_student(request.user):
            messages.error(request, "You don't have permission to access this page.")
            return redirect('home')
        return super().dispatch(request, *args, **kwargs)


class SuperuserRequiredMixin(LoginRequiredMixin):
    """
    Mixin that requires the user to be a superuser
    """
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            messages.error(request, "You don't have permission to access this page.")
            return redirect('home')
        return super().dispatch(request, *args, **kwargs)


class UserTypeContextMixin:
    """
    Adds user_type and common context variables to all views
    """
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            context['user_type'] = get_user_type(self.request.user)
            context['is_teacher'] = is_teacher(self.request.user)
            context['is_student'] = is_student(self.request.user)
        return context
