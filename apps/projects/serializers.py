from rest_framework import serializers

from .models import Project


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ["id", "name", "description", "workspace", "created_by",
                  "updated_at", "created_at"]
        read_only_fields = ["id", "created_by", "updated_at", "created_at"]

    def __init__(self, *args, **kwargs):
        # you cant update the worksspace it self its read only field and can only be set on creation of the project
        super().__init__(*args, **kwargs)
        if self.instance is not None:
            self.fields["workspace"].read_only = True

    def create(self, validated_data):
        user = self.context['request'].user
        project = Project.objects.create(created_by=user, **validated_data)
        return project


