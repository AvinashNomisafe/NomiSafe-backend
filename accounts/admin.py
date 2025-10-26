from django.contrib import admin
from django.contrib.auth import get_user_model
from .models import Policy

User = get_user_model()

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    pass

@admin.register(Policy)
class PolicyAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'user', 'uploaded_at')
    search_fields = ('name', 'user__phone_number', 'user__email')