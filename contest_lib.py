"""
Společná knihovna pro Mikulášskou soutěž
Obsahuje sdílené datové struktury, konstanty a utility funkce
"""

import adif_io
import pathlib
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field


# ============================================================================
# KONSTANTY
# ============================================================================

# Časová tolerance pro validaci QSO (v minutách)
TIME_VALIDATION_TOLERANCE_MINUTES = 5

# Pravidla bodování
SCORING_RULES = {
    "base": 10,  # Základní body za QSO s POZEMSTAN
    "special_points": {
        "CERT": 20,      # Celkem 20 bodů za kontakt s CERT
        "MIKULAS": 30,   # Celkem 30 bodů za kontakt s MIKULAS
        "ANDEL": 50,     # Celkem 50 bodů za kontakt s ANDEL
    },
    "complete_set_bonus": 40,  # Bonus za kompletní sadu
    "minimum_counts": {
        "devils": 2,      # Minimálně 2× CERT
        "nikolas": 1,     # Minimálně 1× MIKULAS
        "angels": 1,      # Minimálně 1× ANDEL
    }
}


# ============================================================================
# ENUMERACE
# ============================================================================

class StationType(Enum):
    """Typy stanic v soutěži"""
    POZEMSTAN = "POZEMSTAN"
    CERT = "CERT"
    MIKULAS = "MIKULAS"
    ANDEL = "ANDEL"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def from_string(cls, value: str) -> 'StationType':
        """Převede string na StationType"""
        value_upper = value.upper() if value else ""
        try:
            return cls(value_upper)
        except ValueError:
            return cls.UNKNOWN


class ErrorType(Enum):
    """Typy validačních chyb"""
    HARD = "hard"      # Kritická chyba - QSO neplatné
    SOFT = "soft"      # Méně závažná - QSO platné, ale varování
    WARNING = "warning"  # Varování - informativní
    INFO = "info"      # Pouze informace


# ============================================================================
# DATOVÉ STRUKTURY
# ============================================================================

@dataclass
class ValidationResult:
    """Výsledek validace jednoho QSO"""
    error_type: ErrorType
    message: str

    def is_blocking(self) -> bool:
        """Vrátí True pokud chyba blokuje bodování"""
        return self.error_type == ErrorType.HARD


@dataclass
class QSORecord:
    """Reprezentuje jedno QSO se všemi relevantními poli"""

    # Základní info
    station: str           # Vlastní volací značka
    call: str             # Volací značka protistanice
    time: datetime        # Čas QSO

    # Přijatá data (od protistanice)
    their_gridsquare: str = ""
    their_name: str = ""

    # Odeslaná data (naše)
    my_gridsquare: str = ""
    my_operator: str = ""

    # Identity
    srx_string: Optional[str] = None  # Identita protistanice (co jsme přijali)
    stx_string: Optional[str] = None  # Naše identita (co jsme poslali)

    # Bodování
    points: int = 0
    bonus_points: int = 0
    is_valid_for_scoring: bool = True

    # Validace
    validation_errors: List[ValidationResult] = field(default_factory=list)
    is_matched: bool = False  # Má párované QSO v logu protistanice?
    matched_qso: Optional['QSORecord'] = None  # Reference na párované QSO

    # Původní ADIF data (pro případné další zpracování)
    raw_data: dict = field(default_factory=dict)

    def add_validation_error(self, error_type: ErrorType, message: str):
        """Přidá validační chybu"""
        self.validation_errors.append(ValidationResult(error_type, message))
        if error_type == ErrorType.HARD:
            self.is_valid_for_scoring = False

    def get_station_type(self) -> StationType:
        """Vrátí typ protistanice podle SRX_STRING"""
        if self.srx_string:
            return StationType.from_string(self.srx_string)
        return StationType.UNKNOWN

    def get_my_station_type(self) -> StationType:
        """Vrátí typ vlastní stanice podle STX_STRING"""
        if self.stx_string:
            return StationType.from_string(self.stx_string)
        return StationType.UNKNOWN

    def has_hard_errors(self) -> bool:
        """Vrátí True pokud QSO má kritické chyby"""
        return any(err.error_type == ErrorType.HARD for err in self.validation_errors)

    def has_soft_errors(self) -> bool:
        """Vrátí True pokud QSO má soft errory"""
        return any(err.error_type == ErrorType.SOFT for err in self.validation_errors)

    def __repr__(self):
        return f"QSO({self.station}->{self.call} @ {self.time})"


@dataclass
class StationScore:
    """Celkový výsledek stanice"""

    callsign: str
    station_type: StationType

    # QSO
    qsos: List[QSORecord] = field(default_factory=list)
    valid_qso_count: int = 0
    invalid_qso_count: int = 0

    # Body
    total_points: int = 0
    base_points: int = 0
    bonus_points: int = 0
    complete_set_bonus: int = 0

    # Počty speciálních kontaktů
    devils_count: int = 0      # CERT
    mikulas_count: int = 0     # MIKULAS
    angels_count: int = 0      # ANDEL
    has_complete_set: bool = False

    # Validační statistiky
    hard_errors_count: int = 0
    soft_errors_count: int = 0
    warnings_count: int = 0

    # Pořadí
    rank: int = 0

    def calculate_totals(self):
        """Přepočítá celkové hodnoty"""
        self.valid_qso_count = sum(1 for qso in self.qsos if qso.is_valid_for_scoring)
        self.invalid_qso_count = len(self.qsos) - self.valid_qso_count

        self.hard_errors_count = sum(1 for qso in self.qsos if qso.has_hard_errors())
        self.soft_errors_count = sum(1 for qso in self.qsos if qso.has_soft_errors())
        self.warnings_count = sum(
            1 for qso in self.qsos
            if any(err.error_type == ErrorType.WARNING for err in qso.validation_errors)
        )

        self.total_points = self.base_points + self.bonus_points + self.complete_set_bonus


# ============================================================================
# UTILITY FUNKCE
# ============================================================================

def normalize_callsign(callsign: str) -> str:
    """
    Normalizuje volací značku odstraněním /P a /M sufixů

    Args:
        callsign: Volací značka

    Returns:
        Normalizovaná volací značka (uppercase, bez /P a /M)
    """
    callsign = callsign.upper()
    # Odstranit /P nebo /M suffix
    if callsign.endswith("/P") or callsign.endswith("/M"):
        return callsign[:-2]
    return callsign


def load_adif_file(file_path: pathlib.Path) -> Tuple[Optional[str], List[QSORecord]]:
    """
    Načte ADIF soubor a vrátí volací značku stanice + seznam QSO

    Args:
        file_path: Cesta k ADIF souboru

    Returns:
        Tuple (station_callsign, list_of_qsos)
        station_callsign je None pokud se nepodařilo načíst
    """
    try:
        qsos_raw, _ = adif_io.read_from_file(str(file_path))

        if not qsos_raw:
            return None, []

        # Získat volací značku stanice z prvního QSO
        station_call = qsos_raw[0].get("STATION_CALLSIGN", "").upper()

        if not station_call:
            return None, []

        # Parsovat QSO
        qsos = []
        for qso_data in qsos_raw:
            qso = QSORecord(
                station=station_call,
                call=qso_data.get("CALL", "").upper(),
                time=adif_io.time_on(qso_data),
                their_gridsquare=qso_data.get("GRIDSQUARE", "").upper(),
                their_name=qso_data.get("NAME", "").upper(),
                my_gridsquare=qso_data.get("MY_GRIDSQUARE", "").upper(),
                my_operator=qso_data.get("OPERATOR", "").upper(),
                raw_data=qso_data
            )

            # Získat identity z SRX_STRING nebo COMMENT
            if "SRX_STRING" in qso_data:
                qso.srx_string = qso_data["SRX_STRING"].upper()
            elif "COMMENT" in qso_data:
                qso.srx_string = qso_data["COMMENT"].upper()

            # Získat odeslanou identitu
            if "STX_STRING" in qso_data:
                qso.stx_string = qso_data["STX_STRING"].upper()

            qsos.append(qso)

        return station_call, qsos

    except Exception as e:
        print(f"Error loading {file_path}: {e}")
        return None, []


def load_all_logs(directory: pathlib.Path) -> Dict[str, List[QSORecord]]:
    """
    Načte všechny ADIF soubory z adresáře

    Args:
        directory: Adresář s ADIF soubory

    Returns:
        Slovník {station_callsign: [QSORecord, ...]}
    """
    stations = {}

    # Najít všechny ADIF soubory
    adif_files = list(directory.glob("*.adif")) + list(directory.glob("*.adi"))

    for adif_file in adif_files:
        station_call, qsos = load_adif_file(adif_file)

        if station_call and qsos:
            if station_call in stations:
                print(f"  ⚠ {adif_file.name}: Duplicate log for {station_call}")
                continue

            stations[station_call] = qsos
            print(f"  ✓ {adif_file.name}: {station_call} - {len(qsos)} QSOs")
        elif not station_call:
            print(f"  ⚠ {adif_file.name}: No station callsign found")
        else:
            print(f"  ⚠ {adif_file.name}: No QSOs found")

    return stations


def get_all_qsos(stations: Dict[str, List[QSORecord]]) -> List[QSORecord]:
    """
    Vrátí všechna QSO ze všech stanic

    Args:
        stations: Slovník {station_callsign: [QSORecord, ...]}

    Returns:
        Seznam všech QSO
    """
    all_qsos = []
    for qsos in stations.values():
        all_qsos.extend(qsos)
    return all_qsos
