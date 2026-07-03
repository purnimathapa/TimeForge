from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    class RoleChoices(models.TextChoices):
        ADMIN = 'ADMIN', 'Admin'
        TEACHER = 'TEACHER', 'Teacher'

    role = models.CharField(
        max_length=20,
        choices=RoleChoices.choices,
        default=RoleChoices.ADMIN,
    )

    def is_admin(self):
        return self.role == self.RoleChoices.ADMIN

    def is_teacher(self):
        return self.role == self.RoleChoices.TEACHER
