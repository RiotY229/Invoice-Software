import tkinter as tk
from tkinter import ttk, messagebox
from db import fetch_kunden, fetch_rechnungsdaten, check_invoice_paid, upsert_rechnung, fetch_offene_rechnungen, mark_rechnung_bezahlt
from tkinter import filedialog, messagebox
from generate_invoice import generate_invoice
from tkcalendar import DateEntry
from datetime import datetime


def main():
    root = tk.Tk()
    root.title("Rechnungserstellung")
    root.geometry("400x380")

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
        ttk.Button(master, text="Rechnung erstellen", command=self.erstelle_rechnung).pack(pady=(20, 5))

        # NEU: Button für die Rechnungsverwaltung
        ttk.Button(master, text="Offene Rechnungen verwalten", command=self.manage_invoices).pack(pady=5)

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

            rechnung_nr = rechnung['rechnung_nr']

            # --- SCHUTZMECHANISMUS: Ist die Rechnung schon als bezahlt gelockt? ---
            if check_invoice_paid(rechnung_nr):
                messagebox.showerror(
                    "Rechnung gesperrt", 
                    f"Die Rechnung {rechnung_nr} wurde bereits als BEZAHLT markiert.\n\n"
                    "Sie ist revisionssicher gesperrt und kann nicht mehr überschrieben "
                    "oder neu generiert werden."
                )
                return

            # --- Dateiname automatisch vorschlagen ---
            vorgeschlagener_dateiname = f"{rechnung_nr}.pdf"

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

            # --- UPSERT: Rechnung in die Datenbank schreiben ---
            upsert_rechnung(rechnung, kdnr)

            messagebox.showinfo("Erfolg", f"✅ Rechnung {rechnung_nr} gespeichert und in Datenbank verbucht:\n{pfad}")
            
        except Exception as e:
            messagebox.showerror("Fehler", f"Rechnung konnte nicht erstellt werden:\n{e}")
    
    # Verwaltung offener Rechnungen
    def manage_invoices(self):
        """Öffnet ein neues Fenster zur Verwaltung unbezahlter Rechnungen."""
        top = tk.Toplevel(self.master)
        top.title("Offene Rechnungen verwalten")
        top.geometry("600x300")
        
        # Frame für die Tabelle
        frame = ttk.Frame(top)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Tabelle (Treeview) erstellen
        columns = ("nr", "datum", "kunde", "summe")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings")
        self.tree.heading("nr", text="Rechnungs-Nr.")
        self.tree.heading("datum", text="Datum")
        self.tree.heading("kunde", text="Kunde")
        self.tree.heading("summe", text="Summe (€)")
        
        self.tree.column("nr", width=100)
        self.tree.column("datum", width=100)
        self.tree.column("kunde", width=250)
        self.tree.column("summe", width=100, anchor=tk.E)
        
        # Scrollbar für die Tabelle
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Buttons unten
        btn_frame = ttk.Frame(top)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(btn_frame, text="Zahlungseingang verbuchen", command=self.mark_as_paid).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Schließen", command=top.destroy).pack(side=tk.RIGHT)
        
        # Daten initial laden
        self.load_open_invoices()

    def load_open_invoices(self):
        """Lädt die offenen Rechnungen aus der DB in die Tabelle."""
        # Tabelle leeren
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        try:
            offene = fetch_offene_rechnungen()
            for r in offene:
                self.tree.insert("", tk.END, values=(r['rechnung_nr'], r['datum'], r['kunde'], f"{r['summe']:.2f}"))
        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Laden der Rechnungen:\n{e}")

    def mark_as_paid(self):
        """Markiert die ausgewählte Rechnung als bezahlt."""
        selected_item = self.tree.focus()
        if not selected_item:
            messagebox.showwarning("Hinweis", "Bitte wähle zuerst eine Rechnung aus der Liste aus.")
            return
            
        item_data = self.tree.item(selected_item)
        rechnung_nr = item_data['values'][0]
        kunde = item_data['values'][2]
        
        if messagebox.askyesno("Zahlungseingang", f"Wurde die Rechnung {rechnung_nr} von '{kunde}' wirklich bezahlt?"):
            try:
                mark_rechnung_bezahlt(rechnung_nr)
                messagebox.showinfo("Erfolg", f"Rechnung {rechnung_nr} erfolgreich als bezahlt markiert!")
                self.load_open_invoices() # Liste sofort aktualisieren
            except Exception as e:
                messagebox.showerror("Fehler", f"Fehler beim Speichern:\n{e}")

if __name__ == "__main__":
    main()