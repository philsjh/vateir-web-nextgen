from django.urls import path
from . import views

app_name = "training"

urlpatterns = [
    path("", views.my_training, name="my_training"),
    path("request/", views.request_training, name="request_training"),
    path("<int:pk>/", views.training_detail, name="detail"),
    path("mentor/", views.mentor_dashboard, name="mentor_dashboard"),
    path("<int:pk>/log-session/", views.log_session, name="log_session"),
]
