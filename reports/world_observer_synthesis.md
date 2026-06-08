# GeoNexus over World Observer synthesis

_GeoNexus **consumes World Observer's own scores** (instability, attention, narrative) as node attributes and adds the relational layer (co-occurrence graph, blocs, connectivity). No recomputation of attention; no LLM here._

## Most unstable countries (WO instability)

| Country | Instability | Class | Top driver |
| --- | --: | --- | --- |
| Iran | 90 | war | Active armed conflict in-country |
| Kuwait | 90 | war | Active armed conflict in-country |
| Lebanon | 90 | war | Active armed conflict in-country |
| Russia | 90 | war | Active armed conflict in-country |
| Ukraine | 90 | war | Active armed conflict in-country |
| Somalia | 88 | crisis | Deteriorating security signal |
| Yemen | 82 | crisis | Deteriorating security signal |
| Sudan | 77 | crisis | Deteriorating security signal |
| Dr Congo | 76 | crisis | Deteriorating public health: China's Medical Aid in DRC Ebola Outbreak |
| Syria | 76 | crisis | Deteriorating security signal |

## Highest-attention theatres (WO coverage share)

| Theatre | Share |
| --- | --: |
| gulf_iran | 0.63 |
| ukraine_russia | 0.35 |
| western_europe | 0.35 |
| israel_gaza | 0.29 |
| strait_hormuz | 0.29 |
| balkans_eastern_europe | 0.29 |
| korean_peninsula | 0.27 |
| israel_hezbollah_lebanon | 0.23 |

## Most connected countries (GeoNexus co-occurrence degree)

| Country | Degree | WO instability |
| --- | --: | --: |
| United States | 0.274 | 58 |
| Russia | 0.204 | 90 |
| Iran | 0.157 | 90 |
| China | 0.152 | 32 |
| France | 0.152 | 37 |
| United Kingdom | 0.139 | 34 |
| India | 0.126 | 38 |
| Japan | 0.122 | 20 |
| Brazil | 0.117 | 38 |
| Canada | 0.113 | 25 |

## Blocs (co-occurrence communities, by mean WO instability)

- **mean instability 55** — Iran, Kuwait, Lebanon, United States, Bahrain, Oman
- **mean instability 54** — Somalia, Yemen, Sudan, Syria, South Sudan, Mali
- **mean instability 41** — Venezuela, Bolivia, Nicaragua, Guatemala, Honduras, Colombia
- **mean instability 40** — Pakistan, Myanmar, North Korea, Bangladesh, Cambodia, Philippines
- **mean instability 38** — Russia, Ukraine, Afghanistan, Belarus, Estonia, Latvia
- **mean instability 34** — Kosovo, North Macedonia, Albania, Montenegro

## Attention momentum (WO 7-day share change)

| Theatre | First | Last | Δ |
| --- | --: | --: | --: |
| balkans_eastern_europe | 0.06 | 0.29 | +0.23 |
| ukraine_russia | 0.13 | 0.35 | +0.22 |
| korean_peninsula | 0.09 | 0.27 | +0.18 |
| israel_gaza | 0.12 | 0.29 | +0.17 |
| strait_hormuz | 0.14 | 0.29 | +0.15 |
| gulf_iran | 0.52 | 0.63 | +0.11 |
| taiwan_strait | 0.10 | 0.17 | +0.06 |
| japan_security | 0.03 | 0.09 | +0.05 |
