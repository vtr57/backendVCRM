from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.core.throttling import AuthRateThrottle
from apps.users.serializers import (
    LoginSerializer,
    OrganizationSerializer,
    RegisterSerializer,
    build_auth_payload,
    build_token_pair_for_user,
)
from apps.users.services import resolve_membership_for_request


class RegisterAPIView(GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer
    throttle_classes = [AuthRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, membership = serializer.save()

        return Response(
            build_token_pair_for_user(user, current_membership=membership),
            status=status.HTTP_201_CREATED,
        )


class LoginAPIView(TokenObtainPairView):
    permission_classes = [AllowAny]
    serializer_class = LoginSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class RefreshAPIView(TokenRefreshView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class MeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        current_membership = resolve_membership_for_request(request, request.user)
        request.organization = current_membership.organization
        request.membership = current_membership

        return Response(
            {
                "user": build_auth_payload(
                    request.user,
                    current_membership=current_membership,
                ),
                "organization": OrganizationSerializer(current_membership.organization).data,
            }
        )
