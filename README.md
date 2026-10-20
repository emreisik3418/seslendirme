# DocVoice

Belgeden seslendirmeye hazır metin.

Word/PDF içeriğini şirket LLM servisine kural setiyle gönderir, SSML formatında seslendirme metni üretir ve TTS servisiyle ses dosyasına dönüştürür. İleride video adımı modül olarak eklenecek.

## Kurulum

```
pip install -r requirements.txt
```
`.env.example` dosyasını kopyalayıp adını `.env` yapın ve değerleri doldurun.

## Çalıştırma

```
python -m streamlit run app.py
```
Tarayıcıda `http://localhost:8501` açılır. Kapatmak için terminalde `Ctrl + C`.

## Yapı

```
app.py                       Arayüz (Streamlit)
config.py                    .env'den ayarları okur
rules/kurallar.txt           Varsayılan kural seti (system prompt)
services/document_reader.py  Word / PDF / TXT okuma
services/llm_client.py       LLM servisi istemcisi
services/tts_client.py       Seslendirme servisi (SSML -> ses dosyası)
output/                      Üretilen ses dosyaları (repoya gitmez)
```

Servis yanıt formatı farklıysa sadece `services/llm_client.py` içindeki `_cevabi_ayikla` fonksiyonunu güncellemek yeterlidir.
