from flask import Flask, request, jsonify
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)

# Configuration
CREDENTIALS_FILE = "google_credentials.json"
GOOGLE_SHEET_NAME = "ETS2_Mod_Data"

def authenticate_google():
    creds = Credentials.from_service_account_file(
        CREDENTIALS_FILE,
        scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    )
    client = gspread.authorize(creds)
    return client

def get_user_mods(user_email):
    client = authenticate_google()
    sheet = client.open(GOOGLE_SHEET_NAME).sheet1
    data = sheet.get_all_records()
    for row in data:
        if row["Email"] == user_email:
            # Assume mods are stored as comma-separated values in "User Mods" column.
            return [mod.strip() for mod in row.get("User Mods", "").split(",") if mod.strip()]
    return []

def fetch_all_mods():
    client = authenticate_google()
    sheet = client.open(GOOGLE_SHEET_NAME).sheet1
    mods = []
    for row in sheet.get_all_records():
        if row.get("Mod Name") and row.get("Google Drive Link"):
            mods.append({
                "Mod Name": row["Mod Name"],
                "Mod Internal Name": row["Mod Internal Name"],
                "Google Drive Link": row["Google Drive Link"],
                "Serial Key": row["Serial Key"]
            })
    return mods

@app.route('/get_mods', methods=['GET'])
def get_mods():
    # Expect a query parameter "email"
    user_email = request.args.get('email')
    if not user_email:
        return jsonify({"error": "Email parameter is required."}), 400

    user_mods = get_user_mods(user_email)
    all_mods = fetch_all_mods()
    # Filter mods: only include those in the user's purchased mods list.
    available_mods = [mod for mod in all_mods if mod["Mod Name"] in user_mods]
    return jsonify(available_mods)

# You can add additional endpoints, for example, to update serial keys, validate logins, etc.

if __name__ == '__main__':
    # For development only; in production, use a WSGI server like Gunicorn.
    app.run(debug=True, host="0.0.0.0", port=5000)
