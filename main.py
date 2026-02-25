import tkinter as tk
from tkinter import ttk, messagebox
from db import fetch_kunden, fetch_rechnungsdaten
from tkinter import filedialog, messagebox
from generate_invoice import generate_invoice
from tkcalendar import DateEntry
from datetime import datetime


def main():
    root = tk.Tk()
    root.title("Rechnungserstellung")
    root.geometry("400x300")

    app = InvoiceApp(root)
    root.mainloop()

class InvoiceApp:
    def __init__(self, master):
        self.master = master

        # Label und Dropdown für Kunden
        ttk.Label(master, text="Kunde auswählen:").pack(pady=5)
        self.kunde_var = tk.StringVar()
        self.kunde_dropdown = ttk.Combobox(master, textvariable=self.kunde_var, state="readonly")
        self.kunde_dropdown.pack(pady=5)

        # Datumseingaben mit Kalender
        ttk.Label(master, text="Startdatum:").pack(pady=5)
        self.start_entry = DateEntry(
            master,
            width=12,
            background="darkblue",
            foreground="white",
            borderwidth=2,
            date_pattern="yyyy-mm-dd"
        )
        self.start_entry.pack(pady=5)

        ttk.Label(master, text="Enddatum:").pack(pady=5)
        self.end_entry = DateEntry(
            master,
            width=12,
            background="darkblue",
            foreground="white",
            borderwidth=2,
            date_pattern="yyyy-mm-dd"
        )
        self.end_entry.pack(pady=5)


        # Button zum Laden der Daten
        ttk.Button(master, text="Rechnung erstellen", command=self.erstelle_rechnung).pack(pady=20)

        # Kundenliste laden
        self.lade_kunden()

    def lade_kunden(self):
        """Lädt Kundendaten aus der DB und füllt das Dropdown."""
        try:
            kunden = fetch_kunden()
            self.kunden_dict = {f"{k['name']} ({k['kdnr']})": k['kdnr'] for k in kunden}
            self.kunde_dropdown['values'] = list(self.kunden_dict.keys())
        except Exception as e:
            messagebox.showerror("Fehler", f"Kunden konnten nicht geladen werden:\n{e}")
        
        max_len = max(len(name) for name in self.kunden_dict.keys())
        self.kunde_dropdown.config(width=max_len)

    def erstelle_rechnung(self):
        """Lädt Rechnungsdaten für den gewählten Kunden und Zeitraum und erzeugt PDF-Rechnung."""
        auswahl = self.kunde_var.get()
        if not auswahl:
            messagebox.showwarning("Hinweis", "Bitte zuerst einen Kunden auswählen.")
            return
        
        kdnr = self.kunden_dict[auswahl]
        start_str = self.start_entry.get()
        ende_str = self.end_entry.get()
        
        if datetime.strptime(ende_str, "%Y-%m-%d") < datetime.strptime(start_str, "%Y-%m-%d"):
            messagebox.showerror("Fehler", "Das Enddatum darf nicht vor dem Startdatum liegen.")
            return

        # Uhrzeit hinzufügen, damit der ausgewählte Zeitraum
        # vom Beginn des ersten Tages bis zum Ende des letzten Tages reicht
        start_db = f"{start_str} 00:00:00"
        ende_db = f"{ende_str} 23:59:59"

        try:
            rechnung = fetch_rechnungsdaten(kdnr, start_db, ende_db)
            
            # --- Fehlende Konditionen abfangen ---
            if rechnung.get('summe') is None:
                messagebox.showwarning(
                    "Achtung: Keine Konditionen gefunden", 
                    "Es konnten keine Kosten für diesen Zeitraum berechnet werden.\n\n"
                    "Wahrscheinlicher Grund:\n"
                    "Für diesen Kunden fehlt noch der Eintrag in der Tabelle 'kondition' "
                    "(Preis pro Einheit, km-Geld etc.) oder die Konditionen sind in diesem "
                    "Zeitraum nicht gültig.\n\n"
                    "Bitte trage die Konditionen für diesen Kunden in der Datenbank nach!"
                )
                return

            # --- NEUES FEATURE: Dateiname automatisch vorschlagen ---
            vorgeschlagener_dateiname = f"{rechnung['rechnung_nr']}.pdf"

            # Nutzer nach Speicherort fragen
            pfad = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                initialfile=vorgeschlagener_dateiname,
                filetypes=[("PDF-Datei", "*.pdf")],
                title="Rechnung speichern unter..."
            )
            if not pfad:
                return  # Benutzer hat abgebrochen
            
            generate_invoice(rechnung, pfad)

            messagebox.showinfo("Erfolg", f"✅ Rechnung gespeichert:\n{pfad}")
            
        except Exception as e:
            messagebox.showerror("Fehler", f"Rechnung konnte nicht erstellt werden:\n{e}")

if __name__ == "__main__":
    main()