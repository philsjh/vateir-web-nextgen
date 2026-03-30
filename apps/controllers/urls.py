from django.urls import path
from . import views

app_name = "controllers"

urlpatterns = [
    path("", views.roster, name="roster"),
    path("<int:cid>/", views.detail, name="detail"),
]
