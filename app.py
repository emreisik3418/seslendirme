"""
DocVoice - Metin -> LLM formatlama -> Seslendirme
Calistirma:  python -m streamlit run app.py
"""
import json
from datetime import datetime

from pathlib import Path

import streamlit as st

from dosya_kontrol import MESAJ, eksikleri_bul

_sorunlar = eksikleri_bul()
if _sorunlar:
    st.set_page_config(page_title="DocVoice", page_icon="🎙️")
    st.error("**Dosyalar güncel değil**\n\n" + "\n".join(f"- {s}" for s in _sorunlar))
    st.info(MESAJ)
    st.stop()

import config  # noqa: E402
from services.document_reader import metin_cikar, sayfa_dosyasi_oku, sayfalara_esle
from services.llm_client import LLMHatasi, formatla, sayfalari_formatla
from services.pdf_kartlar import sayfa_duzeni
from services.pdf_pages import sayfa_gorseli, sayfa_metinleri
from services.sunum_cizim import sunum_slayti
from services import qlik_yukleyici
from services.ssml_tools import etiketsiz, ssml_onar
from services.tts_client import TTSHatasi, dosya_uzantisi, seslendir
from services.video_builder import (VideoHatasi, kullanilabilir_karakterler, pdf_videosu_olustur,
                                    video_olustur)

st.set_page_config(page_title="DocVoice", page_icon="🎙️", layout="wide")
st.title("🎙️ DocVoice")
st.caption("Belgeden seslendirmeye hazır metin")

# --- Oturum durumu ---
if "kurallar" not in st.session_state:
    st.session_state.kurallar = (
        config.KURALLAR_DOSYASI.read_text(encoding="utf-8")
        if config.KURALLAR_DOSYASI.exists()
        else ""
    )
st.session_state.setdefault("metin", "")
st.session_state.setdefault("sonuc", "")
st.session_state.setdefault("ham_yanit", None)
st.session_state.setdefault("son_dosya", None)
st.session_state.setdefault("ses", None)
st.session_state.setdefault("gonderilen_ssml", "")
st.session_state.setdefault("video", None)
st.session_state.setdefault("pdf_veri", None)
st.session_state.setdefault("pdf_adi", "")
st.session_state.setdefault("pdf_sayfa", 0)

# --- Yan panel: ayar durumu ---
with st.sidebar:
    st.header("Bağlantı")
    if config.LLM_URL:
        st.success("LLM servisi tanımlı")
        st.caption(config.LLM_URL)
    else:
        st.error("LLM_URL tanımlı değil (.env)")
    st.caption(f"x-application-name: {config.LLM_APP_NAME or '— (boş)'}")
    st.caption(f"Token: {'var' if config.LLM_TOKEN else 'yok'}")
    st.caption(f"SSL doğrulama: {'açık' if config.VERIFY_SSL else 'KAPALI'}")
    st.divider()
    if config.TTS_URL:
        st.success("Seslendirme servisi tanımlı")
    else:
        st.error("TTS_URL tanımlı değil (.env)")
    st.caption(f"Ses modeli: {config.TTS_VOICE or '— (boş)'}")
    st.caption(f"Çıktı formatı: {config.TTS_OUTPUT_FORMAT}")
    st.caption(f"Anahtar: {'var' if config.TTS_KEY else 'yok'}")
    st.divider()
    if config.VIDEO_LOGO:
        st.caption("Logo")
        st.image(config.VIDEO_LOGO, width=160)
    else:
        st.caption("Logo: yok")
    st.divider()
    if qlik_yukleyici.tanimli_mi():
        st.success("Qlik tanımlı")
        st.caption(f"{config.QLIK_URL} · kütüphane: {config.QLIK_KUTUPHANE} · kimlik: {config.QLIK_KIMLIK}")
        if config.QLIK_DOSYA_ADI:
            st.caption(f"Qlik'e hep şu adla yüklenir: {qlik_yukleyici.yukleme_adi(None)}")
        for not_ in config.QLIK_NOTLAR:
            st.info(not_)
        if st.button("Qlik bağlantısını test et"):
            try:
                st.info(qlik_yukleyici.baglanti_testi())
            except qlik_yukleyici.QlikHatasi as e:
                st.error(str(e))
    else:
        st.caption("Qlik: tanımlı değil (QLIK_URL)")
    for uyari in config.UYARILAR:
        st.warning(uyari)



@st.cache_data(show_spinner=False, max_entries=200)
def kucuk_resim(veri: bytes, sira: int):
    return sayfa_gorseli(veri, sira, dpi=45)


@st.cache_data(show_spinner=False, max_entries=200)
def kart_duzeni(veri: bytes, sira: int):
    try:
        return sayfa_duzeni(veri, sira)
    except Exception:
        return None


@st.cache_data(show_spinner=False, max_entries=200)
def sunum_onizleme(veri: bytes, sira: int, toplam: int):
    duzen = kart_duzeni(veri, sira)
    if not duzen:
        return None
    img = sunum_slayti(duzen, sira + 1, toplam, altyazi_alani=False)
    img.thumbnail((640, 360))
    return img


def pdf_yukle(ad: str, veri: bytes):
    """PDF sayfa modu icin dosyayi ve sayfa metinlerini hazirlar."""
    metinler = sayfa_metinleri(veri)
    st.session_state.pdf_veri = veri
    st.session_state.pdf_adi = ad
    st.session_state.pdf_sayfa = len(metinler)
    st.session_state.pdf_metinler = metinler
    st.session_state.pdf_metinler_pdf = metinler      # PDF'ten okunan asil metinler
    st.session_state.word_adi = ""
    for i in range(len(metinler)):
        st.session_state[f"sayfa_ssml_{i}"] = ""


def video_goster():
    v = st.session_state.video
    if v and v.video.exists():
        st.video(str(v.video))
        st.caption(f"{v.bolum_sayisi} sahne · {int(v.sure // 60)} dk {int(v.sure % 60)} sn · output/{v.video.name}")
        k1, k2, k3 = st.columns(3)
        k1.download_button("⬇️ Videoyu indir (.mp4)", v.video.read_bytes(), file_name=v.video.name, mime="video/mp4")
        k2.download_button("⬇️ Altyazıyı indir (.srt)", v.altyazi.read_bytes(), file_name=v.altyazi.name)
        if qlik_yukleyici.tanimli_mi():
            qlik_bolumu(v)
        else:
            k3.caption("Qlik'e göndermek için .env'de QLIK_URL tanımlayın.")


QLIK_TURLERI = {"video": "Video (.mp4)", "pdf": "PDF (.pdf)", "ses": f"Ses (.{config.QLIK_SES_FORMATI})",
                "srt": "Altyazı (.srt)"}


def qlik_bolumu(v):
    """Video, PDF ve sesi Qlik content library'ye AYNI adla gonderir (eskilerin uzerine yazilir)."""
    st.markdown(f"**📤 Qlik'e gönder** · content library: `{config.QLIK_KUTUPHANE}`")
    onerilen = Path(qlik_yukleyici.yukleme_adi(st.session_state.get("video_kaynak") or v.video.name)).stem
    pdf = st.session_state.get("video_pdf")
    q1, q2 = st.columns([1, 2])
    qlik_adi = q1.text_input("Dosya adı (uzantısız)", value=onerilen, key=f"qlik_adi_{v.video.name}",
                             help="Tüm dosyalar bu adla gider; Qlik'teki aynı adlı eski dosyaların üzerine yazılır.")
    varsayilan = [t for t in config.QLIK_YUKLENECEKLER if t in QLIK_TURLERI and (t != "pdf" or pdf)]
    turler = q2.multiselect("Gönderilecek dosyalar", list(QLIK_TURLERI), default=varsayilan,
                            format_func=QLIK_TURLERI.get, key=f"qlik_tur_{v.video.name}")
    if "pdf" in turler and not pdf:
        q2.caption("Bu video bir PDF'ten üretilmedi; PDF gönderilmeyecek.")
    kok = Path(qlik_yukleyici.temiz_ad(qlik_adi) or onerilen + ".mp4").stem
    if turler:
        uz = {"video": ".mp4", "pdf": ".pdf", "ses": "." + config.QLIK_SES_FORMATI, "srt": ".srt"}
        st.caption("Qlik'e gidecek: " + " · ".join(kok + uz[t] for t in turler if t != "pdf" or pdf))
    if st.button("📤 Qlik'e gönder", disabled=not turler, key=f"qlik_gonder_{v.video.name}"):
        with st.spinner("Qlik'e yükleniyor..."):
            try:
                sonuc = qlik_yukleyici.dosyalari_yukle(v.video, v.altyazi, pdf=pdf, ad=kok + ".mp4",
                                                       turler=turler)
                st.session_state.qlik_sonuc = (v.video.name, [(r.dosya, r.adres) for r in sonuc.yuklenenler],
                                               sonuc.atlananlar)
            except qlik_yukleyici.QlikHatasi as e:
                st.error(f"Qlik'e yüklenemedi: {e}")
    onceki = st.session_state.get("qlik_sonuc")
    if onceki and onceki[0] == v.video.name:
        st.success(f"Qlik'e yüklendi ({len(onceki[1])} dosya). Uygulamada Video player nesnesine "
                   "video adresini verin:")
        for dosya, adres in onceki[1]:
            st.code(adres, language=None)
        for a in onceki[2]:
            st.caption(a)

sol, sag = st.columns(2)

# --- 1) Kural seti (system) ---
with sol:
    st.subheader("1. Kural seti")
    st.session_state.kurallar = st.text_area(
        "LLM'e 'system' olarak gönderilir",
        value=st.session_state.kurallar,
        height=260,
    )
    if st.button("💾 Kuralları kaydet"):
        config.KURALLAR_DOSYASI.parent.mkdir(exist_ok=True)
        config.KURALLAR_DOSYASI.write_text(st.session_state.kurallar, encoding="utf-8")
        st.toast("Kurallar kaydedildi")

# --- 2) Icerik (user) ---
with sag:
    st.subheader("2. İçerik")
    dosya = st.file_uploader("Word, PDF veya TXT yükleyin", type=["docx", "pdf", "txt"])
    if dosya is not None and dosya.name != st.session_state.son_dosya:
        try:
            st.session_state.metin = metin_cikar(dosya.name, dosya.getvalue())
            st.session_state.son_dosya = dosya.name
            if dosya.name.lower().endswith(".pdf"):
                pdf_yukle(dosya.name, dosya.getvalue())
        except Exception as e:
            st.error(f"Dosya okunamadı: {e}")

    st.session_state.metin = st.text_area(
        "LLM'e 'user' olarak gönderilir (elle de yazabilir/düzeltebilirsiniz)",
        value=st.session_state.metin,
        height=260,
    )
    st.caption(f"{len(st.session_state.metin):,} karakter".replace(",", "."))

# --- 3) LLM'e gonder ---
st.divider()
st.subheader("3. Formatla")
hazir = bool(st.session_state.kurallar.strip() and st.session_state.metin.strip())
if st.button("🚀 LLM'e gönder", type="primary", disabled=not hazir):
    with st.spinner("LLM servisi çalışıyor... (birkaç dakika sürebilir)"):
        try:
            sonuc, ham = formatla(st.session_state.kurallar, st.session_state.metin)
            sonuc, onarildi = ssml_onar(sonuc)
            if onarildi:
                st.info("LLM çıktısındaki hatalı SSML etiketleri otomatik düzeltildi.")
            st.session_state.sonuc = sonuc
            st.session_state.ham_yanit = ham
        except LLMHatasi as e:
            st.error(str(e))

if st.session_state.sonuc:
    st.session_state.sonuc = st.text_area(
        "Düzenlenmiş metin / SSML (seslendirmeden önce düzeltebilirsiniz)",
        value=st.session_state.sonuc,
        height=300,
    )
    with st.expander("Okunabilir önizleme (etiketler gizli)"):
        st.write(etiketsiz(st.session_state.sonuc))
    zaman = datetime.now().strftime("%Y%m%d_%H%M")
    st.download_button(
        "⬇️ Metni indir (.txt)",
        st.session_state.sonuc.encode("utf-8"),
        file_name=f"duzenlenmis_{zaman}.txt",
    )
    with st.expander("Ham servis yanıtı (hata ayıklama için)"):
        st.code(json.dumps(st.session_state.ham_yanit, ensure_ascii=False, indent=2), "json")

# --- 4) Seslendirme ---
st.divider()
st.subheader("4. Seslendir")
ses_hazir = bool(st.session_state.sonuc.strip() and config.TTS_URL)
if st.button("🔊 Seslendir", type="primary", disabled=not ses_hazir):
    with st.spinner("Ses üretiliyor..."):
        try:
            ses, ssml = seslendir(st.session_state.sonuc)
            st.session_state.ses = ses
            st.session_state.gonderilen_ssml = ssml
            # Kopyasini output klasorune de kaydet
            config.CIKTI_KLASORU.mkdir(exist_ok=True)
            ad = f"ses_{datetime.now():%Y%m%d_%H%M%S}.{dosya_uzantisi()}"
            (config.CIKTI_KLASORU / ad).write_bytes(ses)
            st.toast(f"Kaydedildi: output/{ad}")
        except TTSHatasi as e:
            st.error(str(e))

if st.session_state.ses:
    uzanti = dosya_uzantisi()
    tur = {"mp3": "audio/mpeg", "wav": "audio/wav", "ogg": "audio/ogg", "webm": "audio/webm"}
    st.audio(st.session_state.ses, format=tur.get(uzanti, "audio/mpeg"))
    st.download_button(
        f"⬇️ Sesi indir (.{uzanti})",
        st.session_state.ses,
        file_name=f"docvoice_{datetime.now():%Y%m%d_%H%M}.{uzanti}",
    )
    with st.expander("Gönderilen SSML (hata ayıklama için)"):
        st.code(st.session_state.gonderilen_ssml, "xml")

# --- 5) Video ---
st.divider()
st.subheader("5. Video oluştur")
t1, t2 = st.columns(2)
altyazi_goster = t1.toggle(
    "Altyazı göster", value=config.VIDEO_ALTYAZI,
    help="Kapalıyken videoda altyazı görünmez; .srt dosyası yine de ayrıca indirilebilir.",
)
karakter_acik = t2.toggle(
    "Konuşan karakter", value=config.VIDEO_KARAKTER,
    help="Sağ alt köşede konuşan bir karakter gösterilir: ağzı seslendirmeyle senkron, yeni sayfada "
         "içeriği gösterir, anlatırken hareket eder. İçerik sola kayar.",
)
karakter_goster = False
if karakter_acik:
    secenekler = kullanilabilir_karakterler()
    anahtarlar = list(secenekler)
    varsayilan = config.VIDEO_KARAKTER_TIPI if config.VIDEO_KARAKTER_TIPI in anahtarlar else anahtarlar[0]
    karakter_goster = t2.radio("Karakter", anahtarlar, index=anahtarlar.index(varsayilan),
                               format_func=secenekler.get, horizontal=True)
sekme_slayt, sekme_pdf = st.tabs(["🖼️ Slayt modu", "📄 PDF sayfa modu"])

with sekme_slayt:
    st.caption("3. adımdaki metin <break> noktalarından bölümlere ayrılır; her bölüm bir slayt olur.")
    video_hazir = bool(st.session_state.sonuc.strip() and config.TTS_URL)
    if st.button("🎬 Video oluştur", type="primary", disabled=not video_hazir, key="btn_slayt"):
        cubuk = st.progress(0.0, text="Başlıyor...")
        try:
            st.session_state.video = video_olustur(
                st.session_state.sonuc,
                ilerleme=lambda oran, mesaj: cubuk.progress(oran, text=mesaj),
                altyazi=altyazi_goster,
                karakter=karakter_goster,
            )
            st.session_state.video_kaynak = st.session_state.son_dosya or "docvoice"
            kaynak_pdf = (st.session_state.son_dosya or "").lower().endswith(".pdf")
            st.session_state.video_pdf = st.session_state.pdf_veri if kaynak_pdf else None
            st.toast(f"Kaydedildi: output/{st.session_state.video.video.name}")
        except (VideoHatasi, TTSHatasi, ValueError) as e:
            cubuk.empty()
            st.error(str(e))

with sekme_pdf:
    st.caption(
        "Her PDF sayfası arka planda gösterilir. Sayfanın metni kural setiyle ayrı ayrı LLM'e "
        "gönderilir; o sayfanın seslendirmesi bitince sonraki sayfaya geçilir."
    )
    if st.session_state.pdf_veri is None:
        pdf_dosya = st.file_uploader("PDF yükleyin", type=["pdf"], key="pdf_yukleyici")
        if pdf_dosya is not None:
            pdf_yukle(pdf_dosya.name, pdf_dosya.getvalue())
            st.rerun()
    else:
        n = st.session_state.pdf_sayfa
        b1, b2 = st.columns([3, 1])
        b1.info(f"**{st.session_state.pdf_adi}** · {n} sayfa")
        if b2.button("Başka PDF seç"):
            st.session_state.pdf_veri = None
            st.rerun()

        sunum_gorunumu = st.toggle(
            "Sunum görünümü (gösterge kartlarını modern slayt olarak yeniden çiz)",
            value=config.VIDEO_SUNUM,
            help="Kart bulunan sayfalarda rakamlar PDF'ten okunup yeniden çizilir; anlatılan metriğe göre "
                 "kutucuklar vurgulanır. Kart bulunmayan sayfalar sayfa görseliyle gösterilir.",
        )
        if sunum_gorunumu:
            kartli = [i + 1 for i in range(n) if kart_duzeni(st.session_state.pdf_veri, i)]
            st.caption(f"Gösterge kartı bulunan sayfalar: {', '.join(map(str, kartli)) or 'yok'}")

        KAYNAK_PDF, KAYNAK_DOSYA, KAYNAK_HAZIR = (
            "PDF'ten oku", "Dosyadan al (LLM'e gönder)", "Hazır metin (LLM'siz)")
        kaynak = st.radio(
            "Sayfa metinleri", [KAYNAK_PDF, KAYNAK_DOSYA, KAYNAK_HAZIR], horizontal=True,
            help="Dosyada (.docx veya .txt) her sayfanın metninden önce ayrı bir satırda 'Sayfa 1', "
                 "'Sayfa 2' ... olmalı. 'Hazır metin' seçilirse metinler LLM'e gönderilmeden doğrudan "
                 "seslendirilir (LLM'den daha önce dönen SSML'i yapıştırabilirsiniz).",
        )
        if kaynak in (KAYNAK_DOSYA, KAYNAK_HAZIR):
            hazir_mod = kaynak == KAYNAK_HAZIR
            dosya_turu = "seslendirme metinlerini (SSML veya düz metin)" if hazir_mod else "sayfa metinlerini"
            sdosya = st.file_uploader(f"{dosya_turu.capitalize()} içeren dosya (.docx veya .txt)",
                                      type=["docx", "txt"], key=f"sayfa_dosyasi_{int(hazir_mod)}")
            anahtar = (sdosya.name, sdosya.size, hazir_mod) if sdosya is not None else None
            if anahtar and anahtar != st.session_state.get("sayfa_dosyasi_anahtar"):
                try:
                    sayfalar, yontem = sayfa_dosyasi_oku(sdosya.name, sdosya.getvalue())
                    metinler, uyarilar = sayfalara_esle(sayfalar, n)
                    if hazir_mod:
                        # LLM atlanir: metinler dogrudan seslendirme kutularina yazilir
                        onarilan = []
                        for i, m in enumerate(metinler):
                            if m:
                                m, onarildi = ssml_onar(m)
                                if onarildi:
                                    onarilan.append(str(i + 1))
                            st.session_state[f"sayfa_ssml_{i}"] = m
                        if onarilan:
                            uyarilar.append(f"Hatalı SSML etiketleri otomatik düzeltildi: sayfa {', '.join(onarilan)}")
                    else:
                        st.session_state.pdf_metinler = metinler
                    st.session_state.word_adi = sdosya.name
                    st.session_state.word_bilgi = (yontem, uyarilar, sum(1 for m in metinler if m))
                    st.session_state.sayfa_dosyasi_anahtar = anahtar
                except Exception as e:
                    st.error(f"Dosya okunamadı: {e}")
            if st.session_state.get("word_adi") and st.session_state.get("sayfa_dosyasi_anahtar", (0, 0, None))[2] == hazir_mod:
                yontem, uyarilar, dolu = st.session_state.word_bilgi
                st.success(f"**{st.session_state.word_adi}** · {dolu} / {n} sayfaya metin eşleşti"
                           + (" · LLM atlanacak, metinler doğrudan seslendirilecek" if hazir_mod else ""))
                for u in uyarilar:
                    st.warning(u)
            else:
                st.caption("Format: her sayfanın metninden önce ayrı bir satırda **Sayfa 1**, **Sayfa 2** ... "
                           "Yazılmayan sayfalar sessiz geçilir.")
        if kaynak != KAYNAK_DOSYA and st.session_state.pdf_metinler != st.session_state.pdf_metinler_pdf:
            st.session_state.pdf_metinler = st.session_state.pdf_metinler_pdf
        if kaynak == KAYNAK_PDF and st.session_state.get("word_adi"):
            st.session_state.word_adi = ""
            st.session_state.sayfa_dosyasi_anahtar = None

        if kaynak == KAYNAK_HAZIR:
            st.caption("LLM adımı atlandı. Sayfa kutularındaki metinler düzenlenebilir; hazır olunca "
                       "**PDF videosu oluştur**'a basın.")
        elif st.button("📝 Sayfaları LLM ile hazırla", disabled=not st.session_state.kurallar.strip()):
            cubuk = st.progress(0.0, text="Sayfalar LLM'e gönderiliyor...")
            try:
                sonuclar = sayfalari_formatla(
                    st.session_state.kurallar,
                    st.session_state.pdf_metinler,
                    ilerleme=lambda biten, top: cubuk.progress(
                        biten / top, text=f"LLM: {biten} / {top} sayfa hazır"),
                )
                onarilan = []
                for i, ssml in enumerate(sonuclar):
                    ssml, onarildi = ssml_onar(ssml) if ssml.strip() else (ssml, False)
                    if onarildi:
                        onarilan.append(str(i + 1))
                    st.session_state[f"sayfa_ssml_{i}"] = ssml
                cubuk.empty()
                if onarilan:
                    st.info(f"Hatalı SSML etiketleri otomatik düzeltildi: sayfa {', '.join(onarilan)}")
                st.toast("Sayfalar hazır")
            except LLMHatasi as e:
                cubuk.empty()
                st.error(str(e))

        for i in range(n):
            ham = st.session_state.pdf_metinler[i]
            durum = "✅" if st.session_state.get(f"sayfa_ssml_{i}", "").strip() else ("—" if not ham else "⏳")
            with st.expander(f"{durum} Sayfa {i + 1}"):
                c1, c2 = st.columns([1, 3])
                onizleme = sunum_onizleme(st.session_state.pdf_veri, i, n) if sunum_gorunumu else None
                c1.image(onizleme if onizleme is not None else kucuk_resim(st.session_state.pdf_veri, i))
                if onizleme is not None:
                    c1.caption("Sunum görünümü")
                c2.text_area(
                    "Seslendirme metni (boş sayfa 3 sn sessiz gösterilir)",
                    key=f"sayfa_ssml_{i}", height=200,
                )
                if not ham:
                    c2.caption("Bu sayfa için metin yok (Word'de yazılmamış veya görsel/taranmış sayfa).")
                else:
                    c2.caption("LLM'e gidecek metin: " + (ham[:300] + " …" if len(ham) > 300 else ham))

        sayfa_ssml = [st.session_state.get(f"sayfa_ssml_{i}", "") for i in range(n)]
        pdf_hazir = bool(config.TTS_URL and any(x.strip() for x in sayfa_ssml))
        if st.button("🎬 PDF videosu oluştur", type="primary", disabled=not pdf_hazir, key="btn_pdf"):
            cubuk = st.progress(0.0, text="Başlıyor...")
            try:
                st.session_state.video = pdf_videosu_olustur(
                    st.session_state.pdf_veri, sayfa_ssml,
                    ilerleme=lambda oran, mesaj: cubuk.progress(oran, text=mesaj),
                    altyazi=altyazi_goster,
                    sunum=sunum_gorunumu,
                    karakter=karakter_goster,
                )
                st.session_state.video_kaynak = st.session_state.pdf_adi or "docvoice"
                st.session_state.video_pdf = st.session_state.pdf_veri
                st.toast(f"Kaydedildi: output/{st.session_state.video.video.name}")
            except (VideoHatasi, TTSHatasi, ValueError) as e:
                cubuk.empty()
                st.error(str(e))

video_goster()
