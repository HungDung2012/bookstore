from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import Book, Staff, Category, Publisher
from .serializers import BookSerializer, CategorySerializer, PublisherSerializer

class BookListCreate(APIView):
    def get(self, request):
        books = Book.objects.all()
        serializer = BookSerializer(books, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = BookSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class BookDetail(APIView):
    def get(self, request, pk):
        book = get_object_or_404(Book, pk=pk)
        return Response(BookSerializer(book).data)

    def put(self, request, pk):
        book = get_object_or_404(Book, pk=pk)
        serializer = BookSerializer(book, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        book = get_object_or_404(Book, pk=pk)
        book.delete()
        return Response({"message": "Book deleted"}, status=status.HTTP_204_NO_CONTENT)

class CategoryList(APIView):
    def get(self, request):
        categories = Category.objects.all()
        return Response(CategorySerializer(categories, many=True).data)

class PublisherList(APIView):
    def get(self, request):
        publishers = Publisher.objects.all()
        return Response(PublisherSerializer(publishers, many=True).data)

class UpdatePrice(APIView):
    def put(self, request, pk):
        staff_id = request.data.get("staff_id")
        new_price = request.data.get("price")
        
        if not staff_id or not new_price:
            return Response({"error": "staff_id and price are required"}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            Staff.objects.get(id=staff_id)
        except Staff.DoesNotExist:
            return Response({"error": "Unauthorized. Staff not found."}, status=status.HTTP_403_FORBIDDEN)
            
        book = get_object_or_404(Book, pk=pk)
        book.price = new_price
        book.save()
        
        return Response(BookSerializer(book).data)

class AddPromotion(APIView):
    def post(self, request, pk):
        staff_id = request.data.get("staff_id")
        discount_percentage = request.data.get("discount_percentage")
        
        if not staff_id or discount_percentage is None:
            return Response({"error": "staff_id and discount_percentage are required"}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            Staff.objects.get(id=staff_id)
        except Staff.DoesNotExist:
            return Response({"error": "Unauthorized. Staff not found."}, status=status.HTTP_403_FORBIDDEN)
            
        book = get_object_or_404(Book, pk=pk)
        
        try:
            discount = float(discount_percentage)
            if not (0 <= discount <= 100):
                return Response({"error": "Discount must be between 0 and 100"}, status=status.HTTP_400_BAD_REQUEST)
                
            book.price = float(book.price) * (1 - (discount / 100))
            book.save()
        except ValueError:
             return Response({"error": "Invalid discount format"}, status=status.HTTP_400_BAD_REQUEST)
             
        return Response(BookSerializer(book).data)
