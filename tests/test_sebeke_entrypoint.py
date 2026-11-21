import json
from sebekekalkan_core.__main__ import main


def test_turkish_entrypoint_and_scope(capsys):
    main()
    raw = capsys.readouterr().out
    result = json.loads(raw)
    assert result['proje'] == 'ŞebekeKalkan'
    assert result['birinci_yazar_ve_sunucu'] == 'Öğr. Gör. Enise Odabaş'
    assert result['ikinci_arastirmaci'] == 'Öğr. Gör. Mert Hızmalı'
    assert 'saha ölçümü değildir' in result['kapsam']
    assert 'Hidrolik çözümleyici' in result['sinir']
    assert result['onarim_takvimi'][2] == {'boru': 'P3', 'ekip': 2, 'baslangic_saat': 1.0, 'bitis_saat': 4.0}
    assert 'Öğr. Gör.' in raw
