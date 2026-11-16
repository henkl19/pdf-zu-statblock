from __future__ import annotations
import csv, os, re, sys, threading, queue, subprocess, shutil
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import fitz
    from PIL import Image
except Exception as exc:
    raise SystemExit(f"Fehlende Bibliothek: {exc}\nBitte requirements installieren.")

APP_NAME = "Atlas Monster Importer"


def resource_path(*parts):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base.joinpath(*parts)


def tesseract_path():
    bundled = resource_path("tesseract.exe")
    if bundled.exists():
        return str(bundled)
    return shutil.which("tesseract") or ""


def norm(s: str) -> str:
    s = s.casefold().strip()
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return re.sub(r"[^a-z0-9]+", "", s)


def load_srd_csv(path: str) -> dict[str, str]:
    if not path:
        return {}
    out = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(2048); f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
        except csv.Error:
            dialect = csv.excel
        rows = csv.reader(f, dialect)
        for row in rows:
            if not row: continue
            name = row[0].strip()
            if not name or name.casefold() in {"name", "monster", "creature", "kreatur"}: continue
            out[norm(name)] = name
    return out


def run_ocr(exe: str, image_path: Path, lang: str) -> str:
    env = os.environ.copy()
    tessdata = resource_path("tessdata")
    if tessdata.exists(): env["TESSDATA_PREFIX"] = str(tessdata)
    cmd = [exe, str(image_path), "stdout", "-l", lang, "--psm", "11"]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    if p.returncode not in (0, 1):
        raise RuntimeError(p.stderr.strip() or "Tesseract-OCR fehlgeschlagen")
    return p.stdout.strip()


def find_heading(text: str, page_no: int) -> str:
    lines = [re.sub(r"\s+", " ", x).strip(" |:-") for x in text.splitlines() if x.strip()]
    # Headings are usually near the beginning of a statblock; avoid generic labels.
    skip = {"monster", "aktionen", "reaktionen", "legendare aktionen", "werte"}
    for line in lines[:18]:
        clean = re.sub(r"[^A-Za-zÄÖÜäöüß0-9 '\-’]", "", line).strip()
        if 2 <= len(clean) <= 48 and norm(clean) not in skip and not re.search(r"\d{2,}", clean):
            if not re.search(r"(rüstungsklasse|trefferpunkte|bewegung|initiative|stärke|geschicklichkeit)", clean, re.I):
                return clean
    return f"Monster Seite {page_no}"


def is_monster_page(text: str) -> bool:
    t = text.casefold()
    checks = [
        any(x in t for x in ("rüstungsklasse", "ruestungsklasse", "rüstungskl.", "rk ")),
        any(x in t for x in ("trefferpunkte", "tp ", "tp\n", "hit points")),
        any(x in t for x in ("aktionen", "aktion", "actions")),
        any(x in t for x in ("herausforderungsgrad", "cr", "übung", "übungsbonus")),
    ]
    return sum(checks) >= 3


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} 0.1")
        self.geometry("780x590")
        self.minsize(700, 540)
        self.q = queue.Queue()
        self.worker = None
        self.pdf_var = tk.StringVar()
        self.out_var = tk.StringVar(value=str(Path.home() / "Documents" / "Atlas-Monsterimport"))
        self.srd_var = tk.StringVar()
        self.start_var = tk.StringVar(value="1")
        self.end_var = tk.StringVar(value="0")
        self.dpi_var = tk.StringVar(value="200")
        self.lang_var = tk.StringVar(value="deu+eng")
        self._build()
        self.after(150, self._poll)

    def _build(self):
        root = ttk.Frame(self, padding=16); root.pack(fill="both", expand=True)
        ttk.Label(root, text="Atlas Monster Importer", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(root, text="OCR-Import für gescannte Monsterhandbücher – erzeugt prüfbare Obsidian-Entwürfe.", wraplength=730).pack(anchor="w", pady=(3, 14))
        self._file_row(root, "Monsterhandbuch (PDF)", self.pdf_var, self._pick_pdf)
        self._file_row(root, "Ausgabeordner", self.out_var, self._pick_out, is_dir=True)
        self._file_row(root, "SRD-Monsterliste (CSV, optional)", self.srd_var, self._pick_srd)
        opts = ttk.LabelFrame(root, text="Importeinstellungen", padding=10); opts.pack(fill="x", pady=12)
        grid = ttk.Frame(opts); grid.pack(fill="x")
        for col, (label, var, width) in enumerate([
            ("Startseite", self.start_var, 8), ("Endseite (0 = alle)", self.end_var, 8), ("DPI", self.dpi_var, 8), ("OCR-Sprache", self.lang_var, 12)
        ]):
            cell = ttk.Frame(grid); cell.grid(row=0, column=col, padx=(0, 14), sticky="w")
            ttk.Label(cell, text=label).pack(anchor="w")
            ttk.Entry(cell, textvariable=var, width=width).pack(anchor="w", pady=(4, 0))
        ttk.Label(opts, text="Deutsch + Englisch: deu+eng. Höhere DPI verbessert OCR, benötigt aber mehr Zeit.", foreground="#555").pack(anchor="w", pady=(8, 0))
        self.start_btn = ttk.Button(root, text="Import starten", command=self.start); self.start_btn.pack(anchor="w", pady=(2, 10))
        self.progress = ttk.Progressbar(root, mode="determinate"); self.progress.pack(fill="x")
        self.status = tk.StringVar(value="Bereit")
        ttk.Label(root, textvariable=self.status).pack(anchor="w", pady=(6, 5))
        self.log = tk.Text(root, height=12, wrap="word", state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True)
        ttk.Label(root, text="Hinweis: OCR-Entwürfe sind noch keine fertigen Atlas-Statblöcke. Werte und Aktionen müssen geprüft werden.", foreground="#8a4b08", wraplength=730).pack(anchor="w", pady=(9, 0))

    def _file_row(self, parent, label, var, command, is_dir=False):
        row = ttk.Frame(parent); row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, width=29).pack(side="left")
        ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True, padx=7)
        ttk.Button(row, text="Auswählen…", command=command).pack(side="left")

    def _pick_pdf(self):
        p = filedialog.askopenfilename(filetypes=[("PDF-Dateien", "*.pdf")])
        if p: self.pdf_var.set(p)
    def _pick_out(self):
        p = filedialog.askdirectory()
        if p: self.out_var.set(p)
    def _pick_srd(self):
        p = filedialog.askopenfilename(filetypes=[("CSV-Dateien", "*.csv")])
        if p: self.srd_var.set(p)

    def logline(self, s):
        self.log.configure(state="normal"); self.log.insert("end", s + "\n"); self.log.see("end"); self.log.configure(state="disabled")

    def start(self):
        if self.worker and self.worker.is_alive(): return
        pdf = Path(self.pdf_var.get())
        if not pdf.is_file(): messagebox.showerror("PDF fehlt", "Bitte ein gültiges Monsterhandbuch-PDF auswählen."); return
        exe = tesseract_path()
        if not exe: messagebox.showerror("OCR-Komponente fehlt", "Tesseract-OCR wurde nicht gefunden. Nutze die vollständige Windows-Version oder installiere Tesseract-OCR."); return
        try:
            start, end, dpi = int(self.start_var.get()), int(self.end_var.get()), int(self.dpi_var.get())
            if start < 1 or end < 0 or dpi < 100 or dpi > 400: raise ValueError()
        except ValueError:
            messagebox.showerror("Einstellungen prüfen", "Startseite >= 1, Endseite >= 0 und DPI zwischen 100 und 400 eingeben."); return
        out = Path(self.out_var.get())
        out.mkdir(parents=True, exist_ok=True)
        self.start_btn.configure(state="disabled"); self.progress["value"] = 0; self.logline("Import wird vorbereitet …")
        args = (str(pdf), str(out), self.srd_var.get(), start, end, dpi, self.lang_var.get(), exe)
        self.worker = threading.Thread(target=self._work, args=args, daemon=True); self.worker.start()

    def _work(self, pdf_path, out_path, srd_path, start, end, dpi, lang, exe):
        try:
            out = Path(out_path); notes = out / "Monster-Entwuerfe"; assets = out / "assets"
            notes.mkdir(parents=True, exist_ok=True); assets.mkdir(parents=True, exist_ok=True)
            srd = load_srd_csv(srd_path)
            doc = fitz.open(pdf_path)
            first = start - 1; last = min(end, len(doc)) if end else len(doc)
            if first >= len(doc) or last <= first: raise ValueError(f"Ungültiger Seitenbereich. PDF hat {len(doc)} Seiten.")
            self.q.put(("max", last-first)); self.q.put(("log", f"PDF: {len(doc)} Seiten | Verarbeite PDF-Seiten {start} bis {last}"))
            index_rows = []
            for i in range(first, last):
                page = doc.load_page(i)
                pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72), alpha=False)
                tmp_img = out / f".ocr_page_{i+1}.png"
                pix.save(tmp_img)
                text = run_ocr(exe, tmp_img, lang)
                tmp_img.unlink(missing_ok=True)
                if is_monster_page(text):
                    heading = find_heading(text, i+1)
                    safe = re.sub(r"[^A-Za-z0-9ÄÖÜäöüß_-]+", "_", heading).strip("_")[:55] or f"Monster_{i+1}"
                    base = f"{safe}_PDF-{i+1:03d}"
                    # Full page is preserved as a visual source reference; crop/illustration selection is a later manual step.
                    img_path = assets / f"{base}.webp"
                    page_pix = page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8), alpha=False)
                    img = Image.frombytes("RGB", [page_pix.width, page_pix.height], page_pix.samples)
                    img.save(img_path, "WEBP", quality=86, method=5)
                    book_page = i + 1 - 1  # printed page often differs; keep PDF page as authoritative reference
                    srd_match = srd.get(norm(heading), "")
                    note = notes / f"{base}.md"
                    rel_img = Path("..") / "assets" / img_path.name
                    note.write_text(
                        "---\n" + f'name: "{heading.replace(chr(34), chr(39))}"\n' +
                        f"source-pdf-page: {i+1}\n" +
                        'import-status: "OCR-Entwurf – Prüfung erforderlich"\n' +
                        f'image: "{rel_img.as_posix()}"\n' +
                        (f'srd-match: "{srd_match}"\n' if srd_match else "srd-match: \"Kein Namens-Treffer in der optionalen SRD-Liste\"\n") +
                        "---\n\n" + f"# {heading}\n\n" +
                        f"**Quelle:** PDF-Seite {i+1}. Bitte mit dem Buch vergleichen.\n\n" +
                        f"![[{rel_img.as_posix()}]]\n\n" +
                        "## OCR-Text (Rohfassung)\n\n```text\n" + text.replace("```", "'''" ) + "\n```\n\n" +
                        "## Atlas-VTT-Übertragung\n\nNoch nicht erstellt. Werte, Rettungswürfe, Fertigkeiten, Eigenschaften und Aktionen vor Übernahme prüfen.\n",
                        encoding="utf-8")
                    index_rows.append({"PDF-Seite": i+1, "Erkannter Name": heading, "Notiz": note.name, "SRD-Treffer": srd_match or "kein Namens-Treffer"})
                    self.q.put(("log", f"Kandidat: {heading} (PDF-Seite {i+1})"))
                if (i-first+1) % 5 == 0 or i == last-1:
                    self.q.put(("progress", i-first+1, last-first, f"OCR: Seite {i+1}/{last}"))
            with open(out / "Importindex.csv", "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["PDF-Seite", "Erkannter Name", "Notiz", "SRD-Treffer"])
                writer.writeheader(); writer.writerows(index_rows)
            (out / "README_IMPORT.txt").write_text(
                f"Atlas Monster Importer 0.1\n\nPDF: {Path(pdf_path).name}\nVerarbeitete Seiten: {start}-{last}\nKandidaten: {len(index_rows)}\n\n"
                "Die erzeugten Markdown-Dateien sind OCR-Entwürfe und keine fertigen Atlas-VTT-Statblöcke. OCR kann Zahlen, Sonderzeichen und Zeilenumbrüche falsch erkennen.\n"
                "Die Bilder zeigen die vollständige Buchseite als Referenz; sie sind noch nicht automatisch auf die Monsterillustration zugeschnitten.\n"
                "Die optionale SRD-Prüfung ist ein normalisierter Namensvergleich auf Basis der von dir gewählten CSV-Datei, kein inhaltlicher Dublettenvergleich.\n",
                encoding="utf-8")
            self.q.put(("done", len(index_rows), str(out)))
        except Exception as e:
            self.q.put(("error", str(e)))

    def _poll(self):
        try:
            while True:
                item = self.q.get_nowait(); kind = item[0]
                if kind == "log": self.logline(item[1])
                elif kind == "max": self.progress["maximum"] = item[1]
                elif kind == "progress":
                    _, n, total, status = item; self.progress["maximum"] = total; self.progress["value"] = n; self.status.set(status)
                elif kind == "done":
                    _, count, path = item; self.start_btn.configure(state="normal"); self.status.set(f"Fertig: {count} Monster-Kandidaten")
                    self.logline(f"Fertig. Ausgabe: {path}"); messagebox.showinfo("Import abgeschlossen", f"{count} Monster-Kandidaten wurden angelegt.\n\nAusgabeordner:\n{path}\n\nBitte OCR-Entwürfe prüfen; sie sind noch keine fertigen Atlas-Statblöcke.")
                elif kind == "error":
                    self.start_btn.configure(state="normal"); self.status.set("Fehler"); self.logline("FEHLER: " + item[1]); messagebox.showerror("Importfehler", item[1])
        except queue.Empty: pass
        self.after(150, self._poll)


if __name__ == "__main__":
    App().mainloop()
