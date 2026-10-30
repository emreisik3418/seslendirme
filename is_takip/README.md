# İş Takip

Projeleri gruplar halinde takip etmek, dipnot ve kod parçacığı eklemek için sunucusuz, tek dosyalık web uygulaması.

## Kullanım

`is_takip.html` dosyasına çift tıklayın (Chrome veya Edge önerilir). Kurulum ve internet gerekmez.

## Kayıt

- İlk açılışta **Veri dosyası oluştur** ile bir `is_takip_veri.json` dosyası seçin; her değişiklik bu dosyaya otomatik yazılır.
- Tarayıcı yeniden açıldığında güvenlik gereği bir kez **Dosyaya bağlan** düğmesine basmanız istenir.
- Veriler ayrıca tarayıcıda (localStorage) yedeklenir. **Veri dosyası** menüsünden JSON yedeği indirip geri yükleyebilirsiniz.
- Firefox dosyaya doğrudan yazmayı desteklemez; orada yalnızca tarayıcı kaydı ve JSON indirme/yükleme kullanılabilir.

## Özellikler

- Renkli gruplar; gruplar açılıp kapanabilir
- İş: başlık, grup, durum, öncelik, başlangıç / son tarih, açıklama
- Görünümler: Tüm işler, Açık, Süresi geçen (kırmızı), Tamamlanan
- Dipnotlar (tarihli); açıklamada `[1]`, `[2]` ile atıf
- Kod parçacıkları: dil etiketi, kopyalama, düzenleme
- Başlık, açıklama, dipnot ve kod içinde arama (Ctrl+K)

> Not: Veri dosyanızı (`is_takip_veri.json`) bu repoya eklemeyin; repo herkese açık.
