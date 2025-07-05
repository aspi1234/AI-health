# health_app/forms.py
from django import forms
from .models import User,PatientRecord, RiskAssessment

class HospitalRegistrationForm(forms.Form):
    hospital_name = forms.CharField(max_length=200, required=True, widget=forms.TextInput(attrs={'placeholder': 'General Hospital'}))
    first_name = forms.CharField(max_length=150, required=True, widget=forms.TextInput(attrs={'placeholder': 'John'}))
    last_name = forms.CharField(max_length=150, required=True, widget=forms.TextInput(attrs={'placeholder': 'Doe'}))
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'placeholder': 'admin@hospital.com'}))
    password = forms.CharField(widget=forms.PasswordInput, required=True)
    password_confirm = forms.CharField(widget=forms.PasswordInput, required=True, label="Confirm Password")

    def clean_email(self):
        email = self.cleaned_data.get('email').lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")
        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError("Passwords do not match.")
        return cleaned_data

class DoctorInvitationForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].widget.attrs['placeholder'] = 'Jane'
        self.fields['last_name'].widget.attrs['placeholder'] = 'Smith'
        self.fields['email'].widget.attrs['placeholder'] = 'doctor@hospital.com'

    def clean_email(self):
        email = self.cleaned_data.get('email').lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

class CSVUploadForm(forms.Form):
    csv_file = forms.FileField(
        label="Select a CSV file",
        help_text="File must be in CSV format with specific headers.",
        widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.csv'})
    )

    def clean_csv_file(self):
        file = self.cleaned_data.get('csv_file')
        if not file.name.endswith('.csv'):
            raise forms.ValidationError("Invalid file type. Please upload a .csv file.")
        return file

class ManualPatientForm(forms.ModelForm):
    class Meta:
        model = PatientRecord
        # Define the fields to show in the form
        fields = [
            'patient_identifier', 'glucose', 'hba1c', 'total_cholesterol', 'ldl',
            'hdl', 'triglycerides', 'alt', 'ast', 'creatinine', 'urea', 'crp', 'wbc'
        ]
        # Add Bootstrap classes and placeholders to the widgets
        widgets = {
            'patient_identifier': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., P001 or MRN-456'}),
            'glucose': forms.NumberInput(attrs={'class': 'form-control'}),
            'hba1c': forms.NumberInput(attrs={'class': 'form-control'}),
            'total_cholesterol': forms.NumberInput(attrs={'class': 'form-control'}),
            'ldl': forms.NumberInput(attrs={'class': 'form-control'}),
            'hdl': forms.NumberInput(attrs={'class': 'form-control'}),
            'triglycerides': forms.NumberInput(attrs={'class': 'form-control'}),
            'alt': forms.NumberInput(attrs={'class': 'form-control'}),
            'ast': forms.NumberInput(attrs={'class': 'form-control'}),
            'creatinine': forms.NumberInput(attrs={'class': 'form-control'}),
            'urea': forms.NumberInput(attrs={'class': 'form-control'}),
            'crp': forms.NumberInput(attrs={'class': 'form-control'}),
            'wbc': forms.NumberInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        # We need to know the hospital to check for unique patient_identifier
        self.hospital = kwargs.pop('hospital', None)
        super(ManualPatientForm, self).__init__(*args, **kwargs)

    def clean_patient_identifier(self):
        identifier = self.cleaned_data.get('patient_identifier')
        # Check if a record with this ID already exists in this hospital
        if self.hospital and PatientRecord.objects.filter(hospital=self.hospital, patient_identifier=identifier).exists():
            raise forms.ValidationError(f"A patient with the identifier '{identifier}' already exists in your hospital.")
        return identifier

class DoctorReviewForm(forms.ModelForm):
    class Meta:
        model = RiskAssessment
        fields = ['doctor_comments']
        widgets = {
            'doctor_comments': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 5,
                    'placeholder': 'Enter your final assessment and recommendations here...'
                }
            ),
        }
        labels = {
            'doctor_comments': "Doctor's Final Review and Comments"
        }