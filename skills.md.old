# PCB Skill Notes (ABD + LLM Workflow)

Bu dosya, LLM ile PCB gelistirme surecinde **ABD toolunu** nasil kullanacagimizi ve sureci nasil yurutecegimizi tanimlar.

## 1) Kapsam

- Bu repo bir LLM runtime degildir.
- Claude/Codex devreyi tasarlar, duzeltir, placement yapar.
- `abd` deterministic kontrolleri ve stage hafizasini yonetir.
- Hedef akis: `schema -> layout -> manufacturing`.

## 2) Sorumluluk Paylasimi

LLM sorumlulugu:

1. Board hedeflerini planlamak (guc, USB, IO, footprint kararlari).
2. Komponentleri toplamak ve devreyi (schema/netlist) kurmak.
3. Placement iyilestirmek ve routing/DRC hatalarini duzeltmek.

ABD sorumlulugu:

1. Stage-state hafizasi tutmak (`.autoboard/<example>.json`).
2. Schema/layout checklerini deterministic calistirmak.
3. Routing zincirini kosmak ve hangi stage'in fail oldugunu acik dondurmek.
4. Board degismediyse ayni hatayi tekrar dondurmek (gereksiz rerun engeli).

## 3) Iki Ana Dongu

### A) Schema Dongusu

1. **Plan/Arastirma** (LLM only, ABD disi)
2. **Schema Build**: komponent ve baglantilar dosyalara islenir
3. **Schema Check**: net/pin/footprint tutarliligi kontrol edilir

Gate:

- `schema_build=pass` ve `schema_check=pass` olmadan layouta guvenilmez.

### B) Layout Dongusu

1. **Layout Place**: placement, board siniri, cakisma kontrolu
2. **Layout Export**: unrouted PCB + DSN
3. **Layout Route**: freerouting + SES parse + routed PCB
4. **Layout Check**: DRC
5. **Layout Pack**: gerber/render

Retry:

- `layout_route` veya `layout_check` fail ise placement/netler duzeltilir.
- `schema_check` fail ise schema dongusune geri donulur.

## 4) ABD Stage Modeli

Schema loop:

1. `schema_build`
2. `schema_check`

Layout loop:

1. `layout_place`
2. `layout_export`
3. `layout_route`
4. `layout_check`
5. `layout_pack`

Status degerleri:

- `pending`
- `pass`
- `fail`

## 5) ABD Komutlari

Temel komutlar:

- `./abd help`
- `./abd status --example <name>`
- `./abd status --example <name> --pretty`
- `./abd status --example <name> --short`
- `./abd check --example <name>`
- `./abd route --example <name>`
- `./abd forward --example <name>`
- `./abd pull-forward --example <name>`
- `./abd rewind --example <name>`
- `./abd reset --example <name>`

Notlar:

- `route`: `check` + layout zinciri.
- `forward`/`pull-forward`: route ile ayni akis (orchestrator dili icin alias).
- `rewind`: state'i sifirlayip bastan sona yeniden kosar.
- `reset`: sadece state temizler, route calistirmaz.
- `--force`: ayni hash fail korumasini bypass eder.

## 6) LLM Operasyon Playbook

LLM her iterasyonda su sirayi izlemeli:

1. `./abd status --example <board> --short`
2. Gerekirse `./abd check --example <board>`
3. Check temizse `./abd forward --example <board>`
4. Fail stage'e gore dosya duzeltmesi yap
5. Tekrar `./abd forward --example <board>`

Fail yorumlama:

- `schema_check` fail: net/pin/footprint map duzelt
- `layout_place` fail: cakisma, board disi placement duzelt
- `layout_route` fail: placement/topoloji/sinif kurallari iyilestir
- `layout_check` fail: DRC kaynakli elektriksel/fiziksel ihlal duzelt
- `layout_export` fail: footprint/export zinciri duzelt

## 7) Ayni Hata Tekrari Engeli

ABD, `board_hash` ile degisiklik tespit eder.

- Son fail ile ayni hash gelirse rerun yapmaz.
- `reused_failure: true` ile ayni hatayi geri verir.
- LLM once dosyalari degistirmeli, sonra komutu tekrar calistirmali.

Bu davranis, "degisiklik yoksa tekrar deneme" maliyetini engeller.

## 8) Ornek Kisa Akis

1. `./abd status --example led --short`
2. `./abd check --example led`
3. `./abd forward --example led`
4. Fail varsa duzeltme
5. `./abd forward --example led`
6. Basariliysa artifactleri kontrol et (`output/<board>/`)

## 9) Arac Secim Kurali

- Normalde `pipeline.py` dogrudan cagrilmaz.
- LLM yonetiminde standart arac `abd` olmalidir.
- `pipeline.py` sadece debug/altyapi testi icin dogrudan kullanilir.
