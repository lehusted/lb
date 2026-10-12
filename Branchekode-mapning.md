# Mapning mellem DB25 og DB07

Virksomhedens aktuelle branchekode behandles som DB25. Historisk branchestatistik hentes fra ERHV1, som bruger DB07.

[app/industry.py](app/industry.py) vælger kildebrancher ud fra Danmarks Statistiks officielle relationer i [industry_correspondence.json](app/data/industry_correspondence.json):

- **1:1 (406 koder):** Statistikken hentes for den tilsvarende DB07-branche.
- **Komplet sammenlægning (15 koder):** Alle DB07-kildebrancher hentes i ét opslag, og deres tal summeres. Hver kildebranche skal overgå fuldt og udelukkende til den valgte DB25-branche. Eksempel: DB25 `622000` bruger DB07 `620200` og `620300`.
- **Delvis korrespondance (317 koder):** Mindst én kildebranche fordeles også til andre DB25-brancher. Statistikken udelades for at undgå misvisende tal.

Ukendte eller manglende branchekoder giver også et svar uden statistik. Virksomhedsdata bevares, og API'et returnerer `partial`, `industry_statistics: null` og en forklaring i `warnings`.

De anvendte kildekoder vises i `industry_codes_db07`. Mangler en nødvendig kildeværdi, bliver summen for det pågældende mål `null`; nul bevares som nul.

Tallene beskriver historiske DB07-brancher for det valgte år. Virksomhedsoplysningerne er aktuelle, og tallene er ikke en officiel historisk DB25-opgørelse.
