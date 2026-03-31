from django.urls import path
from . import views

app_name = "admin_panel"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("controllers/", views.controllers_list, name="controllers_list"),
    path("controllers/<int:cid>/", views.controller_edit, name="controller_edit"),
    path("training/", views.training_list, name="training_list"),
    path("training/<int:pk>/", views.training_manage, name="training_manage"),
    path("events/", views.events_list, name="events_list"),
    path("events/create/", views.event_create, name="event_create"),
    path("events/<int:pk>/edit/", views.event_edit, name="event_edit"),
    path("feedback/", views.feedback_list, name="feedback_list"),
    path("feedback/<int:pk>/", views.feedback_review, name="feedback_review"),
    path("training/courses/", views.training_courses, name="training_courses"),
    path("training/courses/new/", views.training_course_edit, name="training_course_create"),
    path("training/courses/<int:pk>/", views.training_course_edit, name="training_course_edit"),
    path("roles/", views.roles_manage, name="roles_manage"),
    path("config/", views.site_config, name="site_config"),
    path("dev/", views.dev_tools, name="dev_tools"),
    path("dev/trigger/", views.dev_trigger_task, name="dev_trigger_task"),
    path("dev/clear-cache/", views.dev_clear_cache, name="dev_clear_cache"),
]
