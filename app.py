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
    st.caption("Seslendirme: " + ("tanımlı" if config.TTS_URL else "henüz ayarlanmadı"))

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
st.button("🔊 Seslendir", disabled=True, help="TTS servis bilgileri gelince açılacak")
