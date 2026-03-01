from rest_framework import serializers

from apps.pipeline.serializers import PipelineSerializer


class AnalyticsQuerySerializer(serializers.Serializer):
    from_date = serializers.DateField(required=False, input_formats=["%Y-%m-%d"], source="from")
    to_date = serializers.DateField(required=False, input_formats=["%Y-%m-%d"], source="to")
    pipeline_id = serializers.UUIDField(required=False)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        start = attrs.get("from")
        end = attrs.get("to")
        if start and end and start > end:
            raise serializers.ValidationError({"to": "End date must be greater than or equal to start date."})
        return attrs


class DashboardKpiSerializer(serializers.Serializer):
    total_leads = serializers.IntegerField()
    total_deals = serializers.IntegerField()
    won_deals = serializers.IntegerField()
    conversion_rate = serializers.FloatField()
    open_pipeline_value = serializers.DecimalField(max_digits=12, decimal_places=2)
    closed_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    average_ticket = serializers.DecimalField(max_digits=12, decimal_places=2)


class SourceCountSerializer(serializers.Serializer):
    source_id = serializers.UUIDField(allow_null=True)
    source_name = serializers.CharField(allow_null=True)
    lead_count = serializers.IntegerField()


class StageAmountSerializer(serializers.Serializer):
    stage_id = serializers.UUIDField()
    stage_name = serializers.CharField()
    stage_color = serializers.CharField()
    stage_order = serializers.IntegerField()
    deal_count = serializers.IntegerField()
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2)


class PeriodAmountSerializer(serializers.Serializer):
    period = serializers.DateField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    won_count = serializers.IntegerField()


class DashboardSerializer(serializers.Serializer):
    period = serializers.DictField()
    pipeline = PipelineSerializer(allow_null=True)
    kpis = DashboardKpiSerializer()
    leads_by_source = SourceCountSerializer(many=True)
    deals_by_stage = StageAmountSerializer(many=True)
    won_amount_by_period = PeriodAmountSerializer(many=True)


class StageConversionResultSerializer(serializers.Serializer):
    stage_id = serializers.UUIDField()
    stage_name = serializers.CharField()
    stage_kind = serializers.CharField()
    stage_color = serializers.CharField()
    entered_deals = serializers.IntegerField()
    won_deals = serializers.IntegerField()
    conversion_rate = serializers.FloatField()
    current_deals = serializers.IntegerField()
    current_amount = serializers.DecimalField(max_digits=12, decimal_places=2)


class StageConversionReportSerializer(serializers.Serializer):
    period = serializers.DictField()
    pipeline = PipelineSerializer(allow_null=True)
    results = StageConversionResultSerializer(many=True)


class OwnerConversionResultSerializer(serializers.Serializer):
    owner_id = serializers.UUIDField(allow_null=True)
    owner_name = serializers.CharField()
    owner_email = serializers.CharField(allow_null=True)
    total_deals = serializers.IntegerField()
    open_deals = serializers.IntegerField()
    won_deals = serializers.IntegerField()
    lost_deals = serializers.IntegerField()
    open_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    won_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    conversion_rate = serializers.FloatField()


class OwnerConversionReportSerializer(serializers.Serializer):
    period = serializers.DictField()
    results = OwnerConversionResultSerializer(many=True)


class SourceProfitabilityResultSerializer(serializers.Serializer):
    source_id = serializers.UUIDField(allow_null=True)
    source_name = serializers.CharField()
    total_leads = serializers.IntegerField()
    total_deals = serializers.IntegerField()
    won_deals = serializers.IntegerField()
    won_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    open_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    conversion_rate = serializers.FloatField()


class SourceProfitabilityReportSerializer(serializers.Serializer):
    period = serializers.DictField()
    results = SourceProfitabilityResultSerializer(many=True)
