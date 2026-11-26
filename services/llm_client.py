"""Sirket LLM servisine istek atar (chat/completions formati)."""
import logging
import os
import time

import httpx

import config


log = logging.getLogger("docvoice.llm")


class LLMHatasi(Exception):
    pass


def _proxy_bilgisi(url: str | None = None) -> str:
    """Adres (varsayilan LLM_URL) icin ortam degiskenlerinden (HTTPS_PROXY vb.) kullanilacak proxy; NO_PROXY ile atlanan
    adreslerde bos. httpx yalnizca ortam degiskenlerine bakar, Windows'un Internet Ayarlari'ndaki
    (Bruno'nun da kullanabildigi) sistem proxy'sine bakmaz."""
    import urllib.request
    from urllib.parse import urlsplit

    p = urlsplit(url or config.LLM_URL)
    if not p.hostname or urllib.request.proxy_bypass_environment(p.hostname):
        return ""
    vekiller = urllib.request.getproxies_environment()
    vekil = vekiller.get(p.scheme) or vekiller.get("all")
    return vekil or ""


def _zaman_asimi() -> httpx.Timeout:
    # baglanti 30 sn'de kurulmali; yanit icin LLM_TIMEOUT kadar beklenir
    return httpx.Timeout(config.LLM_TIMEOUT, connect=min(30.0, config.LLM_TIMEOUT))


def _headerlar() -> dict:
    h = {"Content-Type": "application/json"}
    if config.LLM_APP_NAME:
        h["x-application-name"] = config.LLM_APP_NAME
    if config.LLM_TOKEN:
        h["Authorization"] = f"Bearer {config.LLM_TOKEN}"
    return h


def _cevabi_ayikla(veri: dict) -> str:
    """Yanittaki metni bulur. Format farkliysa burayi guncellemek yeterli."""
    # Sirket servisi formati: {"result": 1, "error": null, "errorCode": null, "content": "..."}
    if isinstance(veri, dict) and "content" in veri and "result" in veri:
        if veri.get("error") or veri.get("result") != 1:
            raise LLMHatasi(
                f"Servis hata dondu (errorCode: {veri.get('errorCode')}): {veri.get('error')}"
            )
        return veri["content"] or ""

    try:
        return veri["choices"][0]["message"]["content"]  # OpenAI tarzi
    except (KeyError, IndexError, TypeError):
        pass
    for anahtar in ("content", "result", "response", "text", "answer"):
        if isinstance(veri, dict) and isinstance(veri.get(anahtar), str):
            return veri[anahtar]
    raise LLMHatasi(f"Yanit formati taninmadi. Gelen yanit:\n{veri}")


def formatla(kurallar: str, metin: str) -> tuple[str, dict]:
    """Kurallari (system) ve metni (user) gonderir.
    Doner: (duzenlenmis_metin, ham_yanit)"""
    if not config.LLM_URL:
        raise LLMHatasi(".env dosyasinda LLM_URL tanimli degil.")

    govde = {
        "messages": [
            {"role": "system", "content": kurallar},
            {"role": "user", "content": metin},
        ]
    }

    proxy = _proxy_bilgisi() if config.LLM_SISTEM_PROXY else ""
    yol = f" (proxy üzerinden: {proxy})" if proxy else ""
    log.info(f"LLM isteği gönderildi: {len(metin)} karakter{yol}")
    bas = time.monotonic()

    def sure() -> str:
        return f"{time.monotonic() - bas:.0f} sn"

    ipucu = (" Bruno'da çalışıp burada çalışmıyorsa: .env'de LLM_SISTEM_PROXY=false deneyin "
             "(istek şu an sistem proxy'si üzerinden gidiyor)." if proxy else
             " Birden çok sayfa aynı anda gönderiliyorsa LLM_PARALEL=1 ile deneyin.")
    try:
        with httpx.Client(timeout=_zaman_asimi(), verify=config.ssl_dogrulama(),
                          trust_env=config.LLM_SISTEM_PROXY) as istemci:
            yanit = istemci.post(config.LLM_URL, json=govde, headers=_headerlar())
    except httpx.ConnectTimeout as e:
        raise LLMHatasi(f"Servise {sure()} içinde bağlanılamadı (ağ / proxy / güvenlik duvarı).{ipucu}") from e
    except httpx.ConnectError as e:
        raise LLMHatasi(f"Servise bağlanılamadı (ağ/SSL): {e}{ipucu}") from e
    except httpx.TimeoutException as e:
        raise LLMHatasi(f"Servis {config.LLM_TIMEOUT:.0f} sn içinde yanıt vermedi ({sure()}).{ipucu}") from e
    except httpx.TransportError as e:   # RemoteProtocolError, ReadError: baglanti karsi taraftan kapatildi
        raise LLMHatasi(f"Bağlantı {sure()} sonra yanıt gelmeden kapandı ({type(e).__name__}: {e}). "
                        f"Aradaki proxy / gateway'in kendi zaman aşımı olabilir.{ipucu}") from e
    log.info(f"LLM yanıtı: HTTP {yanit.status_code}, {sure()}")

    if yanit.status_code != 200:
        ek = ""
        if yanit.status_code in (502, 503, 504):
            ek = (f" ({sure()} sonra; aradaki proxy / gateway zaman aşımına uğramış veya servis "
                  f"meşgul olabilir.{ipucu})")
        raise LLMHatasi(f"HTTP {yanit.status_code}{ek}: {yanit.text[:1000]}")

    try:
        veri = yanit.json()
    except ValueError:
        # JSON degilse duz metin olarak kabul et
        return yanit.text, {"raw": yanit.text}

    return _cevabi_ayikla(veri), veri


def sayfalari_formatla(kurallar: str, metinler: list[str], ilerleme=None) -> list[str]:
    """Her sayfa metnini ayri istekle gonderir (LLM_PARALEL kadar es zamanli).
    Bos sayfalar icin bos metin doner. ilerleme: fn(biten, toplam)"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    sonuc = [""] * len(metinler)
    isler = {i: m for i, m in enumerate(metinler) if m.strip()}
    biten = 0
    with ThreadPoolExecutor(max_workers=max(1, config.LLM_PARALEL)) as havuz:
        gelecek = {havuz.submit(formatla, kurallar, m): i for i, m in isler.items()}
        for g in as_completed(gelecek):
            i = gelecek[g]
            try:
                sonuc[i] = g.result()[0]
            except LLMHatasi as e:
                for diger in gelecek:
                    diger.cancel()
                raise LLMHatasi(f"Sayfa {i + 1}: {e}") from e
            biten += 1
            if ilerleme:
                ilerleme(biten, len(isler))
    return sonuc
