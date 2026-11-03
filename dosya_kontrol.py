"""Proje dosyalarinin birbiriyle uyumlu (ayni surumden) olup olmadigini kontrol eder.

Dosyalar tek tek kopyalandiginda biri eski kalirsa uygulama anlasilmaz bir hatayla cokmek
yerine hangi dosyanin guncellenmesi gerektigini soyler.
"""
import importlib

# Kodun kullandigi tum config ayarlari
GEREKLI_AYARLAR = """
CIKTI_KLASORU IZLE_ARALIK IZLE_BEKLEME IZLE_HEDEF_KLASORU IZLE_KLASORU IZLE_KURALLAR IZLE_SRT
KARAKTER_KLASORU KURALLAR_DOSYASI LLM_APP_NAME LLM_PARALEL LLM_TIMEOUT LLM_TOKEN LLM_URL
PROJE_KLASORU TTS_BEKLEME TTS_KEY TTS_LANG TTS_LEXICON TTS_OUTPUT_FORMAT TTS_RETRY TTS_TIMEOUT
TTS_URL TTS_VOICE UYARILAR VERIFY_SSL VIDEO_ACCENT VIDEO_ALTYAZI VIDEO_BG VIDEO_BG2 VIDEO_FFMPEG
VIDEO_FONT VIDEO_FONT_BOLD VIDEO_KARAKTER VIDEO_LOGO VIDEO_LOGO_ZEMIN VIDEO_SAYFA_NO VIDEO_SUNUM
""".split()

# Modul -> icinde bulunmasi gereken isimler
GEREKLI_MODULLER = {
    "services.document_reader": ["metin_cikar", "sayfa_dosyasi_oku", "sayfalara_esle", "word_sayfa_metinleri"],
    "services.llm_client": ["LLMHatasi", "formatla", "sayfalari_formatla"],
    "services.pdf_pages": ["sayfa_gorseli", "sayfa_metinleri"],
    "services.pdf_kartlar": ["sayfa_duzeni"],
    "services.ssml_tools": ["etiketsiz", "ssml_onar", "bolumlere_ayir"],
    "services.tts_client": ["TTSHatasi", "dosya_uzantisi", "seslendir"],
    "services.karakter": ["sprite_seti", "agiz_halleri", "konum"],
    "services.video_builder": ["VideoHatasi", "pdf_videosu_olustur", "video_olustur", "SAG_BOSLUK"],
    "services.sunum_cizim": ["sunum_slayti", "SunumCizici"],
}


def eksikleri_bul() -> list[str]:
    sorunlar = []
    try:
        import config
    except Exception as e:
        return [f"config.py yüklenemedi: {e}"]
    eksik = [a for a in GEREKLI_AYARLAR if not hasattr(config, a)]
    if eksik:
        sorunlar.append(f"config.py güncel değil (eksik ayar: {', '.join(eksik[:5])}"
                        f"{' ...' if len(eksik) > 5 else ''})")
    for modul, isimler in GEREKLI_MODULLER.items():
        dosya = modul.replace(".", "/") + ".py"
        try:
            m = importlib.import_module(modul)
        except ModuleNotFoundError as e:
            if e.name == modul:
                sorunlar.append(f"{dosya} bulunamadı (yeni dosya, repodan alın)")
            else:
                sorunlar.append(f"{dosya} yüklenemedi: {e}")
            continue
        except Exception as e:
            sorunlar.append(f"{dosya} yüklenemedi: {type(e).__name__}: {e}")
            continue
        eksik = [i for i in isimler if not hasattr(m, i)]
        if eksik:
            sorunlar.append(f"{dosya} güncel değil (eksik: {', '.join(eksik)})")
    return sorunlar


MESAJ = ("Bazı proje dosyaları birbiriyle uyumsuz; büyük ihtimalle biri eski kaldı. "
         "En kolayı repodan tüm projeyi indirip (Code → Download ZIP) .env dosyanızı koruyarak üzerine "
         "kopyalamak. Ardından uygulamayı Ctrl+C ile durdurup yeniden başlatın.")
