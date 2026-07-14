from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    class RoleChoices(models.TextChoices):
        ADMIN = 'ADMIN', 'Admin'
        TEACHER = 'TEACHER', 'Teacher'
        CLASS_REP = 'CLASS_REP', 'Class Representative'

    role = models.CharField(
        max_length=20,
        choices=RoleChoices.choices,
        default=RoleChoices.ADMIN,
    )
    school = models.ForeignKey(
        'core.School',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='users',
    )

    def is_admin(self):
        return self.role == self.RoleChoices.ADMIN

    def is_teacher(self):
        return self.role == self.RoleChoices.TEACHER

    def is_class_rep(self):
        return self.role == self.RoleChoices.CLASS_REP
