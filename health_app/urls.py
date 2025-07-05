# health_app/urls.py
from django.urls import path
from django.contrib.auth.views import LogoutView
from . import views

urlpatterns = [

    path('', views.CustomLoginView.as_view(), name='home'),
    # Registration & Auth
    path('register/', views.HospitalRegistrationView.as_view(), name='register'),
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),

    # Dashboards
    path('dashboard/', views.DashboardRedirectView.as_view(), name='dashboard_redirect'),
    path('manage/dashboard/', views.AdminDashboardView.as_view(), name='admin_dashboard'),
    path('doctor/dashboard/', views.DoctorDashboardView.as_view(), name='doctor_dashboard'),
    path('manage/upload-csv/', views.UploadCSVView.as_view(), name='upload_csv'),
    path('manage/add-patient/', views.AddPatientView.as_view(), name='add_patient'),
    path('patients/', views.PatientListView.as_view(), name='patient_list'),
    path('patients/<int:pk>/delete/', views.DeletePatientView.as_view(), name='delete_patient'),
    path('patient/<int:pk>/analyze/', views.AnalyzePatientRecordView.as_view(), name='analyze_record'),
    path('assessment/<int:pk>/', views.AssessmentDetailView.as_view(), name='view_assessment'),
    path('manage/export-reports/', views.export_reviewed_reports_csv, name='export_reports_csv'),
    path('assessment/<int:pk>/assign/', views.AssignDoctorView.as_view(), name='assign_doctor'),

    # Admin Actions
    path('manage/invite-doctor/', views.InviteDoctorView.as_view(), name='invite_doctor'),
]