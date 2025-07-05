# health_app/services.py
import os
from huggingface_hub import InferenceClient
from .models import PatientRecord

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Get the API key from environment variables
api_key = os.getenv("HUGGING_FACE_API_KEY")
if not api_key:
    raise ValueError("HUGGING_FACE_API_KEY not found in environment variables.")

# --- THIS IS THE CORRECTED PART ---
# The token is passed during the client's initialization.
client = InferenceClient(token=api_key)
# --- END OF CORRECTION ---

# This is the model we will use. It's powerful and popular.
MODEL_NAME = "mistralai/Mistral-7B-Instruct-v0.2"

def generate_risk_assessment_for_record(patient_record: PatientRecord) -> str:
    """
    Takes a PatientRecord model instance, sends its data to the Hugging Face API,
    and returns the generated text report.
    """
    patient_data_string = f"""
    - Glucose: {patient_record.glucose} mg/dL
    - HbA1c: {patient_record.hba1c} %
    - Total Cholesterol: {patient_record.total_cholesterol} mg/dL
    - LDL: {patient_record.ldl} mg/dL
    - HDL: {patient_record.hdl} mg/dL
    - Triglycerides: {patient_record.triglycerides} mg/dL
    - ALT: {patient_record.alt} U/L
    - AST: {patient_record.ast} U/L
    - Creatinine: {patient_record.creatinine} mg/dL
    - Urea: {patient_record.urea} mg/dL
    - CRP: {patient_record.crp} mg/L
    - WBC: {patient_record.wbc} x10^9/L
    """

    prompt = f"""<s>[INST]
    **ROLE AND GOAL:**
    You are an AI clinical decision support assistant. Your purpose is to analyze patient blood test results and provide a clear, concise risk assessment based ONLY on the provided thresholds. You must identify markers that are outside the normal range and explain the potential risks associated with them. Do not provide a medical diagnosis. The output must be in well-structured Markdown format.

    **RISK THRESHOLDS (Strictly Adhere to These):**
    - **Glucose:** High if >= 126 mg/dL (Indicates risk for Type 2 Diabetes, Metabolic Syndrome).
    - **HbA1c:** Pre-diabetes if 5.7-6.4%, Diabetes if >= 6.5%.
    - **Total Cholesterol:** High if > 200 mg/dL (Indicates risk for Cardiovascular Disease).
    - **LDL:** High if > 130 mg/dL (Indicates risk for Heart disease, Stroke).
    - **HDL:** Low (high risk) if < 40 mg/dL (Low HDL increases CVD risk).
    - **Triglycerides:** High if > 150 mg/dL (Indicates risk for CVD, Pancreatitis).
    - **ALT:** High if > 40 U/L (Indicates risk for Liver disease, Fatty liver, Cirrhosis).
    - **AST:** High if > 35 U/L (Indicates risk for Liver disease, Fatty liver, Cirrhosis).
    - **Creatinine:** High if > 1.3 mg/dL (Indicates risk for Kidney disease).
    - **Urea:** High if > 50 mg/dL (Indicates risk for Kidney disease).
    - **CRP:** High risk if > 3 mg/L (Indicates risk for Chronic inflammation, CVD, Cancer).
    - **WBC:** High if > 11 x10^9/L (Indicates risk for Chronic infections, Inflammation, Cancer).

    **PATIENT DATA TO ANALYZE:**
    {patient_data_string}

    **REQUIRED OUTPUT FORMAT:**
    Generate a report with the following markdown sections exactly as specified:

    ### Overall Risk Summary
    (A brief, one-paragraph summary of the key findings and most significant risks based on the data.)

    ### Markers of Concern
    (A bulleted list. For EACH marker outside the normal range, state its value, the threshold, and the specific NCDs/risks it indicates. If all markers are normal, state "All markers are within the normal range.")

    ### Recommendations for Reviewer
    (A bulleted list of general next steps a clinician might consider based on the findings. For example: 'Elevated glucose and HbA1c may warrant formal diabetes screening.' or 'High LDL and Total Cholesterol suggest a review of the patient's cardiovascular risk profile.')
    [/INST]"""

    try:
        # --- START OF NEW, MORE ROBUST CLEANING LOGIC ---

        messages = [{"role": "user", "content": prompt}]
        response = client.chat_completion(
            messages=messages,
            model=MODEL_NAME,
            max_tokens=2048,
        )
        
        raw_report = response.choices[0].message.content

        # 1. Define the known start of our real content.
        anchor = "### Overall Risk Summary"
        
        # 2. Find the position of this anchor in the report.
        anchor_position = raw_report.find(anchor)
        
        if anchor_position != -1:
            # 3. If the anchor is found, slice the string from that point.
            cleaned_report = raw_report[anchor_position:]
        else:
            # 4. If, for some reason, the anchor is missing, use the raw report but strip it.
            # This makes the function resilient to unexpected AI outputs.
            cleaned_report = raw_report.strip()

        # 5. Finally, remove any trailing backticks just in case.
        final_report = cleaned_report.replace("```", "").strip()

        return final_report

        # --- END OF NEW, MORE ROBUST CLEANING LOGIC ---
    except Exception as e:
        print(f"Error calling Hugging Face API: {e}")
        return f"Error: Could not generate AI assessment with Hugging Face. Please try again later. Details: {e}"