# İş Takip

Projeler, görevler ve notlar için basit masaüstü uygulaması (Python + Tkinter, ek paket gerektirmez).

## Çalıştırma

```
python is_takip.py
```

Veriler programın yanındaki `is_takip_veri.json` dosyasında tutulur; her kayıtta önceki hali `is_takip_veri.json.bak` olarak yedeklenir.

## Sekmeler

- **Projeler:** durum, öncelik, tarih, açıklama ve tarihli proje günlüğü (durum değişiklikleri otomatik kaydedilir)
- **Görevler:** projeye bağlı görevler, son tarih; süresi geçenler kırmızı, çift tık ile tamamlandı
- **Notlar:** serbest notlar, arama, Ctrl+S ile kaydetme

## .exe oluşturma (isteğe bağlı)

```
pip install pyinstaller
pyinstaller --onefile --noconsole is_takip.py
```
