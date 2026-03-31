from django.urls import path
from . import views

app_name = "controllers"

urlpatterns = [
    path("", views.roster, name="roster"),
    path("search/", views.search_api, name="search_api"),
    path("<int:cid>/", views.detail, name="detail"),
]
