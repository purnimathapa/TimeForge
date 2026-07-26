from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class TimeForgeUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('role', User.RoleChoices.ADMIN)
        extra_fields.setdefault('can_create_admins', True)
        return super().create_superuser(username, email, password, **extra_fields)


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
    can_create_admins = models.BooleanField(
        default=False,
        help_text='If ticked, this admin may create other admin accounts.',
    )

    objects = TimeForgeUserManager()

    def is_admin(self):
        return self.role == self.RoleChoices.ADMIN

    def is_teacher(self):
        return self.role == self.RoleChoices.TEACHER

    def is_class_rep(self):
        return self.role == self.RoleChoices.CLASS_REP

    def may_create_admins(self):
        """True when this user is allowed to create other admin accounts."""
        return self.is_admin() and (self.can_create_admins or self.is_superuser)
