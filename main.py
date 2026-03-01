import tkinter as tk
from tkinter import ttk, messagebox
from db import (
    fetch_kunden, fetch_rechnungsdaten, check_invoice_paid, upsert_rechnung,
    fetch_offene_rechnungen, mark_rechnung_bezahlt,
    fetch_kunde_details, update_kunde_stammdaten, update_kunde_konditionen, correct_kunde_konditionen
)
from tkinter import filedialog, messagebox
from generate_invoice import generate_invoice
from tkcalendar import DateEntry
from datetime import datetime


def main():
    root = tk.Tk()
    root.title("Rechnungserstellung & Verwaltung")
    root.geometry("400x420")

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


        # Buttons
        ttk.Button(master, text="Rechnung erstellen", command=self.erstelle_rechnung).pack(pady=(20, 5))
        ttk.Button(master, text="Offene Rechnungen verwalten", command=self.manage_invoices).pack(pady=5)
        ttk.Button(master, text="Kunden & Konditionen verwalten", command=self.manage_customers).pack(pady=5)

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
        
        if self.kunden_dict:
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

    # NEU: KUNDEN & KONDITIONEN VERWALTEN
    def manage_customers(self):
        self.cust_top = tk.Toplevel(self.master)
        self.cust_top.title("Kunden & Konditionen verwalten")
        self.cust_top.geometry("500x650")

        # 1. Kundenauswahl
        sel_frame = ttk.Frame(self.cust_top)
        sel_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Label(sel_frame, text="Kunde wählen:").pack(side=tk.LEFT, padx=5)
        self.mng_kunde_var = tk.StringVar()
        mng_dropdown = ttk.Combobox(sel_frame, textvariable=self.mng_kunde_var, values=list(self.kunden_dict.keys()), state="readonly", width=40)
        mng_dropdown.pack(side=tk.LEFT, padx=5)
        mng_dropdown.bind("<<ComboboxSelected>>", self.load_customer_data_into_form)

        # Variablen für die Formularfelder
        self.f_name = tk.StringVar()
        self.f_kuerzel = tk.StringVar()
        self.f_ansprechpartner = tk.StringVar()
        self.f_strasse = tk.StringVar()
        self.f_hausnr = tk.StringVar()
        self.f_plz = tk.StringVar()
        self.f_ort = tk.StringVar()

        self.f_preis = tk.DoubleVar()
        self.f_dauer = tk.IntVar()
        self.f_strecke = tk.DoubleVar()
        self.f_kmgeld = tk.DoubleVar()

        # Speicher für die Original-Konditionen (um Änderungen zu erkennen)
        self.orig_konditionen = {}

        # 2. Frame Stammdaten
        stamm_frame = ttk.LabelFrame(self.cust_top, text="Stammdaten")
        stamm_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.add_form_row(stamm_frame, 0, "Name:", self.f_name)
        self.add_form_row(stamm_frame, 1, "Kürzel:", self.f_kuerzel)
        self.add_form_row(stamm_frame, 2, "Ansprechpartner:", self.f_ansprechpartner)
        self.add_form_row(stamm_frame, 3, "Straße:", self.f_strasse)
        self.add_form_row(stamm_frame, 4, "Hausnr.:", self.f_hausnr)
        self.add_form_row(stamm_frame, 5, "PLZ:", self.f_plz)
        self.add_form_row(stamm_frame, 6, "Ort:", self.f_ort)

        # 3. Frame Konditionen
        self.kond_frame = ttk.LabelFrame(self.cust_top, text="Aktuelle Konditionen (Werden bei Änderung versioniert)")
        self.kond_frame.pack(fill=tk.X, padx=10, pady=10)

        self.add_form_row(self.kond_frame, 0, "Preis pro Einheit (€):", self.f_preis)
        self.add_form_row(self.kond_frame, 1, "Dauer (Min):", self.f_dauer)
        self.add_form_row(self.kond_frame, 2, "Fahrtstrecke (km):", self.f_strecke)
        self.add_form_row(self.kond_frame, 3, "KM-Geld (€/km):", self.f_kmgeld)

        ttk.Label(self.kond_frame, text="Neue Konditionen gültig ab:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=5)
        self.gueltig_ab_entry = DateEntry(self.kond_frame, width=12, background="darkblue", foreground="white", borderwidth=2, date_pattern="yyyy-mm-dd")
        self.gueltig_ab_entry.grid(row=4, column=1, sticky=tk.W, padx=5, pady=5)

        # Checkbox für Tippfehler-Korrektur
        self.f_tippfehler = tk.BooleanVar(value=False)
        self.chk_tippfehler = ttk.Checkbutton(
            self.kond_frame, 
            text="Nur Tippfehler korrigieren (überschreibt aktuellen Eintrag)", 
            variable=self.f_tippfehler,
            command=self.toggle_kondition_mode
        )
        self.chk_tippfehler.grid(row=5, column=0, columnspan=2, sticky=tk.W, padx=5, pady=10)

        # 4. Speichern Button
        ttk.Button(self.cust_top, text="Änderungen speichern", command=self.save_customer_data).pack(pady=15)

    def add_form_row(self, parent, row, label_text, var):
        ttk.Label(parent, text=label_text).grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Entry(parent, textvariable=var, width=30).grid(row=row, column=1, sticky=tk.W, padx=5, pady=5)

    def toggle_kondition_mode(self):
        """Aktiviert oder deaktiviert das Datum-Feld basierend auf der Checkbox."""
        if self.f_tippfehler.get():
            self.gueltig_ab_entry.config(state="disabled")
        else:
            self.gueltig_ab_entry.config(state="normal")

    def load_customer_data_into_form(self, event=None):
        auswahl = self.mng_kunde_var.get()
        if not auswahl: return
        kdnr = self.kunden_dict[auswahl]

        try:
            details = fetch_kunde_details(kdnr)
            if details:
                self.f_name.set(details['name'])
                self.f_kuerzel.set(details['kuerzel'])
                self.f_ansprechpartner.set(details['ansprechpartner'])
                self.f_strasse.set(details['strasse'])
                self.f_hausnr.set(details['hausnummer'])
                self.f_plz.set(details['plz'])
                self.f_ort.set(details['ort'])

                self.f_preis.set(details['preis'])
                self.f_dauer.set(details['dauer'])
                self.f_strecke.set(details['strecke'])
                self.f_kmgeld.set(details['km_geld'])

                # Originale Konditionen merken, um zu prüfen, ob sie geändert wurden
                self.orig_konditionen = {
                    "preis": details['preis'],
                    "dauer": details['dauer'],
                    "strecke": details['strecke'],
                    "km_geld": details['km_geld']
                }
                
                # Datum auf heute setzen für potentielle Änderungen
                self.gueltig_ab_entry.set_date(datetime.now().date())

                # Dynamischer Titel für den Konditionen-Rahmen
                gueltig_von_str = details.get('gueltig_von', 'Unbekannt')
                self.kond_frame.config(text=f"Aktuelle Konditionen (Gültig seit: {gueltig_von_str})")
                
                # Checkbox zurücksetzen
                self.f_tippfehler.set(False)
                self.toggle_kondition_mode()

        except Exception as e:
            messagebox.showerror("Fehler", f"Daten konnten nicht geladen werden:\n{e}")

    def save_customer_data(self):
        auswahl = self.mng_kunde_var.get()
        if not auswahl:
            messagebox.showwarning("Hinweis", "Bitte zuerst einen Kunden auswählen.")
            return
        
        kdnr = self.kunden_dict[auswahl]

        try:
            # 1. Stammdaten speichern (immer)
            stamm_daten = {
                "name": self.f_name.get(),
                "kuerzel": self.f_kuerzel.get(),
                "ansprechpartner": self.f_ansprechpartner.get(),
                "strasse": self.f_strasse.get(),
                "hausnummer": self.f_hausnr.get(),
                "plz": self.f_plz.get(),
                "ort": self.f_ort.get()
            }
            update_kunde_stammdaten(kdnr, stamm_daten)

            # 2. Prüfen, ob Konditionen geändert wurden
            neu_preis = self.f_preis.get()
            neu_dauer = self.f_dauer.get()
            neu_strecke = self.f_strecke.get()
            neu_kmgeld = self.f_kmgeld.get()

            konditionen_geandert = (
                neu_preis != self.orig_konditionen.get('preis') or
                neu_dauer != self.orig_konditionen.get('dauer') or
                neu_strecke != self.orig_konditionen.get('strecke') or
                neu_kmgeld != self.orig_konditionen.get('km_geld')
            )

            # 3. Wenn geändert -> Versionieren!
            if konditionen_geandert:
                if self.f_tippfehler.get():
                    # Nur Update ausführen (Tippfehler)
                    correct_kunde_konditionen(kdnr, neu_preis, neu_dauer, neu_strecke, neu_kmgeld)
                    msg = "Stammdaten und Tippfehler in den Konditionen erfolgreich gespeichert!"
                else:
                    # Neue Version anlegen (Preiserhöhung etc.)
                    gueltig_ab = self.gueltig_ab_entry.get()
                    update_kunde_konditionen(kdnr, neu_preis, neu_dauer, neu_strecke, neu_kmgeld, gueltig_ab)
                    msg = "Stammdaten gespeichert und NEUE Konditionen-Version erfolgreich angelegt!"
            else:
                msg = "Stammdaten erfolgreich gespeichert! (Konditionen blieben unverändert)"

            messagebox.showinfo("Erfolg", msg)
            
            # Haupt-Dropdown (in InvoiceApp) sicherheitshalber neu laden
            self.lade_kunden() 
            self.cust_top.destroy()

        except Exception as e:
            messagebox.showerror("Fehler", f"Speichern fehlgeschlagen:\n{e}")


if __name__ == "__main__":
    main()