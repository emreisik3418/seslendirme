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
