from django.urls import path

from . import views

urlpatterns = [
    path("", views.start, name="start"),
    path("apply/<uuid:application_id>/step/<str:step_key>/", views.step, name="step"),
    path("apply/<uuid:application_id>/review/", views.review, name="review"),
    path("apply/<uuid:application_id>/result/", views.result, name="result"),
    path("apply/<uuid:application_id>/audit/", views.audit_trail, name="audit_trail"),
    path("resume/", views.resume_entry, name="resume_entry"),
    path("resume/<str:token>/", views.resume_magic_link, name="resume_magic_link"),
]
