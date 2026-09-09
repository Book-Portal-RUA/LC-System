"""
URL configuration for the Student Assessment System (GEP) project.
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('', include('gep.urls')),
]
