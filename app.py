"""
DocVoice - Metin -> LLM formatlama -> Seslendirme
Calistirma:  python -m streamlit run app.py
"""
import json
import re
from datetime import datetime

import streamlit as st

import config
from services.document_reader import metin_cikar
from services.llm_client import LLMHatasi, formatla
from services.tts_client import TTSHatasi, dosya_uzantisi, seslendir

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
        duz = re.sub(r"<break[^>]*/>", "\n", st.session_state.sonuc)
        duz = re.sub(r"<[^>]+>", "", duz)
        st.write(duz.strip())
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
