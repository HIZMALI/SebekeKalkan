"""Fetch only pinned teaching/benchmark files, retaining originals and publisher notice."""
from datetime import datetime
from pathlib import Path
import urllib.request
import wntr

from sebekekalkan_core.s02_physics import OUT, SOURCE, MODELS, csv_file, sha, utc, write

TAG = "https://raw.githubusercontent.com/USEPA/WNTR/1.5.0/"
MODELS_PICKED = {
    "Net2":"library/networks/Net2.inp",
    "Skeletonize":"tests/networks_for_testing/skeletonize.inp",
    "Awumah1":"tests/networks_for_testing/Awumah_layout1.inp",
    "Anytown":"tests/networks_for_testing/Anytown.inp",
    "Todini2":"tests/networks_for_testing/Todini_Fig2_optCost_CMH.inp",
}


def obtain(url,path):
    with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"SebekeKalkan-source-audit/2"}),timeout=30) as r:
        if r.status!=200:raise ValueError(r.status)
        data=r.read(2_000_001)
    if not 0<len(data)<=2_000_000:raise ValueError("Model boyut kapısı")
    if path.exists():
        if path.read_bytes()!=data:raise ValueError("Önceki kaynak değişti")
    else:
        with path.open("xb") as f:f.write(data)
    return data


def main():
    if SOURCE.exists():raise FileExistsError(SOURCE)
    MODELS.mkdir(parents=True,exist_ok=True)
    notice=MODELS/"WNTR-LICENSE.md"
    obtain(TAG+"LICENSE.md",notice)
    rows=[]
    for key,sub in MODELS_PICKED.items():
        url=TAG+"wntr/"+sub
        path=MODELS/Path(sub).name
        data=obtain(url,path)
        installed=Path(wntr.__file__).parent/sub
        if data.splitlines()!=installed.read_bytes().splitlines():raise ValueError("Dağıtım ve etiket içeriği farklı: "+key)
        model=wntr.network.WaterNetworkModel(str(path))
        peak=wntr.metrics.expected_demand(model).max()
        rows.append(dict(model_id=key,filename=path.name,source_url=url,tag="1.5.0",accessed=utc(),
            license="WNTR dağıtımında Revised BSD bildirimi; özgün veri haklarında daha geniş iddia yok",
            license_url=TAG+"LICENSE.md",license_sha256=sha(notice),original_sha256=sha(path),working_sha256=sha(path),
            wheel_sha256=sha(installed),wheel_equal_ignoring_line_endings=True,bytes=len(data),
            model_class="WNTR kütüphane örneği; saha kalibrasyonu yok" if key=="Net2" else "WNTR dağıtımındaki araştırma/test örneği; saha doğrulaması yok",
            counts_junctions=model.num_junctions,pipes=model.num_pipes,tanks=model.num_tanks,reservoirs=model.num_reservoirs,
            pumps=model.num_pumps,valves=model.num_valves,positive_demand_nodes=int((peak>0).sum()),
            negative_base_junctions=sum(j.base_demand<0 for _,j in model.junctions()),
            variant="Özgün baytlar; çalışma sırasında yalnız ön kayıtlı PDD, olay ve zaman ayarları"))
    write(SOURCE,{"accessed_utc":utc(),"library":"https://usepa.github.io/WNTR/libraries.html","models":rows})
    csv_file(OUT/"VERI_KATALOGU_S02.csv",rows)
    print([(r["model_id"],r["pipes"],r["positive_demand_nodes"]) for r in rows])


if __name__=="__main__":
    main()
