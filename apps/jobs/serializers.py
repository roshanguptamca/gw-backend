from rest_framework import serializers

from .models import ATSReport, JobDescription, JobMatch


class JobDescriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobDescription
        exclude = ["user"]


class ATSReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = ATSReport
        fields = ["score", "checks", "recommendations"]


class JobMatchSerializer(serializers.ModelSerializer):
    ats_report = ATSReportSerializer(read_only=True)

    class Meta:
        model = JobMatch
        fields = "__all__"
        read_only_fields = ["user"]


class ConfirmedSkillSerializer(serializers.Serializer):
    skill = serializers.CharField()
    confirmed = serializers.BooleanField()
    evidence = serializers.CharField(required=False, allow_blank=True)


class OptimizeRequestSerializer(serializers.Serializer):
    target_score = serializers.IntegerField(min_value=50, max_value=100)
    confirmed_skills = ConfirmedSkillSerializer(many=True, required=False, default=list)
    declined_skills = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    output_language = serializers.ChoiceField(choices=["en", "nl"], required=False, default="en")

    def validate(self, attrs):
        declined = {skill.strip().lower() for skill in attrs["declined_skills"]}
        for item in attrs["confirmed_skills"]:
            if item["confirmed"] and item["skill"].strip().lower() in declined:
                raise serializers.ValidationError(
                    {"confirmed_skills": f"{item['skill']} cannot be both confirmed and declined."}
                )
        return attrs
