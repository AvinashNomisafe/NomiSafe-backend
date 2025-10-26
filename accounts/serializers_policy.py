from rest_framework import serializers
from .models import Policy

class PolicyBenefitsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Policy
        fields = ['id', 'name', 'benefits']
        read_only_fields = ['name', 'benefits']