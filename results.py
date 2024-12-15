import adif_io
import sys
import pathlib


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

    for qso in qsos_raw:
        print(adif_io.time_on(qso))
        print(qso["CALL"])
        print(qso["GRIDSQUARE"])

        points += 10 # 10 points per QSO
        if "COMMENT" in qso:
            # Extra points
            if qso["COMMENT"] in ("Cert"):
                points += 10
            elif qso["COMMENT"] in ("Mikulas"):
                points += 20
            elif qso["COMMENT"] in ("Andel"):
                points += 40
            else:
                print("Unknown comment: ", qso["COMMENT"])

    print("Total points: ", points)


if __name__ == "__main__":
    main()
