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

    special_station = False

    for qso in qsos_raw:
        print(adif_io.time_on(qso))
        print(qso["CALL"])
        print(qso["GRIDSQUARE"])

        points += 10 # 10 points per QSO
        if "COMMENT" in qso and not special_station:
            # Extra points
            if qso["COMMENT"].upper() in ("CERT"):
                points += 10
                devils += 1
            elif qso["COMMENT"].upper() in ("MIKULAS"):
                points += 20
                nicholashs += 1
            elif qso["COMMENT"].upper() in ("ANDEL"):
                points += 40
                angels += 1
            else:
                print("Unknown comment: ", qso["COMMENT"])

    # Extra points
    if devils >= DEVILS_MIN and nicholashs >= NICHOLASHS_MIN and angels >= ANGELS_MIN:
        points += 40

    print("Total points: ", points)


if __name__ == "__main__":
    main()
