"""Türkçe, yerel başlangıç kontrolü; web sunucusu değildir."""
import json

from .sebeke import RepairTask, allocate_crews


def main():
    assignments = allocate_crews([RepairTask('P1', 2), RepairTask('P2', 1), RepairTask('P3', 3)], 2)
    result = {
        'proje': 'ŞebekeKalkan',
        'kapsam': 'Yalnız ekip tahsisi örneği; borular ve süreler yöntem kontrolü içindir, saha ölçümü değildir.',
        'birinci_yazar_ve_sunucu': 'Öğr. Gör. Enise Odabaş',
        'ikinci_arastirmaci': 'Öğr. Gör. Mert Hızmalı',
        'onarim_takvimi': [
            {'boru': x.pipe_id, 'ekip': x.crew + 1, 'baslangic_saat': x.starts_at_h, 'bitis_saat': x.ends_at_h}
            for x in assignments
        ],
        'sinir': 'Hidrolik çözümleyici EPANET 2.2 web/deney akışında çalışır; bu komut yalnız ekip tahsisini kontrol eder. Gerçek analiz: scripts/start-web.ps1.',
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    main()
