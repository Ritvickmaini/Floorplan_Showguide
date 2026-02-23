import requests
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import time
import re

# =====================================================
# GOOGLE SHEETS CONFIG
# =====================================================

SHEET_NAME = "Expo-Sales-Management"
SHEET_TAB = "exhibitors-1"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

CREDS_FILE = "/etc/secrets/service_account.json"

# =====================================================
# API CONFIG
# =====================================================

FLOORPLAN_URL = "https://b2bgrowthexpo.com/wp-json/custom-api/v1/protected/floorplan-form-data"
SHOWGUIDE_URL = "https://b2bgrowthexpo.com/wp-json/custom-api/v1/protected/showguide-form-data"

HEADERS = {
    "Authorization": "Bearer e3e6836eb425245556aebc1e0a9e5bfbb41ee9c81ec5db1bc121debc5907fd85"
}

# =====================================================
# HELPERS
# =====================================================

def clean_phone(phone):
    if not phone:
        return ""
    return re.sub(r"\D", "", phone)


def build_row(form_entry, email, show_name, lead_source):
    full_name = form_entry.get("Name", "").strip()

    first_name = ""
    last_name = ""

    if full_name:
        parts = full_name.split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""

    today = datetime.now().strftime("%d/%m/%Y")

    return [
        "",                                  # Assigned To
        today,                               # Lead Date
        lead_source,
        first_name,
        last_name,
        form_entry.get("Company", ""),
        clean_phone(form_entry.get("Phone", "")),
        email,
        show_name,
        "", "", "", "", "", "", "",
        "Exhibitors_opportunity",
        "", "", ""
    ]


# =====================================================
# PHASE 1 - FLOORPLAN
# =====================================================

def process_floorplan(data, existing_emails, new_rows):
    print("🔵 Processing Floor Plan entries...")

    for item in data:

        form_entry = item.get("Form_Entry", {})
        email = form_entry.get("Email", "").strip().lower()

        if not email or email in existing_emails:
            continue

        full_name = form_entry.get("Name", "").strip()
        if "http" in full_name.lower() or len(full_name) > 80:
            continue

        expo_name_raw = item.get("expo_name", "").strip()
        if not expo_name_raw:
            continue

        show_name = expo_name_raw.replace("Floor Plan", "").strip() + " Expo"

        row = build_row(
            form_entry,
            email,
            show_name,
            "B2B Website Floor Plan"
        )

        new_rows.append(row)
        existing_emails.add(email)


# =====================================================
# PHASE 2 - SHOW GUIDE
# =====================================================

def process_showguide(data, existing_emails, new_rows):
    print("🟢 Processing Show Guide entries...")

    for item in data:

        form_entry = item.get("Form_Entry", {})
        email = form_entry.get("Email", "").strip().lower()

        if not email or email in existing_emails:
            continue

        full_name = form_entry.get("Name", "").strip()
        if "http" in full_name.lower() or len(full_name) > 80:
            continue

        subject = form_entry.get("Your Subject", "").strip()

        if not subject or "Show Guide" not in subject:
            continue

        show_base = subject.replace("Show Guide", "").strip()
        show_name = show_base + " Expo"

        row = build_row(
            form_entry,
            email,
            show_name,
            "B2B Website Show Guide"
        )

        new_rows.append(row)
        existing_emails.add(email)


# =====================================================
# MAIN SCRIPT
# =====================================================

def run_script():

    print("🔧 Connecting to Google Sheets...")

    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
    gc = gspread.authorize(creds)
    sheet = gc.open(SHEET_NAME).worksheet(SHEET_TAB)

    header_row = sheet.row_values(1)
    email_col_index = header_row.index("Email") + 1

    existing_emails = set(
        email.strip().lower()
        for email in sheet.col_values(email_col_index)[1:]
        if email.strip()
    )

    print(f"📊 Existing emails found: {len(existing_emails)}")

    new_rows = []

    # ---------------------------
    # FETCH FLOORPLAN
    # ---------------------------

    print("\n🌐 Fetching Floor Plan data...")
    response = requests.get(FLOORPLAN_URL, headers=HEADERS, timeout=30)

    if response.status_code == 200:
        json_response = response.json()
        if json_response.get("status") == "success":
            data = json_response.get("data", [])
            print(f"📥 Floor Plan entries: {len(data)}")
            process_floorplan(data, existing_emails, new_rows)
        else:
            print("❌ Floor Plan API error:", json_response)
    else:
        print("❌ Floor Plan HTTP error:", response.text)

    # ---------------------------
    # FETCH SHOW GUIDE
    # ---------------------------

    print("\n🌐 Fetching Show Guide data...")
    response = requests.get(SHOWGUIDE_URL, headers=HEADERS, timeout=30)

    if response.status_code == 200:
        json_response = response.json()
        if json_response.get("status") == "success":
            data = json_response.get("data", [])
            print(f"📥 Show Guide entries: {len(data)}")
            process_showguide(data, existing_emails, new_rows)
        else:
            print("❌ Show Guide API error:", json_response)
    else:
        print("❌ Show Guide HTTP error:", response.text)

    # ---------------------------
    # INSERT INTO SHEET
    # ---------------------------

    print(f"\n🧾 Total New leads to insert: {len(new_rows)}")

    if new_rows:
        sheet.insert_rows(new_rows[::-1], row=2, value_input_option="USER_ENTERED")
        print("✅ Leads inserted successfully")
    else:
        print("🔁 No new leads found")


# =====================================================
# CORN JOB EVERY 15 MIN
# =====================================================

while True:
    try:
        print("\n🔄 Starting sync...")
        run_script()
    except Exception as e:
        print("❌ Script Error:", e)

    print("⏸ Sleeping 15 mins...")
    time.sleep(900)
