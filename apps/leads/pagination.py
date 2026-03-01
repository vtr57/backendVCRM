from rest_framework.pagination import PageNumberPagination


class LeadPagination(PageNumberPagination):
    page_size = 10
