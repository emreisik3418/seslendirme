"""
DocVoice - Metin -> LLM formatlama -> Seslendirme
Calistirma:  python -m streamlit run app.py
"""
import json
from datetime import datetime

import streamlit as st

import config
from services.document_reader import metin_cikar
from services.llm_client import LLMHatasi, formatla, sayfalari_formatla
from services.pdf_pages import sayfa_gorseli, sayfa_metinleri
from services.ssml_tools import etiketsiz, ssml_onar
from services.tts_client import TTSHatasi, dosya_uzantisi, seslendir
from services.video_builder import VideoHatasi, pdf_videosu_olustur, video_olustur

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
    for uyari in config.UYARILAR:
        st.warning(uyari)



@st.cache_data(show_spinner=False, max_entries=200)
def kucuk_resim(veri: bytes, sira: int):
    return sayfa_gorseli(veri, sira, dpi=45)


def pdf_yukle(ad: str, veri: bytes):
    """PDF sayfa modu icin dosyayi ve sayfa metinlerini hazirlar."""
    metinler = sayfa_metinleri(veri)
    st.session_state.pdf_veri = veri
    st.session_state.pdf_adi = ad
    st.session_state.pdf_sayfa = len(metinler)
    st.session_state.pdf_metinler = metinler
    for i in range(len(metinler)):
        st.session_state[f"sayfa_ssml_{i}"] = ""


def video_goster():
    v = st.session_state.video
    if v and v.video.exists():
        st.video(str(v.video))
        st.caption(f"{v.bolum_sayisi} sahne · {int(v.sure // 60)} dk {int(v.sure % 60)} sn · output/{v.video.name}")
        k1, k2 = st.columns(2)
        k1.download_button("⬇️ Videoyu indir (.mp4)", v.video.read_bytes(), file_name=v.video.name, mime="video/mp4")
        k2.download_button("⬇️ Altyazıyı indir (.srt)", v.altyazi.read_bytes(), file_name=v.altyazi.name)


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
altyazi_goster = st.toggle(
    "Altyazı göster", value=config.VIDEO_ALTYAZI,
    help="Kapalıyken videoda altyazı görünmez; .srt dosyası yine de ayrıca indirilebilir.",
)
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
            )
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

        if st.button("📝 Sayfaları LLM ile hazırla", disabled=not st.session_state.kurallar.strip()):
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
                c1.image(kucuk_resim(st.session_state.pdf_veri, i))
                c2.text_area(
                    "Seslendirme metni (boş sayfa 3 sn sessiz gösterilir)",
                    key=f"sayfa_ssml_{i}", height=200,
                )
                if not ham:
                    c2.caption("Bu sayfada metin bulunamadı (görsel/taranmış sayfa olabilir).")

        sayfa_ssml = [st.session_state.get(f"sayfa_ssml_{i}", "") for i in range(n)]
        pdf_hazir = bool(config.TTS_URL and any(x.strip() for x in sayfa_ssml))
        if st.button("🎬 PDF videosu oluştur", type="primary", disabled=not pdf_hazir, key="btn_pdf"):
            cubuk = st.progress(0.0, text="Başlıyor...")
            try:
                st.session_state.video = pdf_videosu_olustur(
                    st.session_state.pdf_veri, sayfa_ssml,
                    ilerleme=lambda oran, mesaj: cubuk.progress(oran, text=mesaj),
                    altyazi=altyazi_goster,
                )
                st.toast(f"Kaydedildi: output/{st.session_state.video.video.name}")
            except (VideoHatasi, TTSHatasi, ValueError) as e:
                cubuk.empty()
                st.error(str(e))

video_goster()
