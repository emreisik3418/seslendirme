# İş Takip

İşleri ve mevcut uygulamaları gruplar halinde takip etmek, dipnot ve kod parçacığı eklemek için sunucusuz, tek dosyalık web uygulaması.

## Kullanım

`is_takip.html` dosyasına çift tıklayın (Chrome veya Edge önerilir). Kurulum ve internet gerekmez.

## Kayıt

- İlk açılışta **Veri dosyası oluştur** ile bir `is_takip_veri.json` dosyası seçin; her değişiklik bu dosyaya otomatik yazılır.
- Tarayıcı yeniden açıldığında güvenlik gereği bir kez **Dosyaya bağlan** düğmesine basmanız istenir.
- Veriler ayrıca tarayıcıda (localStorage) yedeklenir. **Veri dosyası** menüsünden JSON yedeği indirip geri yükleyebilirsiniz.
- Firefox dosyaya doğrudan yazmayı desteklemez; orada yalnızca tarayıcı kaydı ve JSON indirme/yükleme kullanılabilir.

## Özellikler

İki bölüm vardır: **İşler** ve **Uygulamalar**. Her bölümün kendi grupları olur (ör. uygulamalar için Mobil, Qlik, BO).

- Renkli gruplar; gruplar açılıp kapanabilir
- Uygulama: ad, grup, durum (Canlıda / Test / Geliştirmede / Kullanım dışı), teknoloji, sürüm, sunucu/konum, sorumlu, bağlantı, açıklama
- İş: başlık, grup, durum, öncelik, başlangıç / son tarih, açıklama
- Görünümler: Tüm işler, Açık, Süresi geçen (kırmızı), Tamamlanan
- İşlerde ve uygulamalarda dipnotlar (tarihli); açıklamada `[1]`, `[2]` ile atıf
- Kod parçacıkları: dil etiketi, kopyalama, düzenleme
- Başlık, bilgi alanları, açıklama, dipnot ve kod içinde arama (Ctrl+K)

> Not: Veri dosyanızı (`is_takip_veri.json`) bu repoya eklemeyin; repo herkese açık.
