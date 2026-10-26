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
services/ssml_tools.py       SSML'i <break> noktalarından bölümlere ayırır, altyazı temizliği
services/pdf_pages.py        PDF sayfa metinleri ve sayfa görselleri
services/video_builder.py    Slayt çizimi + FFmpeg ile MP4 ve SRT üretimi
output/                      Üretilen ses dosyaları (repoya gitmez)
```

Servis yanıt formatı farklıysa sadece `services/llm_client.py` içindeki `_cevabi_ayikla` fonksiyonunu güncellemek yeterlidir.

## Video

İki mod var (arayüzde 5. adım, sekmeler):

**Slayt modu:** 3. adımdaki metin `<break>` noktalarından bölümlere ayrılır, her bölüm kurumsal tasarımlı bir slayt olur.

**PDF sayfa modu:** Her PDF sayfası arka planda gösterilir. Her sayfanın metni kural setiyle ayrı ayrı LLM'e gönderilir
(`LLM_PARALEL` kadar eş zamanlı), sonuçlar sayfa sayfa düzenlenebilir. Bir sayfanın seslendirmesi bitince sonrakine geçilir.
Metni olmayan sayfalar 3 saniye sessiz gösterilir.

Her iki modda:
- Her bölüm ayrı seslendirilir, böylece geçişler ve altyazılar sesle senkron kalır.
- Altyazı isteğe bağlıdır ("Altyazı göster" anahtarı; varsayılanı `VIDEO_ALTYAZI`). Kapalıyken de `.srt` dosyası üretilir.
- Altyazılarda noktalama işaretleri gösterilmez (sayı içindeki ayraçlar ve kelime içi kesme işareti korunur).
- Çıktı: `output/` klasörüne `.mp4` (1920x1080) ve `.srt` altyazı dosyası.
- FFmpeg, `imageio-ffmpeg` paketiyle pip üzerinden gelir; ayrıca kurulum gerekmez.
- Renkler ve logo `.env` içindeki `VIDEO_*` ayarlarıyla değiştirilebilir.

## Sorun giderme

- **HTTP 503 / 429 (seslendirme):** Servis geçici olarak yoğun. Uygulama `TTS_RETRY` kez otomatik tekrar dener.
  Başarılı bölümler `output/.tts_cache` içinde saklanır; "Video oluştur"a tekrar basınca sadece eksikler istenir.
  Sık tekrarlanıyorsa `.env` içinde `TTS_BEKLEME` değerini artırın (ör. 1 veya 2 saniye).
- Hata mesajında gösterilen metni Bruno'da göndererek sorunun içerikten mi servisten mi kaynaklandığını ayırt edebilirsiniz.
