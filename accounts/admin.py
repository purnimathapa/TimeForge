from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Role Info', {'fields': ('role', 'school', 'can_create_admins')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Role Info', {'fields': ('role', 'school', 'can_create_admins')}),
    )
    list_display = (
        'username', 'email', 'first_name', 'last_name',
        'role', 'can_create_admins', 'is_staff',
    )
    list_filter = ('role', 'can_create_admins', 'is_staff', 'is_superuser', 'is_active')

admin.site.register(User, CustomUserAdmin)
