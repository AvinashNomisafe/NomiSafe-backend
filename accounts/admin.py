from django.contrib import admin
from django.contrib.auth import get_user_model
from .models import UserProfile

User = get_user_model()


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'
    fields = ['name', 'date_of_birth', 'alternate_phone']


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['phone_number', 'email', 'is_aadhaar_verified', 'is_active', 'is_staff']
    list_filter = ['is_aadhaar_verified', 'is_active', 'is_staff']
    search_fields = ['phone_number', 'email']
    inlines = [UserProfileInline]


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'name', 'date_of_birth', 'alternate_phone']
    search_fields = ['user__phone_number', 'name', 'alternate_phone']
    list_filter = ['date_of_birth']

