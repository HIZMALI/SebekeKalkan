type Metrics={weighted_unmet_volume_m3:number;critical_low_pressure_node_hours:number;repair_completion_hour:number;unmet_demand_volume_m3:number};
type Assignment={pipe_id:string;crew:number;starts_at_h:number;ends_at_h:number};
type Plan={decision_classification?:{in_best_set:boolean};metrics:Metrics;assignments:Assignment[]};
const number=(value:number)=>value.toLocaleString('tr-TR',{maximumFractionDigits:2});
function compare(a:Metrics,b:Metrics){
  for(const key of ['weighted_unmet_volume_m3','critical_low_pressure_node_hours','repair_completion_hour'] as const){
    const tolerance=1e-6+1e-8*Math.max(Math.abs(a[key]),Math.abs(b[key]));
    if(Math.abs(a[key]-b[key])>tolerance)return a[key]<b[key]?-1:1;
  }
  return 0;
}
export default function DecisionSummary({policyV2,pipes,crews,proposal,greedy,fifo,ties,plans}:{policyV2?:boolean;pipes:string[];crews:number;proposal:Plan;greedy:Plan;fifo:Plan;ties:number;plans:Plan[]}){
  const first=Math.min(...proposal.assignments.map(a=>a.starts_at_h));
  const simultaneous=proposal.assignments.filter(a=>a.starts_at_h===first);
  const relation=policyV2?(greedy.decision_classification?.in_best_set?0:-1):compare(proposal.metrics,greedy.metrics);
  const numericalConflict=!policyV2&&plans.some(plan=>compare(plan.metrics,proposal.metrics)<0);
  return <section className="decision-summary" aria-label="Karar özeti">
    <h3>Bu plan ne söylüyor?</h3>
    <div className="decision-cards">
      <article><h4>Hangi borular arızalı?</h4><strong>{pipes.join(' · ')}</strong><p>{crews} ekip · Boru izolasyonu ve onarım sonrası açılma</p></article>
      <article><h4>İlk müdahale</h4><strong>{simultaneous.map(a=>`Boru ${a.pipe_id}`).join(' ve ')}</strong><p>{number(first)}. saatte {simultaneous.length>1?'paralel':'başlayan'} müdahale. Öncelik listesi: {proposal.assignments.map(a=>a.pipe_id).join(' → ')}.</p></article>
      <article className="method-verdict"><h4>Sezgisel yöntemle karşılaştırma</h4><strong>{relation===0?'Eşit sonuç':relation<0?'Hedefte daha iyi sonuç':'Hedefte daha kötü sonuç'}</strong><p>Öneri: {number(proposal.metrics.weighted_unmet_volume_m3)} m³; sezgisel: {number(greedy.metrics.weighted_unmet_volume_m3)} m³ ağırlıklandırılmış hizmet açığı. Basınç süresi ve son onarım da hedefe dahildir.</p></article>
    </div>
    <p className="fifo-comparison"><strong>Bildirim sırasıyla karşılaştırma:</strong> {number(fifo.metrics.unmet_demand_volume_m3)} → {number(proposal.metrics.unmet_demand_volume_m3)} m³ karşılanamayan müşteri talebi. Bu fark bildirim sırasına göredir.</p>
    <p className="muted">{ties} eşit iyi öncelik listesi. Arama yalnız en fazla üç borulu, iş bekletmeyen sıralamaları kapsar. Müşteri hizmet açığı kaçak su değildir.</p>
    {numericalConflict&&<p className="warning numerical-warning" role="note"><strong>Sayısal eşitlik uyarısı:</strong> Tam arama ham sayıları sıralar. Toleransla eşit hizmet açığında başka bir plan daha erken bitebilir. Bu vaka için tolerans altında en iyi hedef garantisi verilmez; bütün planları karşılaştırın.</p>}
  </section>;
}
