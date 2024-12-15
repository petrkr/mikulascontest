import adif_io

qsos_raw, _ = adif_io.read_from_file("log.sample.adi")

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
