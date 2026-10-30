"""
İş Takip - Projeler, görevler ve notlar için basit masaüstü uygulaması.

Çalıştırma:  python is_takip.py
Veriler bu dosyanın yanındaki 'is_takip_veri.json' dosyasında tutulur.
Her kayıtta bir önceki hali 'is_takip_veri.json.bak' olarak yedeklenir.
Gereksinim: Python 3.8+ (Tkinter Windows kurulumunda hazır gelir, ek paket yok).
"""

import json
import os
import shutil
import sys
import tkinter as tk
import uuid
from datetime import date, datetime
from tkinter import messagebox, ttk

# ---------------------------------------------------------------- ayarlar
if getattr(sys, "frozen", False):          # .exe olarak paketlendiyse
    UYG_KLASORU = os.path.dirname(sys.executable)
else:
    UYG_KLASORU = os.path.dirname(os.path.abspath(__file__))
VERI_DOSYASI = os.path.join(UYG_KLASORU, "is_takip_veri.json")

PROJE_DURUMLARI = ["Planlandı", "Devam Ediyor", "Beklemede", "Tamamlandı", "İptal"]
GOREV_DURUMLARI = ["Yapılacak", "Devam Ediyor", "Beklemede", "Tamamlandı"]
ONCELIKLER = ["Düşük", "Orta", "Yüksek"]
TUMU = "(Tümü)"
BITMIS = {"Tamamlandı", "İptal"}


def simdi():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def yeni_id():
    return uuid.uuid4().hex[:10]


def tarih_gecerli(metin):
    if not metin:
        return True
    try:
        datetime.strptime(metin, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def gecikmis(son_tarih, durum):
    return bool(son_tarih) and durum not in BITMIS and son_tarih < date.today().isoformat()


# ---------------------------------------------------------------- veri katmanı
class Veri:
    def __init__(self, yol):
        self.yol = yol
        self.d = {"projeler": [], "gorevler": [], "notlar": []}
        self.yukle()

    def yukle(self):
        if not os.path.exists(self.yol):
            return
        try:
            with open(self.yol, encoding="utf-8") as f:
                okunan = json.load(f)
            for k in self.d:
                self.d[k] = okunan.get(k, [])
        except (json.JSONDecodeError, OSError) as e:
            messagebox.showerror(
                "Veri okunamadı",
                f"{self.yol} okunamadı:\n{e}\n\nYedek dosyayı (.bak) kontrol edin. "
                "Bozuk dosyanın üzerine yazılmaması için program kapanacak.")
            sys.exit(1)

    def kaydet(self):
        if os.path.exists(self.yol):
            shutil.copy2(self.yol, self.yol + ".bak")
        gecici = self.yol + ".tmp"
        with open(gecici, "w", encoding="utf-8") as f:
            json.dump(self.d, f, ensure_ascii=False, indent=2)
        os.replace(gecici, self.yol)   # yarım yazılmış dosya kalmasın

    def bul(self, tur, kid):
        return next((x for x in self.d[tur] if x["id"] == kid), None)

    def sil(self, tur, kid):
        self.d[tur] = [x for x in self.d[tur] if x["id"] != kid]


# ---------------------------------------------------------------- ortak yardımcılar
def etiketli(parent, metin, satir, widget):
    ttk.Label(parent, text=metin).grid(row=satir, column=0, sticky="w", pady=3, padx=(0, 6))
    widget.grid(row=satir, column=1, sticky="ew", pady=3)
    return widget


def metin_kutusu(parent, yukseklik):
    cerceve = ttk.Frame(parent)
    t = tk.Text(cerceve, height=yukseklik, wrap="word", font=("Segoe UI", 10), undo=True)
    sb = ttk.Scrollbar(cerceve, command=t.yview)
    t.configure(yscrollcommand=sb.set)
    t.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    return cerceve, t


def tablo(parent, kolonlar):
    """kolonlar: [(anahtar, başlık, genişlik), ...]"""
    cerceve = ttk.Frame(parent)
    tv = ttk.Treeview(cerceve, columns=[k for k, _, _ in kolonlar], show="headings",
                      selectmode="browse")
    for k, baslik, gen in kolonlar:
        tv.heading(k, text=baslik, command=lambda k=k: sirala(tv, k))
        tv.column(k, width=gen, anchor="w")
    sb = ttk.Scrollbar(cerceve, command=tv.yview)
    tv.configure(yscrollcommand=sb.set)
    tv.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    tv.tag_configure("gecikmis", foreground="#c0392b")
    tv.tag_configure("bitti", foreground="#7f8c8d")
    return cerceve, tv


def sirala(tv, kolon):
    ters = getattr(tv, "_ters", {}).get(kolon, False)
    satirlar = [(tv.set(i, kolon).lower(), i) for i in tv.get_children("")]
    satirlar.sort(reverse=ters)
    for idx, (_, i) in enumerate(satirlar):
        tv.move(i, "", idx)
    tv._ters = {kolon: not ters}


# ---------------------------------------------------------------- PROJELER sekmesi
class ProjelerSekmesi(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=8)
        self.app, self.veri = app, app.veri
        self.secili = None

        # sol: filtre + liste
        sol = ttk.Frame(self)
        sol.pack(side="left", fill="both", expand=True)
        filtre = ttk.Frame(sol)
        filtre.pack(fill="x", pady=(0, 6))
        ttk.Label(filtre, text="Ara:").pack(side="left")
        self.ara = tk.StringVar()
        self.ara.trace_add("write", lambda *_: self.listele())
        ttk.Entry(filtre, textvariable=self.ara, width=20).pack(side="left", padx=4)
        ttk.Label(filtre, text="Durum:").pack(side="left", padx=(8, 0))
        self.filtre_durum = ttk.Combobox(filtre, values=[TUMU, "Aktif"] + PROJE_DURUMLARI,
                                         state="readonly", width=14)
        self.filtre_durum.set("Aktif")
        self.filtre_durum.bind("<<ComboboxSelected>>", lambda e: self.listele())
        self.filtre_durum.pack(side="left", padx=4)

        lc, self.tv = tablo(sol, [("ad", "Proje", 220), ("durum", "Durum", 100),
                                  ("oncelik", "Öncelik", 70), ("bitis", "Bitiş", 90),
                                  ("gorev", "Açık Görev", 80), ("guncel", "Güncelleme", 120)])
        lc.pack(fill="both", expand=True)
        self.tv.bind("<<TreeviewSelect>>", self.secildi)

        # sağ: form
        sag = ttk.LabelFrame(self, text="Proje Detayı", padding=8)
        sag.pack(side="right", fill="both", padx=(8, 0))
        sag.columnconfigure(1, weight=1)
        self.ad = etiketli(sag, "Ad:", 0, ttk.Entry(sag, width=36))
        self.durum = etiketli(sag, "Durum:", 1, ttk.Combobox(sag, values=PROJE_DURUMLARI, state="readonly"))
        self.oncelik = etiketli(sag, "Öncelik:", 2, ttk.Combobox(sag, values=ONCELIKLER, state="readonly"))
        self.baslangic = etiketli(sag, "Başlangıç:", 3, ttk.Entry(sag))
        self.bitis = etiketli(sag, "Bitiş:", 4, ttk.Entry(sag))
        ttk.Label(sag, text="Tarih biçimi: YYYY-AA-GG", foreground="gray").grid(row=5, column=1, sticky="w")
        ttk.Label(sag, text="Açıklama:").grid(row=6, column=0, sticky="nw", pady=3)
        ac, self.aciklama = metin_kutusu(sag, 5)
        ac.grid(row=6, column=1, sticky="nsew", pady=3)

        btn = ttk.Frame(sag)
        btn.grid(row=7, column=0, columnspan=2, sticky="ew", pady=6)
        ttk.Button(btn, text="Yeni", command=self.temizle).pack(side="left")
        ttk.Button(btn, text="Kaydet", command=self.kaydet).pack(side="left", padx=4)
        ttk.Button(btn, text="Sil", command=self.sil).pack(side="right")

        # proje günlüğü
        ttk.Label(sag, text="Proje Günlüğü (tarihli notlar):").grid(row=8, column=0, columnspan=2, sticky="w", pady=(8, 2))
        gc = ttk.Frame(sag)
        gc.grid(row=9, column=0, columnspan=2, sticky="nsew")
        sag.rowconfigure(9, weight=1)
        self.gunluk = tk.Listbox(gc, height=8, font=("Segoe UI", 9))
        gsb = ttk.Scrollbar(gc, command=self.gunluk.yview)
        self.gunluk.configure(yscrollcommand=gsb.set)
        self.gunluk.pack(side="left", fill="both", expand=True)
        gsb.pack(side="right", fill="y")
        ekle = ttk.Frame(sag)
        ekle.grid(row=10, column=0, columnspan=2, sticky="ew", pady=4)
        self.gunluk_giris = ttk.Entry(ekle)
        self.gunluk_giris.pack(side="left", fill="x", expand=True)
        self.gunluk_giris.bind("<Return>", lambda e: self.gunluk_ekle())
        ttk.Button(ekle, text="Ekle", command=self.gunluk_ekle).pack(side="left", padx=4)
        ttk.Button(ekle, text="Sil", command=self.gunluk_sil).pack(side="left")

        self.temizle()
        self.listele()

    def acik_gorev_sayisi(self, pid):
        return sum(1 for g in self.veri.d["gorevler"]
                   if g.get("proje_id") == pid and g["durum"] != "Tamamlandı")

    def listele(self):
        self.tv.delete(*self.tv.get_children())
        q, fd = self.ara.get().lower(), self.filtre_durum.get()
        for p in sorted(self.veri.d["projeler"], key=lambda x: x["guncelleme"], reverse=True):
            if fd == "Aktif" and p["durum"] in BITMIS:
                continue
            if fd not in (TUMU, "Aktif") and p["durum"] != fd:
                continue
            if q and q not in (p["ad"] + " " + p["aciklama"]).lower():
                continue
            tag = "bitti" if p["durum"] in BITMIS else ("gecikmis" if gecikmis(p["bitis"], p["durum"]) else "")
            self.tv.insert("", "end", iid=p["id"], tags=(tag,), values=(
                p["ad"], p["durum"], p["oncelik"], p["bitis"],
                self.acik_gorev_sayisi(p["id"]), p["guncelleme"]))
        if self.secili and self.tv.exists(self.secili):
            self.tv.selection_set(self.secili)

    def secildi(self, _=None):
        sel = self.tv.selection()
        if not sel:
            return
        p = self.veri.bul("projeler", sel[0])
        self.secili = p["id"]
        self.doldur(p)

    def doldur(self, p):
        for w, v in ((self.ad, p["ad"]), (self.baslangic, p["baslangic"]), (self.bitis, p["bitis"])):
            w.delete(0, "end")
            w.insert(0, v)
        self.durum.set(p["durum"])
        self.oncelik.set(p["oncelik"])
        self.aciklama.delete("1.0", "end")
        self.aciklama.insert("1.0", p["aciklama"])
        self.gunluk.delete(0, "end")
        for g in reversed(p["gunluk"]):
            self.gunluk.insert("end", f"{g['tarih']}  —  {g['metin']}")

    def temizle(self):
        self.secili = None
        self.tv.selection_remove(*self.tv.selection())
        self.doldur({"ad": "", "baslangic": date.today().isoformat(), "bitis": "",
                     "durum": "Planlandı", "oncelik": "Orta", "aciklama": "", "gunluk": []})
        self.ad.focus_set()

    def kaydet(self):
        ad = self.ad.get().strip()
        if not ad:
            messagebox.showwarning("Eksik", "Proje adı boş olamaz.")
            return
        bas, bit = self.baslangic.get().strip(), self.bitis.get().strip()
        if not (tarih_gecerli(bas) and tarih_gecerli(bit)):
            messagebox.showwarning("Tarih", "Tarihleri YYYY-AA-GG biçiminde girin (ör. 2026-11-15).")
            return
        p = self.veri.bul("projeler", self.secili) if self.secili else None
        if p is None:
            p = {"id": yeni_id(), "olusturma": simdi(), "gunluk": []}
            self.veri.d["projeler"].append(p)
        elif p["durum"] != self.durum.get():
            p["gunluk"].append({"tarih": simdi(), "metin": f"Durum: {p['durum']} → {self.durum.get()}"})
        p.update(ad=ad, durum=self.durum.get(), oncelik=self.oncelik.get(), baslangic=bas,
                 bitis=bit, aciklama=self.aciklama.get("1.0", "end").strip(), guncelleme=simdi())
        self.secili = p["id"]
        self.app.kaydet_ve_yenile()
        self.doldur(p)

    def sil(self):
        if not self.secili:
            return
        p = self.veri.bul("projeler", self.secili)
        if messagebox.askyesno("Sil", f"'{p['ad']}' projesi silinsin mi?\n"
                               "(Bağlı görevler silinmez, projesiz kalır.)"):
            self.veri.sil("projeler", self.secili)
            for g in self.veri.d["gorevler"]:
                if g.get("proje_id") == self.secili:
                    g["proje_id"] = ""
            self.app.kaydet_ve_yenile()
            self.temizle()

    def gunluk_ekle(self):
        metin = self.gunluk_giris.get().strip()
        if not metin:
            return
        if not self.secili:
            messagebox.showinfo("Bilgi", "Önce projeyi kaydedin veya listeden seçin.")
            return
        p = self.veri.bul("projeler", self.secili)
        p["gunluk"].append({"tarih": simdi(), "metin": metin})
        p["guncelleme"] = simdi()
        self.gunluk_giris.delete(0, "end")
        self.app.kaydet_ve_yenile()
        self.doldur(p)

    def gunluk_sil(self):
        sel = self.gunluk.curselection()
        if not sel or not self.secili:
            return
        p = self.veri.bul("projeler", self.secili)
        gercek = len(p["gunluk"]) - 1 - sel[0]   # liste ters sırada gösteriliyor
        if messagebox.askyesno("Sil", "Seçili günlük kaydı silinsin mi?"):
            del p["gunluk"][gercek]
            self.app.kaydet_ve_yenile()
            self.doldur(p)


# ---------------------------------------------------------------- GÖREVLER sekmesi
class GorevlerSekmesi(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=8)
        self.app, self.veri = app, app.veri
        self.secili = None

        sol = ttk.Frame(self)
        sol.pack(side="left", fill="both", expand=True)
        filtre = ttk.Frame(sol)
        filtre.pack(fill="x", pady=(0, 6))
        ttk.Label(filtre, text="Ara:").pack(side="left")
        self.ara = tk.StringVar()
        self.ara.trace_add("write", lambda *_: self.listele())
        ttk.Entry(filtre, textvariable=self.ara, width=18).pack(side="left", padx=4)
        ttk.Label(filtre, text="Proje:").pack(side="left", padx=(8, 0))
        self.filtre_proje = ttk.Combobox(filtre, state="readonly", width=18)
        self.filtre_proje.bind("<<ComboboxSelected>>", lambda e: self.listele())
        self.filtre_proje.pack(side="left", padx=4)
        self.tamam_goster = tk.BooleanVar(value=False)
        ttk.Checkbutton(filtre, text="Tamamlananları göster", variable=self.tamam_goster,
                        command=self.listele).pack(side="left", padx=8)

        lc, self.tv = tablo(sol, [("baslik", "Görev", 240), ("proje", "Proje", 150),
                                  ("durum", "Durum", 100), ("oncelik", "Öncelik", 70),
                                  ("son", "Son Tarih", 90)])
        lc.pack(fill="both", expand=True)
        self.tv.bind("<<TreeviewSelect>>", self.secildi)
        self.tv.bind("<Double-1>", lambda e: self.hizli_tamamla())
        ttk.Label(sol, text="Kırmızı: süresi geçmiş  •  Çift tık: tamamlandı/geri al",
                  foreground="gray").pack(anchor="w", pady=(4, 0))

        sag = ttk.LabelFrame(self, text="Görev Detayı", padding=8)
        sag.pack(side="right", fill="both", padx=(8, 0))
        sag.columnconfigure(1, weight=1)
        self.baslik = etiketli(sag, "Görev:", 0, ttk.Entry(sag, width=36))
        self.proje = etiketli(sag, "Proje:", 1, ttk.Combobox(sag, state="readonly"))
        self.durum = etiketli(sag, "Durum:", 2, ttk.Combobox(sag, values=GOREV_DURUMLARI, state="readonly"))
        self.oncelik = etiketli(sag, "Öncelik:", 3, ttk.Combobox(sag, values=ONCELIKLER, state="readonly"))
        self.son = etiketli(sag, "Son tarih:", 4, ttk.Entry(sag))
        ttk.Label(sag, text="Tarih biçimi: YYYY-AA-GG", foreground="gray").grid(row=5, column=1, sticky="w")
        ttk.Label(sag, text="Detay:").grid(row=6, column=0, sticky="nw", pady=3)
        dc, self.detay = metin_kutusu(sag, 10)
        dc.grid(row=6, column=1, sticky="nsew", pady=3)
        sag.rowconfigure(6, weight=1)
        btn = ttk.Frame(sag)
        btn.grid(row=7, column=0, columnspan=2, sticky="ew", pady=6)
        ttk.Button(btn, text="Yeni", command=self.temizle).pack(side="left")
        ttk.Button(btn, text="Kaydet", command=self.kaydet).pack(side="left", padx=4)
        ttk.Button(btn, text="Sil", command=self.sil).pack(side="right")

        self.projeleri_guncelle()
        self.temizle()
        self.listele()

    def proje_adlari(self):
        return {p["id"]: p["ad"] for p in self.veri.d["projeler"]}

    def projeleri_guncelle(self):
        adlar = sorted(self.proje_adlari().values(), key=str.lower)
        self.proje["values"] = ["(Projesiz)"] + adlar
        eski = self.filtre_proje.get()
        self.filtre_proje["values"] = [TUMU, "(Projesiz)"] + adlar
        self.filtre_proje.set(eski if eski in self.filtre_proje["values"] else TUMU)

    def listele(self):
        self.tv.delete(*self.tv.get_children())
        adlar = self.proje_adlari()
        q, fp = self.ara.get().lower(), self.filtre_proje.get()
        sira = {"Yüksek": 0, "Orta": 1, "Düşük": 2}
        for g in sorted(self.veri.d["gorevler"],
                        key=lambda x: (x["durum"] == "Tamamlandı", x["son_tarih"] or "9999",
                                       sira.get(x["oncelik"], 1))):
            proje_ad = adlar.get(g.get("proje_id"), "")
            if g["durum"] == "Tamamlandı" and not self.tamam_goster.get():
                continue
            if fp == "(Projesiz)" and proje_ad:
                continue
            if fp not in (TUMU, "(Projesiz)") and proje_ad != fp:
                continue
            if q and q not in (g["baslik"] + " " + g["detay"]).lower():
                continue
            tag = "bitti" if g["durum"] == "Tamamlandı" else ("gecikmis" if gecikmis(g["son_tarih"], g["durum"]) else "")
            self.tv.insert("", "end", iid=g["id"], tags=(tag,), values=(
                g["baslik"], proje_ad, g["durum"], g["oncelik"], g["son_tarih"]))
        if self.secili and self.tv.exists(self.secili):
            self.tv.selection_set(self.secili)

    def secildi(self, _=None):
        sel = self.tv.selection()
        if not sel:
            return
        g = self.veri.bul("gorevler", sel[0])
        self.secili = g["id"]
        self.doldur(g)

    def doldur(self, g):
        self.baslik.delete(0, "end")
        self.baslik.insert(0, g["baslik"])
        self.son.delete(0, "end")
        self.son.insert(0, g["son_tarih"])
        self.proje.set(self.proje_adlari().get(g.get("proje_id"), "(Projesiz)"))
        self.durum.set(g["durum"])
        self.oncelik.set(g["oncelik"])
        self.detay.delete("1.0", "end")
        self.detay.insert("1.0", g["detay"])

    def temizle(self):
        self.secili = None
        self.tv.selection_remove(*self.tv.selection())
        fp = self.filtre_proje.get()
        pid = next((k for k, v in self.proje_adlari().items() if v == fp), "")
        self.doldur({"baslik": "", "son_tarih": "", "proje_id": pid, "durum": "Yapılacak",
                     "oncelik": "Orta", "detay": ""})
        self.baslik.focus_set()

    def kaydet(self):
        baslik = self.baslik.get().strip()
        if not baslik:
            messagebox.showwarning("Eksik", "Görev adı boş olamaz.")
            return
        son = self.son.get().strip()
        if not tarih_gecerli(son):
            messagebox.showwarning("Tarih", "Tarihi YYYY-AA-GG biçiminde girin (ör. 2026-11-15).")
            return
        pid = next((k for k, v in self.proje_adlari().items() if v == self.proje.get()), "")
        g = self.veri.bul("gorevler", self.secili) if self.secili else None
        if g is None:
            g = {"id": yeni_id(), "olusturma": simdi()}
            self.veri.d["gorevler"].append(g)
        g.update(baslik=baslik, proje_id=pid, durum=self.durum.get(), oncelik=self.oncelik.get(),
                 son_tarih=son, detay=self.detay.get("1.0", "end").strip(), guncelleme=simdi())
        self.secili = g["id"]
        self.app.kaydet_ve_yenile()

    def hizli_tamamla(self):
        if not self.secili:
            return
        g = self.veri.bul("gorevler", self.secili)
        g["durum"] = "Yapılacak" if g["durum"] == "Tamamlandı" else "Tamamlandı"
        g["guncelleme"] = simdi()
        self.app.kaydet_ve_yenile()
        self.doldur(g)

    def sil(self):
        if not self.secili:
            return
        g = self.veri.bul("gorevler", self.secili)
        if messagebox.askyesno("Sil", f"'{g['baslik']}' görevi silinsin mi?"):
            self.veri.sil("gorevler", self.secili)
            self.app.kaydet_ve_yenile()
            self.temizle()


# ---------------------------------------------------------------- NOTLAR sekmesi
class NotlarSekmesi(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=8)
        self.app, self.veri = app, app.veri
        self.secili = None

        sol = ttk.Frame(self)
        sol.pack(side="left", fill="y")
        filtre = ttk.Frame(sol)
        filtre.pack(fill="x", pady=(0, 6))
        ttk.Label(filtre, text="Ara:").pack(side="left")
        self.ara = tk.StringVar()
        self.ara.trace_add("write", lambda *_: self.listele())
        ttk.Entry(filtre, textvariable=self.ara).pack(side="left", fill="x", expand=True, padx=4)
        lc, self.tv = tablo(sol, [("baslik", "Başlık", 200), ("tarih", "Güncelleme", 120)])
        lc.pack(fill="both", expand=True)
        self.tv.bind("<<TreeviewSelect>>", self.secildi)

        sag = ttk.Frame(self)
        sag.pack(side="left", fill="both", expand=True, padx=(8, 0))
        ust = ttk.Frame(sag)
        ust.pack(fill="x")
        ttk.Label(ust, text="Başlık:").pack(side="left")
        self.baslik = ttk.Entry(ust, font=("Segoe UI", 11))
        self.baslik.pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(ust, text="Yeni", command=self.temizle).pack(side="left")
        ttk.Button(ust, text="Kaydet (Ctrl+S)", command=self.kaydet).pack(side="left", padx=4)
        ttk.Button(ust, text="Sil", command=self.sil).pack(side="left")
        ic, self.icerik = metin_kutusu(sag, 20)
        ic.pack(fill="both", expand=True, pady=(6, 0))
        self.icerik.bind("<Control-s>", lambda e: (self.kaydet(), "break")[1])
        self.baslik.bind("<Control-s>", lambda e: self.kaydet())

        self.temizle()
        self.listele()

    def listele(self):
        self.tv.delete(*self.tv.get_children())
        q = self.ara.get().lower()
        for n in sorted(self.veri.d["notlar"], key=lambda x: x["guncelleme"], reverse=True):
            if q and q not in (n["baslik"] + " " + n["icerik"]).lower():
                continue
            self.tv.insert("", "end", iid=n["id"], values=(n["baslik"], n["guncelleme"]))
        if self.secili and self.tv.exists(self.secili):
            self.tv.selection_set(self.secili)

    def secildi(self, _=None):
        sel = self.tv.selection()
        if not sel:
            return
        n = self.veri.bul("notlar", sel[0])
        self.secili = n["id"]
        self.baslik.delete(0, "end")
        self.baslik.insert(0, n["baslik"])
        self.icerik.delete("1.0", "end")
        self.icerik.insert("1.0", n["icerik"])

    def temizle(self):
        self.secili = None
        self.tv.selection_remove(*self.tv.selection())
        self.baslik.delete(0, "end")
        self.icerik.delete("1.0", "end")
        self.baslik.focus_set()

    def kaydet(self):
        icerik = self.icerik.get("1.0", "end").rstrip()
        baslik = self.baslik.get().strip() or (icerik.splitlines()[0][:50] if icerik else "")
        if not baslik:
            return
        n = self.veri.bul("notlar", self.secili) if self.secili else None
        if n is None:
            n = {"id": yeni_id(), "olusturma": simdi()}
            self.veri.d["notlar"].append(n)
        n.update(baslik=baslik, icerik=icerik, guncelleme=simdi())
        self.secili = n["id"]
        self.baslik.delete(0, "end")
        self.baslik.insert(0, baslik)
        self.app.kaydet_ve_yenile()

    def sil(self):
        if not self.secili:
            return
        n = self.veri.bul("notlar", self.secili)
        if messagebox.askyesno("Sil", f"'{n['baslik']}' notu silinsin mi?"):
            self.veri.sil("notlar", self.secili)
            self.app.kaydet_ve_yenile()
            self.temizle()


# ---------------------------------------------------------------- ana pencere
class Uygulama(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("İş Takip")
        self.geometry("1150x650")
        self.minsize(900, 500)
        stil = ttk.Style(self)
        if "vista" in stil.theme_names():
            stil.theme_use("vista")
        elif "clam" in stil.theme_names():
            stil.theme_use("clam")
        stil.configure("Treeview", rowheight=24)

        self.veri = Veri(VERI_DOSYASI)
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)
        self.projeler = ProjelerSekmesi(self.nb, self)
        self.gorevler = GorevlerSekmesi(self.nb, self)
        self.notlar = NotlarSekmesi(self.nb, self)
        self.nb.add(self.projeler, text="  Projeler  ")
        self.nb.add(self.gorevler, text="  Görevler  ")
        self.nb.add(self.notlar, text="  Notlar  ")

        self.durum_cubugu = ttk.Label(self, anchor="w", padding=(8, 2))
        self.durum_cubugu.pack(fill="x", side="bottom")
        self.ozet()

    def kaydet_ve_yenile(self):
        try:
            self.veri.kaydet()
        except OSError as e:
            messagebox.showerror("Kayıt hatası", f"Dosyaya yazılamadı:\n{e}")
            return
        self.gorevler.projeleri_guncelle()
        self.projeler.listele()
        self.gorevler.listele()
        self.notlar.listele()
        self.ozet(f"Kaydedildi {datetime.now():%H:%M:%S}")

    def ozet(self, ek=""):
        d = self.veri.d
        aktif = sum(1 for p in d["projeler"] if p["durum"] not in BITMIS)
        acik = [g for g in d["gorevler"] if g["durum"] != "Tamamlandı"]
        gec = sum(1 for g in acik if gecikmis(g["son_tarih"], g["durum"]))
        metin = (f"Aktif proje: {aktif}   •   Açık görev: {len(acik)}   •   "
                 f"Süresi geçen: {gec}   •   Not: {len(d['notlar'])}   •   Dosya: {VERI_DOSYASI}")
        self.durum_cubugu.config(text=metin + (f"   •   {ek}" if ek else ""))


if __name__ == "__main__":
    Uygulama().mainloop()
