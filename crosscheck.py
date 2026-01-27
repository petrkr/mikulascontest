import sys
import pathlib
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Set, Tuple

# Import shared library
from contest_lib import (
    QSORecord,
    ValidationResult,
    ErrorType,
    normalize_callsign,
    load_adif_file,
    TIME_VALIDATION_TOLERANCE_MINUTES
)


class CrossCheckResult:
    """Stores validation results for a QSO pair"""
    def __init__(self, qso1: QSORecord, qso2: QSORecord = None):
        self.qso1 = qso1
        self.qso2 = qso2
        self.matched = qso2 is not None
        self.hard_errors = []
        self.soft_errors = []
        self.warnings = []
        self.info = []  # Informational messages (like name differences)

    def add_hard_error(self, message: str):
        self.hard_errors.append(message)

    def add_soft_error(self, message: str):
        self.soft_errors.append(message)

    def add_warning(self, message: str):
        self.warnings.append(message)

    def add_info(self, message: str):
        self.info.append(message)

    def is_valid(self) -> bool:
        """QSO is valid if it has no hard errors"""
        return len(self.hard_errors) == 0


class ContestCrossCheck:
    """Main cross-check engine"""
    def __init__(self, reports_dir: str):
        self.reports_dir = pathlib.Path(reports_dir)
        self.stations = {}  # callsign -> list of QSOs
        self.all_qsos = []  # All QSO records
        self.results = []  # CrossCheckResults
        self.missing_logs = set()  # Callsigns without logs
        self.confirmed_stations = set()  # Stations confirmed by 2+ others

    def load_logs(self):
        """Load all ADIF files from directory"""
        print(f"Loading logs from {self.reports_dir}")

        adif_files = list(self.reports_dir.glob("*.adif")) + list(self.reports_dir.glob("*.adi"))

        for adif_file in adif_files:
            station_call, qsos = load_adif_file(adif_file)

            if station_call and qsos:
                if station_call in self.stations:
                    print(f"  ⚠ {adif_file.name}: Duplicate log for {station_call}")
                    continue

                self.stations[station_call] = qsos
                self.all_qsos.extend(qsos)
                print(f"  ✓ {adif_file.name}: {station_call} - {len(qsos)} QSOs")
            elif not station_call:
                print(f"  ⚠ {adif_file.name}: No station callsign found")
            else:
                print(f"  ⚠ {adif_file.name}: No QSOs found")

        print(f"\nLoaded {len(self.stations)} station logs with {len(self.all_qsos)} total QSOs")

    def find_matching_qsos(self, qso: QSORecord) -> List[QSORecord]:
        """Find all matching QSOs from the other station's log (by callsign only)"""
        # Normalize callsigns for matching (ignore /P and /M suffixes)
        normalized_call = normalize_callsign(qso.call)
        normalized_station = normalize_callsign(qso.station)

        # Find any station with matching normalized callsign
        other_qsos = None
        for station_call in self.stations:
            if normalize_callsign(station_call) == normalized_call:
                other_qsos = self.stations[station_call]
                break

        if other_qsos is None:
            return []

        # Find all QSOs with matching callsign (A->B matches B->A)
        # Match using normalized callsigns
        matches = []
        for other_qso in other_qsos:
            if normalize_callsign(other_qso.call) == normalized_station:
                matches.append(other_qso)

        return matches

    def validate_qso_pair(self, qso: QSORecord, match: QSORecord) -> CrossCheckResult:
        """Validate a matched QSO pair"""
        result = CrossCheckResult(qso, match)

        # Mark QSO as matched
        qso.is_matched = True
        qso.matched_qso = match

        # HARD CHECKS

        # 1. Check time difference
        time_diff = abs(qso.time - match.time)
        time_diff_minutes = time_diff.total_seconds() / 60

        if time_diff_minutes > TIME_VALIDATION_TOLERANCE_MINUTES:
            # Check if it's likely a timezone error (UTC vs CET = 60 minutes)
            if 55 <= time_diff_minutes <= 65:
                msg = (f"Timezone error (UTC/CET): {int(time_diff_minutes)} min difference "
                       f"({qso.station} at {qso.time.strftime('%H:%M')}, "
                       f"{match.station} at {match.time.strftime('%H:%M')})")
                result.add_hard_error(msg)
                # Časový error je symetrický - obě stanice dostanou error (není jasné kdo má špatně)
                qso.add_validation_error(ErrorType.HARD, msg)
                match.add_validation_error(ErrorType.HARD, msg)
            else:
                msg = (f"Time difference too large: {int(time_diff_minutes)} min "
                       f"(max {TIME_VALIDATION_TOLERANCE_MINUTES} min allowed) "
                       f"({qso.station} at {qso.time.strftime('%H:%M')}, "
                       f"{match.station} at {match.time.strftime('%H:%M')})")
                result.add_hard_error(msg)
                # Časový error je symetrický - obě stanice dostanou error (není jasné kdo má špatně)
                qso.add_validation_error(ErrorType.HARD, msg)
                match.add_validation_error(ErrorType.HARD, msg)

        # 2. Check identity consistency (what I received should match what they sent)
        if qso.srx_string and match.stx_string:
            if qso.srx_string != match.stx_string:
                msg = (f"Identity mismatch: {qso.station} received '{qso.srx_string}' "
                       f"but {match.station} sent '{match.stx_string}'")
                result.add_hard_error(msg)
                # Nevíme kdo udělal chybu (poslal špatně vs. zapsal špatně) → obě stanice dostanou error
                qso.add_validation_error(ErrorType.HARD, msg)
                match.add_validation_error(ErrorType.HARD, msg)

        # Check reverse identity consistency
        if match.srx_string and qso.stx_string:
            if match.srx_string != qso.stx_string:
                msg = (f"Identity mismatch: {match.station} received '{match.srx_string}' "
                       f"but {qso.station} sent '{qso.stx_string}'")
                result.add_hard_error(msg)
                # Nevíme kdo udělal chybu (poslal špatně vs. zapsal špatně) → obě stanice dostanou error
                qso.add_validation_error(ErrorType.HARD, msg)
                match.add_validation_error(ErrorType.HARD, msg)

        # SOFT CHECKS

        # Check grid square consistency
        # What station A received as GRIDSQUARE should match what station B sent as MY_GRIDSQUARE
        if qso.their_gridsquare and match.my_gridsquare:
            # Normalize grids: if both have 6 chars, compare all 6; otherwise compare first 4
            qso_grid = qso.their_gridsquare
            match_grid = match.my_gridsquare

            # If lengths differ, truncate to shortest
            min_len = min(len(qso_grid), len(match_grid))
            if min_len >= 6:
                # Both have 6+ chars, compare all 6
                qso_grid = qso_grid[:6]
                match_grid = match_grid[:6]
            elif min_len >= 4:
                # At least 4 chars, compare first 4
                qso_grid = qso_grid[:4]
                match_grid = match_grid[:4]

            if qso_grid != match_grid:
                msg = (f"Grid mismatch: {qso.station} received '{qso.their_gridsquare}' from {match.station} "
                       f"but {match.station} sent '{match.my_gridsquare}'")
                result.add_soft_error(msg)
                # Nevíme kdo udělal chybu (poslal špatně vs. zapsal špatně) → obě stanice dostanou error
                qso.add_validation_error(ErrorType.SOFT, msg)
                match.add_validation_error(ErrorType.SOFT, msg)

        # Check reverse grid consistency
        if match.their_gridsquare and qso.my_gridsquare:
            qso_grid = qso.my_gridsquare
            match_grid = match.their_gridsquare

            min_len = min(len(qso_grid), len(match_grid))
            if min_len >= 6:
                qso_grid = qso_grid[:6]
                match_grid = match_grid[:6]
            elif min_len >= 4:
                qso_grid = qso_grid[:4]
                match_grid = match_grid[:4]

            if qso_grid != match_grid:
                msg = (f"Grid mismatch: {match.station} received '{match.their_gridsquare}' from {qso.station} "
                       f"but {qso.station} sent '{qso.my_gridsquare}'")
                result.add_soft_error(msg)
                # Nevíme kdo udělal chybu (poslal špatně vs. zapsal špatně) → obě stanice dostanou error
                qso.add_validation_error(ErrorType.SOFT, msg)
                match.add_validation_error(ErrorType.SOFT, msg)

        # INFO - Name differences (informational only, not counted as errors)
        # What station A received as NAME should match what station B sent as OPERATOR
        if qso.their_name and match.my_operator:
            if qso.their_name != match.my_operator:
                result.add_info(
                    f"Name difference: {qso.station} received '{qso.their_name}' from {match.station} "
                    f"but {match.station} sent '{match.my_operator}'"
                )

        # Check reverse name consistency
        if match.their_name and qso.my_operator:
            if match.their_name != qso.my_operator:
                result.add_info(
                    f"Name difference: {match.station} received '{match.their_name}' from {qso.station} "
                    f"but {qso.station} sent '{qso.my_operator}'"
                )

        return result

    def cross_check_all(self):
        """Perform cross-check on all QSOs"""
        print("\n" + "="*70)
        print("CROSS-CHECKING QSOs")
        print("="*70)

        # Count how many stations confirmed each callsign
        callsign_confirmations = defaultdict(set)

        # Track which QSOs between each station pair
        # Key: (station1, station2), Value: list of QSOs from each
        pair_qsos = defaultdict(lambda: defaultdict(list))

        for station_call, qsos in self.stations.items():
            for qso in qsos:
                # Track which stations contacted this callsign (use normalized for confirmation)
                normalized_call = normalize_callsign(qso.call)
                callsign_confirmations[normalized_call].add(station_call)

                # Group QSOs by pair (use normalized callsigns)
                normalized_station = normalize_callsign(station_call)
                pair_key = tuple(sorted([normalized_station, normalized_call]))
                pair_qsos[pair_key][station_call].append(qso)

        # Now process each station pair
        for pair_key, qsos_by_station in pair_qsos.items():
            # pair_key contains normalized callsigns, but qsos_by_station has original callsigns as keys
            # We need to get all QSOs from both stations in this pair

            all_qsos_in_pair = []
            for station_call, station_qsos in qsos_by_station.items():
                all_qsos_in_pair.extend(station_qsos)

            if len(all_qsos_in_pair) == 0:
                continue

            # Split QSOs by which station they belong to (use normalized callsigns)
            qsos_from_1 = []
            qsos_from_2 = []

            for qso in all_qsos_in_pair:
                normalized_station = normalize_callsign(qso.station)
                if normalized_station == pair_key[0]:
                    qsos_from_1.append(qso)
                else:
                    qsos_from_2.append(qso)

            # Sort by time
            qsos_from_1 = sorted(qsos_from_1, key=lambda q: q.time)
            qsos_from_2 = sorted(qsos_from_2, key=lambda q: q.time)

            # Pair them up
            num_pairs = min(len(qsos_from_1), len(qsos_from_2))

            # Validate paired QSOs
            for i in range(num_pairs):
                result = self.validate_qso_pair(qsos_from_1[i], qsos_from_2[i])
                self.results.append(result)

            # Handle unpaired QSOs from station1
            for i in range(num_pairs, len(qsos_from_1)):
                qso = qsos_from_1[i]
                result = CrossCheckResult(qso, None)

                if i == 0:
                    # First QSO, no match found at all
                    # Check if any station with this normalized callsign submitted a log
                    normalized_call = normalize_callsign(qso.call)
                    has_log = any(normalize_callsign(s) == normalized_call for s in self.stations.keys())

                    if not has_log:
                        # No log submitted - check if confirmed by 2+ stations (will be set later)
                        msg = f"No log submitted by {qso.call}"
                        result.add_warning(msg)
                        qso.add_validation_error(ErrorType.WARNING, msg)
                        # Will be updated later based on confirmed_stations
                    else:
                        # Log exists but QSO not found
                        msg = f"QSO not found in {qso.call}'s log"
                        result.add_hard_error(msg)
                        qso.add_validation_error(ErrorType.HARD, msg)
                else:
                    # Duplicate QSO - soft error but still not valid for scoring
                    msg = f"Duplicate QSO with {qso.call} (not allowed)"
                    result.add_soft_error(msg)
                    qso.add_validation_error(ErrorType.SOFT, msg)
                    qso.is_valid_for_scoring = False  # Duplicates don't count

                self.results.append(result)

            # Handle unpaired QSOs from station2
            for i in range(num_pairs, len(qsos_from_2)):
                qso = qsos_from_2[i]
                result = CrossCheckResult(qso, None)

                if i == 0:
                    # First QSO, no match found at all
                    # Check if any station with this normalized callsign submitted a log
                    normalized_call = normalize_callsign(qso.call)
                    has_log = any(normalize_callsign(s) == normalized_call for s in self.stations.keys())

                    if not has_log:
                        # No log submitted - check if confirmed by 2+ stations (will be set later)
                        msg = f"No log submitted by {qso.call}"
                        result.add_warning(msg)
                        qso.add_validation_error(ErrorType.WARNING, msg)
                        # Will be updated later based on confirmed_stations
                    else:
                        # Log exists but QSO not found
                        msg = f"QSO not found in {qso.call}'s log"
                        result.add_hard_error(msg)
                        qso.add_validation_error(ErrorType.HARD, msg)
                else:
                    # Duplicate QSO - soft error but still not valid for scoring
                    msg = f"Duplicate QSO with {qso.call} (not allowed)"
                    result.add_soft_error(msg)
                    qso.add_validation_error(ErrorType.SOFT, msg)
                    qso.is_valid_for_scoring = False  # Duplicates don't count

                self.results.append(result)

        # Identify stations confirmed by 2+ other stations
        # Use normalized callsigns to avoid counting OK1PKR and OK1PKR/P as different
        for callsign, confirming_stations in callsign_confirmations.items():
            # Check if any station with this normalized callsign submitted a log
            has_log = any(normalize_callsign(s) == callsign for s in self.stations.keys())
            if not has_log and len(confirming_stations) >= 2:
                self.confirmed_stations.add(callsign)

        # Identify missing logs (contacted but didn't submit)
        # Use normalized callsigns
        all_contacted_normalized = set()
        for qso in self.all_qsos:
            all_contacted_normalized.add(normalize_callsign(qso.call))

        submitted_normalized = set(normalize_callsign(s) for s in self.stations.keys())
        self.missing_logs = all_contacted_normalized - submitted_normalized

        # Update is_valid_for_scoring for QSOs with missing logs
        # Based on whether the station is confirmed by 2+ others
        for qso in self.all_qsos:
            # Check if QSO has WARNING about missing log
            has_missing_log_warning = any(
                err.error_type == ErrorType.WARNING and "No log submitted" in err.message
                for err in qso.validation_errors
            )

            if has_missing_log_warning:
                normalized_call = normalize_callsign(qso.call)
                # Check if station is confirmed by 2+ others
                if normalized_call in self.confirmed_stations:
                    # Station confirmed by 2+ others - QSO is valid
                    qso.is_valid_for_scoring = True
                else:
                    # Station not confirmed - QSO is invalid
                    qso.is_valid_for_scoring = False
                    # Upgrade WARNING to HARD error
                    qso.add_validation_error(
                        ErrorType.HARD,
                        f"Station {qso.call} not confirmed by 2+ other stations"
                    )

        print(f"✓ Cross-checked {len(self.results)} QSOs")

    def generate_report(self):
        """Generate detailed report"""
        print("\n" + "="*70)
        print("CROSS-CHECK REPORT")
        print("="*70)

        # Statistics
        total_qsos = len(self.results)
        matched_qsos = sum(1 for r in self.results if r.matched)
        unmatched_qsos = total_qsos - matched_qsos
        hard_errors = sum(1 for r in self.results if r.hard_errors)
        soft_errors = sum(1 for r in self.results if r.soft_errors)
        warnings = sum(1 for r in self.results if r.warnings)
        info_messages = sum(1 for r in self.results if r.info)

        print(f"\nTotal QSOs:          {total_qsos}")
        print(f"Matched QSOs:        {matched_qsos} ({matched_qsos*100//total_qsos if total_qsos > 0 else 0}%)")
        print(f"Unmatched QSOs:      {unmatched_qsos}")
        print(f"Hard errors:         {hard_errors}")
        print(f"Soft errors:         {soft_errors}")
        print(f"Warnings:            {warnings}")
        print(f"Info (name diffs):   {info_messages}")

        # Missing logs
        print(f"\n{'='*70}")
        print(f"MISSING LOGS ({len(self.missing_logs)} stations)")
        print(f"{'='*70}")

        if self.missing_logs:
            confirmed_missing = self.missing_logs & self.confirmed_stations
            unconfirmed_missing = self.missing_logs - self.confirmed_stations

            if confirmed_missing:
                print(f"\n✓ Confirmed by 2+ stations ({len(confirmed_missing)}):")
                for call in sorted(confirmed_missing):
                    confirming = [s for s in self.stations.keys()
                                 if any(qso.call == call for qso in self.stations[s])]
                    print(f"  {call} - confirmed by {len(confirming)} stations")

            if unconfirmed_missing:
                print(f"\n⚠ Not confirmed by 2+ stations ({len(unconfirmed_missing)}):")

                # Show each station with list of who confirmed them
                for call in sorted(unconfirmed_missing):
                    confirming = [s for s in self.stations.keys()
                                 if any(qso.call == call for qso in self.stations[s])]
                    confirming_str = ", ".join(sorted(confirming))
                    print(f"  {call} - confirmed by: {confirming_str}")
        else:
            print("All contacted stations submitted logs!")

        # Errors by station
        print(f"\n{'='*70}")
        print("ERRORS BY STATION")
        print(f"{'='*70}")

        station_errors = defaultdict(lambda: {"hard": 0, "soft": 0, "warnings": 0, "info": 0})

        for result in self.results:
            station = result.qso1.station
            if result.hard_errors:
                station_errors[station]["hard"] += len(result.hard_errors)
            if result.soft_errors:
                station_errors[station]["soft"] += len(result.soft_errors)
            if result.warnings:
                station_errors[station]["warnings"] += len(result.warnings)
            if result.info:
                station_errors[station]["info"] += len(result.info)

        print(f"\n{'Station':<15s} {'Hard':<8s} {'Soft':<8s} {'Warnings':<10s} {'Info':<8s}")
        print("-"*70)
        for station in sorted(station_errors.keys()):
            errors = station_errors[station]
            print(f"{station:<15s} {errors['hard']:<8d} {errors['soft']:<8d} {errors['warnings']:<10d} {errors['info']:<8d}")

        # Detailed errors
        print(f"\n{'='*70}")
        print("DETAILED ERRORS")
        print(f"{'='*70}")

        # Categorize hard errors
        timezone_errors = []
        time_errors = []
        identity_errors = []
        missing_qso_errors = []

        for result in self.results:
            if result.hard_errors:
                for error in result.hard_errors:
                    if "Timezone error" in error:
                        timezone_errors.append((result, error))
                    elif "Time difference" in error:
                        time_errors.append((result, error))
                    elif "Identity mismatch" in error:
                        identity_errors.append((result, error))
                    elif "QSO not found" in error:
                        missing_qso_errors.append((result, error))

        # Show timezone errors
        if timezone_errors:
            print(f"\n🔴 TIMEZONE ERRORS (UTC/CET) ({len(timezone_errors)}):")
            print("These logs likely used different time zones (UTC vs CET)")
            for result, error in timezone_errors[:10]:
                print(f"\n  {result.qso1.station} -> {result.qso1.call}")
                print(f"    ✗ {error}")
            if len(timezone_errors) > 10:
                print(f"\n  ... and {len(timezone_errors) - 10} more timezone errors")

        # Show time errors
        if time_errors:
            print(f"\n🔴 TIME ERRORS ({len(time_errors)}):")
            for result, error in time_errors[:10]:
                print(f"\n  {result.qso1.station} -> {result.qso1.call}")
                print(f"    ✗ {error}")
            if len(time_errors) > 10:
                print(f"\n  ... and {len(time_errors) - 10} more time errors")

        # Show identity errors
        if identity_errors:
            print(f"\n🔴 IDENTITY ERRORS ({len(identity_errors)}):")
            for result, error in identity_errors[:10]:
                print(f"\n  {result.qso1.station} -> {result.qso1.call} @ {result.qso1.time.strftime('%H:%M')}")
                print(f"    ✗ {error}")
            if len(identity_errors) > 10:
                print(f"\n  ... and {len(identity_errors) - 10} more identity errors")

        # Show missing QSO errors - aggregated by station
        if missing_qso_errors:
            print(f"\n🔴 MISSING QSOs ({len(missing_qso_errors)}):")
            print("QSOs that station claims but are not in the other station's log")

            # Group by station
            by_station = defaultdict(list)
            for result, error in missing_qso_errors:
                by_station[result.qso1.station].append((result, error))

            # Show aggregated
            shown = 0
            for station in sorted(by_station.keys()):
                if shown >= 15:  # Limit to 15 stations
                    remaining_stations = len(by_station) - shown
                    remaining_qsos = sum(len(by_station[s]) for s in list(by_station.keys())[shown:])
                    print(f"\n  ... and {remaining_qsos} more missing QSOs from {remaining_stations} more stations")
                    break

                errors = by_station[station]
                print(f"\n  {station} ({len(errors)} missing QSO{'s' if len(errors) > 1 else ''}):")

                for result, error in errors[:5]:  # Show first 5 per station
                    print(f"    -> {result.qso1.call} @ {result.qso1.time.strftime('%H:%M')}")

                if len(errors) > 5:
                    print(f"    ... and {len(errors) - 5} more")

                shown += 1

        # Soft errors - separate duplicates from other errors
        duplicate_results = []
        other_soft_errors = []

        for result in self.results:
            if result.soft_errors:
                has_duplicate = any("Duplicate QSO" in err for err in result.soft_errors)
                if has_duplicate:
                    duplicate_results.append(result)
                else:
                    other_soft_errors.append(result)

        # Show duplicates first with detailed info
        if duplicate_results:
            print(f"\n🟡 DUPLICATE QSOs ({len(duplicate_results)}):")
            print("Multiple QSOs between same stations (only first one is valid)")

            # Group duplicates by station pair
            duplicate_pairs = defaultdict(list)
            for result in duplicate_results:
                pair_key = tuple(sorted([result.qso1.station, result.qso1.call]))
                duplicate_pairs[pair_key].append(result)

            for pair_key, dup_list in sorted(duplicate_pairs.items()):
                station1, station2 = pair_key
                print(f"\n  === {station1} <-> {station2} ===")

                # Get all QSOs between this pair (including the valid one)
                all_qsos_pair = []
                for res in self.results:
                    qso_pair = tuple(sorted([res.qso1.station, res.qso1.call]))
                    if qso_pair == pair_key:
                        all_qsos_pair.append(res)

                # Sort by time and show all
                all_qsos_pair.sort(key=lambda r: r.qso1.time)
                for i, res in enumerate(all_qsos_pair):
                    status = "✓ VALID" if i == 0 else "✗ DUPLICATE"
                    qso = res.qso1
                    match_info = ""
                    if res.qso2:
                        match_info = f" <-> {res.qso2.station} @ {res.qso2.time.strftime('%H:%M')}"
                    else:
                        match_info = " (no match in their log)"

                    print(f"    {status}: {qso.station} @ {qso.time.strftime('%H:%M')}{match_info}")
                    print(f"           Grid: {qso.their_gridsquare}, Name: {qso.their_name}, Identity: {qso.srx_string or 'N/A'}")

                    # Show any errors for this QSO
                    if res.hard_errors or res.soft_errors:
                        for err in res.hard_errors:
                            print(f"           ✗ HARD: {err}")
                        for err in res.soft_errors:
                            if "Duplicate" not in err:  # Don't show duplicate error again
                                print(f"           ⚠ SOFT: {err}")

        # Show other soft errors
        if other_soft_errors:
            print(f"\n🟡 OTHER SOFT ERRORS ({len(other_soft_errors)}):")
            for result in other_soft_errors[:20]:
                print(f"\n  {result.qso1.station} -> {result.qso1.call} @ {result.qso1.time.strftime('%H:%M')}")
                for error in result.soft_errors:
                    print(f"    ⚠ {error}")

            if len(other_soft_errors) > 20:
                print(f"\n  ... and {len(other_soft_errors) - 20} more soft errors")

        # Info messages (name differences) - aggregated by station
        info_results = [r for r in self.results if r.info]
        if info_results:
            total_info_messages = sum(len(r.info) for r in info_results)
            print(f"\nℹ️  INFO - NAME DIFFERENCES ({len(info_results)} QSOs, {total_info_messages} differences):")

            # Group by station
            by_station = defaultdict(list)
            for result in info_results:
                by_station[result.qso1.station].append(result)

            # Show aggregated
            shown = 0
            for station in sorted(by_station.keys()):
                if shown >= 10:  # Limit to 10 stations
                    remaining_stations = len(by_station) - shown
                    remaining_diffs = sum(sum(len(r.info) for r in by_station[s]) for s in list(by_station.keys())[shown:])
                    print(f"\n  ... and {remaining_diffs} more name differences from {remaining_stations} more stations")
                    break

                results = by_station[station]
                total_diffs = sum(len(r.info) for r in results)
                print(f"\n  {station} ({total_diffs} name difference{'s' if total_diffs > 1 else ''}):")

                shown_count = 0
                for result in results:
                    if shown_count >= 5:  # Show first 5 differences per station
                        remaining = total_diffs - shown_count
                        if remaining > 0:
                            print(f"    ... and {remaining} more")
                        break

                    for info in result.info:
                        if shown_count >= 5:
                            break
                        # Extract just the key info from the message
                        print(f"    {result.qso1.call}: {info.split(':', 1)[1].strip() if ':' in info else info}")
                        shown_count += 1

                shown += 1

    def run(self):
        """Run the complete cross-check process"""
        self.load_logs()
        if not self.stations:
            print("No logs loaded. Exiting.")
            return

        self.cross_check_all()
        self.generate_report()


def main():
    if len(sys.argv) != 2:
        print("Usage: python crosscheck.py <reports_directory>")
        sys.exit(1)

    reports_dir = sys.argv[1]

    if not pathlib.Path(reports_dir).is_dir():
        print(f"Directory not found: {reports_dir}")
        sys.exit(1)

    checker = ContestCrossCheck(reports_dir)
    checker.run()


if __name__ == "__main__":
    main()
