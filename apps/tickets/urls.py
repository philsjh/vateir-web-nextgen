from django.urls import path
from . import views

app_name = "tickets"

urlpatterns = [
    # User-facing
    path("", views.ticket_list, name="list"),
    path("create/", views.ticket_create, name="create"),

    # Staff management (admin panel) — must come before <str:reference> catch-all
    path("manage/", views.staff_ticket_list, name="staff_list"),
    path("manage/<str:reference>/", views.staff_ticket_detail, name="staff_detail"),
    path("manage/<str:reference>/assign/", views.staff_ticket_assign, name="staff_assign"),
    path("manage/<str:reference>/status/", views.staff_ticket_status, name="staff_status"),
    path("manage/<str:reference>/priority/", views.staff_ticket_priority, name="staff_priority"),
    path("manage/<str:reference>/reply/", views.staff_ticket_reply, name="staff_reply"),

    # User-facing detail — must come after manage/ routes
    path("<str:reference>/", views.ticket_detail, name="detail"),
    path("<str:reference>/reply/", views.ticket_reply, name="reply"),
]
