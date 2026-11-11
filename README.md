# DocVoice

Belgeden seslendirmeye hazır metin.

Word/PDF içeriğini şirket LLM servisine kural setiyle gönderir, SSML formatında seslendirme metni üretir ve TTS servisiyle ses dosyasına dönüştürür. Son adımda slaytlı ve altyazılı 16:9 MP4 video üretir.

## Kurulum

Hızlı kurulum (paketler kuruluysa):
```
pip install -r requirements.txt
```
`.env.example` dosyasını kopyalayıp adını `.env` yapın ve değerleri doldurun.

Farklı bir bilgisayarda sıfırdan kurulum için bkz. [Yeni bilgisayara kurulum](#yeni-bilgisayara-kurulum).

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
   - Size yalnızca bir "klasör" adresi (`https://qliksunucu/content/KutuphaneAdi`) verildiyse: bu izleme adresidir,
     `/content/` sonrası kütüphane adıdır. `QLIK_URL`'ye bunu yazarsanız uygulama kütüphaneyi ve izleme adresini
     çıkarır, yükleme adresini tahmin eder (sertifika: `:4242`) ve yan panelde gösterir.
3. **Dosya adı sabittir:** video Qlik'e kaynak dosyanın adıyla, başındaki tarih atılarak yüklenir
   (`20261111_APK_Rapor.pdf` → `APK_Rapor.mp4`) ve aynı adlı eski video üzerine yazılır; kütüphanede birikme olmaz.
   Hep tek bir ad istenirse `QLIK_DOSYA_ADI=YoneticiOzeti`. Arayüzde ad, gönderme butonunun üstünde değiştirilebilir.
   Video ile birlikte kaynak PDF ve ses dosyası da aynı adla gider (`QLIK_YUKLENECEKLER=video,pdf,ses`):
   `YoneticiOzeti.mp4`, `YoneticiOzeti.pdf`, `YoneticiOzeti.mp3`. Ses videodan çıkarılır (`QLIK_SES_FORMATI=mp3`).
   Slayt modunda (Word'den) üretilen videoda PDF olmadığı için yalnız video ve ses gider.
4. Yan paneldeki **Qlik bağlantısını test et** ile kontrol edin; video oluşunca **Qlik'e gönder**.
5. İzleyicide otomatik yükleme: `IZLE_QLIK=true`. Yükleme başarısız olursa video hedef klasörde kalır, yanına
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

## Yeni bilgisayara kurulum

Kod bu repoda; yeni bilgisayarda yeniden yazmaya gerek yoktur. Repoda **olmayan** ve ayrıca taşınması
gerekenler: `.env` dosyası, logo dosyası, Qlik sertifika dosyaları (`client.pem`, `client_key.pem`, `root.pem`)
ve varsa kendi kural setiniz (`rules/kurallar.txt` repodaki varsayılandır). Bunları e-posta / ortak klasör yerine
şirketin onaylı güvenli yoluyla taşıyın; şifre ve anahtarları kimseyle paylaşmayın.

1. **Python 3.12** kurun (Şirket Portalı / Yazılım Merkezi veya python.org). Kurulumda "Add python.exe to PATH"
   seçeneğini işaretleyin. Kontrol: `python --version`
2. **pip'i şirketin paket deposuna yönlendirin.** `Win + R` → `%APPDATA%` → `pip` klasörü (yoksa oluşturun) →
   içine `pip.ini` (Not Defteri, kayıt türü: Tüm dosyalar):
   ```ini
   [global]
   index-url = https://<sirket-artifactory-adresi>/artifactory/api/pypi/pypi-remote/simple
   trusted-host = <sirket-artifactory-adresi>
   ```
   Kontrol: `pip config list`
3. **Projeyi indirin:** GitHub'da Code → Download ZIP, örn. `C:\Users\<kullanıcı>\Documents\DocVoice` klasörüne açın.
4. **Paketleri kurun** (proje klasöründe terminal): `pip install -r requirements.txt`
5. **Ayarlar:** `.env.example` dosyasını kopyalayıp adını `.env` yapın ve eski bilgisayardaki değerleri girin
   (veya eski `.env` dosyasını kopyalayın). Türkçe karakter varsa UTF-8 kaydedin. Logo ve sertifika yollarını
   yeni bilgisayara göre düzeltin.
6. **Çalıştırın:** `python -m streamlit run app.py` (ilk açılıştaki e-posta sorusunda Enter'a basmanız yeterli).
   Yan panelde LLM / TTS / Qlik durumları ve varsa ayar uyarıları görünür; "Qlik bağlantısını test et" ile
   Qlik'i kontrol edin.
7. **Klasör izleyici (isteğe bağlı):** `IZLE_*` ayarlarını doldurup `izleyici_baslat.bat`'a çift tıklayın;
   otomatik başlaması için kısayolunu `shell:startup` klasörüne koyun.

Açılışta "Dosyalar güncel değil" uyarısı çıkarsa bir dosya eksik/eski kopyalanmıştır; tüm ZIP'i yeniden açın.

### Kurulum için yapay zekâ asistanına verilecek prompt

Kurulumda takılırsanız aşağıdaki metni Claude'a (veya başka bir asistana) yapıştırabilirsiniz:

```
Şirket bilgisayarına (Windows, yönetici yetkisi ve VS Code eklenti kurulumu kısıtlı, internete doğrudan
pip erişimi yok) DocVoice adlı bir Python 3.12 + Streamlit projesini kuracağım. Kod GitHub reposunda hazır
(README'de "Yeni bilgisayara kurulum" adımları var). pip paketleri yalnızca şirketin JFrog Artifactory
PyPI deposundan (<sirket-artifactory-adresi>, api/pypi/pypi-remote/simple) kurulabiliyor; pip.ini ayarını
%APPDATA%\pip\pip.ini içinde yapmam gerekiyor. Şirket SSL sertifikaları için truststore paketi kullanılıyor.
Bana adım adım, her adımda çalıştırmam gereken komutu ve beklenen çıktıyı vererek eşlik et. Hata alırsam
ekran görüntüsü paylaşacağım. Şifre, token ve iç adresleri benden isteme; yerlerine <...> yaz.
```

## Sıfırdan yeniden oluşturma promptu

Projeyi kod olmadan, baştan bir yapay zekâ asistanıyla yeniden geliştirmek gerekirse (örn. repoya erişim yoksa)
aşağıdaki prompt bugüne kadar yapılan her şeyi ve alınan dersleri içerir. Köşeli parantezli yerleri kendi
bilgilerinizle doldurun; token ve şifreleri prompta yazmayın, `.env`'ye kendiniz girin.

```
Benimle birlikte "DocVoice" adlı bir Python uygulaması geliştirmeni istiyorum. Türkçe konuş, kodu ve dosya
adlarını Türkçe (ASCII) tut. Kodu bir GitHub reposuna dosya dosya yükle; repo herkese açık olabilir, bu yüzden
iç adres, token, şifre ve e-posta asla koda/repoya girmesin, hepsi .env'den okunsun (.env repoya gitmesin,
.env.example yer tutucularla olsun).

ORTAM KISITLARI
- Şirket bilgisayarı, Windows. VS Code var ama eklenti kurulamıyor; Visual Studio kullanmıyoruz.
- Python 3.12. pip yalnızca şirket Artifactory'sinden: %APPDATA%\pip\pip.ini içinde
  index-url = https://<artifactory>/artifactory/api/pypi/pypi-remote/simple, trusted-host = <artifactory>.
- Şirket SSL sertifikaları: truststore paketiyle Windows sertifika deposu kullanılsın. truststore'u global
  enjekte ETME (inject_into_ssl): Qlik'in kendi root.pem'i ile doğrulamayı bozuyor ve RecursionError veriyor.
  Bunun yerine config.ssl_dogrulama() fonksiyonu httpx'e verify=truststore.SSLContext(...) döndürsün;
  standart ssl.SSLContext'i ORIJINAL_SSLCONTEXT olarak sakla.
- Bana kod parçası yapıştırmak yerine dosyaların tamamını ver (kopyala-yapıştırda girinti bozuluyor).
  Projede bir dosya_kontrol.py olsun: açılışta modüllerin beklenen fonksiyon/ayarları içerip içermediğini
  kontrol edip "X dosyası güncel değil" desin (eski dosya kopyalandığında anlaşılır hata için).

AKIŞ
Word/PDF/TXT içeriği → şirket LLM servisi (kural seti + içerik) → SSML → şirket TTS servisi → ses → MP4 video
→ (isteğe bağlı) Qlik Sense content library'ye yükleme.

LLM SERVİSİ
- POST <LLM_URL>, header: x-application-name: <uygulama adı>, Content-Type: application/json
  (gerekirse Authorization: Bearer).
- Body: {"messages":[{"role":"system","content":"<kural seti>"},{"role":"user","content":"<içerik>"}]}
- Yanıt: {"result":1,"error":null,"errorCode":null,"content":"<SSML: <prosody>, <break> etiketleri>"}.
  result!=1 veya error doluysa hata göster. Yanıt 3 dakikadan uzun sürebilir: zaman aşımı 400 sn.
- PDF modunda her sayfa ayrı istek, LLM_PARALEL (3) kadar eş zamanlı. LLM'den dönen SSML'de bozuk/eşleşmeyen
  etiketler olabilir ("mismatched tag"): ssml_onar ile düzelt.

TTS SERVİSİ (Azure cognitiveservices/v1 uyumlu)
- POST <TTS_URL>, header: Content-Type: application/ssml+xml, X-Microsoft-OutputFormat:
  audio-24khz-48kbitrate-mono-mp3, Ocp-Apim-Subscription-Key: <anahtar>.
- Gövde: <speak version="1.0" xml:lang="tr-TR" ...><voice name="<ses adı>"><lexicon uri="<isteğe bağlı>"/>
  ...LLM'den gelen içerik...</voice></speak> (LLM zarf eklediyse kaldırıp yeniden kur).
- 503/429'da üstel bekleme ile tekrar dene (TTS_RETRY=4), istekler arası küçük bekleme (0.3 sn),
  aynı metin için diskte önbellek.

ARAYÜZ (Streamlit, adımlı)
1) Kural seti textarea (rules/kurallar.txt'ye kaydet) 2) İçerik: Word/PDF/TXT yükle veya yaz
3) LLM'e gönder, sonuç düzenlenebilir 4) Seslendir, dinle/indir 5) Video: "Altyazı göster" ve
"Konuşan karakter" anahtarları, karakter seçimi; sekmeler: Slayt modu ve PDF sayfa modu.
Yan panelde servis durumları, .env ayar uyarıları (geçersiz renk, bulunamayan logo vb.), Qlik bağlantı testi.
.streamlit/config.toml ile e-posta sorusunu ve istatistik toplamayı kapat. Renk ayarlarını toleranslı oku
(#E30613, E30613, red, rgb(...)); hatalıysa varsayılanı kullan ve uyar. Yol ayarlarında tırnak, ~, %VAR%,
göreli yol ve "\" kaçış sorunlarını tolere et.

VİDEO (FFmpeg imageio-ffmpeg paketiyle gelsin, ayrı kurulum olmasın; 1920x1080, H.264 + AAC, ayrıca .srt)
- SSML <break> noktalarından bölümlere ayrılsın, her bölüm ayrı seslendirilsin (geçiş ve altyazı senkronu için).
- Slayt modu: her bölüm kurumsal tasarımlı başlıklı slayt (renk/logo .env'den; koyu logoya otomatik açık zemin).
- PDF sayfa modu: her PDF sayfası (pypdfium2 ile görsel) arka planda, o sayfanın seslendirmesi bitince sonraki
  sayfa. Metni olmayan sayfa 3 sn sessiz. Boş kenarlar kırpılıp tam ekran; sayfa numarası gösterilmesin.
- Sayfa metinleri kaynağı: PDF'ten / Word dosyasından (LLM'e gönder) / hazır metin (LLM'siz, doğrudan
  seslendir). Word formatı: her sayfa metninden önce ayrı satırda "Sayfa N" (başlık stili, büyük harf,
  "Sayfa 5: metin" de olur); hiç yoksa Word sayfa sonlarına göre böl. TXT için UTF-8 ve cp1254 dene.
- Altyazı isteğe bağlı; noktalama işaretleri gösterilmesin (sayı içi ayraç ve kelime içi kesme korunur);
  kutusuz, konturlu beyaz kalın yazı ve hafif gölge (siyah kutu/gölge bandı olmasın); altta ince ilerleme çizgisi.
- Sunum görünümü (PDF modu): PDF'teki gösterge (KPI) kartlarını pdfplumber ile oku (etiket, birim, değer,
  renk, ok yönü, yorum) ve modern kutucuklar olarak yeniden çiz; konuya göre satırlara grupla; anlatıcı o
  metriği (ör. "bakiye", "faiz") söylediği anda ilgili satırı/kartı vurgula. Kart bulunamazsa sayfa görseli.
- Konuşan karakter (tamamen yerelde, ek servis yok; ham RGBA kareleri FFmpeg'e pipe ile ver, overlay et):
  a) Sunucu: özgün, tüm vücudu görünen 2D kadın sunucu (gerçek bir kişiye benzetme yapma). İskelet tabanlı
     kollar/eller/bacaklar, doğal omuz birleşimi; ağız ses şiddetine (RMS) göre kare kare, göz kırpma, nefes,
     baş hareketi; her sayfa başında sola, içeriğe doğru kolunu uzatıp göstersin; cümle başlarında anlatma/
     gösterme/açık el jestleri, 5 sn'den uzun hareketsiz kalmasın. Katmanları lru_cache ile önbelleğe al
     (kare başı ~10 ms hedef).
  b) Maskot: kurumsal maskotumuz olan kıvırcık tüylü, turuncu yelekli köpek (görselini paylaşacağım):
     konuşurken ağız/dil, kuyruk sallama, kafa yatırma, yeni sayfada pati kaldırma, arada zıplama.
  c) Özel: KARAKTER_KLASORU'ndaki kapali/yarim/acik/kirpik.png ile basit ağız senkronu.
  İçerik ve altyazı karakterin solundaki alana yerleşsin; boyut VIDEO_KARAKTER_BOYUT (0.8).

KLASÖR İZLEYİCİ (izleyici.py + izleyici_baslat.bat)
- IZLE_KLASORU'na düşen PDF'leri kopyalama bitince (boyut sabitliği + %%EOF kontrolü) al, videoya çevir,
  IZLE_HEDEF_KLASORU'na <pdf adı>.mp4 (+ .srt) koy. Alt klasörler: isleniyor/ (yarıda kalan yeniden kuyruğa),
  islenen/, hatali/ (+ .hata.txt). LLM ve TTS sonuçları önbellekte, yeniden denemede tekrar istenmesin.
  Log: logs/izleyici.log. --bir-kez seçeneği.
- PDF'ler NPrinting'den başında tarihle gelir (20261028_APK_Rapor.pdf, 2026-10-28 ..., 28.10.2026- ...):
  tarih önekini regex ile yok sayarak eşleştir. Aynı adlı Word (aynı tarihli) o güne özel: PDF ile taşınır;
  tarihsiz Word (APK_Rapor.docx) sabit şablon: klasörde kalır.

QLIK SENSE (şirket içi, QRS API)
- Yükleme: POST {QLIK_URL}/qrs/contentlibrary/{kütüphane}/uploadfile?externalpath=<ad>&overwrite=true&xrfkey=<16
  karakter>, aynı xrfkey X-Qlik-Xrfkey header'ında. Dosyayı akış olarak gönder. Yanıt düz metin/JSON metni
  olarak "/content/<kütüphane>/<ad>" dönebilir (nesne varsayma). İzleme adresi: https://<sunucu>/content/
  <kütüphane>/<ad> (uygulamada Dashboard bundle > Video player).
- Kimlik: (a) sertifika: 4242 portu, client.pem + client_key.pem + root.pem, header
  X-Qlik-User: UserDirectory=<DOMAIN>; UserId=<kullanıcı>; (b) header ile kimlik doğrulayan virtual proxy.
- Bana sadece "dosyayı bırakacağın klasör" olarak https://<sunucu>/content/<kütüphane> adresi verildi:
  QLIK_URL'ye bu yazılırsa kütüphane adını ve izleme adresini çıkar, yükleme adresini tahmin et
  (sertifika: https://<sunucu>:4242) ve yan panelde göster.
- Dosya adı sabit ve üzerine yazılsın (birikme olmasın): QLIK_DOSYA_ADI (ör. <Rapor_Adı>) veya kaynak dosya
  adının tarihsiz hali. Aynı adla video (.mp4), kaynak PDF (.pdf) ve videodan FFmpeg ile çıkarılan ses (.mp3)
  gönderilsin (QLIK_YUKLENECEKLER=video,pdf,ses[,srt]). Arayüzde ad ve dosya seçimi değiştirilebilsin.
- İzleyicide IZLE_QLIK=true ise otomatik yükle; başarısızsa videonun yanına .qlik_bekliyor işareti (deneme
  sayısı, PDF yolu, hata) bırak, 5 dk'da bir en fazla 12 kez tekrar dene.
- Hata mesajları anlaşılır olsun: 401 kimlik, 403 yetki (xrfkey hatasıyla ayır; gönderilen kullanıcıyı yaz;
  kütüphane için Create/Read/Update/Delete izni gerekir), 404 kütüphane yok, 409 aynı ad, 413 boyut.

ÇALIŞMA ŞEKLİ
- Her özelliği sahte LLM/TTS/QRS sunucularıyla test et, sonra repoya yükle; README ve .env.example'ı güncel tut.
- Önce küçük bir ortam testi (test_ortam.py) ile Python, paketler ve servislere erişimi doğrulayalım,
  sonra adım adım (LLM → TTS → video → izleyici → karakter → Qlik) ilerleyelim.
- Servislerin gerçek header/body örneklerini ve ekran görüntülerini (Bruno) ben paylaşacağım; tahmin
  ettiğin yerleri açıkça belirt.
```

