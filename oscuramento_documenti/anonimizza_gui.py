"""
Oscura Documenti - GUI desktop per l'anonimizzazione di file .docx
Sostituisce nomi/cognomi (con dicitura personalizzabile per ciascuno),
date di nascita, numeri di telefono e codice fiscale in tutti i file
.docx di una cartella.
"""
import os
import re
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from docx import Document
from docx.text.paragraph import Paragraph
from dateutil import parser

TAG_NOME_DEFAULT = "[soggetto_interessato]"
DATA_SOSTITUZIONE = "00.00.00"
TAG_TELEFONO = "[numero_di_telefono_oscurato]"
TAG_CF = "[codice_fiscale_oscurato]"

MESI_IT = {
    1: "gennaio", 2: "febbraio", 3: "marzo", 4: "aprile",
    5: "maggio", 6: "giugno", 7: "luglio", 8: "agosto",
    9: "settembre", 10: "ottobre", 11: "novembre", 12: "dicembre"
}

REGEX_CF = re.compile(
    r"\b[A-Z]{6}\d{2}[A-EHLMPR-T][0-9LMNPQRSTUV]{2}[A-Z]\d{3}[A-Z]\b",
    re.IGNORECASE
)

# Cellulari (3xx xxxxxxx) e fissi (0x[x[x]] xxxxxxxx), con o senza prefisso
# internazionale e con separatori opzionali (spazi, punti, trattini).
REGEX_TELEFONO = re.compile(
    r"\b(?:\+39[\s.-]?|0039[\s.-]?)?"
    r"(?:3\d{2}|0\d{1,3})"
    r"(?:[\s.-]?\d){6,8}\b"
)


def genera_regex_nome(nome_completo):
    parti = [re.escape(p) for p in nome_completo.split() if p]
    if not parti:
        raise ValueError("Nome e cognome non possono essere vuoti.")

    if len(parti) >= 2:
        p1, p2 = parti[0], parti[1]
        iniziale_p1 = rf"{p1[0]}\."
        iniziale_p2 = rf"{p2[0]}\."

        pattern_list = [
            rf"{p1}\s+{p2}",
            rf"{p2}\s+{p1}",
            rf"{iniziale_p1}\s+{p2}",
            rf"{iniziale_p2}\s+{p1}",
            p1,
            p2
        ]
        pattern_finale = r"\b(" + "|".join(pattern_list) + r")\b"
    else:
        pattern_finale = rf"\b{parti[0]}\b"

    return re.compile(pattern_finale, re.IGNORECASE)


def genera_regex_data(input_data):
    data_oggetto = parser.parse(input_data, dayfirst=True, fuzzy=True)
    giorno = str(data_oggetto.day)
    giorno_zero = giorno.zfill(2)
    mese_num = str(data_oggetto.month)
    mese_zero = mese_num.zfill(2)
    anno_completo = str(data_oggetto.year)
    anno_corto = anno_completo[-2:]
    mese_testo = MESI_IT[data_oggetto.month]

    pattern_date = [
        rf"{giorno_zero}[/.-]{mese_zero}[/.-]{anno_completo}",
        rf"{giorno}[/.-]{mese_num}[/.-]{anno_completo}",
        rf"{giorno_zero}[/.-]{mese_zero}[/.-]{anno_corto}",
        rf"{giorno}[/.-]{mese_num}[/.-]{anno_corto}",
        rf"{anno_completo}[/.-]{mese_zero}[/.-]{giorno_zero}",
        rf"{giorno}\s+{mese_testo}\s+{anno_completo}",
        rf"{giorno_zero}\s+{mese_testo}\s+{anno_completo}",
        rf"{giorno}\s+{mese_testo}\s+{anno_corto}",
        rf"{giorno_zero}\s+{mese_testo}\s+{anno_corto}"
    ]
    regex = re.compile(r"\b(" + "|".join(pattern_date) + r")\b", re.IGNORECASE)
    etichetta = f"{giorno_zero} {mese_testo} {anno_completo}"
    return regex, etichetta


def applica_sostituzione_sicura(paragraph, regex, tag_copertura):
    if not paragraph or paragraph.text is None:
        return False
    testo_completo = paragraph.text
    if regex.search(testo_completo):
        nuovo_testo = regex.sub(tag_copertura, testo_completo)
        if paragraph.runs:
            paragraph.runs[0].text = nuovo_testo
            for run in paragraph.runs[1:]:
                run.text = ""
        else:
            paragraph.text = nuovo_testo
        return True
    return False


def anonimizza_singolo_file(file_path, regex_nomi, regex_date, oscura_telefoni, log):
    """regex_nomi: lista di tuple (regex, tag_sostituzione).
    regex_date: lista di regex; ogni corrispondenza viene sostituita da DATA_SOSTITUZIONE."""
    try:
        doc = Document(file_path)
        modificato = False
        tutti_i_paragrafi = []

        tutti_i_paragrafi.extend(doc.paragraphs)

        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    tutti_i_paragrafi.extend(cell.paragraphs)

        for section in doc.sections:
            for p in section.header.paragraphs:
                tutti_i_paragrafi.append(p)
            for p_element in section.footer.paragraphs:
                tutti_i_paragrafi.append(p_element)

        for elemento in doc.element.iter():
            if elemento.tag.endswith('txbxContent'):
                for p_element in elemento.iter():
                    if p_element.tag.endswith('p'):
                        tutti_i_paragrafi.append(Paragraph(p_element, doc))

        for p in tutti_i_paragrafi:
            cambiato = False

            for regex_nome, tag_nome in regex_nomi:
                if applica_sostituzione_sicura(p, regex_nome, tag_nome):
                    cambiato = True

            # I numeri di telefono vanno oscurati prima delle date: la
            # dicitura di sostituzione della data ("00.00.00") e' a sua
            # volta un pattern numerico e verrebbe altrimenti ri-catturato.
            if oscura_telefoni and applica_sostituzione_sicura(p, REGEX_TELEFONO, TAG_TELEFONO):
                cambiato = True

            for regex_data in regex_date:
                if applica_sostituzione_sicura(p, regex_data, DATA_SOSTITUZIONE):
                    cambiato = True

            if applica_sostituzione_sicura(p, REGEX_CF, TAG_CF):
                cambiato = True

            if cambiato:
                modificato = True

        if modificato:
            doc.save(file_path)
            return True
        return False
    except Exception as e:
        log(f"❌ Errore durante l'elaborazione di {os.path.basename(file_path)}: {e}")
        return False


def elabora_cartella(cartella, nominativi, date_input, oscura_telefoni, log):
    """nominativi: lista di tuple (nome_completo, tag_sostituzione).
    date_input: lista di stringhe data in qualsiasi formato."""
    if not os.path.exists(cartella):
        log(f"Errore: la cartella '{cartella}' non esiste.")
        return

    regex_nomi = [
        (genera_regex_nome(nome), tag.strip() or TAG_NOME_DEFAULT)
        for nome, tag in nominativi
    ]

    regex_date = []
    etichette_date = []
    for data_input in date_input:
        regex_data, etichetta_data = genera_regex_data(data_input)
        regex_date.append(regex_data)
        etichette_date.append(etichetta_data)

    log(f"✅ Nominativi configurati: {len(regex_nomi)} | Date configurate: {', '.join(etichette_date)}")
    if oscura_telefoni:
        log("✅ Oscuramento numeri di telefono attivo.")

    files = [f for f in os.listdir(cartella) if f.endswith('.docx') and not f.startswith('~$')]

    if not files:
        log(f"Nessun file .docx trovato in '{cartella}'.")
        return

    log(f"Inizio... Elaborazione di {len(files)} file nella cartella '{cartella}'...\n")
    file_modificati = 0

    for file_nome in files:
        percorso_completo = os.path.join(cartella, file_nome)
        ha_subito_modifiche = anonimizza_singolo_file(
            percorso_completo, regex_nomi, regex_date, oscura_telefoni, log
        )
        if ha_subito_modifiche:
            log(f" Modificato (Rilevato testo/date/telefono/CF): {file_nome}")
            file_modificati += 1
        else:
            log(f" Saltato (Nessuna corrispondenza): {file_nome}")

    log(f"\nFine! File totali modificati ed anonimizzati: {file_modificati}/{len(files)}")


class NominativoRow:
    def __init__(self, parent, on_remove):
        self.frame = ttk.Frame(parent)
        self.nome_var = tk.StringVar()
        self.tag_var = tk.StringVar()

        ttk.Entry(self.frame, textvariable=self.nome_var, width=26).pack(side="left", padx=(0, 4))
        ttk.Entry(self.frame, textvariable=self.tag_var, width=26).pack(side="left", padx=(0, 4))
        ttk.Button(self.frame, text="✕", width=3, command=lambda: on_remove(self)).pack(side="left")

        self.frame.pack(fill="x", pady=2)

    def valori(self):
        return self.nome_var.get().strip(), self.tag_var.get().strip()

    def destroy(self):
        self.frame.destroy()


class DataRow:
    def __init__(self, parent, on_remove):
        self.frame = ttk.Frame(parent)
        self.data_var = tk.StringVar()

        ttk.Entry(self.frame, textvariable=self.data_var, width=26).pack(side="left", padx=(0, 4))
        ttk.Button(self.frame, text="✕", width=3, command=lambda: on_remove(self)).pack(side="left")

        self.frame.pack(fill="x", pady=2)

    def valore(self):
        return self.data_var.get().strip()

    def destroy(self):
        self.frame.destroy()


class OscuraDocumentiApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Oscura Documenti")
        self.root.geometry("720x700")
        self.root.minsize(640, 560)

        self.log_queue = queue.Queue()
        self.worker_thread = None
        self.nominativi_rows = []
        self.date_rows = []

        self._build_ui()
        self.root.after(100, self._poll_log_queue)

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        top = ttk.Frame(self.root)
        top.pack(fill="x", **pad)
        top.columnconfigure(0, weight=1)

        ttk.Label(top, text="Cartella da elaborare:").grid(row=0, column=0, sticky="w")
        self.cartella_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.cartella_var).grid(row=1, column=0, sticky="we")
        ttk.Button(top, text="Sfoglia...", command=self._scegli_cartella).grid(row=1, column=1, padx=(6, 0))

        # --- Nominativi ---
        nomi_frame = ttk.LabelFrame(self.root, text="Nominativi da oscurare")
        nomi_frame.pack(fill="x", **pad)

        header = ttk.Frame(nomi_frame)
        header.pack(fill="x", pady=(4, 0))
        ttk.Label(header, text="Nome e Cognome", width=26).pack(side="left", padx=(0, 4))
        ttk.Label(header, text="Dicitura di sostituzione", width=26).pack(side="left", padx=(0, 4))

        self.nominativi_container = ttk.Frame(nomi_frame)
        self.nominativi_container.pack(fill="x")

        ttk.Button(
            nomi_frame, text="+ Aggiungi nominativo", command=self._aggiungi_nominativo
        ).pack(anchor="w", pady=(4, 6))

        # --- Date ---
        date_frame = ttk.LabelFrame(
            self.root, text=f"Date di nascita da oscurare (sostituite da \"{DATA_SOSTITUZIONE}\")"
        )
        date_frame.pack(fill="x", **pad)

        self.date_container = ttk.Frame(date_frame)
        self.date_container.pack(fill="x", pady=(4, 0))

        ttk.Button(
            date_frame, text="+ Aggiungi data", command=self._aggiungi_data
        ).pack(anchor="w", pady=(4, 6))

        # --- Opzioni ---
        opzioni_frame = ttk.Frame(self.root)
        opzioni_frame.pack(fill="x", **pad)
        self.telefoni_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            opzioni_frame, text="Oscura anche i numeri di telefono", variable=self.telefoni_var
        ).pack(anchor="w")

        self.avvia_btn = ttk.Button(self.root, text="Avvia oscuramento", command=self._avvia)
        self.avvia_btn.pack(pady=(4, 8))

        self.log_text = scrolledtext.ScrolledText(self.root, wrap="word", height=10, state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self._aggiungi_nominativo()
        self._aggiungi_data()

    def _aggiungi_nominativo(self):
        row = NominativoRow(self.nominativi_container, self._rimuovi_nominativo)
        self.nominativi_rows.append(row)

    def _rimuovi_nominativo(self, row):
        row.destroy()
        self.nominativi_rows.remove(row)

    def _aggiungi_data(self):
        row = DataRow(self.date_container, self._rimuovi_data)
        self.date_rows.append(row)

    def _rimuovi_data(self, row):
        row.destroy()
        self.date_rows.remove(row)

    def _scegli_cartella(self):
        percorso = filedialog.askdirectory(title="Seleziona la cartella con i file .docx")
        if percorso:
            self.cartella_var.set(percorso)

    def _log(self, messaggio):
        self.log_queue.put(messaggio)

    def _poll_log_queue(self):
        try:
            while True:
                messaggio = self.log_queue.get_nowait()
                self.log_text.configure(state="normal")
                self.log_text.insert("end", messaggio + "\n")
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self._poll_log_queue)

    def _avvia(self):
        cartella = self.cartella_var.get().strip()
        nominativi = [row.valori() for row in self.nominativi_rows]
        nominativi = [(nome, tag) for nome, tag in nominativi if nome]
        date_input = [row.valore() for row in self.date_rows]
        date_input = [d for d in date_input if d]
        oscura_telefoni = self.telefoni_var.get()

        if not cartella:
            messagebox.showwarning("Campo mancante", "Seleziona la cartella da elaborare.")
            return
        if not nominativi:
            messagebox.showwarning("Campo mancante", "Inserisci almeno un nominativo da oscurare.")
            return
        if not date_input:
            messagebox.showwarning("Campo mancante", "Inserisci almeno una data da oscurare.")
            return

        try:
            for data_input in date_input:
                parser.parse(data_input, dayfirst=True, fuzzy=True)
        except Exception as e:
            messagebox.showerror("Data non valida", f"Impossibile interpretare la data '{data_input}': {e}")
            return

        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

        self.avvia_btn.configure(state="disabled")
        self.worker_thread = threading.Thread(
            target=self._esegui_elaborazione,
            args=(cartella, nominativi, date_input, oscura_telefoni),
            daemon=True
        )
        self.worker_thread.start()

    def _esegui_elaborazione(self, cartella, nominativi, date_input, oscura_telefoni):
        try:
            elabora_cartella(cartella, nominativi, date_input, oscura_telefoni, self._log)
        except Exception as e:
            self._log(f"❌ Impossibile completare l'operazione: {e}")
        finally:
            self.root.after(0, lambda: self.avvia_btn.configure(state="normal"))


def main():
    root = tk.Tk()
    OscuraDocumentiApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
