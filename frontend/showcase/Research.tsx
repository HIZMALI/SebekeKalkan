import {mu, net, num, study} from './record';

const baski = 'https://balikesir.bel.tr/haberler/baskide-ariza-sayilari-dusuyor-cozum-hizi-artiyor';
// The historical case and both reference rows are retained in the published demo catalog.
const net1 = {id:'Net1_A3_C1', reference:386.11200196799996, proposal:215.76847168799998,
  source:'https://github.com/HIZMALI/SebekeKalkan/blob/da4a26a11ea1ccea2b34ff3f54da343a6681c0a5/data/reference/SPRINT02/DEMO_KATALOGU.json#L140-L188'};
const cases = [
  {name:'Net1', id:net1.id, percent:100 * (net1.reference - net1.proposal) / net1.reference,
    reference:'Bildirim sırası ve tekli etki', method:'ŞebekeKalkan v2'},
  {name:'Net2', id:net.id, percent:net.percent, reference:'Güçlü tekli etki/süre', method:'ŞebekeKalkan B6'},
  {name:'MuR0009', id:mu.id, percent:mu.percent, reference:'Güçlü tekli etki/süre', method:'ŞebekeKalkan B6'},
];

export default function Research({researchPage}: {researchPage: string}) {
  return <>
    <section className="section" id="arastirma" aria-labelledby="research-title">
      <div className="section-heading">
        <div><h2 id="research-title">Araştırma sonuçları</h2><p>Üç ayrı vakada ağırlıklı hizmet açığındaki düşüş.</p></div>
        <a className="text-link" href={researchPage}>Tüm deneyleri incele <span aria-hidden="true">↗</span></a>
      </div>
      <div className="research-cases">
        {cases.map(item=><article key={item.id}>
          <p className="case-name">{item.name}<span>{item.id}</span></p>
          <p className="case-result">%{num(item.percent)}</p>
          <p className="case-baseline">{item.reference} → {item.method}</p>
        </article>)}
      </div>
      <details className="evidence-details">
        <summary>Araştırmanın kapsamı ve tüm sonuçlar</summary>
        <p>{study.clusters} arıza kümesi, {study.main} bağlı ana koşul. {study.primary} birincil kıyasta {study.WIN} kazanım, {study.TIE} eşitlik, {study.LOSS} kayıp. Eksik {study.main - study.primary} koşulun {study.SOLVER_ERROR}’ü çözücü hatası, {study.PHYSICAL_INVALID}’si fizik reddi, {study.TIMEOUT}’i zaman aşımı. Tüm yöntemleri {study.all_methods} iş tamamladı. Duyarlılıkta {study.sensitivity}/{study.sensitivity_total} kıyas yapılabildi.</p>
        <p>Üç MuR topolojisi aynı sentetik aileden. MuR0006’da on kıyasta referansın birincil açığı sıfır. Skeletonize’ın önceki dış değerlendirmesinde altı koşulda kazanım bulunmadı. Sonuçlar kendi simülasyon koşullarına aittir. Saha tasarrufu ve genel üstünlük için kanıt yetersiz.</p>
        <dl>
          <dt>Net1 · Başvuru dönemi</dt><dd>{num(net1.reference, 3)} → {num(net1.proposal, 3)} ağırlıklı m³. <a href={net1.source}>Tarihsel vaka kaydı</a></dd>
          <dt>MuR0009 · Seçili vaka</dt><dd>{num(mu.reference, 3)} → {num(mu.candidate, 3)} ağırlıklı m³. İki plan da 16. saatte tamamlandı. Güçlü yöntem {mu.calls.greedy}, B6 {mu.calls.s02_b6} WNTR çağrısı yaptı.</dd>
          <dt>MuR0009 kayıt kimliği</dt><dd><code>{mu.run}</code></dd>
          <dt>MuR0009 sonuç SHA-256</dt><dd><code>{mu.sha256}</code></dd>
        </dl>
        <a href={researchPage}>Kaynaklı araştırma eki</a>
      </details>
    </section>
    <section className="section local-context" aria-labelledby="local-title">
      <div>
        <h2 id="local-title">Balıkesir’de altyapı arızaları</h2>
        <p className="local-total">88.802</p>
        <p><strong>2026’nın ilk yedi ayında toplam altyapı arıza kaydı.</strong></p>
      </div>
      <div className="local-source">
        <p>BASKİ kayıtları içme suyu, kanalizasyon, abone işleri, tarımsal sulama ve diğer altyapı arızalarını kapsıyor. ŞebekeKalkan deneyleri örnek şebekelerde yürütüldü.</p>
        <a className="text-link" href={baski}>BASKİ’nin 17 Ağustos 2026 açıklaması <span aria-hidden="true">↗</span></a>
        <details className="pilot">
          <summary>Önerilen saha pilotu</summary>
          <ol>
            <li>İzinli şebeke verilerini aktar.</li>
            <li>Modeli gerçek ölçümlerle doğrula.</li>
            <li>Onarım kararlarını aynı koşullarda karşılaştır.</li>
          </ol>
        </details>
      </div>
    </section>
    <section className="section" id="nasil-calisir" aria-labelledby="steps-title">
      <div className="section-heading"><h2 id="steps-title">Nasıl çalışır?</h2></div>
      <ol className="method-steps">
        <li><h3>Koşulları sabitle</h3><p>Aynı arızalar, ekip ve onarım süreleri.</p></li>
        <li><h3>Onarım sırasını değiştir</h3><p>İki planı aynı saatte karşılaştır.</p></li>
        <li><h3>Su hizmetine etkisini gör</h3><p>Karşılanan talebi ve onarım çizelgesini izle.</p></li>
      </ol>
    </section>
  </>;
}
