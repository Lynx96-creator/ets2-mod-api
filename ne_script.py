import customtkinter as ctk

ctk.set_appearance_mode("dark")
root = ctk.CTk()
root.title("Test UI")
root.geometry("400x300")
label = ctk.CTkLabel(root, text="If you see this, UI works!")
label.pack(pady=20)
root.mainloop()
