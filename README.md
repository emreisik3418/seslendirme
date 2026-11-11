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
dosya_kontrol.py             Açılışta proje dosyalarının birbiriyle uyumunu kontrol eder
services/qlik_yukleyici.py   Videoyu Qlik Sense content library'ye yükler (QRS API)
config.py                    .env'den ayarları okur
rules/kurallar.txt           Varsayılan kural seti (system prompt)
services/document_reader.py  Word / PDF / TXT okuma
services/llm_client.py       LLM servisi istemcisi
services/tts_client.py       Seslendirme servisi (SSML -> ses dosyası)
services/ssml_tools.py       SSML'i <break> noktalarından bölümlere ayırır, altyazı temizliği
services/pdf_pages.py        PDF sayfa metinleri ve sayfa görselleri
services/pdf_kartlar.py      PDF'teki gösterge kartlarını (KPI) okur: etiket, birim, değer, renk, ok, yorum
services/sunum_cizim.py      Kartları modern sunum slaytı olarak çizer, anlatıma göre vurgular
services/figur.py            Tüm vücut animasyonlu sunucu (jestler, nefes, baş hareketi)
services/maya.py             Maskot Maya: kıvırcık tüylü köpek (dil, kuyruk, kafa yatırma, pati)
services/karakter.py         Sesten dudak senkronu; kendi görsel setinizle basit karakter
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

**Sayfa metinlerini Word'den vermek:** PDF sekmesinde "Sayfa metinleri → Word dosyasından al" seçilip bir .docx
yüklenirse LLM'e PDF'teki metin yerine Word'deki metin gönderilir (görseller yine PDF'ten gelir). Format:

```
Sayfa 1
Birinci sayfanın seslendirilecek metni. Birden fazla paragraf olabilir.

Sayfa 2
İkinci sayfanın metni.

Sayfa 4
Sayfa 3 yazılmadığı için sessiz geçilir.
```

- "Sayfa N" satırı başlık stilinde, büyük harfle veya `Sayfa 5: kısa metin` şeklinde olabilir; sıra serbesttir.
- İlk "Sayfa N" satırından önceki metin dikkate alınmaz (açıklama yazılabilir).
- Hiç "Sayfa N" satırı yoksa Word'deki sayfa sonlarına (Ctrl + Enter) göre bölünür.
- Örnek: `ornekler/sayfa_metinleri_ornek.docx`

**Hazır metin (LLM'siz):** PDF sekmesinde "Sayfa metinleri → Hazır metin (LLM'siz)" seçilip aynı formatta bir
.docx veya .txt yüklenirse metinler LLM'e gönderilmeden doğrudan seslendirilir. LLM'den daha önce dönen SSML'i
sayfa numaralarıyla yapıştırabilir ya da düz metin yazabilirsiniz. Hatalı SSML etiketleri otomatik düzeltilir;
metinler yüklendikten sonra sayfa kutularında düzenlenebilir. .txt dosyası UTF-8 veya Not Defteri'nin Türkçe
kodlamasıyla (ANSI) kaydedilebilir.

**Sunum görünümü (PDF modunda, varsayılan açık):** Gösterge kartı içeren sayfalarda rakamlar, renkler ve
yorum PDF'ten okunur (LLM'e gönderilmez) ve modern kutucuklar halinde yeniden çizilir. Kutucuklar konuya
göre satırlara gruplanır (bakiye, faiz); anlatıcı "bakiye" dediğinde bakiye satırı, "faiz" dediğinde faiz
satırı vurgulanır. Birden fazla kart varsa kart adı geçtiğinde o karta odaklanılır. Kart bulunamayan
sayfalar sayfa görseliyle gösterilir. Kartlar PDF içinde seçilebilir metin olmalıdır (resim olarak gömülü
tablolar okunamaz).

**Konuşan karakter:** 5. adımdaki "Konuşan karakter" anahtarı açıksa sağ alt köşede animasyonlu bir karakter
gösterilir; iki seçenek var (izleyici için `VIDEO_KARAKTER_TIPI=sunucu|maya`):

*Maya (maskot):* turuncu kapitone yelekli, kıvırcık tüylü köpek. Konuşurken ağzı açılıp dili görünür, kuyruğunu
sallar, merakla başını yana yatırır, kulakları sallanır; yeni sayfada patisini kaldırıp içeriği gösterir,
arada mutlu zıplar.

*Sunucu (kadın):* tüm vücudu görünen, animasyonlu kadın sunucu:
- Ağzı seslendirmenin şiddetine göre kare kare açılıp kapanır, arada göz kırpar.
- Her yeni sayfa/slayt başında sol tarafa, içeriğe doğru kolunu uzatıp gösterir.
- Konuşurken cümle başlarında anlatma, gösterme ve açık el hareketleri yapar; uzun konuşmalarda da
  5 saniyeden fazla hareketsiz kalmaz, elleri vurgularla hafifçe hareket eder.
- Nefes alır gibi hafifçe yükselip alçalır, salınır, konuşurken başını hafifçe eğip sallar.
İçerik ve altyazı figürün solundaki alana yerleşir. Boyutu `VIDEO_KARAKTER_BOYUT` ile ayarlanır (varsayılan 0.8).
Tamamen yerelde üretilir, ek servis gerekmez.

Kendi karakterinizi kullanmak için `.env` içinde `KARAKTER_KLASORU` ile şeffaf arka planlı PNG'lerin bulunduğu
klasörü verin: `kapali.png`, `yarim.png`, `acik.png` (ağız halleri, zorunlu) ve isteğe bağlı `kirpik.png`.
Bu durumda sabit görselin ağzı hareket eder (el hareketi olmaz). İzleyici `VIDEO_KARAKTER` ayarını kullanır.

Her iki modda:
- Her bölüm ayrı seslendirilir, böylece geçişler ve altyazılar sesle senkron kalır.
- Altyazı isteğe bağlıdır ("Altyazı göster" anahtarı; varsayılanı `VIDEO_ALTYAZI`). Kapalıyken de `.srt` dosyası üretilir.
- PDF sayfalarının boş kenarları kırpılır ve içerik tüm ekranı kullanır (`VIDEO_PDF_TAM_EKRAN`, varsayılan açık);
  altyazı sayfanın üzerine yazılır. Kapatılırsa sayfa tam haliyle, altyazı bandının üstünde gösterilir.
- Altyazı kutusuz, konturlu beyaz yazıdır (`VIDEO_ALTYAZI_STIL=kutusuz`); eski siyah kutu için `kutu`.
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

PDF ile aynı adlı bir Word dosyası konursa (`rapor.pdf` + `rapor.docx`) sayfa metinleri Word'den alınır;
Word dosyasını PDF'ten önce veya aynı anda kopyalayın.

PDF adının başında tarih varsa (NPrinting gibi: `20261028_APK_Rapor.pdf`) eşleştirme tarih yok sayılarak yapılır:
- `APK_Rapor.docx` (tarihsiz) → sabit şablon; her gün kullanılır, klasörde kalır
- `20261028_APK_Rapor.docx` (aynı tarihli) → o güne özel; PDF ile birlikte `islenen/` klasörüne taşınır
- Video adı tarihli kalır (`20261028_APK_Rapor.mp4`), günlük videolar birbirinin üzerine yazılmaz.

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

## Qlik Sense'e yükleme

Oluşan video, Qlik Sense (şirket içi) content library'sine QRS API ile yüklenir ve
`https://<qlik>/content/<kütüphane>/<dosya>.mp4` adresinden izlenir. Uygulamada Dashboard bundle içindeki
**Video player** nesnesine bu adres verilir.

1. Qlik ekibi bir content library oluşturur (örn. `DocVoice`), yazma izni verir ve izleyecek kullanıcılara okuma
   izni tanımlar.
2. `.env` içinde `QLIK_*` ayarlarını doldurun. İki kimlik doğrulama yolu desteklenir:
   - `QLIK_KIMLIK=sertifika`: Qlik'ten dışa aktarılan `client.pem`, `client_key.pem`, `root.pem`;
     `QLIK_URL=https://qliksunucu:4242`, `QLIK_KULLANICI=UserDirectory=INTERNAL; UserId=sa_repository`
     (veya Qlik ekibinin vereceği servis kullanıcısı). İzleme adresi için `QLIK_ICERIK_URL=https://qliksunucu`.
   - `QLIK_KIMLIK=header`: header ile kimlik doğrulayan bir virtual proxy; `QLIK_URL=https://qliksunucu/<önek>`,
     `QLIK_HEADER_ADI` ve `QLIK_KULLANICI=DOMAIN\kullanici`.
3. Yan paneldeki **Qlik bağlantısını test et** ile kontrol edin; video oluşunca **Qlik'e gönder**.
4. İzleyicide otomatik yükleme: `IZLE_QLIK=true`. Yükleme başarısız olursa video hedef klasörde kalır, yanına
   `.qlik_bekliyor` dosyası yazılır ve izleyici 5 dakikada bir (en fazla 12 kez) yeniden dener.

## Sorun giderme

- **"Dosyalar güncel değil" uyarısı / `module 'config' has no attribute ...` hatası:** Bir dosya eski kalmış.
  Uygulama ve izleyici açılışta dosyaların uyumunu kontrol edip hangisinin güncellenmesi gerektiğini yazar.
  En kolayı repodan tüm projeyi indirmek (Code → Download ZIP) ve `.env` dosyanızı koruyarak üzerine kopyalamak.
  Dosyayı güncelledikten sonra Streamlit'i Ctrl+C ile durdurup yeniden başlatın (açıkken içe aktarılan
  dosyaları her zaman yeniden okumaz).

- **HTTP 503 / 429 (seslendirme):** Servis geçici olarak yoğun. Uygulama `TTS_RETRY` kez otomatik tekrar dener.
  Başarılı bölümler `output/.tts_cache` içinde saklanır; "Video oluştur"a tekrar basınca sadece eksikler istenir.
  Sık tekrarlanıyorsa `.env` içinde `TTS_BEKLEME` değerini artırın (ör. 1 veya 2 saniye).
- Hata mesajında gösterilen metni Bruno'da göndererek sorunun içerikten mi servisten mi kaynaklandığını ayırt edebilirsiniz.
