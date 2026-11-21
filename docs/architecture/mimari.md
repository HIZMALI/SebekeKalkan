# Çalışma biçimi

Yerel başlatıcı, kilitli V4.1 çekirdeğini ve çalışma yolunu yalıtılmış bir dizinde kurar. Uygulamanın izlediği kaynak modeli SHA-256 ile denetlenir. Paylaşılan çekirdek kaynak kodu depoda tek yerde bulunur. Çalışma kopyası yalnız başlatırken üretilir. Tarayıcıdaki kayıtlı gösterim aynı zaman serisinin küçük, türetilmiş JSON kopyasını kullanır.

Yeni WNTR istekleri iki izinli ağ ve geçerli borularla sınırlandırılır. Yalnız bir iş çalışır. İşçi 180 saniyede kesilir. Başarılı işte fizik kabulü ve sonuç/kayıt doğrulaması gerçekleşmeden dışa aktarma açılamaz. Başlatılan ve tamamlanan işler birbirinden ayrı kimlik alır. Önceki kaynak ve deney arşivleri yerel araştırma kaydında saklanır.

İsteğe bağlı ayrık servis yalnız V4 kullanıcı senaryosu, hazır model tanımı, sağlık ve statik varlık uçlarını sunar. Uzak yayında TLS ve IP yönetimi onaylanmış ters vekil tarafından sağlanır. API’de bir kaynak adresi başına bir yeni gönderim/dakika, süreç başına dört gönderim/dakika, 8 KiB gövde sınırı ve kayıt birikim sınırı vardır. Vekil arkasında uygulama varsayılan olarak tüm istekleri vekilin adresinden görür ve daha düşük ortak hız sınırı oluşur. Güvenilen vekil yapılandırması yapılmadan istemci IP başlıkları işlenmez.

Rekabet günü ana anlatım kayıtlı gösterimle tamamlanır. Canlı hesap ayrı bir sekmeden açılır. Yerel HTML ve PDF kararlı ikinci bir yol sağlar. Yazılım, hidrolik örnek modelinde karar desteği sağlar.
