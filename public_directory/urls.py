from django.urls import path
from .views import public_helpdesk_directory

urlpatterns = [
    path("", public_helpdesk_directory, name="public_helpdesk_directory"),
]