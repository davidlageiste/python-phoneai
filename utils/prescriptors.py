import requests
import string
import csv


def get_prescripteurs():
    url = "https://resultat-imagerie.riva56.fr/XaPriseRvGateway/Application/api/External/GetListePrescripteurs"

    lettres = string.ascii_uppercase
    comb = []

    for l1 in lettres:
        for l2 in lettres:
            for l3 in lettres:
                combinaison = l1 + l2 + l3
                comb.append(combinaison)

    presc = {}

    for c in comb:
        payload = {"nom": c, "prenom": "", "rpps": ""}
        try:
            response = requests.post(url, json=payload, verify=False)
            response.raise_for_status()
            data = response.json()
            print(c, data)
            for d in data.get("data"):
                if d["id"] not in presc.keys():
                    presc[d["id"]] = d
        except requests.RequestException as e:
            print("Request failed:", c, e)
    print(presc)

    colonnes = list(next(iter(presc.values())).keys())

    with open("presc.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=colonnes)
        writer.writeheader()
        for valeur in presc.values():
            writer.writerow(valeur)


get_prescripteurs()
