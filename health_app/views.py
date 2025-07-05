# health_app/views.py
import csv
import io
import random
import string
import markdown
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.views.generic import ListView,DetailView
from django.shortcuts import render, redirect
from django.views import View
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.db.models import Q


from .models import User, Hospital, PatientRecord,RiskAssessment
from .services import generate_risk_assessment_for_record
from .forms import (
    HospitalRegistrationForm, DoctorInvitationForm, CSVUploadForm,
    ManualPatientForm,DoctorReviewForm
)

# --- Role Checking Mixins for Security ---
class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.role == User.Role.HOSPITAL_ADMIN

class DoctorRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.role == User.Role.DOCTOR

# --- Registration and Login ---
class HospitalRegistrationView(View):
    def get(self, request):
        form = HospitalRegistrationForm()
        return render(request, 'registration/register.html', {'form': form})

    def post(self, request):
        form = HospitalRegistrationForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            try:
                with transaction.atomic():
                    hospital = Hospital.objects.create(name=data['hospital_name'])
                    admin_user = User(
                        username=data['email'], email=data['email'],
                        first_name=data['first_name'], last_name=data['last_name'],
                        role=User.Role.HOSPITAL_ADMIN, hospital=hospital
                    )
                    admin_user.set_password(data['password'])
                    admin_user.save()
            except Exception as e:
                form.add_error(None, "There was an error during registration. Please try again.")
                return render(request, 'registration/register.html', {'form': form})
            login(request, admin_user)
            return redirect('dashboard_redirect')
        return render(request, 'registration/register.html', {'form': form})

class CustomLoginView(LoginView):
    template_name = 'registration/login.html'
    redirect_authenticated_user = True

# --- Dashboards & Redirects ---
class DashboardRedirectView(LoginRequiredMixin, View):
    """
    Redirects users to the correct dashboard based on their role.
    This view only needs a 'get' method.
    """
    def get(self, request):
        user = request.user
        if user.role == User.Role.HOSPITAL_ADMIN:
            return redirect('admin_dashboard')
        elif user.role == User.Role.DOCTOR:
            return redirect('doctor_dashboard')
        else:
            # Fallback for any other case
            return redirect('login')


class AdminDashboardView(AdminRequiredMixin, View):
    def get(self, request):
        newly_uploaded_ids = request.session.get('newly_uploaded_ids', [])
        new_records = []
        if newly_uploaded_ids:
            new_records = PatientRecord.objects.filter(pk__in=newly_uploaded_ids)
            # Clear the session variable after use
            del request.session['newly_uploaded_ids']
        context = {'new_records': new_records}
        return render(request, 'health_app/admin_dashboard.html', context)

class DoctorDashboardView(DoctorRequiredMixin, ListView):
    model = RiskAssessment
    template_name = 'health_app/doctor_dashboard.html'
    context_object_name = 'pending_assessments'
    paginate_by = 10

    def get_queryset(self):
        """
        Builds the doctor's worklist. A doctor sees reports that are:
        - Assigned directly to them
        OR
        - Unassigned and belong to their hospital.
        This uses the new "Assign Doctor" logic.
        """
        user = self.request.user

        # Q objects allow for complex queries with OR conditions.
        assigned_to_me = Q(assigned_doctor=user)
        unassigned_in_my_hospital = Q(assigned_doctor__isnull=True)

        queryset = RiskAssessment.objects.filter(
            (assigned_to_me | unassigned_in_my_hospital),  # The core logic
            status=RiskAssessment.Status.PENDING_REVIEW,
            patient_record__hospital=user.hospital
        ).select_related(
            'patient_record',
            'assigned_doctor'
        ).order_by('assigned_doctor', '-patient_record__created_at') # Show assigned first, then newest unassigned

        return queryset

    def get_context_data(self, **kwargs):
        """
        Add extra context, such as a title.
        """
        context = super().get_context_data(**kwargs)
        context['page_title'] = "Pending Reviews"
        return context

# --- Doctor Invitation ---
class InviteDoctorView(AdminRequiredMixin, View):
    # ... (This view remains unchanged)
    def get(self, request):
        form = DoctorInvitationForm()
        return render(request, 'health_app/invite_doctor.html', {'form': form})

    def post(self, request):
        form = DoctorInvitationForm(request.POST)
        if form.is_valid():
            new_doctor_user = form.save(commit=False)
            new_doctor_user.username = new_doctor_user.email
            new_doctor_user.role = User.Role.DOCTOR
            new_doctor_user.hospital = request.user.hospital
            temp_password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
            new_doctor_user.set_password(temp_password)
            new_doctor_user.save()
            return render(request, 'health_app/invite_success.html', {
                'doctor_email': new_doctor_user.email,
                'temp_password': temp_password
            })
        return render(request, 'health_app/invite_doctor.html', {'form': form})

# --- Data Entry Views ---
class AddPatientView(AdminRequiredMixin, View):
    def get(self, request):
        form = ManualPatientForm(hospital=request.user.hospital)
        return render(request, 'health_app/add_patient.html', {'form': form})
    
    def post(self, request):
        form = ManualPatientForm(request.POST, hospital=request.user.hospital)
        if form.is_valid():
            patient_record = form.save(commit=False)
            patient_record.hospital = request.user.hospital
            patient_record.uploaded_by = request.user
            patient_record.save()
            request.session['newly_uploaded_ids'] = [patient_record.pk]
            messages.success(request, f"Successfully added record for patient {patient_record.patient_identifier}.")
            return redirect('admin_dashboard')
        return render(request, 'health_app/add_patient.html', {'form': form})

class UploadCSVView(AdminRequiredMixin, View):
    def get(self, request):
        form = CSVUploadForm()
        return render(request, 'health_app/upload_csv.html', {'form': form})

    def post(self, request):
        form = CSVUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, 'health_app/upload_csv.html', {'form': form})

        csv_file = request.FILES['csv_file']
        try:
            decoded_file = csv_file.read().decode('utf-8')
            io_string = io.StringIO(decoded_file)
            reader = csv.DictReader(io_string)
            rows = list(reader)
            if not rows:
                raise ValueError("The CSV file is empty.")
        except Exception:
            messages.error(request, "Error reading file. Ensure it is a valid UTF-8 encoded CSV.")
            return render(request, 'health_app/upload_csv.html', {'form': form})

        new_record_ids = []
        try:
            with transaction.atomic():
                # --- START OF ROBUST UNIQUENESS CHECKS ---
                # 1. Get all patient identifiers from the CSV, checking for missing values.
                csv_identifiers = []
                for i, row in enumerate(rows):
                    identifier = row.get('patient_identifier')
                    if not identifier or not identifier.strip():
                        raise ValueError(f"Row {i+2} is missing a patient_identifier.")
                    csv_identifiers.append(identifier.strip())

                # 2. Check for duplicates WITHIN the CSV file itself.
                if len(csv_identifiers) != len(set(csv_identifiers)):
                    raise ValueError("The CSV file contains duplicate patient identifiers. Please correct the file.")

                # 3. Check for duplicates against the DATABASE.
                existing_identifiers_in_db = set(PatientRecord.objects.filter(
                    hospital=request.user.hospital,
                    patient_identifier__in=csv_identifiers
                ).values_list('patient_identifier', flat=True))

                conflicting_ids = set(csv_identifiers).intersection(existing_identifiers_in_db)
                if conflicting_ids:
                    raise ValueError(f"The following patient identifiers already exist in your hospital: {', '.join(conflicting_ids)}")
                # --- END OF ROBUST UNIQUENESS CHECKS ---

                for row in rows:
                    patient_identifier_val = row.pop('patient_identifier', None).strip()
                    cleaned_row = {k.lower().strip(): (float(v) if v and v.strip() else None) for k, v in row.items()}
                    cleaned_row['patient_identifier'] = patient_identifier_val

                    new_record = PatientRecord.objects.create(
                        hospital=request.user.hospital, uploaded_by=request.user,
                        **cleaned_row # Use dictionary unpacking for cleaner code
                    )
                    new_record_ids.append(new_record.pk)

        except (ValueError, TypeError) as e:
            messages.error(request, f"Error processing file: {e}. The upload has been cancelled.")
            return render(request, 'health_app/upload_csv.html', {'form': form})
        except Exception as e:
            messages.error(request, f"An unexpected error occurred: {e}. The upload has been cancelled.")
            return render(request, 'health_app/upload_csv.html', {'form': form})

        request.session['newly_uploaded_ids'] = new_record_ids
        messages.success(request, f"Successfully uploaded and created {len(new_record_ids)} patient records for verification.")
        return redirect('admin_dashboard')

# --- Patient Management Views ---
class PatientListView(LoginRequiredMixin, ListView):
    model = PatientRecord
    template_name = 'health_app/patient_list.html'
    context_object_name = 'patients'
    paginate_by = 15 # Shows 15 patients per page

    def get_queryset(self):
        """
        This is the core security feature. It ensures that users can only see
        patients from their own hospital.
        """
        user = self.request.user
        # Start with a base queryset
        queryset = super().get_queryset()
        # Filter by the user's hospital
        return queryset.filter(hospital=user.hospital).select_related('assessment').order_by('-created_at')

    def get_context_data(self, **kwargs):
        """
        Add extra context to the template.
        """
        context = super().get_context_data(**kwargs)
        context['page_title'] = "Patient Records"
        return context

# --- view for deleting records---
class DeletePatientView(AdminRequiredMixin, View):
    def post(self, request, pk):
        # Get the specific patient record we want to delete, or return a 404 error if it doesn't exist.
        patient_record = get_object_or_404(PatientRecord, pk=pk)

        # Critical security check: Ensure the record belongs to the logged-in user's hospital.
        # This prevents a user from one hospital from deleting records of another via a crafted URL.
        if patient_record.hospital != request.user.hospital:
            messages.error(request, "You are not authorized to perform this action.")
            return redirect('patient_list')

        # If all checks pass, store the identifier for the message, then delete the object.
        record_identifier = patient_record.patient_identifier
        patient_record.delete()

        # Flash a success message to the user.
        messages.success(request, f"The record for patient '{record_identifier}' has been successfully deleted.")
        return redirect('patient_list')

class AnalyzePatientRecordView(AdminRequiredMixin, View):
    def post(self, request, pk):
        # 1. Get the patient record, ensuring it exists
        patient_record = get_object_or_404(PatientRecord, pk=pk)

        # 2. Security Check: Ensure the record belongs to the admin's hospital
        if patient_record.hospital != request.user.hospital:
            messages.error(request, "You are not authorized to analyze this record.")
            return redirect('admin_dashboard')

        # 3. Prevent Duplicate Analysis: Check if an assessment already exists
        if RiskAssessment.objects.filter(patient_record=patient_record).exists():
            messages.warning(request, f"An assessment for patient {patient_record.patient_identifier} already exists.")
            return redirect('admin_dashboard')

        # 4. Call the AI Service
        ai_report = generate_risk_assessment_for_record(patient_record)

        # 5. Check for errors from the API call
        if ai_report.startswith("Error:"):
            messages.error(request, ai_report)
            return redirect('admin_dashboard')

        # 6. Create the RiskAssessment object in the database
        RiskAssessment.objects.create(
            patient_record=patient_record,
            ai_generated_report=ai_report
            # The status defaults to PENDING_REVIEW as per your model
        )

        messages.success(request, f"AI analysis complete for patient {patient_record.patient_identifier}. The report is now ready for doctor review.")
        return redirect('admin_dashboard')

class DoctorOrAdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.role in [User.Role.HOSPITAL_ADMIN, User.Role.DOCTOR]
    
class AssessmentDetailView(DoctorOrAdminRequiredMixin, View):
    def get(self, request, pk):
        # Fetch the assessment and related patient data in one query
        assessment = get_object_or_404(
            RiskAssessment.objects.select_related(
                'patient_record', 
                'patient_record__uploaded_by',
                'reviewed_by' # Follow the foreign key relationship
            ), 
            pk=pk
        )
        
        # Security check: Ensure the user belongs to the same hospital as the patient record
        if assessment.patient_record.hospital != request.user.hospital:
            messages.error(request, "You are not authorized to view this record.")
            return redirect('dashboard_redirect')

        # --- NEW, STRICTER SECURITY CHECK ---
        # If the user is a doctor AND the report has an assigned doctor that is NOT them...
        if (request.user.role == User.Role.DOCTOR and 
            assessment.assigned_doctor and 
            assessment.assigned_doctor != request.user):
            
            messages.error(request, "This report is assigned to another doctor and you are not authorized to view it.")
            return redirect('doctor_dashboard')
        # --- END OF NEW CHECK ---
        
        assessment.html_report = markdown.markdown(assessment.ai_generated_report)
        
        form = DoctorReviewForm(instance=assessment)
        
        context = {
            'assessment': assessment,
            'patient': assessment.patient_record,
            'form': form
        }
        return render(request, 'health_app/assessment_detail.html', context)

    def post(self, request, pk):
        assessment = get_object_or_404(RiskAssessment, pk=pk)

        # Security check (only doctors can submit reviews)
        if request.user.role != User.Role.DOCTOR:
            messages.error(request, "Only doctors can submit reviews.")
            return redirect('view_assessment', pk=assessment.pk)
            
        # Security check for hospital
        if assessment.patient_record.hospital != request.user.hospital:
            messages.error(request, "You are not authorized to edit this record.")
            return redirect('dashboard_redirect')

        form = DoctorReviewForm(request.POST, instance=assessment)
        if form.is_valid():
            review = form.save(commit=False)
            review.status = RiskAssessment.Status.REVIEWED
            review.reviewed_by = request.user
            review.reviewed_at = timezone.now()
            review.save()
            messages.success(request, f"Review for patient {assessment.patient_record.patient_identifier} has been successfully submitted.")
            return redirect('doctor_dashboard')
        
        # If form is invalid, re-render the page with errors
        assessment.html_report = markdown.markdown(assessment.ai_generated_report)
        context = {
            'assessment': assessment,
            'patient': assessment.patient_record,
            'form': form
        }
        return render(request, 'health_app/assessment_detail.html', context)

@login_required
def export_reviewed_reports_csv(request):
    """
    Handles the request to download all reviewed risk assessments as a CSV file.
    This view is restricted to Hospital Admins.
    """
    # 1. Security Check: Ensure the user is a Hospital Admin
    if request.user.role != User.Role.HOSPITAL_ADMIN:
        messages.error(request, "You are not authorized to perform this action.")
        return redirect('dashboard_redirect')

    # 2. Prepare the HTTP Response to indicate a CSV download
    response = HttpResponse(
        content_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename="reviewed_reports_{timezone.now().strftime("%Y-%m-%d")}.csv"'},
    )

    # 3. Create a CSV writer
    writer = csv.writer(response)

    # 4. Define CSV Header Row
    # We will include patient data, AI report, and doctor's review details.
    header = [
        'Patient Identifier', 'Glucose', 'HbA1c', 'Total Cholesterol', 'LDL', 'HDL',
        'Triglycerides', 'ALT', 'AST', 'Creatinine', 'Urea', 'CRP', 'WBC',
        'AI Generated Report', 'Doctor Comments', 'Reviewed By (Doctor)', 'Reviewed At'
    ]
    writer.writerow(header)

    # 5. Query the Database for Reviewed Assessments
    # Fetch all assessments marked as 'REVIEWED' for the admin's hospital.
    # Use select_related to efficiently join related models in a single database query.
    reviewed_assessments = RiskAssessment.objects.filter(
        status=RiskAssessment.Status.REVIEWED,
        patient_record__hospital=request.user.hospital
    ).select_related('patient_record', 'reviewed_by').order_by('reviewed_at')

    # 6. Write Data Rows to the CSV
    for assessment in reviewed_assessments:
        patient = assessment.patient_record
        row = [
            patient.patient_identifier,
            patient.glucose,
            patient.hba1c,
            patient.total_cholesterol,
            patient.ldl,
            patient.hdl,
            patient.triglycerides,
            patient.alt,
            patient.ast,
            patient.creatinine,
            patient.urea,
            patient.crp,
            patient.wbc,
            assessment.ai_generated_report,
            assessment.doctor_comments,
            assessment.reviewed_by.get_full_name() if assessment.reviewed_by else 'N/A',
            assessment.reviewed_at.strftime("%Y-%m-%d %H:%M") if assessment.reviewed_at else 'N/A'
        ]
        writer.writerow(row)

    # 7. Return the response
    return response

class AssignDoctorView(AdminRequiredMixin, View):
    """
    Handles the POST request from an admin to assign a doctor to an assessment.
    """
    def post(self, request, pk):
        # 1. Get the assessment object
        assessment = get_object_or_404(RiskAssessment, pk=pk)

        # 2. Security Check: Ensure the assessment belongs to the admin's hospital
        if assessment.patient_record.hospital != request.user.hospital:
            messages.error(request, "You are not authorized to modify this record.")
            return redirect('patient_list')

        # 3. Get the doctor's ID from the form submission
        doctor_id = request.POST.get('doctor_id')
        if not doctor_id:
            messages.error(request, "No doctor was selected.")
            return redirect('patient_list')

        # 4. Get the doctor user object
        try:
            doctor_to_assign = User.objects.get(
                pk=doctor_id,
                hospital=request.user.hospital, # Security: Doctor must be in the same hospital
                role=User.Role.DOCTOR          # Security: User must be a doctor
            )
        except User.DoesNotExist:
            messages.error(request, "The selected doctor could not be found or is invalid.")
            return redirect('patient_list')

        # 5. Perform the assignment
        assessment.assigned_doctor = doctor_to_assign
        assessment.save()

        messages.success(request, f"Report for patient {assessment.patient_record.patient_identifier} has been assigned to Dr. {doctor_to_assign.get_full_name()}.")
        return redirect('patient_list')