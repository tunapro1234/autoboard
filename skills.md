# PCB Agent Skills / Handoff Contract

Bu dosya, **LLM'i dogrudan gommeden** (API key, model server, SDK yok) Claude Code veya Codex gibi agent'larin PCB tasarim surecini asama asama yurutup programa sinyal vermesi icin ortak sozlesmeyi tanimlar.

## 1) Kapsam ve Sinirlar

- Bu repo bir LLM runtime degildir.
- Agent sadece dosya degistirir, komut calistirir ve sinyal birakir.
- Program tarafi sinyali okuyup ilgili tool adimini calistirir.
- Uretim hedefi: `circuit -> simulate -> route -> gerber`.

## 2) Roller

- `Agent (Codex/Claude)`:
  - Board/circuit dosyalarini uretir veya gunceller.
  - Asama tamamlayinca bir sinyal olusturur.
  - Gerekli output dosya yollarini sinyal payload'ina yazar.
- `Orchestrator (bizim program)`:
  - Sinyali validate eder.
  - Uygun pipeline komutunu calistirir.
  - Sonucu `ok/fail` olarak yeni sinyal ile geri yazar.

## 3) Tasima Katmani (No Direct LLM Integration)

Sinyal iletimi dosya tabanli:

- Klasor: `.signals/<run_id>/`
- Her olay bir JSON dosyasi:
  - `0001_requirements_done.json`
  - `0002_circuit_done.json`
  - `0003_simulate_done.json`
- Yazim kurali: once `*.tmp`, sonra atomic rename.

Bu yapi CI, local shell ve farkli agent ortamlarinda ayni calisir.

## 4) Olay Semasi (JSON)

Tum olaylar su sekilde olmalidir:

```json
{
  "run_id": "2026-02-25-esp32s3-001",
  "seq": 3,
  "stage": "simulate_done",
  "status": "ok",
  "producer": "codex",
  "timestamp_utc": "2026-02-25T15:40:00Z",
  "board": "esp32s3",
  "outputs": {
    "primary": "output/esp32s3/sim_report.json"
  },
  "meta": {
    "notes": "3v3 rail 3.31V"
  }
}
```

Zorunlu alanlar:

- `run_id`, `seq`, `stage`, `status`, `producer`, `timestamp_utc`
- `status`: `ok | fail`

Opsiyonel alanlar:

- `board`, `outputs`, `meta`

## 5) Asama Modeli

Standart stage isimleri:

1. `requirements_done`
2. `circuit_done`
3. `simulate_done`
4. `pcb_export_done`
5. `route_done`
6. `checks_done`
7. `gerber_done`

Fail durumu icin ayni stage + `status: fail` kullanilir.

## 6) Program Tarafi Eylem Haritasi

Minimum ve mevcut repo ile uyumlu yurutum:

1. Agent `circuit_done` sinyali birakir (`board` alani dolu).
2. Orchestrator CLI ile check + route surecini kontrol eder:
   - `./abd route --example <board>`
3. Orchestrator pipeline loglarindan asama sonuclarini cikarir ve
   `.signals/<run_id>/` altina sirali `*_done.json` olaylarini yazar.

Not:

- `abd`, `autoboard` komutunun kisaltmasidir.
- `route` komutu check asamasini otomatik calistirir.

## 7) Agent Tool Set (Claude/Codex icin)

Agent'e verilecek minimum tool yetkileri:

- Dosya okuma/yazma: `rg`, `sed`, `cat`, patch/apply
- Calistirma: `python pipeline.py --example <name>`
- Test: `pytest -q`
- (Opsiyonel) KiCad dogrulama:
  - `kicad-cli sch erc <file.kicad_sch>`
  - `kicad-cli pcb drc <file.kicad_pcb>`

Agent, bu repo disinda model host etmez; sadece mevcut toollarla calisir.

## 8) Basit Akis Ornegi

1. Agent board dosyasini gunceller.
2. Agent su olayi yazar:

```json
{
  "run_id": "run-led-001",
  "seq": 2,
  "stage": "circuit_done",
  "status": "ok",
  "producer": "claude",
  "timestamp_utc": "2026-02-25T16:00:00Z",
  "board": "led"
}
```

3. Program `./abd route --example led` calistirir.
4. Program sonuc olaylarini yazar:
   - `simulate_done`
   - `pcb_export_done`
   - `route_done`
   - `checks_done`
   - `gerber_done`

## 9) Guardrail'ler

- Stage sirasi bozulursa olay reddedilir (`seq` monotonic olmali).
- `fail` olayi geldiyse sonraki stage otomatik baslamaz.
- Her stage icin zaman asimi ve retry politikasi `meta` icinde tutulur.
- Ayni `run_id + seq` ciftine ikinci kez izin verilmez.

## 10) Neden Bu Model

- LLM baglantisi yok: vendor lock ve runtime karmasasi azalir.
- Claude Code ve Codex ayni protokolle calisir.
- Pipeline logic bizde kalir; agent sadece uretim ve handoff yapar.
- Sonradan webhook/queue eklense bile payload sozlesmesi degismez.

## 11) ABD Tool Kullanimi

`abd` ve `autoboard` ayni tooldur:

- `./abd status --example led`
- `./abd status --example led --pretty`
- `./abd status --example led --short`
- `./abd check --example led`
- `./abd route --example led`
- `./abd forward --example led`
- `./abd pull-forward --example led`
- `./abd rewind --example led`
- `./abd reset --example led`
- `./abd help`

Komutlar:

1. `status`: schema/layout stage hafizasini gosterir (`.autoboard/<example>.json`).
   - `--pretty`: insan okunur ozet
   - `--short`: tek satir ozet
2. `check`: `schema_check` + `layout_place` kontrollerini yapar.
3. `route`: once `check`, sonra layout pipeline (`layout_export -> layout_route -> layout_check -> layout_pack`) calistirir.
4. `forward` / `pull-forward`: route ile ayni akisi, stage ilerletme komutu olarak calistirir.
5. `rewind`: state'i sifirlayip tum akisi bastan sona tekrar calistirir.
6. `reset`: o board icin sadece stage hafizasini sifirlar.
7. `help`: komut dokumantasyonunu verir (`./abd help route` gibi).

ABD stage isimleri:

- Schema loop:
  - `schema_build`
  - `schema_check`
- Layout loop:
  - `layout_place`
  - `layout_export`
  - `layout_route`
  - `layout_check`
  - `layout_pack`

Onemli davranis:

- Son calismada hata varsa ve board degismediyse (`board_hash` ayni),
  `route` ayni hatayi tekrar dondurur, yeniden deneme yapmaz.
- LLM once dosyalari duzeltmeli, sonra `./abd route --example <board>` tekrar cagirmali.
