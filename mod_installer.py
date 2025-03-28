import os
import platform
import gspread
import uuid
import customtkinter as ctk
from tkinter import messagebox, simpledialog
from google.oauth2.service_account import Credentials
import gdown
import threading
import time
import logging
import shutil
import subprocess

# === CONFIG ===
GOOGLE_SHEET_NAME = "ETS2_Mod_Data"
MOD_INSTALL_PATH = os.path.expanduser("~/Documents/Euro Truck Simulator 2/mod")
CREDENTIALS_FILE = "google_credentials.json"

# === SETUP LOGGING ===
logging.basicConfig(filename="mod_installer.log", level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Global variable to store logged-in user's email
current_user_email = None

# === OS-SPECIFIC HELPER FUNCTIONS ===
def set_file_attributes(file_path):
    """Set file attributes to hide and make read-only based on OS."""
    if platform.system() == "Windows":
        os.system(f'attrib +h +s +r "{file_path}"')
    elif platform.system() == "Darwin":
        # macOS: hide file and set it as read-only
        os.system(f'chflags hidden "{file_path}"')
        os.chmod(file_path, 0o444)
    else:
        # For other OSes (like Linux), you might mimic similar behavior:
        os.chmod(file_path, 0o444)

def remove_file_attributes(file_path):
    """Remove hidden/read-only attributes from a file based on OS."""
    if platform.system() == "Windows":
        os.system(f'attrib -h -s -r "{file_path}"')
    elif platform.system() == "Darwin":
        os.system(f'chflags nohidden "{file_path}"')
        os.chmod(file_path, 0o666)
    else:
        os.chmod(file_path, 0o666)

# === GOOGLE AUTH ===
def authenticate_google():
    creds = Credentials.from_service_account_file(
        CREDENTIALS_FILE,
        scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    )
    client = gspread.authorize(creds)
    return client

def get_mac_address():
    return ':'.join(format(x, '02x') for x in uuid.getnode().to_bytes(6, 'big'))

def authenticate_user(email, password):
    client = authenticate_google()
    sheet = client.open(GOOGLE_SHEET_NAME).sheet1
    data = sheet.get_all_records()
    for index, row in enumerate(data):
        if row["Email"] == email and row["Password"] == password:
            if not row["MAC Address"]:
                sheet.update_cell(index + 2, 3, get_mac_address())
                return True
            elif row["MAC Address"] == get_mac_address():
                return True
            else:
                return False
    return False

def get_user_purchased_mods(user_email):
    client = authenticate_google()
    sheet = client.open(GOOGLE_SHEET_NAME).sheet1
    data = sheet.get_all_records()
    for row in data:
        if row["Email"] == user_email:
            return [mod.strip() for mod in row["User Mods"].split(",")] if row["User Mods"] else []
    return []

def fetch_mod_list():
    client = authenticate_google()
    sheet = client.open(GOOGLE_SHEET_NAME).sheet1
    return [
        {
            "Mod Name": row["Mod Name"],
            "Mod Internal Name": row["Mod Internal Name"],
            "Google Drive Link": row["Google Drive Link"],
            "Serial Key": row["Serial Key"]
        }
        for row in sheet.get_all_records() if row["Mod Name"] and row["Google Drive Link"]
    ]

def extract_drive_file_id(drive_link):
    if "/file/d/" in drive_link:
        return drive_link.split("/file/d/")[1].split("/")[0]
    elif "id=" in drive_link:
        return drive_link.split("id=")[1].split("&")[0]
    return None

def download_with_gdown(file_id, destination, progress_bar, progress_label, internal_name):
    """
    Downloads the mod file directly into the mod folder and then sets its attributes
    to hidden, system, and read-only. The 'internal_name' parameter is accepted for compatibility.
    """
    url = f"https://drive.google.com/uc?id={file_id}"

    def download():
        try:
            progress_label.configure(text="Initializing Download...")
            progress_bar.set(0)

            # Download to a temporary file first.
            temp_file = destination + ".tmp"
            gdown.download(url, temp_file, quiet=True)

            # Simulate progress for user feedback.
            for i in range(1, 101, 10):
                progress_bar.set(i / 100)
                progress_label.configure(text=f"Downloading: {i}%")
                time.sleep(0.3)

            if os.path.getsize(temp_file) < 500000:
                os.remove(temp_file)
                messagebox.showerror("Error", "Download failed! Try again.")
                progress_label.configure(text="Download Failed")
                progress_bar.set(0)
                return False

            # Move the temporary file to the final destination.
            os.rename(temp_file, destination)
            # Set file attributes to hide and make read-only.
            set_file_attributes(destination)

            progress_label.configure(text="Mod Installed!")
            progress_bar.set(1)
            messagebox.showinfo("Success", f"{os.path.basename(destination)} installed successfully!")
            load_mod_list(current_user_email)  # Refresh UI using the global user email
            return True

        except Exception as e:
            logging.error(f"Download failed: {str(e)}")
            messagebox.showerror("Error", f"Failed to download mod: {str(e)}")
            progress_label.configure(text="Download Failed")
            return False

    threading.Thread(target=download, daemon=True).start()

def install_mod(mod_name, internal_name, drive_link, serial_key, progress_bar, progress_label):
    client = authenticate_google()
    sheet = client.open(GOOGLE_SHEET_NAME).sheet1
    data = sheet.get_all_records()

    for index, row in enumerate(data):
        if row["Mod Name"] == mod_name and row["Serial Key"].strip() == serial_key.strip():
            progress_label.configure(text=f"Preparing {mod_name}...")
            progress_bar.set(0)

            file_id = extract_drive_file_id(drive_link)
            if not file_id:
                messagebox.showerror("Error", "Invalid Google Drive link!")
                return

            # Define the file path in the mod folder.
            mod_path = os.path.join(MOD_INSTALL_PATH, f"{internal_name}.scs")
            if os.path.exists(mod_path):
                remove_file_attributes(mod_path)
                os.remove(mod_path)

            download_with_gdown(file_id, mod_path, progress_bar, progress_label, internal_name)

            new_serial_key = str(uuid.uuid4()).replace("-", "")[:14].upper()
            sheet.update_cell(index + 2, 6, new_serial_key)
            return  

    messagebox.showerror("Error", "Invalid serial key!")
    progress_label.configure(text="Invalid Key")

def uninstall_mod(internal_name, progress_label):
    # Remove the file in the mod folder.
    mod_path = os.path.join(MOD_INSTALL_PATH, f"{internal_name}.scs")
    removed_any = False
    if os.path.exists(mod_path):
        remove_file_attributes(mod_path)
        os.remove(mod_path)
        removed_any = True

    if removed_any:
        progress_label.configure(text=f"{internal_name} uninstalled")
        messagebox.showinfo("Success", f"{internal_name} uninstalled!")
        load_mod_list(current_user_email)
    else:
        messagebox.showerror("Error", "Mod not found.")

def load_mod_list(user_email):
    global scrollable_frame

    for widget in scrollable_frame.winfo_children():
        widget.destroy()

    # Get the mods the user has purchased
    purchased_mods = get_user_purchased_mods(user_email)
    mod_list = fetch_mod_list()

    for mod in mod_list:
        if mod["Mod Name"] in purchased_mods:
            frame = ctk.CTkFrame(scrollable_frame)
            frame.pack(pady=5, padx=10, fill="x")

            label = ctk.CTkLabel(frame, text=mod["Mod Name"], font=("Arial", 12))
            label.pack()

            progress_label = ctk.CTkLabel(frame, text="")
            progress_label.pack()

            progress_bar = ctk.CTkProgressBar(frame)
            progress_bar.set(0)
            progress_bar.pack(pady=5)

            install_button = ctk.CTkButton(
                frame, text="Install", 
                command=lambda m=mod, pl=progress_label, pb=progress_bar: install_mod(
                    m["Mod Name"], m["Mod Internal Name"],
                    m["Google Drive Link"], 
                    simpledialog.askstring("Serial Key", f"Enter serial key for {m['Mod Name']}:"),
                    pb, pl
                )
            )
            install_button.pack(side="left", padx=5)

            decoy_path = os.path.join(MOD_INSTALL_PATH, f"{mod['Mod Internal Name']}.scs")
            if os.path.exists(decoy_path):
                uninstall_button = ctk.CTkButton(
                    frame, text="Uninstall", fg_color="red", 
                    command=lambda internal_name=mod["Mod Internal Name"], pl=progress_label: uninstall_mod(internal_name, pl)
                )
                uninstall_button.pack(side="left", padx=5)

def main_ui(user_email):
    global root, scrollable_frame, current_user_email
    current_user_email = user_email  # Store the logged-in user's email globally

    ctk.set_appearance_mode("dark")

    root = ctk.CTk()
    root.title("ETS2 Mod Installer")
    root.geometry("800x600")

    title = ctk.CTkLabel(root, text="Available Mods", font=("Arial", 16, "bold"))
    title.pack(pady=10)

    scrollable_frame = ctk.CTkScrollableFrame(root)
    scrollable_frame.pack(fill="both", expand=True, padx=10, pady=10)

    load_mod_list(user_email)
    root.mainloop()

def on_login():
    email = email_entry.get()
    password = password_entry.get()
    if authenticate_user(email, password):
        login_window.destroy()
        main_ui(email)
    else:
        messagebox.showerror("Login Failed", "Invalid credentials or unauthorized device.")

login_window = ctk.CTk()
login_window.title("ETS2 Mod Installer - Login")
login_window.geometry("300x200")

email_entry = ctk.CTkEntry(login_window, placeholder_text="Email")
email_entry.pack(pady=5)

password_entry = ctk.CTkEntry(login_window, placeholder_text="Password", show="*")
password_entry.pack(pady=5)

login_button = ctk.CTkButton(login_window, text="Login", command=on_login)
login_button.pack()

login_window.mainloop()
