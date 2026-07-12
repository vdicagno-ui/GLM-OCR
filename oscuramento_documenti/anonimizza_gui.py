"""
Oscura Documenti - GUI desktop per l'anonimizzazione di file .docx
Basato sullo script da riga di comando: sostituisce nome/cognome, data di nascita
e codice fiscale con dei tag di copertura in tutti i file .docx di una cartella.
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

TAG_NOME = "[soggetto_interessato]"
TAG_DATA = "[data_nascita_oscurata]"
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


def anonimizza_singolo_file(file_path, regex_nome, regex_data, log):
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
            cambiato_nome = applica_sostituzione_sicura(p, regex_nome, TAG_NOME)
            cambiato_data = applica_sostituzione_sicura(p, regex_data, TAG_DATA)
            cambiato_cf = applica_sostituzione_sicura(p, REGEX_CF, TAG_CF)
            if cambiato_nome or cambiato_data or cambiato_cf:
                modificato = True

        if modificato:
            doc.save(file_path)
            return True
        return False
    except Exception as e:
        log(f"❌ Errore durante l'elaborazione di {os.path.basename(file_path)}: {e}")
        return False


def elabora_cartella(cartella, nome_input, data_input, log):
    if not os.path.exists(cartella):
        log(f"Errore: la cartella '{cartella}' non esiste.")
        return

    regex_nome = genera_regex_nome(nome_input)
    regex_data, etichetta_data = genera_regex_data(data_input)
    log(f"✅ Configurazione completata per il soggetto e per la data: {etichetta_data}")

    files = [f for f in os.listdir(cartella) if f.endswith('.docx') and not f.startswith('~$')]

    if not files:
        log(f"Nessun file .docx trovato in '{cartella}'.")
        return

    log(f"Inizio... Elaborazione di {len(files)} file nella cartella '{cartella}'...\n")
    file_modificati = 0

    for file_nome in files:
        percorso_completo = os.path.join(cartella, file_nome)
        ha_subito_modifiche = anonimizza_singolo_file(percorso_completo, regex_nome, regex_data, log)
        if ha_subito_modifiche:
            log(f" Modificato (Rilevato testo/date/CF): {file_nome}")
            file_modificati += 1
        else:
            log(f" Saltato (Nessuna corrispondenza): {file_nome}")

    log(f"\nFine! File totali modificati ed anonimizzati: {file_modificati}/{len(files)}")


class OscuraDocumentiApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Oscura Documenti")
        self.root.geometry("640x520")
        self.root.minsize(560, 440)

        self.log_queue = queue.Queue()
        self.worker_thread = None

        self._build_ui()
        self.root.after(100, self._poll_log_queue)

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}
        frame = ttk.Frame(self.root)
        frame.pack(fill="x", **pad)

        ttk.Label(frame, text="Cartella da elaborare:").grid(row=0, column=0, sticky="w")
        self.cartella_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.cartella_var, width=50).grid(row=1, column=0, sticky="we")
        ttk.Button(frame, text="Sfoglia...", command=self._scegli_cartella).grid(row=1, column=1, padx=(6, 0))

        ttk.Label(frame, text="Nome e Cognome da oscurare:").grid(row=2, column=0, sticky="w", pady=(10, 0))
        self.nome_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.nome_var, width=50).grid(row=3, column=0, columnspan=2, sticky="we")

        ttk.Label(frame, text="Data di nascita (qualsiasi formato):").grid(row=4, column=0, sticky="w", pady=(10, 0))
        self.data_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.data_var, width=50).grid(row=5, column=0, columnspan=2, sticky="we")

        frame.columnconfigure(0, weight=1)

        self.avvia_btn = ttk.Button(self.root, text="Avvia oscuramento", command=self._avvia)
        self.avvia_btn.pack(pady=(4, 8))

        self.log_text = scrolledtext.ScrolledText(self.root, wrap="word", state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))

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
        nome = self.nome_var.get().strip()
        data = self.data_var.get().strip()

        if not cartella:
            messagebox.showwarning("Campo mancante", "Seleziona la cartella da elaborare.")
            return
        if not nome:
            messagebox.showwarning("Campo mancante", "Inserisci il nome e cognome da oscurare.")
            return
        if not data:
            messagebox.showwarning("Campo mancante", "Inserisci la data da oscurare.")
            return

        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

        self.avvia_btn.configure(state="disabled")
        self.worker_thread = threading.Thread(
            target=self._esegui_elaborazione, args=(cartella, nome, data), daemon=True
        )
        self.worker_thread.start()

    def _esegui_elaborazione(self, cartella, nome, data):
        try:
            elabora_cartella(cartella, nome, data, self._log)
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
