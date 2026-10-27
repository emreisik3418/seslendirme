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
izleyici.py                  Klasör izleyici: gelen PDF'leri otomatik videoya çevirir
izleyici_baslat.bat          İzleyiciyi Windows'ta çift tıklayarak başlatır
config.py                    .env'den ayarları okur
rules/kurallar.txt           Varsayılan kural seti (system prompt)
services/document_reader.py  Word / PDF / TXT okuma
services/llm_client.py       LLM servisi istemcisi
services/tts_client.py       Seslendirme servisi (SSML -> ses dosyası)
services/ssml_tools.py       SSML'i <break> noktalarından bölümlere ayırır, altyazı temizliği
services/pdf_pages.py        PDF sayfa metinleri ve sayfa görselleri
services/pdf_kartlar.py      PDF'teki gösterge kartlarını (KPI) okur: etiket, birim, değer, renk, ok, yorum
services/sunum_cizim.py      Kartları modern sunum slaytı olarak çizer, anlatıma göre vurgular
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

**Sunum görünümü (PDF modunda, varsayılan açık):** Gösterge kartı içeren sayfalarda rakamlar, renkler ve
yorum PDF'ten okunur (LLM'e gönderilmez) ve modern kutucuklar halinde yeniden çizilir. Kutucuklar konuya
göre satırlara gruplanır (bakiye, faiz); anlatıcı "bakiye" dediğinde bakiye satırı, "faiz" dediğinde faiz
satırı vurgulanır. Birden fazla kart varsa kart adı geçtiğinde o karta odaklanılır. Kart bulunamayan
sayfalar sayfa görseliyle gösterilir. Kartlar PDF içinde seçilebilir metin olmalıdır (resim olarak gömülü
tablolar okunamaz).

Her iki modda:
- Her bölüm ayrı seslendirilir, böylece geçişler ve altyazılar sesle senkron kalır.
- Altyazı isteğe bağlıdır ("Altyazı göster" anahtarı; varsayılanı `VIDEO_ALTYAZI`). Kapalıyken de `.srt` dosyası üretilir.
- Altyazılarda noktalama işaretleri gösterilmez (sayı içindeki ayraçlar ve kelime içi kesme işareti korunur).
- Çıktı: `output/` klasörüne `.mp4` (1920x1080) ve `.srt` altyazı dosyası.
- FFmpeg, `imageio-ffmpeg` paketiyle pip üzerinden gelir; ayrıca kurulum gerekmez.
- Renkler ve logo `.env` içindeki `VIDEO_*` ayarlarıyla değiştirilebilir.

## Klasör izleyici (otomatik mod)

Belirlenen klasöre düşen her PDF'i arayüze gerek kalmadan videoya çevirir.

1. `.env` içinde `IZLE_KLASORU` ve `IZLE_HEDEF_KLASORU` değerlerini doldurun.
2. Kural seti olarak `rules/kurallar.txt` kullanılır (arayüzde "Kuralları kaydet" ile güncellenir)
   veya `IZLE_KURALLAR` ile ayrı bir dosya verilebilir.
3. `izleyici_baslat.bat` dosyasına çift tıklayın ya da `python izleyici.py` çalıştırın.
   Mevcut dosyaları işleyip çıkmak için: `python izleyici.py --bir-kez`

Akış: yeni PDF → kopyalama bitene kadar beklenir → sayfalar LLM'e gönderilir → sunum videosu üretilir →
`<pdf adı>.mp4` (ve `.srt`) hedef klasöre konur. Sunum görünümü ve altyazı `.env`'deki
`VIDEO_SUNUM` / `VIDEO_ALTYAZI` ayarlarını izler.

İzlenen klasörde oluşan alt klasörler:
- `isleniyor/` o an işlenen PDF (bilgisayar kapanırsa sonraki açılışta yeniden kuyruğa alınır)
- `islenen/` başarıyla videoya çevrilen PDF'ler
- `hatali/` işlenemeyen PDF'ler; yanında `.hata.txt` açıklaması. Yeniden denemek için PDF'i ana klasöre
  geri taşıyın; LLM ve seslendirme sonuçları önbellekte olduğu için tekrar istenmez.

Kayıtlar `logs/izleyici.log` dosyasına yazılır. Bilgisayar açıldığında otomatik başlaması için
`izleyici_baslat.bat` dosyasının kısayolunu Windows'un Başlangıç klasörüne (`Win + R` → `shell:startup`) koyabilirsiniz.

## Sorun giderme

- **HTTP 503 / 429 (seslendirme):** Servis geçici olarak yoğun. Uygulama `TTS_RETRY` kez otomatik tekrar dener.
  Başarılı bölümler `output/.tts_cache` içinde saklanır; "Video oluştur"a tekrar basınca sadece eksikler istenir.
  Sık tekrarlanıyorsa `.env` içinde `TTS_BEKLEME` değerini artırın (ör. 1 veya 2 saniye).
- Hata mesajında gösterilen metni Bruno'da göndererek sorunun içerikten mi servisten mi kaynaklandığını ayırt edebilirsiniz.
