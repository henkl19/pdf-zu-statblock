from __future__ import annotations
import csv, json, os, re, sys, threading, queue, subprocess, shutil, hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import fitz
from PIL import Image

APP_NAME = "Atlas Monster Importer"
VERSION = "0.2"

def resource_path(*parts):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base.joinpath(*parts)

def tesseract_path():
    bundled = resource_path("tesseract.exe")
    if bundled.exists(): return str(bundled)
    return shutil.which("tesseract") or ""

def norm(s: str) -> str:
    s = s.casefold().strip().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return re.sub(r"[^a-z0-9]+", "", s)

def load_srd_csv(path: str) -> dict[str, str]:
    if not path: return {}
    out = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        sample=f.read(2048); f.seek(0)
        try: dialect=csv.Sniffer().sniff(sample, delimiters=";,\t")
        except csv.Error: dialect=csv.excel
        for row in csv.reader(f, dialect):
            if not row: continue
            name=row[0].strip()
            if name and name.casefold() not in {"name","monster","creature","kreatur"}: out[norm(name)]=name
    return out

def run_ocr(exe: str, image_path: Path, lang: str, psm: int = 11) -> str:
    env=os.environ.copy(); tessdata=resource_path("tessdata")
    if tessdata.exists(): env["TESSDATA_PREFIX"]=str(tessdata)
    cmd=[exe,str(image_path),"stdout","-l",lang,"--psm",str(psm)]
    p=subprocess.run(cmd,capture_output=True,text=True,encoding="utf-8",errors="replace",env=env)
    if p.returncode not in (0,1): raise RuntimeError(p.stderr.strip() or "Tesseract-OCR fehlgeschlagen")
    return p.stdout.strip()

def is_monster_page(text: str) -> bool:
    t=text.casefold()
    checks=[any(x in t for x in ("rüstungsklasse","ruestungsklasse","rüstungskl.","rk ")),
            any(x in t for x in ("trefferpunkte","tp ","hit points")),
            any(x in t for x in ("aktionen","aktion","actions")),
            any(x in t for x in ("herausforderungsgrad","challenge rating","übungsbonus","proficiency bonus"))]
    # Also catch statblocks whose OCR mangles one or two headings.
    numeric_markers=sum(bool(re.search(p,text,re.I)) for p in [r"\bSTR\b|Stärke",r"\bGES\b|Geschick",r"\bKON\b|Konstitution",r"\bWEI\b|Weisheit",r"\bCHA\b|Charisma"])
    return sum(checks)>=3 or (sum(checks)>=2 and numeric_markers>=3)

def find_heading(text: str, page_no: int) -> str:
    lines=[re.sub(r"\s+"," ",x).strip(" |:-") for x in text.splitlines() if x.strip()]
    skip={"monster","aktionen","reaktionen","legendäre aktionen","werte","aktionen"}
    for line in lines[:24]:
        clean=re.sub(r"[^A-Za-zÄÖÜäöüß0-9 '\-’]","",line).strip()
        if 2<=len(clean)<=48 and norm(clean) not in skip and not re.search(r"\d{2,}",clean):
            if not re.search(r"(rüstungsklasse|trefferpunkte|bewegung|initiative|stärke|geschicklichkeit|konstitution)",clean,re.I): return clean
    return f"Monster Seite {page_no}"

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title(f"{APP_NAME} {VERSION}"); self.geometry("850x650"); self.minsize(760,590)
        self.q=queue.Queue(); self.worker=None; self.stop_event=threading.Event()
        self.pdf_var=tk.StringVar(); self.out_var=tk.StringVar(value=str(Path.home()/"Documents"/"Atlas-Monsterimport")); self.srd_var=tk.StringVar()
        self.start_var=tk.StringVar(value="1"); self.end_var=tk.StringVar(value="0"); self.scan_dpi_var=tk.StringVar(value="130"); self.detail_dpi_var=tk.StringVar(value="300")
        self.workers_var=tk.StringVar(value="6"); self.lang_var=tk.StringVar(value="deu+eng")
        self._build(); self.after(150,self._poll)

    def _build(self):
        root=ttk.Frame(self,padding=16); root.pack(fill="both",expand=True)
        ttk.Label(root,text="Atlas Monster Importer",font=("Segoe UI",18,"bold")).pack(anchor="w")
        ttk.Label(root,text=f"Version {VERSION} · lokale OCR · parallele Verarbeitung · Wiederaufnahme",wraplength=790).pack(anchor="w",pady=(3,12))
        self._file_row(root,"Monsterhandbuch (PDF)",self.pdf_var,self._pick_pdf); self._file_row(root,"Ausgabeordner",self.out_var,self._pick_out); self._file_row(root,"SRD-Monsterliste (CSV, optional)",self.srd_var,self._pick_srd)
        opts=ttk.LabelFrame(root,text="Leistung und Importbereich",padding=10); opts.pack(fill="x",pady=10)
        grid=ttk.Frame(opts); grid.pack(fill="x")
        fields=[("Startseite",self.start_var,8),("Endseite (0 = alle)",self.end_var,8),("Schnellscan DPI",self.scan_dpi_var,8),("Detail-DPI",self.detail_dpi_var,8),("Parallelprozesse",self.workers_var,8),("OCR-Sprache",self.lang_var,12)]
        for col,(label,var,width) in enumerate(fields):
            cell=ttk.Frame(grid); cell.grid(row=0,column=col,padx=(0,10),sticky="w"); ttk.Label(cell,text=label).pack(anchor="w"); ttk.Entry(cell,textvariable=var,width=width).pack(anchor="w",pady=(4,0))
        ttk.Label(opts,text="Voreinstellung für i7-9700K / 32 GB RAM: 6 parallele OCR-Prozesse, 130 DPI Seitenscan, 300 DPI Detailseiten.",foreground="#444").pack(anchor="w",pady=(8,0))
        bar=ttk.Frame(root); bar.pack(fill="x",pady=(3,8)); self.start_btn=ttk.Button(bar,text="Import starten / fortsetzen",command=self.start); self.start_btn.pack(side="left"); self.stop_btn=ttk.Button(bar,text="Anhalten",command=self.stop, state="disabled"); self.stop_btn.pack(side="left",padx=8)
        self.progress=ttk.Progressbar(root,mode="determinate"); self.progress.pack(fill="x")
        self.status=tk.StringVar(value="Bereit"); ttk.Label(root,textvariable=self.status).pack(anchor="w",pady=(6,5))
        self.log=tk.Text(root,height=15,wrap="word",state="disabled",font=("Consolas",9)); self.log.pack(fill="both",expand=True)
        ttk.Label(root,text="Hinweis: Die Version erzeugt OCR-Entwürfe und Quellenbilder, noch keine geprüften Atlas-Statblöcke. Die OCR läuft lokal; es werden keine Daten hochgeladen.",foreground="#8a4b08",wraplength=790).pack(anchor="w",pady=(9,0))

    def _file_row(self,parent,label,var,command):
        row=ttk.Frame(parent); row.pack(fill="x",pady=4); ttk.Label(row,text=label,width=29).pack(side="left"); ttk.Entry(row,textvariable=var).pack(side="left",fill="x",expand=True,padx=7); ttk.Button(row,text="Auswählen…",command=command).pack(side="left")
    def _pick_pdf(self):
        p=filedialog.askopenfilename(filetypes=[("PDF-Dateien","*.pdf")]); self.pdf_var.set(p) if p else None
    def _pick_out(self):
        p=filedialog.askdirectory(); self.out_var.set(p) if p else None
    def _pick_srd(self):
        p=filedialog.askopenfilename(filetypes=[("CSV-Dateien","*.csv")]); self.srd_var.set(p) if p else None
    def logline(self,s):
        self.log.configure(state="normal"); self.log.insert("end",s+"\n"); self.log.see("end"); self.log.configure(state="disabled")
    def start(self):
        if self.worker and self.worker.is_alive(): return
        pdf=Path(self.pdf_var.get()); exe=tesseract_path()
        if not pdf.is_file(): messagebox.showerror("PDF fehlt","Bitte ein gültiges Monsterhandbuch-PDF auswählen."); return
        if not exe: messagebox.showerror("OCR fehlt","Tesseract-OCR wurde nicht gefunden. Bitte die vollständige Windows-Version verwenden oder Tesseract installieren."); return
        try:
            start,end,sdpi,ddpi,workers=map(int,[self.start_var.get(),self.end_var.get(),self.scan_dpi_var.get(),self.detail_dpi_var.get(),self.workers_var.get()])
            if start<1 or end<0 or not (90<=sdpi<=200) or not (200<=ddpi<=400) or not (1<=workers<=12): raise ValueError()
        except ValueError: messagebox.showerror("Einstellungen prüfen","Start >= 1, Ende >= 0, Schnellscan 90–200 DPI, Detail 200–400 DPI und 1–12 Prozesse eingeben."); return
        out=Path(self.out_var.get()); out.mkdir(parents=True,exist_ok=True); self.stop_event.clear(); self.start_btn.configure(state="disabled"); self.stop_btn.configure(state="normal"); self.progress["value"]=0; self.logline("Import wird vorbereitet …")
        args=(str(pdf),str(out),self.srd_var.get(),start,end,sdpi,ddpi,workers,self.lang_var.get(),exe)
        self.worker=threading.Thread(target=self._work,args=args,daemon=True); self.worker.start()
    def stop(self):
        self.stop_event.set(); self.logline("Anhalten angefordert. Bereits abgeschlossene Seiten bleiben gespeichert.")

    def _work(self,pdf_path,out_path,srd_path,start,end,sdpi,ddpi,workers,lang,exe):
        try:
            out=Path(out_path); work=out/".atlas_import_work"; cache=work/"ocr_cache"; notes=out/"Monster-Entwuerfe"; assets=out/"assets"
            for p in (cache,notes,assets): p.mkdir(parents=True,exist_ok=True)
            doc=fitz.open(pdf_path); first=start-1; last=min(end,len(doc)) if end else len(doc)
            if first>=len(doc) or last<=first: raise ValueError(f"Ungültiger Seitenbereich. PDF hat {len(doc)} Seiten.")
            pdf_hash=hashlib.sha256((str(Path(pdf_path).resolve())+str(Path(pdf_path).stat().st_size)).encode()).hexdigest()[:12]
            self.q.put(("max",last-first)); self.q.put(("log",f"PDF: {len(doc)} Seiten | Schnellscan {sdpi} DPI | Detail {ddpi} DPI | {workers} Prozesse"))
            srd=load_srd_csv(srd_path); candidates=[]; pending=[]
            # Pass 1: low-resolution page scan; cached text makes restart cheap.
            for i in range(first,last):
                if self.stop_event.is_set(): break
                txtfile=cache/f"{pdf_hash}_{i+1}_{sdpi}_{lang.replace('+','-')}.txt"
                if txtfile.exists():
                    txt=txtfile.read_text(encoding="utf-8",errors="replace")
                    if is_monster_page(txt): candidates.append((i,txt))
                    self.q.put(("progress",i-first+1,last-first,f"Schnellscan (Cache): Seite {i+1}/{last}"))
                else:
                    pix=doc.load_page(i).get_pixmap(matrix=fitz.Matrix(sdpi/72,sdpi/72),alpha=False)
                    imgfile=work/f"scan_{i+1}.png"; pix.save(imgfile); pending.append((i,imgfile,txtfile))
            if pending:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures={pool.submit(run_ocr,exe,img,lang,11):(i,img,txt) for i,img,txt in pending}
                    done=0
                    for fut in as_completed(futures):
                        i,img,txtfile=futures[fut]; text=fut.result(); txtfile.write_text(text,encoding="utf-8"); img.unlink(missing_ok=True)
                        if is_monster_page(text): candidates.append((i,text)); self.q.put(("log",f"Kandidat erkannt: PDF-Seite {i+1}"))
                        done+=1; self.q.put(("progress",min(last-first,(i-first+1)),last-first,f"Schnellscan: {done}/{len(pending)} neue Seiten fertig"))
                        if self.stop_event.is_set():
                            for f in futures: f.cancel()
                            break
            if self.stop_event.is_set(): self.q.put(("paused",str(out))); return
            candidates.sort(key=lambda x:x[0]); self.q.put(("log",f"Schnellscan abgeschlossen: {len(candidates)} mögliche Monsterseiten."))
            # Pass 2: only candidate pages receive high-res OCR and source image export.
            index_rows=[]
            for n,(i,lowtext) in enumerate(candidates,1):
                if self.stop_event.is_set(): break
                page=doc.load_page(i); pix=page.get_pixmap(matrix=fitz.Matrix(ddpi/72,ddpi/72),alpha=False)
                imgfile=work/f"detail_{i+1}.png"; pix.save(imgfile); text=run_ocr(exe,imgfile,lang,11); imgfile.unlink(missing_ok=True)
                heading=find_heading(text,i+1); safe=re.sub(r"[^A-Za-z0-9ÄÖÜäöüß_-]+","_",heading).strip("_")[:55] or f"Monster_{i+1}"; base=f"{safe}_PDF-{i+1:03d}"
                pagepix=page.get_pixmap(matrix=fitz.Matrix(1.8,1.8),alpha=False); im=Image.frombytes("RGB",[pagepix.width,pagepix.height],pagepix.samples); image_name=base+"_Quellseite.webp"; im.save(assets/image_name,"WEBP",quality=84,method=5)
                rel_img=Path("..")/"assets"/image_name; match=srd.get(norm(heading),""); note=notes/(base+".md")
                note.write_text("---\n"+f'name: "{heading.replace(chr(34),chr(39))}"\n'+f"source-pdf-page: {i+1}\n"+'import-status: "OCR-Entwurf – Prüfung erforderlich"\n'+f'image: "{rel_img.as_posix()}"\n'+(f'srd-match: "{match}"\n' if match else 'srd-match: "Kein Namens-Treffer in der optionalen SRD-Liste"\n')+"---\n\n"+f"# {heading}\n\n**Quelle:** PDF-Seite {i+1}. Bitte mit dem Buch vergleichen.\n\n![[{rel_img.as_posix()}]]\n\n## OCR-Text (Detailauflösung)\n\n```text\n"+text.replace("```","'''" )+"\n```\n\n## Atlas-VTT-Übertragung\n\nNoch nicht erstellt. Werte und Aktionen vor Übernahme prüfen.\n",encoding="utf-8")
                index_rows.append({"PDF-Seite":i+1,"Erkannter Name":heading,"Notiz":note.name,"SRD-Treffer":match or "kein Namens-Treffer"})
                self.q.put(("progress",n,len(candidates),f"Detail-OCR: {n}/{len(candidates)} Kandidaten"))
                if n%10==0: self.q.put(("log",f"Detailseiten verarbeitet: {n}/{len(candidates)}"))
            if self.stop_event.is_set(): self.q.put(("paused",str(out))); return
            with open(out/"Importindex.csv","w",encoding="utf-8-sig",newline="") as f:
                w=csv.DictWriter(f,fieldnames=["PDF-Seite","Erkannter Name","Notiz","SRD-Treffer"]); w.writeheader(); w.writerows(index_rows)
            (out/"README_IMPORT.txt").write_text(f"Atlas Monster Importer {VERSION}\n\nPDF: {Path(pdf_path).name}\nSeitenbereich: {start}-{last}\nKandidaten: {len(index_rows)}\n\nDie OCR läuft lokal. Es werden keine PDF-Seiten oder Texte an einen Online-Dienst übertragen.\nDie Dateien sind OCR-Entwürfe, keine geprüften Atlas-Statblöcke. Bilder sind vollständige Quellseiten, keine automatisch isolierten Monsterillustrationen.\nDer SRD-Abgleich ist ein normalisierter Namensvergleich anhand der optionalen CSV-Liste.\nDer Arbeitsordner .atlas_import_work enthält den OCR-Cache und kann nach erfolgreichem Import gelöscht werden.\n",encoding="utf-8")
            self.q.put(("done",len(index_rows),str(out)))
        except Exception as e: self.q.put(("error",str(e)))

    def _poll(self):
        try:
            while True:
                item=self.q.get_nowait(); k=item[0]
                if k=="log": self.logline(item[1])
                elif k=="max": self.progress["maximum"]=item[1]
                elif k=="progress": _,n,total,status=item; self.progress["maximum"]=total; self.progress["value"]=n; self.status.set(status)
                elif k=="paused": self.start_btn.configure(state="normal"); self.stop_btn.configure(state="disabled"); self.status.set("Angehalten – kann fortgesetzt werden"); self.logline("Angehalten. Starte erneut, um mit dem OCR-Cache fortzufahren.")
                elif k=="done": _,count,path=item; self.start_btn.configure(state="normal"); self.stop_btn.configure(state="disabled"); self.status.set(f"Fertig: {count} Kandidaten"); self.logline(f"Fertig. Ausgabe: {path}"); messagebox.showinfo("Import abgeschlossen",f"{count} Monster-Kandidaten angelegt.\n\n{path}\n\nBitte OCR-Entwürfe prüfen.")
                elif k=="error": self.start_btn.configure(state="normal"); self.stop_btn.configure(state="disabled"); self.status.set("Fehler"); self.logline("FEHLER: "+item[1]); messagebox.showerror("Importfehler",item[1])
        except queue.Empty: pass
        self.after(150,self._poll)

if __name__=="__main__": App().mainloop()
