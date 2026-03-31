from django.urls import path
from . import views

app_name = "training"

urlpatterns = [
    # Student
    path("", views.my_training, name="my_training"),
    path("request/", views.request_training, name="request_training"),
    path("<int:pk>/", views.training_detail, name="detail"),
    path("report/<int:session_pk>/", views.view_report, name="view_report"),

    # Mentor
    path("mentor/", views.mentor_dashboard, name="mentor_dashboard"),
    path("<int:pk>/log-session/", views.log_session, name="log_session"),
    path("report/<int:session_pk>/write/", views.write_report, name="write_report"),

    # Staff — board & waiting list
    path("board/", views.training_board, name="board"),
    path("board/move/", views.board_move_card, name="board_move_card"),
    path("waiting-list/", views.waiting_list, name="waiting_list"),
    path("waiting-list/reorder/", views.reorder_waiting_list, name="reorder_waiting_list"),
    path("waiting-list/<int:pk>/remove/", views.remove_from_waiting, name="remove_from_waiting"),

    # Staff — reports
    path("reports/", views.training_reports, name="reports"),
]
