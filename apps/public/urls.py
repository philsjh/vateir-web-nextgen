from django.urls import path
from . import views

app_name = "public"

urlpatterns = [
    path("", views.homepage, name="homepage"),
    path("staff/", views.staff_page, name="staff"),
    path("info/<slug:slug>/", views.info_page, name="info_page"),
]
