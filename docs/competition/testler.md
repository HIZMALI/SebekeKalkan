# Testleri çalıştırma

Yayın kopyasında yerel başlatma ve tarayıcı testi temiz bir Python 3.12 ortamında çalışır. `npm ci` ile kilitli frontend araçlarını hazırlayın. Edge ve Chrome projeleri için tarayıcılar makinede kurulu olmalıdır.

1. `RUN_LOCAL.cmd` ile uygulamayı başlatın ve terminaldeki hazır URL’yi kontrol edin.
2. `frontend` dizininde `npm test` çalıştırın. Varsayılan adres 127.0.0.1 port 18760. Farklı port için `SE_BASE_URL` tanımlayın.
3. `scripts/smoke-test.ps1 -RunWntr` üç hazır girdiyi gerçek yerel API’ye gönderir. Kabul durumunu ve CSV, JSON, PDF çıkışlarını kanıt klasöründe saklar.

Eski Python araştırma regresyonları eski anlık görüntünün `experiments/results`, `docs/research` ve kilitli `experiments/configs/build02_s_protocol_v1.json` kayıtlarıyla, özgün SPRINT 01, SPRINT 02 ve çalışan referans arşivi kullanılarak çalıştırılır. Yayın kopyasındaki kişisel yerel yol, göreli model yoluna dönüştürülmüştür. Tarihsel protokol hash’i için onaylı asıl dosyayı izole test dizinine yerleştirin. Canlı duman testi için büyük araştırma arşivleri gerekmez.
