# ŞebekeKalkan · BAÜN finali konuşma metni

Öğr. Gör. Enise Odabaş · 26 Kasım 2026. Ana sunum yedi slayt. Soru gelirse 8–12. slaytlar açılır. Başvuru posterinin basılı sürümü aynı kalır.

| Akış | Süre | Bitiş |
| --- | ---: | ---: |
| Slayt 1–6 | 4.15 | 4.15 |
| Kayıtlı ürün gösterimi | 1.45–2.00 | 6.00–6.15 |
| Slayt 7 | 0.30 | 6.30–6.45 |
| Soru-cevap | 3.00 | 9.30–9.45 |

## Slayt 1 · 0.00–0.35

Bir su şebekesinde dört borunun aynı anda arızalandığını düşünelim. Arızaların hepsini onaracağız. Ama ekipler aynı anda her yere yetişemiyor ve vereceğimiz ilk karar, onarım sürerken kimin ne kadar su alabildiğini değiştiriyor. ŞebekeKalkan bu farkı, ekip görevlendirilmeden önce simülasyonda hesaplıyor. Ben Enise Odabaş. Çalışmayı Mert Hızmalı ile birlikte yürüttük. Bugün aynı arızalar ve aynı ekip için iki kararın su hizmetini nasıl değiştirdiğini göstereceğim.

## Slayt 2 · 0.35–1.19

Bu örnekte dört boru saat ikide izole ediliyor ve bir onarım ekibi var. Tekli etkiyi onarım süresine bölen güçlü referans, dokuz numaralı boruyla başlıyor. ŞebekeKalkan on iki numaralı boruyu öne alıyor ve üçüncü sırayı da değiştiriyor. Her iki plan aynı boruları onarıyor, aynı süreleri kullanıyor ve on altıncı saatte bitiyor. Fark, aradaki saatlerde ortaya çıkıyor. Tek başına etkili görünen bir borunun değeri, başka bir bağlantı kapalıyken değişebiliyor. O yüzden onarım boyunca şebekenin nasıl davrandığını karşılaştırıyoruz.

## Slayt 3 · 1.19–2.08

Akış üç adımda ilerliyor. Önce kullanıcı arızaları, ekip sayısını ve onarım sürelerini seçiyor. Sonra sistem bildirim sırasını ve güçlü referansı da içeren, en çok altı öncelik sırasını aynı koşullarda hesaplıyor. Her aday için basınca bağlı talebi WNTR ile çözüyoruz. Basınç düşünce bir düğümün alabileceği su da düşebiliyor. Kütle dengesi, depo sınırları ve borunun gerçekten kapalı ve açık olduğu anlar denetleniyor. Son adımda kullanıcı hangi borunun ne zaman onarılacağını, müşteriye ne kadar su ulaştığını ve hangi ölçütün öneriyi belirlediğini görüyor. Bu kayıtlar sonucu yeniden denetlemeyi mümkün kılıyor.

## Slayt 4 · 2.08–2.53

Net2 değerlendirme vakasında, kritik müşterileri de ağırlıklandıran hizmet açığı, bin beş yüz dokuzdan bin dört yüz otuz yedi ağırlıklı metreküpe düştü. Fark yetmiş bir virgül doksan dokuz ağırlıklı metreküp, yani yüzde dört virgül yetmiş yedi. Kritik düşük basınç süresi de otuz dört buçuktan otuz bir buçuk düğüm-saate indi. Saat sekizde bir an için bakarsak, karşılanan müşteri talebi güçlü yöntemde saniyede sekiz virgül doksan yedi litre, bizim planda on bir virgül sıfır üç litre. İki çizelgenin bitişi aynı. Bunlar bu şebeke ve bu arızalar için simülasyon ölçümleri.

## Slayt 5 · 2.53–3.38

Başvurumuzdan sonra aynı yöntemi daha önce değerlendirmediğimiz şebekelerde önceden kayıtlı bir planla sınadık. MuR dokuz adlı sentetik ağdan seçtiğimiz bu vakada, güçlü referansa karşı hizmet açığı üç yüz otuz yedi virgül dört yüz yetmiş beşten üç yüz altı virgül dokuz yüz dokuza düştü. Yüzde dokuz virgül sıfır altılık farkın karşılığında çözücü çağrıları on altıdan yirmi altıya çıktı. Bu kez de iki plan on altıncı saatte tamamlandı. Araştırmanın tamamında otuz koşulun yirmi üçü birincil kıyas için doğrulandı. Üçünde ek kazanım, yirmisinde eşitlik var. Diğer koşullar ekte.

## Slayt 6 · 3.38–4.15

Şimdi jürinin kullanacağı ekrana geçiyorum. Karşınıza çıkan ilk şebeke, aynı Net2 deneyinin doğrulanmış kaydı. Boruların durumu ve düğümlerdeki basınç, hesaplanmış zaman serisinden geliyor. İki yöntemi aynı saatte değiştireceğim. Sonra onarım çizelgesini ve her ölçümün dayandığı kayıt kimliğini açacağım. Kullanıcı isterse yerel WNTR modunda kendi borularını seçerek yeni bir hesap başlatabiliyor. Bu işlem yeni bir iş kimliği alıyor ve dışa aktarma fiziksel kontroller geçildikten sonra açılıyor.

## Uygulama · 4.15–6.00/6.15

| Demo saati | Eylem | Söylenecek cümle |
| --- | --- | --- |
| 0.00–0.20 | Net2 açıkken 02.00 düğmesine bas. Dört işaretli boruyu göster. | “Dört arıza burada. Bu noktada borular izole edilmiş ve bir ekip çalışmaya başlıyor.” |
| 0.20–0.50 | 08.00’a dön. Güçlü referans ve ŞebekeKalkan B6 arasında geç. | “Saati sabit tuttum. Güçlü sırada karşılanan talep 8,97. B6’da 11,03 litre/saniye. Düğüm renkleri basınçtaki değişimi gösteriyor.” |
| 0.50–1.10 | İki onarım sırası ve son onarımı göster. | “İlk onarım farklı, son onarım iki planda da 16. saatte. Yüzde 4,77, bütün koşunun ağırlıklı hizmet açığı farkı.” |
| 1.10–1.30 | Vaka kaynağını aç. Gerekirse kanıt JSON veya CSV düğmesini göster. | “Bu koşunun kayıt kimliği burada. Talep değerleri zaman serisinden indirilebiliyor.” |
| 1.30–1.45 | MuR araştırma örneğine kaydır. | “Diğer örnek bağımsız araştırma kaydından. Aynı ölçüt, farklı şebeke ve senaryo.” |
| 1.45–2.00 | Süre varsa yerel sekmede Kendi senaryon’u ve hazır örnekleri aç. Sadece zaman uygunsa yeni iş başlat. | “Yeni bir iş başlatsak yeni kimlik alır. Fizik kabulü sonuçtan önce gelir.” |

Sunumdan önce kayıtlı sayfayı, yerel canlı sekmeyi ve PDF yedeğini aynı cihazda aç. Yeni hesap başlatılırsa sonucu beklemeden yedinci slayda dön. Yerel bağlantı kesilirse indirilen çevrimdışı gösterimi kullan.

## Slayt 7 · 6.00/6.15–6.30/6.45

ŞebekeKalkan’ın bugün sunduğu şey, bir onarım önceliğini gerekçesi ve ölçümleriyle birlikte görebilmek. Prototip araştırmada farklı sıraları sınamak, eğitimde basınç ve hizmet ilişkisini incelemek, planlamada ise hangi verinin toplanması gerektiğini görmek için kullanılabilir. Bir belediyeyle sonraki adım, ağı ve arıza kayıtlarını kalibre edip önceden belirlenmiş ölçütlerle pilot yapmak. Bugünkü örnekte bütün işler aynı saatte bitti. Müdahale sürerken müşterilere ulaşan suyu değiştiren, onarıma hangi borudan başladığımızdı. Teşekkür ederim.

## Üç dakikalık kısa anlatım

**0.00–0.40.** Dört boru aynı anda arızalandığında bir ekip hangisinden başlayacak? ŞebekeKalkan, aynı arızaları farklı sıralarda onarırken müşterilere ne kadar su ulaşacağını hesaplıyor. Ben Enise Odabaş. Çalışmayı Mert Hızmalı ile yürüttük. Sistem, kullanıcının arıza ve süre girdilerinden bir çizelge kuruyor. Bildirim sırası ve güçlü tekli etki/süre de dahil en çok altı sıra, basınca bağlı talep modeliyle karşılaştırılıyor. Geçerli sonuçlar model, yöntem ve iş kimliğiyle izlenebiliyor.

**0.40–1.40.** Net2’de güçlü referans dokuz numaralı boruya, B6 on iki numaralı boruya öncelik verdi. İki plan on altıncı saatte bitti. B6’da ağırlıklı hizmet açığı yüzde 4,77 daha düşük. Kritik düşük basınç 34,5’ten 31,5 düğüm-saate indi. Şimdi ekranda 08.00’ı sabitliyorum. Yöntemi değiştirdiğimde karşılanan müşteri talebinin 8,97’den 11,03 litre/saniyeye çıktığını görüyoruz. Yüzde bütün koşuya, debi yalnız bu zaman adımına ilişkin.

**1.40–2.22.** Başvuru sonrasındaki MuR0009 deneyinde yüzde 9,06 daha düşük ağırlıklı hizmet açığı hesaplandı. İki planın son onarımı yine 16. saatteydi. Çözücü çağrıları 16’dan 26’ya çıktı. Bu seçilmiş sentetik vaka için bir sonuç. Yeni örneklemin 30 koşulunda 23 tam birincil kıyas bulunuyor. Üç kazanım ve yirmi eşitlik var. Diğer koşullar ve yöntem bütçeleri bilimsel ekte ayrı olarak verildi.

**2.22–3.00.** Yerel sürümde yeni bir arıza kombinasyonu da girilebilir ve fizik denetimini geçen sonuca iş kimliğiyle dönülebilir. Prototip, kararın gerekçesini göstermek için bugün kullanılabilir. Bir belediye pilotu için önce kalibre bir model, işletme verisi ve saha doğrulaması gerekiyor. ŞebekeKalkan bize onarımın bitişinin yanında, o ana kadar verilen su hizmetini de karşılaştırma imkânı veriyor.

## Altmış saniyelik acil gösterim

- **0.00–0.12** · Yerel çevrimdışı BASLA.html dosyasını aç. Açılmazsa PDF’de 4. slayta git.
- **0.12–0.30** · 08.00’ı göster. Güçlü referans ve B6 arasında bir kez geç. “8,97 ve 11,03 litre/saniye.”
- **0.30–0.44** · Ana kartı göster. “Net2’de yüzde 4,77 daha az ağırlıklı hizmet açığı. İki plan da aynı saatte bitiyor.”
- **0.44–1.00** · MuR bölümüne veya PDF’de 5. slayta geç. “Sonraki araştırmadaki seçilmiş sentetik örnekte yüzde 9,06 ve ek çözücü çağrısı. Tam çalışma ekte.”
