from django.urls import path
from . import views

app_name = "feedback"

urlpatterns = [
    path("", views.submit_feedback, name="submit"),
    path("thanks/", views.thanks, name="thanks"),
]
