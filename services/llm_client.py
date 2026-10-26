"""Sirket LLM servisine istek atar (chat/completions formati)."""
import httpx

import config


class LLMHatasi(Exception):
    pass


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

    try:
        yanit = httpx.post(
            config.LLM_URL,
            json=govde,
            headers=_headerlar(),
            timeout=config.LLM_TIMEOUT,
            verify=config.VERIFY_SSL,
        )
    except httpx.ConnectError as e:
        raise LLMHatasi(f"Servise baglanilamadi (ag/SSL): {e}") from e
    except httpx.TimeoutException as e:
        raise LLMHatasi(f"Servis {config.LLM_TIMEOUT} sn icinde yanit vermedi.") from e

    if yanit.status_code != 200:
        raise LLMHatasi(f"HTTP {yanit.status_code}: {yanit.text[:1000]}")

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
