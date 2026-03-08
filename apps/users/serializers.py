from django.contrib.auth import authenticate
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import Membership, Organization, User


def build_auth_payload(user, current_membership=None):
    memberships = (
        user.memberships.select_related("organization")
        .filter(is_active=True, organization__is_active=True)
        .order_by("-is_default", "organization__name")
    )
    serializer = AuthUserSerializer(
        user,
        context={
            "memberships": memberships,
            "current_membership": current_membership,
        },
    )
    return serializer.data


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "name", "slug", "plan", "timezone", "currency", "is_active"]


class MembershipSerializer(serializers.ModelSerializer):
    organization = OrganizationSerializer(read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "role", "is_default", "is_active", "joined_at", "organization"]


class TeamMemberSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(source="user.id", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "user_id", "email", "first_name", "last_name", "full_name", "role"]


class AuthUserSerializer(serializers.ModelSerializer):
    memberships = serializers.SerializerMethodField()
    current_membership = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "is_active",
            "date_joined",
            "memberships",
            "current_membership",
        ]

    def get_memberships(self, obj):
        memberships = self.context.get("memberships")
        if memberships is None:
            memberships = obj.memberships.select_related("organization").all()
        return MembershipSerializer(memberships, many=True).data

    def get_current_membership(self, obj):
        membership = self.context.get("current_membership")
        if membership is None:
            return None
        return MembershipSerializer(membership).data


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(validators=[UniqueValidator(queryset=User.objects.all())])
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True, min_length=8)
    organization_name = serializers.CharField(max_length=255)
    organization_slug = serializers.CharField(max_length=255, required=False, allow_blank=True)

    default_error_messages = {
        "password_mismatch": "Passwords do not match.",
        "invalid_slug": "Organization slug is invalid.",
    }

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            self.fail("password_mismatch")
        return attrs

    def validate_organization_slug(self, value):
        if not value:
            return value

        normalized = slugify(value)
        if not normalized:
            self.fail("invalid_slug")
        return normalized

    def _generate_unique_slug(self, base_slug):
        slug = base_slug
        suffix = 2
        while Organization.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{suffix}"
            suffix += 1
        return slug

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop("password")
        validated_data.pop("password_confirm")
        organization_name = validated_data.pop("organization_name")
        organization_slug = validated_data.pop("organization_slug", "")

        user = User.objects.create_user(password=password, **validated_data)

        base_slug = slugify(organization_slug or organization_name)
        if not base_slug:
            self.fail("invalid_slug")

        organization = Organization.objects.create(
            name=organization_name,
            slug=self._generate_unique_slug(base_slug),
        )
        membership = Membership.objects.create(
            user=user,
            organization=organization,
            role=Membership.Role.OWNER,
            is_default=True,
        )
        return user, membership


class LoginSerializer(TokenObtainPairSerializer):
    username_field = User.USERNAME_FIELD

    default_error_messages = {
        "no_active_account": "Unable to log in with the provided credentials.",
    }

    def validate(self, attrs):
        credentials = {
            self.username_field: attrs.get(self.username_field),
            "password": attrs.get("password"),
        }
        user = authenticate(**credentials)
        if user is None or not user.is_active:
            self.fail("no_active_account")

        user.last_login = timezone.now()
        user.save(update_fields=["last_login", "updated_at"])

        refresh = self.get_token(user)
        current_membership = (
            user.memberships.select_related("organization")
            .filter(is_default=True, is_active=True, organization__is_active=True)
            .first()
        )
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": build_auth_payload(user, current_membership=current_membership),
        }


def build_token_pair_for_user(user, current_membership=None):
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": build_auth_payload(user, current_membership=current_membership),
    }
