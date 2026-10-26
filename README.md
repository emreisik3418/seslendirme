# DocVoice

Belgeden seslendirmeye hazır metin.

Word/PDF içeriğini şirket LLM servisine kural setiyle gönderir, SSML formatında seslendirme metni üretir ve TTS servisiyle ses dosyasına dönüştürür. Son adımda slaytlı ve altyazılı 16:9 MP4 video üretir.

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
services/ssml_tools.py       SSML'i <break> noktalarından bölümlere ayırır
services/video_builder.py    Slayt çizimi + FFmpeg ile MP4 ve SRT üretimi
output/                      Üretilen ses dosyaları (repoya gitmez)
```

Servis yanıt formatı farklıysa sadece `services/llm_client.py` içindeki `_cevabi_ayikla` fonksiyonunu güncellemek yeterlidir.

## Video

- Metin, LLM çıktısındaki `<break>` noktalarından bölümlere ayrılır; her bölüm bir slayt olur.
- Her bölüm ayrı seslendirilir, böylece slayt geçişleri ve altyazılar sesle senkron kalır.
- Çıktı: `output/` klasörüne `.mp4` (1920x1080) ve `.srt` altyazı dosyası.
- FFmpeg, `imageio-ffmpeg` paketiyle pip üzerinden gelir; ayrıca kurulum gerekmez.
- Renkler ve logo `.env` içindeki `VIDEO_*` ayarlarıyla değiştirilebilir.
