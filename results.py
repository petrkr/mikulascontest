import adif_io
import sys
import pathlib

DEVILS_MIN = 2
NICHOLASHS_MIN = 1
ANGELS_MIN = 1

def main():
    if len(sys.argv) != 2:
        print("Usage: python results.py <log.adi>")
        sys.exit(1)

    adif_file = sys.argv[1]
    
    if not pathlib.Path(adif_file).is_file():
        print("File not found: ", adif_file)
        sys.exit(1)


    qsos_raw, _ = adif_io.read_from_file(adif_file)

    points = 0
    devils = 0
    nicholashs = 0
    angels = 0

    # Determine if this is a special station (CERT/MIKULAS/ANDEL)
    # Special stations send something other than POZEMSTAN in STX_STRING
    special_station = False
    station_type = "POZEMSTAN"
    if qsos_raw:
        # Check first QSO to determine station type
        first_qso = qsos_raw[0]
        if "STX_STRING" in first_qso:
            sent_identity = first_qso["STX_STRING"].upper()
            if sent_identity in ("CERT", "MIKULAS", "ANDEL"):
                special_station = True
                station_type = sent_identity

    # Get station callsign
    station_callsign = qsos_raw[0].get("STATION_CALLSIGN", "???") if qsos_raw else "???"

    # Print header
    print("\n" + "="*70)
    print(f"STATION: {station_callsign}")
    if special_station:
        station_icon = {"CERT": "😈", "MIKULAS": "🎅", "ANDEL": "👼"}.get(station_type, "")
        print(f"TYPE: {station_icon} {station_type} (Special Station - 10 pts per QSO)")
    else:
        print(f"TYPE: POZEMSTAN (Normal Station)")
    print("="*70)
    print(f"{'TIME'} {'CALLSIGN':<10s} {'GRID':<8s} {'IDENTITY':<15s} {'POINTS'}")
    print("-"*70)

    for qso in qsos_raw:
        # Get received identity from SRX_STRING, fallback to COMMENT
        received_identity = None
        if "SRX_STRING" in qso:
            received_identity = qso["SRX_STRING"].upper()
        elif "COMMENT" in qso:
            received_identity = qso["COMMENT"].upper()

        # Base points for QSO
        qso_points = 10

        # Count special contacts (for statistics)
        if received_identity == "CERT":
            devils += 1
            if not special_station:
                qso_points = 20
        elif received_identity == "MIKULAS":
            nicholashs += 1
            if not special_station:
                qso_points = 30
        elif received_identity == "ANDEL":
            angels += 1
            if not special_station:
                qso_points = 50
        elif received_identity == "POZEMSTAN":
            # Normal station, keep base 10 points
            pass
        elif received_identity:
            print("Unknown identity: ", received_identity)

        points += qso_points

        # Print QSO details
        time = adif_io.time_on(qso).strftime("%H:%M")
        call = qso.get("CALL", "???")
        grid = qso.get("GRIDSQUARE", "??????")
        identity_str = received_identity if received_identity else "POZEMSTAN"

        # Format identity with color indicators
        if received_identity == "ANDEL":
            identity_display = "👼 ANDEL"
        elif received_identity == "MIKULAS":
            identity_display = "🎅 MIKULAS"
        elif received_identity == "CERT":
            identity_display = "😈 CERT"
        else:
            identity_display = "   POZEMSTAN"

        print(f"{time} {call:10s} {grid:8s} {identity_display:15s} +{qso_points:2d} pts")

    # Bonus points for complete set (only for normal stations)
    bonus = 0
    if not special_station and devils >= DEVILS_MIN and nicholashs >= NICHOLASHS_MIN and angels >= ANGELS_MIN:
        bonus = 40
        points += bonus

    print("\n" + "="*50)
    print("RESULTS SUMMARY")
    print("="*50)
    print(f"Angels contacted:    {angels}")
    print(f"Nicholas contacted:  {nicholashs}")
    print(f"Devils contacted:    {devils}")
    print(f"Total QSOs:          {len(qsos_raw)}")

    if not special_station:
        if bonus > 0:
            print(f"\nBonus (complete set): +{bonus} points")
        elif devils >= DEVILS_MIN and nicholashs >= NICHOLASHS_MIN and angels >= ANGELS_MIN:
            print(f"\nBonus eligible: Complete set achieved!")
    else:
        print(f"\nNote: Special stations get 10 points per QSO (no bonuses)")

    print(f"\nTOTAL POINTS:        {points}")
    print("="*50)


if __name__ == "__main__":
    main()
