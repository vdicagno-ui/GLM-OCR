# -*- coding: utf-8 -*-
"""
Stampa Ricevute PEC
===================

Programma desktop OFFLINE per Windows che:

1. Apre automaticamente la cartella "Posta in arrivo" di Outlook.
2. Chiede, ad ogni avvio, una cartella di destinazione e una data.
3. Per ogni sottocartella della Posta in arrivo cerca, nella cartella
   scelta, la sottocartella la cui dicitura CONTIENE il nome della
   sottocartella di Outlook.
4. Nelle sottocartelle di Outlook corrispondenti, stampa in PDF tutte le
   ricevute di consegna PEC (oggetto che inizia con "CONSEGNA:") ricevute
   nella data indicata, escludendo quelle collegate agli indirizzi INPS
   configurati.
5. Salva ogni PDF con nome "bozza ad avv." nella sottocartella corrispondente
   della cartella scelta.

Richiede: Windows con Microsoft Outlook (e Microsoft Word per la conversione
in PDF, oppure PDF24). Dipendenza Python: pywin32.
"""

import os
import sys
import queue
import threading
import traceback
from datetime import date, datetime

def _load_config():
    """
    Carica la configurazione.

    Da' priorita' a un file 'config.py' posto accanto all'eseguibile o allo
    script: cosi' l'utente puo' modificarlo senza ricompilare. In assenza,
    usa la configurazione inclusa.
    """
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    external = os.path.join(base_dir, "config.py")
    if os.path.exists(external):
        import importlib.util
        spec = importlib.util.spec_from_file_location("config", external)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    import config as bundled  # type: ignore
    return bundled


config = _load_config()

# tkinter fa parte della libreria standard di Python (nessuna installazione).
import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox


# Costanti Outlook (evitiamo la dipendenza dalle costanti generate da pywin32)
OL_FOLDER_INBOX = 6          # olFolderInbox
WD_EXPORT_FORMAT_PDF = 17    # wdExportFormatPDF


# ---------------------------------------------------------------------------
# Utilita' varie
# ---------------------------------------------------------------------------
def normalize(text):
    """Normalizza un nome per il confronto: minuscolo, spazi compattati."""
    if text is None:
        return ""
    return " ".join(str(text).lower().split())


def safe(value):
    """Ritorna una stringa anche se il valore e' None o solleva eccezioni."""
    try:
        return "" if value is None else str(value)
    except Exception:
        return ""


def sanitize_filename(name):
    """Rende una stringa utilizzabile come nome file su Windows."""
    invalid = '<>:"/\\|?*'
    cleaned = "".join(("_" if c in invalid else c) for c in name)
    return cleaned.strip().rstrip(".") or "file"


def unique_pdf_path(folder, base_name):
    """
    Costruisce un percorso PDF non esistente a partire dal nome base.

    Primo file:  "<base>.pdf"
    Successivi:  "<base> (2).pdf", "<base> (3).pdf", ...
    """
    candidate = os.path.join(folder, base_name + ".pdf")
    if not os.path.exists(candidate):
        return candidate
    n = 2
    while True:
        candidate = os.path.join(folder, "{} ({}).pdf".format(base_name, n))
        if not os.path.exists(candidate):
            return candidate
        n += 1


def parse_date(text):
    """Converte una stringa data (GG/MM/AAAA o AAAA-MM-GG) in datetime.date."""
    text = text.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(
        "Data non valida: '{}'. Usa il formato GG/MM/AAAA.".format(text)
    )


# ---------------------------------------------------------------------------
# Interazione con Outlook (COM)
# ---------------------------------------------------------------------------
def get_sender_smtp(mail):
    """Ricava l'indirizzo SMTP del mittente, anche per account Exchange."""
    try:
        if getattr(mail, "SenderEmailType", "") == "EX":
            sender = mail.Sender
            if sender is not None:
                exch = sender.GetExchangeUser()
                if exch is not None and exch.PrimarySmtpAddress:
                    return exch.PrimarySmtpAddress
    except Exception:
        pass
    return safe(getattr(mail, "SenderEmailAddress", ""))


def recipients_addresses(mail):
    """Elenco degli indirizzi (SMTP quando possibile) dei destinatari."""
    result = []
    try:
        for rec in mail.Recipients:
            addr = safe(getattr(rec, "Address", ""))
            try:
                exch = rec.AddressEntry.GetExchangeUser()
                if exch is not None and exch.PrimarySmtpAddress:
                    addr = exch.PrimarySmtpAddress
            except Exception:
                pass
            if addr:
                result.append(addr)
    except Exception:
        pass
    return result


def is_delivery_receipt(mail):
    """Vero se l'oggetto della mail corrisponde a una ricevuta di consegna."""
    subject = normalize(getattr(mail, "Subject", ""))
    for prefix in config.RECEIPT_SUBJECT_PREFIXES:
        if subject.startswith(normalize(prefix)):
            return True
    return False


def is_excluded(mail):
    """Vero se la ricevuta e' collegata a uno degli indirizzi da escludere."""
    excluded = [a.lower() for a in config.EXCLUDED_ADDRESSES]

    sender_fields = [
        get_sender_smtp(mail).lower(),
        safe(getattr(mail, "SenderEmailAddress", "")).lower(),
        safe(getattr(mail, "SenderName", "")).lower(),
    ]
    if config.EXCLUSION_SCOPE == "sender":
        haystack = " ".join(sender_fields)
    else:
        parts = sender_fields + [
            safe(getattr(mail, "To", "")).lower(),
            safe(getattr(mail, "CC", "")).lower(),
            safe(getattr(mail, "Subject", "")).lower(),
            safe(getattr(mail, "Body", "")).lower(),
        ]
        parts += [a.lower() for a in recipients_addresses(mail)]
        haystack = " ".join(parts)

    return any(addr in haystack for addr in excluded)


def received_on(mail, target_day):
    """Vero se la mail e' stata ricevuta nel giorno indicato."""
    try:
        rt = mail.ReceivedTime
        return date(rt.year, rt.month, rt.day) == target_day
    except Exception:
        return False


def iter_matching_receipts(folder, target_day, log):
    """
    Restituisce le ricevute di consegna della cartella Outlook ricevute nel
    giorno indicato e non escluse.
    """
    receipts = []
    try:
        items = folder.Items
        try:
            items.Sort("[ReceivedTime]", True)
        except Exception:
            pass
    except Exception as exc:
        log("    ! Impossibile leggere gli elementi: {}".format(exc))
        return receipts

    for item in items:
        try:
            # Consideriamo solo le mail (MailItem ha Class == 43)
            if getattr(item, "Class", None) != 43:
                continue
            if not received_on(item, target_day):
                continue
            if not is_delivery_receipt(item):
                continue
            if is_excluded(item):
                log("    - esclusa (indirizzo INPS): {}".format(
                    safe(item.Subject)))
                continue
            receipts.append(item)
        except Exception:
            continue
    return receipts


# ---------------------------------------------------------------------------
# Conversione della mail in PDF
# ---------------------------------------------------------------------------
def build_email_html(mail):
    """Costruisce l'HTML di stampa: intestazione + corpo della mail."""
    import html as html_lib

    def esc(v):
        return html_lib.escape(safe(v))

    try:
        received = mail.ReceivedTime
        received_str = received.strftime("%d/%m/%Y %H:%M")
    except Exception:
        received_str = ""

    header = (
        '<table style="font-family:Segoe UI,Arial,sans-serif;font-size:11pt;'
        'border-collapse:collapse;margin-bottom:12px">'
        '<tr><td style="padding:2px 8px 2px 0;font-weight:bold">Da:</td>'
        '<td>{da}</td></tr>'
        '<tr><td style="padding:2px 8px 2px 0;font-weight:bold">Inviato:</td>'
        '<td>{inviato}</td></tr>'
        '<tr><td style="padding:2px 8px 2px 0;font-weight:bold">A:</td>'
        '<td>{a}</td></tr>'
        '<tr><td style="padding:2px 8px 2px 0;font-weight:bold">Oggetto:</td>'
        '<td>{oggetto}</td></tr>'
        '</table><hr>'
    ).format(
        da=esc(get_sender_smtp(mail) or getattr(mail, "SenderName", "")),
        inviato=esc(received_str),
        a=esc(getattr(mail, "To", "")),
        oggetto=esc(getattr(mail, "Subject", "")),
    )

    body_html = safe(getattr(mail, "HTMLBody", ""))
    if not body_html.strip():
        body_html = "<pre style='font-family:Consolas,monospace;font-size:10pt'>{}</pre>".format(
            html_lib.escape(safe(getattr(mail, "Body", "")))
        )

    return (
        '<html><head><meta charset="utf-8"></head>'
        '<body style="font-family:Segoe UI,Arial,sans-serif">'
        + header + body_html +
        '</body></html>'
    )


class WordPdfConverter:
    """Converte HTML in PDF usando Microsoft Word (una sola istanza)."""

    def __init__(self):
        import win32com.client
        self._win32 = win32com.client
        self.word = win32com.client.DispatchEx("Word.Application")
        self.word.Visible = False
        try:
            self.word.DisplayAlerts = 0  # wdAlertsNone
        except Exception:
            pass

    def convert(self, html_text, pdf_path, tmp_dir):
        tmp_html = os.path.join(
            tmp_dir, "_tmp_{}.html".format(os.getpid()))
        with open(tmp_html, "w", encoding="utf-8") as fh:
            fh.write(html_text)
        doc = None
        try:
            # ConfirmConversions=False, ReadOnly=True, AddToRecentFiles=False
            doc = self.word.Documents.Open(
                tmp_html, False, True, False)
            doc.ExportAsFixedFormat(pdf_path, WD_EXPORT_FORMAT_PDF)
        finally:
            if doc is not None:
                try:
                    doc.Close(False)
                except Exception:
                    pass
            try:
                os.remove(tmp_html)
            except Exception:
                pass

    def close(self):
        try:
            self.word.Quit()
        except Exception:
            pass


class Pdf24Converter:
    """Converte HTML in PDF usando lo strumento a riga di comando di PDF24."""

    def __init__(self):
        import subprocess
        self._subprocess = subprocess
        if not os.path.exists(config.PDF24_DOCTOOL):
            raise RuntimeError(
                "PDF24 non trovato in: {}".format(config.PDF24_DOCTOOL))

    def convert(self, html_text, pdf_path, tmp_dir):
        tmp_html = os.path.join(
            tmp_dir, "_tmp_{}.html".format(os.getpid()))
        with open(tmp_html, "w", encoding="utf-8") as fh:
            fh.write(html_text)
        try:
            out_dir = os.path.dirname(pdf_path)
            self._subprocess.run(
                [config.PDF24_DOCTOOL, "-convertToPDF",
                 "-outputDir", out_dir, tmp_html],
                check=True,
            )
            produced = os.path.join(
                out_dir,
                os.path.splitext(os.path.basename(tmp_html))[0] + ".pdf",
            )
            if os.path.exists(produced):
                os.replace(produced, pdf_path)
        finally:
            try:
                os.remove(tmp_html)
            except Exception:
                pass

    def close(self):
        pass


def make_converter():
    if config.PDF_ENGINE == "pdf24":
        return Pdf24Converter()
    return WordPdfConverter()


# ---------------------------------------------------------------------------
# Elaborazione principale
# ---------------------------------------------------------------------------
def list_chosen_subfolders(chosen_folder):
    """Elenco (nome, percorso) delle sottocartelle della cartella scelta."""
    result = []
    for entry in os.scandir(chosen_folder):
        if entry.is_dir():
            result.append((entry.name, entry.path))
    return result


def find_matching_chosen_subfolder(outlook_name, chosen_subfolders):
    """
    Trova la sottocartella scelta la cui dicitura CONTIENE il nome della
    cartella Outlook. Ritorna (percorso, elenco_ambiguita').
    """
    key = normalize(outlook_name)
    if not key:
        return None, []
    matches = [
        path for (name, path) in chosen_subfolders
        if key in normalize(name)
    ]
    if not matches:
        return None, []
    return matches[0], matches


def run_processing(chosen_folder, target_day, log, progress):
    """Esegue l'intera procedura. Chiamata in un thread separato."""
    import pythoncom
    pythoncom.CoInitialize()
    converter = None
    total_pdf = 0
    try:
        import win32com.client
        log("Connessione a Outlook in corso...")
        outlook = win32com.client.Dispatch("Outlook.Application")
        ns = outlook.GetNamespace("MAPI")
        inbox = ns.GetDefaultFolder(OL_FOLDER_INBOX)

        if config.OPEN_OUTLOOK_INBOX:
            try:
                inbox.Display()
            except Exception:
                pass
        if config.OPEN_CHOSEN_FOLDER:
            try:
                os.startfile(chosen_folder)
            except Exception:
                pass

        chosen_subfolders = list_chosen_subfolders(chosen_folder)
        log("Cartella scelta: {} ({} sottocartelle)".format(
            chosen_folder, len(chosen_subfolders)))
        log("Data selezionata: {}".format(target_day.strftime("%d/%m/%Y")))
        log("-" * 60)

        outlook_subfolders = list(inbox.Folders)
        log("Sottocartelle in Posta in arrivo: {}".format(
            len(outlook_subfolders)))

        converter = make_converter()

        for ol_folder in outlook_subfolders:
            ol_name = safe(ol_folder.Name)
            log("")
            log("Cartella Outlook: '{}'".format(ol_name))

            dest_path, all_matches = find_matching_chosen_subfolder(
                ol_name, chosen_subfolders)
            if dest_path is None:
                log("    ~ nessuna sottocartella corrispondente: salto.")
                continue
            if len(all_matches) > 1:
                log("    ! Attenzione: {} corrispondenze, uso la prima:"
                    " {}".format(len(all_matches),
                                 os.path.basename(dest_path)))
            log("    -> destinazione: {}".format(
                os.path.basename(dest_path)))

            receipts = iter_matching_receipts(ol_folder, target_day, log)
            if not receipts:
                log("    (nessuna ricevuta di consegna da stampare)")
                continue

            for mail in receipts:
                try:
                    pdf_path = unique_pdf_path(
                        dest_path, config.BASE_FILENAME)
                    html_text = build_email_html(mail)
                    converter.convert(html_text, pdf_path, dest_path)
                    total_pdf += 1
                    log("    OK  {}  <-  {}".format(
                        os.path.basename(pdf_path),
                        safe(mail.Subject)[:60]))
                except Exception as exc:
                    log("    ERRORE stampa: {} ({})".format(
                        safe(getattr(mail, "Subject", "")), exc))

        log("")
        log("=" * 60)
        log("Completato. PDF generati: {}".format(total_pdf))
    except Exception as exc:
        log("ERRORE GRAVE: {}".format(exc))
        log(traceback.format_exc())
    finally:
        if converter is not None:
            converter.close()
        pythoncom.CoUninitialize()
        progress(total_pdf)


# ---------------------------------------------------------------------------
# Interfaccia grafica (tkinter)
# ---------------------------------------------------------------------------
class App:
    def __init__(self, root):
        self.root = root
        self.chosen_folder = tk.StringVar()
        self.date_var = tk.StringVar(value=date.today().strftime("%d/%m/%Y"))
        self.log_queue = queue.Queue()
        self.worker = None

        root.title("Stampa Ricevute PEC")
        root.geometry("760x560")
        root.minsize(640, 460)

        self._build_ui()
        self._poll_log_queue()

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        top = tk.Frame(self.root)
        top.pack(fill="x", **pad)

        # Data
        tk.Label(top, text="Data (GG/MM/AAAA):").grid(
            row=0, column=0, sticky="w")
        tk.Entry(top, textvariable=self.date_var, width=16).grid(
            row=0, column=1, sticky="w", padx=6)

        # Cartella
        tk.Label(top, text="Cartella di destinazione:").grid(
            row=1, column=0, sticky="w", pady=(8, 0))
        tk.Entry(top, textvariable=self.chosen_folder, width=52).grid(
            row=1, column=1, sticky="we", padx=6, pady=(8, 0))
        tk.Button(top, text="Scegli...", command=self.choose_folder).grid(
            row=1, column=2, sticky="w", pady=(8, 0))
        top.columnconfigure(1, weight=1)

        # Avvio
        self.start_btn = tk.Button(
            self.root, text="Avvia stampa ricevute",
            command=self.start, height=2)
        self.start_btn.pack(fill="x", padx=10, pady=(4, 8))

        # Log
        tk.Label(self.root, text="Registro operazioni:").pack(
            anchor="w", padx=10)
        self.log_widget = scrolledtext.ScrolledText(
            self.root, height=20, state="disabled", wrap="word")
        self.log_widget.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def choose_folder(self):
        path = filedialog.askdirectory(
            title="Scegli la cartella di destinazione")
        if path:
            self.chosen_folder.set(path)

    def log(self, message):
        self.log_queue.put(message)

    def _poll_log_queue(self):
        while True:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.log_widget.configure(state="normal")
            self.log_widget.insert("end", message + "\n")
            self.log_widget.see("end")
            self.log_widget.configure(state="disabled")
        self.root.after(120, self._poll_log_queue)

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        chosen = self.chosen_folder.get().strip()
        if not chosen or not os.path.isdir(chosen):
            messagebox.showwarning(
                "Cartella mancante",
                "Seleziona una cartella di destinazione valida.")
            return
        try:
            target_day = parse_date(self.date_var.get())
        except ValueError as exc:
            messagebox.showwarning("Data non valida", str(exc))
            return

        self.start_btn.configure(state="disabled", text="Elaborazione...")
        self.worker = threading.Thread(
            target=run_processing,
            args=(chosen, target_day, self.log, self._on_done),
            daemon=True,
        )
        self.worker.start()

    def _on_done(self, total_pdf):
        # Richiamata dal thread: riattiva il pulsante nel thread della GUI.
        self.root.after(0, lambda: self._finish(total_pdf))

    def _finish(self, total_pdf):
        self.start_btn.configure(
            state="normal", text="Avvia stampa ricevute")
        messagebox.showinfo(
            "Completato",
            "Elaborazione terminata.\nPDF generati: {}".format(total_pdf))


def main():
    if not sys.platform.startswith("win"):
        print("ATTENZIONE: questo programma funziona solo su Windows con "
              "Microsoft Outlook installato.")
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
