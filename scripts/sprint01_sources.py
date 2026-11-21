"""Inventory the pinned public benchmark inputs for SPRINT 01."""
import csv
from datetime import datetime
import hashlib
from importlib.metadata import distribution
import json
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import warnings
from zoneinfo import ZoneInfo

import wntr

ROOT = Path(__file__).resolve().parents[2]
SPRINT = ROOT / "SPRINT01"
LIBRARY = "https://usepa.github.io/WNTR/libraries.html"
UPSTREAM = "https://raw.githubusercontent.com/USEPA/WNTR/1.5.0/"
LICENSE_URL = "https://github.com/USEPA/WNTR/blob/1.5.0/LICENSE.md"
MAX_BYTES = 2_000_000
SELECTED = ("Net2", "Anytown", "Todini2")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def save_json(path, doc):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(doc, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def save_csv(path, rows):
    keys = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, keys, delimiter=";")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value
                             for key, value in row.items()})


def read_inp(data):
    if not 0 < len(data) <= MAX_BYTES or b"\0" in data:
        raise ValueError("INP boyutu veya ikili içeriği geçersiz.")
    content = data.decode("utf-8-sig")
    sections = {}
    key = None
    for raw in content.splitlines():
        line = raw.split(";", 1)[0].strip()
        section = re.fullmatch(r"\[([A-Za-z_]+)\]", line)
        if section:
            key = section[1].upper()
            sections.setdefault(key, [])
        elif line and key:
            sections[key].append(line)
    if not {"JUNCTIONS", "PIPES", "OPTIONS", "END"} <= sections.keys() or not sections["PIPES"]:
        raise ValueError("Gerekli EPANET INP bölümleri eksik.")
    return sections


def limitations(model, sections):
    notes = []
    if sections.get("EMITTERS"):
        notes.append("WNTRSimulator EPANET emitörlerini aynı biçimde modellemez.")
    if model.options.hydraulic.headloss != "H-W":
        notes.append("WNTRSimulator için H-W dışı sürtünme.")
    if any(p.base_speed != 1 or p.speed_pattern_name for _, p in model.pumps()):
        notes.append("Pompa hız deseni veya birimden farklı hız.")
    if any(v.valve_type in {"PBV", "GPV"} for _, v in model.valves()):
        notes.append("WNTRSimulator PBV/GPV sınırlaması.")
    if model.options.time.report_start:
        notes.append("Sıfır dışı rapor başlangıcı.")
    if any(str(action.target()[1]).lower() in {"base_speed", "speed"} for _, control in model.controls()
           for action in control.actions()):
        notes.append("Pompa hız kontrolü.")
    return notes


def inspect(path, data):
    sections = read_inp(data)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        model = wntr.network.WaterNetworkModel(str(path))
    counts = {kind: getattr(model, f"num_{kind}") for kind in
              ("junctions", "pipes", "tanks", "pumps", "valves", "reservoirs", "controls", "patterns")}
    demands = [junction.base_demand for _, junction in model.junctions()]
    restricted = limitations(model, sections)
    return {
        **counts,
        "format": "EPANET INP",
        "inp_flow_unit": str(model.options.hydraulic.inpfile_units),
        "native_duration_s": model.options.time.duration,
        "native_hydraulic_step_s": model.options.time.hydraulic_timestep,
        "native_report_step_s": model.options.time.report_timestep,
        "native_demand_model": model.options.hydraulic.demand_model,
        "positive_base_m3s": sum(d for d in demands if d > 0),
        "zero_base_junctions": sum(d == 0 for d in demands),
        "negative_base_junctions": sum(d < 0 for d in demands),
        "demand_pattern_names": model.pattern_name_list,
        "control_names": model.control_name_list,
        "valve_types": sorted({valve.valve_type for _, valve in model.valves()}),
        "coordinate_type": "Çizim. CRS doğrulanmadı." if sections.get("COORDINATES") else "UNKNOWN",
        "wntr_parse_warnings": [str(w.message) for w in caught],
        "epanet_compatibility": ["EPANET çalıştırılmadı. #623 doğrulanmış bağımsız motor sayılmaz.", *restricted],
        "unsupported_hydraulics": restricted,
    }


def fetch(url):
    with urlopen(Request(url, headers={"User-Agent": "SebekeKalkan-Sprint01/1.0"}), timeout=20) as response:
        data = response.read(MAX_BYTES + 1)
        return data, response.geturl(), response.status


def main():
    if wntr.__version__ != "1.5.0":
        raise RuntimeError("WNTR 1.5.0 gerekli.")
    destination = SPRINT / "MODELLER/v1/orijinal"
    destination.mkdir(parents=True, exist_ok=False)
    package = distribution("wntr")
    notice = next(package.locate_file(f) for f in package.files if str(f).endswith("licenses/LICENSE.md"))
    notice_bytes = notice.read_bytes()
    (destination / "WNTR-LICENSE.md").write_bytes(notice_bytes)
    version = "WNTR 1.5.0"
    at = datetime.now(ZoneInfo("Europe/Istanbul")).isoformat()
    models = wntr.library.model_library
    records = []
    for name in ("Net1", "Net3", "Net2", "Net6", "ky4", "ky10", "Anytown", "Todini2"):
        local = Path(models.get_filepath(name)) if name in models.model_name_list else None
        file = local.name if local else ("Anytown.inp" if name == "Anytown" else "Todini_Fig2_optCost_CMH.inp")
        src = ("wntr/library/networks/" if local else "wntr/tests/networks_for_testing/") + file
        selected = name in SELECTED
        attribution = "USEPA/WNTR, WNTR 1.5.0, " + src
        label = "EPANET mühendislik kıyas ağı"
        if name == "Anytown":
            attribution += ". Hipotetik özgün örnek: Thomas M. Walski ve diğerleri (1987), UKnowledge kaydı 2016."
            label = "Hipotetik kıyas ağı, WNTR test varyantı"
        if name == "Todini2":
            attribution += ". Figür 2 iki çevrimli örnek: Ezio Todini (2000)."
            label = "Sentetik iki çevrimli kıyas ağı, WNTR test varyantı"
        if name in {"ky4", "ky10"}:
            label = "Kentucky saha kökenli araştırma modeli, WNTR paket kopyası"
        if name == "Net6":
            label = "Watson, Murray ve Hart (2009) araştırma kıyası. Saha kökeni UNKNOWN."
        record = {
            "model_id": name, "source_url": "https://github.com/USEPA/WNTR/blob/1.5.0/" + src,
            "download_url": UPSTREAM + src, "version": version, "accessed_at": at,
            "license": "Revised BSD (WNTR dağıtımı ve beraberindeki bildirim)",
            "license_url": LICENSE_URL, "license_notice_sha256": sha256(notice_bytes),
            "attribution": attribution, "model_class": label, "selected_for_pilot": selected,
            "source_variant_note": "Yerel wheel incelendi, uzak etiket ile bayt özdeşliği doğrulanmadı." if name in {"ky4", "ky10"} else "",
        }
        if selected:
            data, effective, status = fetch(record["download_url"])
            read_inp(data)
            if local and sha256(data) != sha256(local.read_bytes()):
                raise ValueError(f"{name}: etiket verisi ve kurulu WNTR kopyası farklı.")
            path = destination / file
            with path.open("xb") as stream:
                stream.write(data)
            record.update(http_status=status, effective_url=effective,
                          local_path=path.relative_to(SPRINT).as_posix(),
                          original_sha256=sha256(data), working_sha256=sha256(data),
                          acquisition="HTTPS indirildi, baytlar değişmedi")
        else:
            path = local
            data = path.read_bytes()
            record.update(original_sha256=sha256(data), working_sha256="UNKNOWN",
                          acquisition="Kurulu WNTR wheel içinde incelendi",
                          exclusion="Eski proje referansı" if name in {"Net1", "Net3"} else
                          "İlk küçük ağ taramasının dışında. Çözüm maliyeti ve dosya sürümü kapsamı.")
        records.append({**record, "bytes": len(data), **inspect(path, data)})

    # Rights were checked on each UKnowledge record before requesting its download.
    kentucky = (
        ("UK_FourteenPipe", "wdst_systems/9", "article=1008&context=wdst_systems&filename=1&type=additional",
         "Ashley Hall (2021), 06 Fourteen Pipe", "2021", 5120, "Basit örnek kıyas"),
        ("UK_Anytown", "wdst_models/1", "article=1000&context=wdst_models&filename=0&type=additional",
         "Thomas M. Walski (2016), 01 Anytown", "2016; kayıt güncellemesi 2021", 10240, "Hipotetik kıyas"),
        ("UK_Hanoi", "wdst_systems/2", "article=1001&context=wdst_systems&filename=4&type=additional",
         "Graeme Dandy (2016), 07 Hanoi System", "2016; kayıt güncellemesi 2021", 8192, "Planlanan iletim sistemi kıyası"),
    )
    for name, record, query, citation, version, advertised, label in kentucky:
        url = "https://uknowledge.uky.edu/cgi/viewcontent.cgi?" + query
        try:
            body, _, status = fetch(url)
            read_inp(body)
            acquisition = "Erişilebilir. Üç ağlık pilot sınırı nedeniyle dosya çalışma alanına alınmadı."
            origin_sha, measured = sha256(body), len(body)
        except (HTTPError, URLError, ValueError) as error:
            status = getattr(error, "code", "UNKNOWN")
            acquisition = f"Geçerli INP alınamadı: {error}"
            origin_sha, measured = "UNKNOWN", "UNKNOWN"
        records.append({
            "model_id": name, "source_url": "https://uknowledge.uky.edu/" + record + "/",
            "download_url": url, "version": version, "accessed_at": at, "attribution": citation,
            "license": "CC BY-NC 4.0", "license_url": "https://creativecommons.org/licenses/by-nc/4.0/",
            "source_variant_note": "Ticari kullanım izni varsayılmaz. WNTR varyantıyla bayt özdeşliği varsayılmaz.",
            "model_class": label, "selected_for_pilot": False, "http_status": status, "bytes": measured,
            "original_sha256": origin_sha, "working_sha256": "UNKNOWN", "advertised_approx_bytes": advertised,
            "acquisition": acquisition, "format": "EPANET INP (kaynak kaydı)",
            **dict.fromkeys(("inp_flow_unit", "junctions", "pipes", "tanks", "pumps", "valves", "reservoirs",
                             "controls", "patterns", "native_demand_model", "coordinate_type",
                             "positive_base_m3s", "zero_base_junctions", "negative_base_junctions",
                             "control_names", "epanet_compatibility"), "UNKNOWN"),
        })
    doc = {"version": "S01-source-v1", "accessed_at": at, "model_library": LIBRARY,
           "kentucky_database": "https://uknowledge.uky.edu/wdsrd/", "models": records}
    save_json(SPRINT / "SOURCE_MANIFEST.json", doc)
    save_csv(SPRINT / "VERI_KATALOGU.csv", records)
    for row in records:
        print(row["model_id"], row.get("junctions"), row.get("pipes"), row["bytes"], row["acquisition"],
              row.get("unsupported_hydraulics", []))


if __name__ == "__main__":
    main()
