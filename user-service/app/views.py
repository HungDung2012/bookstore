from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import User
from .serializers import UserRegisterSerializer, UserLoginSerializer, UserProfileSerializer
from .utils import generate_token, decode_token


class RegisterView(APIView):
    """POST /auth/register/ — Đăng ký tài khoản mới"""
    def post(self, request):
        serializer = UserRegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            token = generate_token(user)
            return Response({
                'message': 'Registration successful',
                'token': token,
                'user': UserProfileSerializer(user).data,
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    """POST /auth/login/ — Đăng nhập, trả về JWT token"""
    def post(self, request):
        serializer = UserLoginSerializer(data=request.data)
        if serializer.is_valid():
            username = serializer.validated_data['username']
            password = serializer.validated_data['password']
            try:
                user = User.objects.get(username=username)
                if not user.is_active:
                    return Response({'error': 'Account is disabled'}, status=status.HTTP_403_FORBIDDEN)
                if user.check_password(password):
                    token = generate_token(user)
                    return Response({
                        'token': token,
                        'user': UserProfileSerializer(user).data,
                    })
                else:
                    return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
            except User.DoesNotExist:
                return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProfileView(APIView):
    """GET /auth/profile/ — Lấy thông tin user từ JWT token
       PUT /auth/profile/ — Cập nhật profile"""
    def get(self, request):
        user = self._get_user_from_token(request)
        if not user:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(UserProfileSerializer(user).data)

    def put(self, request):
        user = self._get_user_from_token(request)
        if not user:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
        serializer = UserProfileSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def _get_user_from_token(self, request):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return None
        token = auth_header.split(' ')[1]
        payload = decode_token(token)
        if not payload:
            return None
        try:
            return User.objects.get(id=payload['user_id'])
        except User.DoesNotExist:
            return None


class VerifyTokenView(APIView):
    """POST /auth/verify/ — Xác minh token (dùng bởi API Gateway và các service khác)"""
    def post(self, request):
        token = request.data.get('token', '')
        payload = decode_token(token)
        if payload:
            try:
                user = User.objects.get(id=payload['user_id'])
                return Response({
                    'valid': True,
                    'user': UserProfileSerializer(user).data,
                })
            except User.DoesNotExist:
                pass
        return Response({'valid': False}, status=status.HTTP_401_UNAUTHORIZED)


class UserListView(APIView):
    """GET /users/ — Danh sách users (admin only, hoặc cho internal service calls)"""
    def get(self, request):
        users = User.objects.all()
        serializer = UserProfileSerializer(users, many=True)
        return Response(serializer.data)


class UserDetailView(APIView):
    """GET /users/<id>/ — Lấy thông tin 1 user (cho internal service calls)"""
    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        return Response(UserProfileSerializer(user).data)
