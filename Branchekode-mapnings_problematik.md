# CH-03: DB25 vs. DB07 – IBM Danmark (eksempel på manglende branchekode mapning)

CVR-opslaget for **IBM DANMARK ApS (CVR 65305216)** returnerer branchekode
**622000** i klassifikationen **DB25**. Branchestatistikken for 2024 hentes fra
**ERHV1**, som anvender **DB07**.

Applikationen sender koden uændret til ERHV1. Koden findes ikke i tabellens
DB07-klassifikation, og StatBank afviser forespørgslen med **HTTP 400**:

> Kan ikke finde værdien: 622000 (BRANCHE07)

Virksomhedsoplysningerne returneres derfor med `status: "partial"`,
`industry_statistics: null` og advarslen `statistics_unavailable`.

En gyldig CVR-branchekode garanterer altså ikke, at den relevante branche kan
findes i ERHV1. Der findes ikke altid en entydig 1:1-mapping mellem DB25 og DB07;
selv ens kodetal garanterer ikke samme brancheafgrænsning. Korrekt berigelse
kræver en verificeret korrespondance mellem klassifikationerne.

Kilde: [Danmarks Statistik om DB25 og korrespondancen til DB07](https://www.dst.dk/da/Statistik/dokumentation/dansk-branchekode-er-gaeldende).
