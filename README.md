# Mikulášský závod - Vyhodnocovací systém

Systém pro vyhodnocení Mikulášského závodu 2025 podle pravidel z https://ok1kbt.fbmi.cvut.cz/pravidla-zavodu/

## Soubory

### `results.py`
Zobrazuje výsledky jednotlivé stanice z ADIF logu.

**Použití:**
```bash
python results.py <log.adif>
```

**Funkce:**
- Načte ADIF log stanice
- Detekuje typ stanice podle STX_STRING (POZEMSTAN / CERT / MIKULAS / ANDEL)
- Počítá body podle pravidel 2025:
  - Běžná stanice: ANDEL = 50b, MIKULAS = 30b, CERT = 20b, POZEMSTAN = 10b
  - Speciální stanice: vždy 10b za QSO (bez bonusů)
  - Bonus +40b za kompletní set (1 anděl + 1 Mikuláš + 2 čerti)
- Zobrazuje přehledný výpis všech QSO s body
- Vypisuje souhrn (počty kontaktů, celkové body)

**Pole v ADIF:**
- `SRX_STRING` - identita přijatá od protistanice (primární)
- `COMMENT` - fallback pro SRX_STRING (kompatibilita)
- `STX_STRING` - identita odeslaná (pro detekci speciální stanice)
- `GRIDSQUARE` - lokátor protistanice
- `MY_GRIDSQUARE` - můj lokátor
- `NAME` - jméno protistanice
- `OPERATOR` - jméno operátora

### `crosscheck.py`
Křížová kontrola všech odevzdaných logů pro detekci chyb.

**Použití:**
```bash
python crosscheck.py <adresář_s_logy>
```

**Funkce:**

#### Párování QSO
- QSO se párují **pouze podle callsignu** (A→B odpovídá B→A)
- Čas se nepoužívá pro párování, pouze pro validaci
- Duplicitní QSO: První je platné, další jsou soft error

#### Validace (Hard Errors)
- ✗ **Čas:** Rozdíl > 5 minut
  - Speciální: 55-65 min = "Timezone error (UTC/CET)"
- ✗ **Identita:** SRX_STRING ≠ STX_STRING (obousměrně)
- ✗ **Missing QSO:** QSO nenalezeno v logu protistanice (pokud log existuje)

#### Soft Errors
- ⚠ **Grid mismatch:** GRIDSQUARE ≠ MY_GRIDSQUARE (porovnává 6 znaků pokud oba mají, jinak 4)
- ⚠ **Duplicate QSO:** Více QSO mezi stejnou dvojicí stanic

#### Warnings
- ⓘ QSO se stanicemi, které **neodevzdaly log**

#### Info
- ℹ️ **Name differences:** Rozdíly ve jménech (zkratky vs plná jména)
  - Nepočítá se jako chyba, pouze informativní

#### Potvrzování stanic bez logu
- Stanice potvrzena **2+ jinými stanicemi** → QSO se počítají
- Stanice potvrzena pouze 1 stanicí → QSO se NEPOČÍTAJÍ (možné vymýšlení)

#### Report obsahuje
1. **Celkové statistiky:** Matched/unmatched QSO, počty chyb
2. **Chybějící logy:**
   - ✓ Potvrzené 2+ stanicemi (se seznamem)
   - ⚠ Nepotvrzené (s inline seznamem potvrzujících stanic)
3. **Chyby podle stanic:** Tabulka s počty hard/soft/warnings/info
4. **Detailní chyby (kategorizované):**
   - 🔴 TIMEZONE ERRORS (UTC/CET)
   - 🔴 TIME ERRORS (jiné)
   - 🔴 IDENTITY ERRORS (CERT/MIKULAS/ANDEL)
   - 🔴 MISSING QSOs (agregované podle stanice)
   - 🟡 DUPLICATE QSOs (s detailem všech QSO v páru včetně chyb)
   - 🟡 OTHER SOFT ERRORS (lokátory)
   - ℹ️ INFO - NAME DIFFERENCES (agregované podle stanice)

## Adresářová struktura

```
mikulascontest/
├── results.py           # Výpočet bodů jednotlivé stanice
├── crosscheck.py        # Křížová kontrola všech logů
├── log.sample.adif      # Starý vzorový soubor (nepoužívá se)
├── reports/             # Adresář s odevzdanými ADIF logy
│   ├── OK1XXX_*.adif
│   └── ...
└── venv/                # Python virtual environment
```

## Instalace

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# nebo
venv\Scripts\activate     # Windows

pip install adif_io
```

## Pravidla bodování 2025 (Etapa 3)

### Pro běžné stanice (POZEMSTAN):
- Spojení s andělem: **50 bodů**
- Spojení s Mikulášem: **30 bodů**
- Spojení s čertem: **20 bodů**
- Běžné spojení: **10 bodů**
- **Bonus**: +40 bodů za kompletní set (min. 1 anděl + 1 Mikuláš + 2 čerti)

### Pro speciální stanice (CERT/MIKULAS/ANDEL):
- **10 bodů** za každé QSO
- Žádné bonusy
- Vlastní kategorie "Nadpřirozené bytosti"

## Changelog

### Aktuální verze
- ✅ Podpora SRX_STRING/STX_STRING polí
- ✅ Detekce speciálních stanic
- ✅ Křížová kontrola s kategorizovanými chybami
- ✅ Detekce timezone problémů (UTC vs CET)
- ✅ Agregované výpisy (duplicity, missing QSO, jména)
- ✅ Potvrzování stanic bez logu (2+ pravidlo)
- ✅ Porovnání 6-znakových lokátorů

## Poznámky k implementaci

### Časová tolerance
- **Párování:** Pouze podle callsignu (čas se nepoužívá)
- **Validace:** Max 5 minut rozdíl
- **Timezone detekce:** 55-65 minut = UTC/CET problém

### Duplicity
- První QSO chronologicky je platné
- Další jsou soft error "Duplicate QSO"
- V reportu zobrazeny všechny s detaily

### Grid validation
- Pokud oba mají 6 znaků → porovná všech 6
- Pokud alespoň jeden má 4-5 znaků → porovná prvních 4
- Zachytí překlepy jako JN79FX vs JN79JV

### Jména
- Pouze informativní (INFO kategorie)
- Nepočítají se jako chyba
- Běžné variace: zkratky vs plná jména, přezdívky
