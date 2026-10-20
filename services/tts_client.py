"""Seslendirme servisi - endpoint bilgileri gelince doldurulacak."""
import config


class TTSHatasi(Exception):
    pass


def seslendir(metin: str) -> bytes:
    """Metni gonderir, ses dosyasinin baytlarini dondurur."""
    if not config.TTS_URL:
        raise TTSHatasi("TTS servisi henuz ayarlanmadi (.env -> TTS_URL).")
    raise NotImplementedError("TTS servis formati paylasilinca eklenecek.")
