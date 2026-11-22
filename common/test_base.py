from django.test import TestCase
from django.contrib.auth import get_user_model
import factory
from factory import Faker, post_generation
from factory.django import DjangoModelFactory
from accounts.models import UserProfile

User = get_user_model()


class UserFactory(DjangoModelFactory):
    """Factory for creating test users"""
    class Meta:
        model = User
        django_get_or_create = ('username',)

    username = factory.Sequence(lambda n: f"user_{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.com")
    first_name = Faker('first_name')
    last_name = Faker('last_name')
    password = 'testpass123'

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Override to use set_password for hashing"""
        password = kwargs.pop('password', 'testpass123')
        user = super()._create(model_class, *args, **kwargs)
        user.set_password(password)
        user.save()
        return user


class TeacherUserFactory(UserFactory):
    """Factory for teacher users"""
    username = factory.Sequence(lambda n: f"teacher_{n}")

    @post_generation
    def profile(self, create, extracted, **kwargs):
        if create:
            UserProfile.objects.update_or_create(
                user=self,
                defaults={
                    'user_type': 'teacher',
                    'employee_id': f'EMP{self.id:04d}',
                    'department': 'Computer Science'
                }
            )


class StudentUserFactory(UserFactory):
    """Factory for student users"""
    username = factory.Sequence(lambda n: f"student_{n}")

    @post_generation
    def profile(self, create, extracted, **kwargs):
        if create:
            UserProfile.objects.update_or_create(
                user=self,
                defaults={
                    'user_type': 'student',
                    'student_id': f'STU{self.id:04d}',
                    'grade': '10',
                    'branch': 'Science'
                }
            )


class BaseTestCase(TestCase):
    """Base test case with common utilities"""

    @classmethod
    def setUpTestData(cls):
        """Set up data for the whole TestCase"""
        cls.teacher = TeacherUserFactory()
        cls.student = StudentUserFactory()

    def assertDictContainsSubset(self, subset, dictionary, msg=None):
        """Check if subset is contained in dictionary"""
        for key, value in subset.items():
            self.assertEqual(dictionary.get(key), value, msg)
