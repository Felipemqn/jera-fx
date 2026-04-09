# JERA BRL/USD — Nota Técnica do Laboratório de Sensibilidade

## Objetivo
O laboratório traduz mudanças nas variáveis centrais do regime macro em deslocamentos transparentes da taxa justa de BRL/USD. Ele foi desenhado para complementar a banda estrutural do REER e o stack comparativo de modelos.

## Estrutura
O motor usa uma âncora estrutural em BRL/USD derivada do REER e aplica multiplicadores por variável:

justo(h) = âncora_REER × f_DXY(h) × f_CDS(h) × f_Carry(h) × f_Commodities(h) × f_Produtividade(h)

onde `h` é o horizonte analítico.

## Neutros usados no laboratório
- DXY / broad dollar: 100
- CDS Brasil 5Y: 140 bps
- Carry real: 9,5 pp
- Índice de commodities BR-linked: 100
- Produtividade relativa EUA vs BR: 0%

## Sensibilidades por horizonte
| Horizonte | DXY | CDS | Carry | Commodities | Produtividade |
|---|---:|---:|---:|---:|---:|
| 12 meses | 0,48 | 0,14 | 0,030 | 0,20 | 0,10 |
| 3 anos | 0,45 | 0,13 | 0,026 | 0,18 | 0,30 |
| 5 anos | 0,42 | 0,12 | 0,020 | 0,16 | 0,60 |
| 10 anos | 0,35 | 0,08 | 0,010 | 0,12 | 0,85 |

## Interpretação dos sinais
- DXY mais alto -> BRL/USD justo mais alto
- CDS mais alto -> BRL/USD justo mais alto
- Carry real mais alto -> BRL/USD justo mais baixo
- Commodities mais altas -> BRL/USD justo mais baixo
- Produtividade acumulada dos EUA acima do Brasil -> BRL/USD justo mais alto no horizonte longo

## Governança analítica
O laboratório é uma ferramenta de sensibilidade e decomposição. O benchmark estrutural do material continua sendo o REER nas bandas. O stack completo de modelos permanece como apêndice comparativo.
