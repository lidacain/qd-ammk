from django.urls import path
from .views import activity_dashboard, activity_insights

urlpatterns = [
    path('activity/', activity_dashboard, name='activity_dashboard'),
    path("activity/insights", activity_insights, name="activity_insights"),
]