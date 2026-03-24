from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db.models import Avg, Count
from .models import Review
from .serializers import ReviewSerializer


class ReviewListCreate(APIView):
    """GET /reviews/?book_id=X — Lấy reviews theo sách
       GET /reviews/?user_id=X — Lấy reviews theo user
       POST /reviews/ — Tạo review mới"""
    def get(self, request):
        book_id = request.query_params.get('book_id')
        user_id = request.query_params.get('user_id')
        reviews = Review.objects.all()
        if book_id:
            reviews = reviews.filter(book_id=book_id)
        if user_id:
            reviews = reviews.filter(user_id=user_id)
        return Response(ReviewSerializer(reviews, many=True).data)

    def post(self, request):
        serializer = ReviewSerializer(data=request.data)
        if serializer.is_valid():
            # Check if user already reviewed this book
            book_id = serializer.validated_data['book_id']
            user_id = serializer.validated_data['user_id']
            existing = Review.objects.filter(book_id=book_id, user_id=user_id).first()
            if existing:
                # Update existing review instead of creating duplicate
                for key, val in serializer.validated_data.items():
                    setattr(existing, key, val)
                existing.save()
                return Response(ReviewSerializer(existing).data)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ReviewDetailView(APIView):
    """GET /reviews/<id>/ — Chi tiết
       PUT /reviews/<id>/ — Cập nhật
       DELETE /reviews/<id>/ — Xóa"""
    def get(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        return Response(ReviewSerializer(review).data)

    def put(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        serializer = ReviewSerializer(review, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        review.delete()
        return Response({"message": "Review deleted"}, status=status.HTTP_204_NO_CONTENT)


class BookRatingView(APIView):
    """GET /reviews/rating/<book_id>/ — Lấy rating trung bình và số lượng đánh giá"""
    def get(self, request, book_id):
        stats = Review.objects.filter(book_id=book_id).aggregate(
            avg_rating=Avg('rating'),
            total_reviews=Count('id'),
        )
        # Distribution
        distribution = {}
        for i in range(1, 6):
            distribution[f"{i}_star"] = Review.objects.filter(book_id=book_id, rating=i).count()
        return Response({
            "book_id": book_id,
            "average_rating": round(stats['avg_rating'], 1) if stats['avg_rating'] else 0,
            "total_reviews": stats['total_reviews'],
            "distribution": distribution,
        })
