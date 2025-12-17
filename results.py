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
    if qsos_raw:
        # Check first QSO to determine station type
        first_qso = qsos_raw[0]
        if "STX_STRING" in first_qso:
            sent_identity = first_qso["STX_STRING"].upper()
            if sent_identity in ("CERT", "MIKULAS", "ANDEL"):
                special_station = True

    for qso in qsos_raw:
        print(adif_io.time_on(qso))
        print(qso["CALL"])
        print(qso["GRIDSQUARE"])

        # Get received identity from SRX_STRING, fallback to COMMENT
        received_identity = None
        if "SRX_STRING" in qso:
            received_identity = qso["SRX_STRING"].upper()
        elif "COMMENT" in qso:
            received_identity = qso["COMMENT"].upper()

        # Base points for QSO
        qso_points = 10

        if received_identity and not special_station:
            # Extra points based on identity
            if received_identity == "CERT":
                qso_points = 20
                devils += 1
            elif received_identity == "MIKULAS":
                qso_points = 30
                nicholashs += 1
            elif received_identity == "ANDEL":
                qso_points = 50
                angels += 1
            elif received_identity == "POZEMSTAN":
                # Normal station, keep base 10 points
                pass
            else:
                print("Unknown identity: ", received_identity)

        points += qso_points

    # Bonus points for complete set
    bonus = 0
    if devils >= DEVILS_MIN and nicholashs >= NICHOLASHS_MIN and angels >= ANGELS_MIN:
        bonus = 40
        points += bonus

    print("\n" + "="*50)
    print("RESULTS SUMMARY")
    print("="*50)
    print(f"Angels contacted:    {angels}")
    print(f"Nicholas contacted:  {nicholashs}")
    print(f"Devils contacted:    {devils}")
    print(f"Total QSOs:          {len(qsos_raw)}")
    if bonus > 0:
        print(f"\nBonus (complete set): +{bonus} points")
    print(f"\nTOTAL POINTS:        {points}")
    print("="*50)


if __name__ == "__main__":
    main()
