# ŞebekeKalkan · Jüri soru-cevap kılavuzu

## 1. ŞebekeKalkan hangi kararı destekliyor?

Sabit arızalar, ekipler ve sürelerde hangi borudan başlamanın onarım boyunca müşteri hizmetine nasıl yansıdığını hesaplıyor. Kullanıcı öneriyi, diğer planları, basınç serilerini, ekip çizelgesini ve karar ölçütünü aynı ekranda görebiliyor.

## 2. Yapay zekâ var mı?

Mevcut sistem kısıtlı sıra araması, deterministik onarım ataması ve WNTR hidrolik simülasyonu kullanıyor. Makine öğrenmesi eğitimi ve üretken yapay zekâ bileşeni bulunmuyor.

## 3. Neden FIFO ile kıyas yeterli olmaz?

FIFO bildirim sırasını temsil ediyor. Güçlü tekli etki/süre referansı, her borunun tekil hizmet etkisine ve onarım süresine bakıyor. Ana iki pozitif örneği bu güçlü referansla karşılaştırdık. SPRINT 01’deki yaklaşık %40,2 ise FIFO’ya göre. O vakada güçlü yönteme karşı eşitlik var.

## 4. Net2’de 71,99 m³ su tasarrufu mu?

71,99 ağırlıklı m³, Net2 kaydında iki simülasyon planının ağırlıklı müşteri hizmet açığı farkı. Hesaplanan müşteri talebi açığı, kritik düğüm katsayılarıyla ağırlıklandırılıyor. Saha tasarrufu için debi ölçümü ve kalibre saha çalışması gerekir.

## 5. 08.00’deki 8,97 ile 11,03 L/s neyi ölçüyor?

Net2 simülasyonunda aynı zaman adımındaki toplam karşılanan müşteri talebini. Yüzde 4,77, analiz ufku boyunca integral alınmış ve ağırlıklandırılmış başka bir ölçüttür. İki yöntemin son onarımı 16. saatte biter.

## 6. Yeni araştırmada neden 23 ve 20 sayıları var?

30 bağlı ana koşulun 23’ünde B6 ile güçlü referansın birincil sonucu fiziksel kabulden geçti. 20 işte bütün yöntemler de tamamlandı. Üç işte sonradan koşan rastgele kontroller süre sınırına takıldı. O üç işin tamamlanmış birincil çiftleri geçerli kaldı.

## 7. Yedi eksik koşuldan ne öğrendiniz?

Dördü çözücü hatası, ikisi fiziksel kabul reddi, biri zaman aşımı. Ana payda 30 koşul olarak kalıyor. 23 tam kıyasta üç kazanım, 20 eşitlik ve sıfır birincil kayıp var. Eksikler eşitlik veya başarı sayılmadı.

## 8. MuR ağları gerçekten bağımsız mı?

Önceden kullanılmamış üç ayrı topoloji var. Üçü aynı sentetik üretici ailesinden, o yüzden aileler arası dış geçerlilik sınırlı. Yalnız MuR0009 daha zorlayıcı ağ kabul ölçütünü karşıladı. MuR0006’da on kıyasta güçlü referansın birincil açığı zaten sıfırdı.

## 9. Skeletonize’da neden üstünlük görülmedi?

Önceden ayrılmış altı koşulun altısında birincil ölçüt güçlü referansla eşit kaldı. Bu örneklemde ek adayların doğrulanmış ilave yararı bulunmadı. Sonuç, yöntemin bağlama bağlı değerinin bir parçası.

## 10. Yöntem 24 sıranın en iyisini neden kaçırdı?

B6 aday bütçesi altı. Dört arızada 24 beklemesiz öncelik sırasının tümünü aramıyor. Tarihsel Net2_G1_C1’de fark 898,169174 ağırlıklı m³ oldu. Kapsamlı mod tüm 24 önceliği karşılaştırır. Ekip seyahati, bekleme ve stok birlikte değiştiğinde problem genişler.

## 11. İyileşmenin maliyeti nedir?

MuR0009_G02_C1’de güçlü yöntem 16, B6 26 WNTR çağrısı yaptı. Aynı donanımdaki yöntem CPU süreleri yaklaşık 5,31 ve 7,66 saniyeydi. Bu bir vaka ölçümü. Hızlı/kapsamlı modun maliyeti ağ, ekip sayısı ve seçilen borulara göre değişir.

## 12. Neden sıfır birincil kayıp genelleme için yeterli değil?

B6 güçlü referansı ve FIFO’yu uygun adaylar arasında tutuyor. Bu, geçerli aday havuzunda birincil hedefte kötüleşmeyi sınırlıyor. Kazanımın sıklığı, ikincil bedeller, eksik çözümler ve hesap maliyeti ayrı ölçülmeli. Eldeki çalışma genel üstünlüğü destekleyecek kapsamda değil.

## 13. Duyarlılık testinde sıralama değişti mi?

36 duyarlılık koşulunun 28’inde tam birincil kıyas yapılabildi. Örneğin talep %20 yükseldiğinde bir koşulda birincil kararın yanında ağırlıksız hizmet açığında 11,64 m³ kötüleşme görüldü. Başvuru dönemindeki 26 koşul ayrı deney grubudur.

## 14. Simülasyon fiziksel olarak nasıl kontrol ediliyor?

Basınca bağlı talep, düğüm kütle dengesi, depo sınırları, kapalı boru akışı ve onarım olayları kontrol ediliyor. Seçilen plan taze çözümlerle yeniden doğrulanıyor. Yetersiz basınç ve negatif basınçlar sonuçta görünür kalır. Çözüm veya fizik reddinde plan ve dışa aktarma açılmaz.

## 15. EPANET #623 ne oldu?

Minimum depo sınırıyla ilgili tarihsel EPANET davranışı kayıtlı. Başvuru ve eski doğrulama sonuçları korunuyor. Yeni doğrulanmış demo ve canlı üretim yolu WNTR PDD kullanıyor. Bilinen DLL davranışının düzeltildiği veya bütün ağların kabul edileceği sonucu çıkarılmadı.

## 16. Gerçek belediye veya SCADA verisi var mı?

Bu teslimde örnek mühendislik ağları ve sentetik araştırma modelleri var. Bir kurumla pilot için veri sahibinin izni, şebeke kalibrasyonu, gerçek vana ve ekip kayıtları ile sahada ölçülebilir hizmet hedefleri gerekiyor.

## 17. Şema rotayı ya da gerçek konumu gösteriyor mu?

Şema modelin bağlantı geometrisini gösterir. Onarım çizelgesi boru önceliği, ekip ataması ve onarım saatlerini verir. Seyahat, trafik, yol durumu, ekip yetkinliği ve malzeme stoku ayrı saha girdileridir.

## 18. Araştırma önceden kayıtlı mı?

Yeni araştırmada ana arıza kümeleri, ekip düzeyleri, karşılaştırma yöntemleri ve ölçütler koşular başlamadan kilitlenmişti. Protokol, model ve sonuçlar SHA-256 ile eşleştirildi. Final hazırlığında iki vaka ham zaman serisinden yeniden denetlendi. Başvuru belgeleri kendi tarihsel kapsamıyla ayrı tutuldu.

## 19. Yeni bir kullanıcı sonucu gösterirken sistem yavaşlar veya kapanırsa ne olur?

Kayıtlı Net2 gösterimi hemen açılır. Canlı yerel işlem ayrı kimlikle kuyruğa girer ve sert üst sınır 180 saniyedir. İptal, çözücü hatası veya zaman aşımında indirmeler açılmaz. Jüri akışı canlı hesap sonucunu beklemeden tamamlanır. İnternet kesilirse tek dosyalı HTML ve PDF kullanılır.

## 20. Kamuya açık hesaplamanın sınırları neler?

Yerel ürün iki izinli ağ, üç veya dört boru, bir veya iki ekip ve iki ile beş saat arasında onarım süreleri kabul ediyor. Uzak servis için ayrı kaynak, tek çalışan, istek kotası ve izinli HTTPS origin gerekir. Aynı anda yeni bir iş sınırında API 429 döndürür. Canlı yayın durumu teslim raporunda gösterilir.

## 21. Yöntemin özgün katkısı nerede?

Öncelik sıralarını, güçlü referansı, fiziksel yeniden çözümü ve kaynak izini bir karar ekranına bağlıyoruz. Ürün, koşulları aynı tutup karar farkını denetlenebilir kılıyor. PDD ve onarım sıralama literatürde yerleşik yöntemler, katkının kapsamını test edilmiş akış ve ölçülmüş senaryolar belirliyor.

## 22. Başvuru posterinden sonra ne büyüdü?

Başvuru Net1 ve Net3 ile üç arızalı deneyleri kapsıyor. 18 ana ve 26 duyarlılık koşulu ayrı. Final ürününe Net2 ve Skeletonize üzerinde dört arıza, kullanıcı girdisi ve yeni araştırma eklendi. Yeni 30 koşulluk çalışma başvuru sonuçlarının yerine geçmiyor.
