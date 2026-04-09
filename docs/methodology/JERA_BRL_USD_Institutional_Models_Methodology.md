# JERA BRL/USD Institutional Monitor — nota metodológica

## Estrutura da peça

A aplicação foi organizada em três camadas:

1. **benchmark oficial: REER em bandas**
2. **stack legado: todos os modelos**
3. **híbridos experimentais: REER × dólar global × produtividade**

A decisão metodológica foi manter o **REER em bandas** como âncora institucional principal e tratar o stack completo e os híbridos como camadas complementares.

## 1) Benchmark oficial: REER em bandas

- Série usada: **REER amplo do Brasil** (BIS via FRED)
- Conversão nominal: banda do REER convertida em faixa implícita de BRL/USD
- Leitura atual:
  - REER: **111,67**
  - mediana histórica: **121,64**
  - banda nominal: **R$ 4,11 – R$ 5,63**
  - justo mediano: **R$ 4,77**
- Interpretação: o BRL está **fraco, mas não em extremo de crise**

## 2) Stack legado: todos os modelos

O app recoloca o gráfico com todos os modelos do painel original:

- Big Mac (bruto)
- Big Mac (ajustado)
- IPCA-CPI PPP
- Balassa-Samuelson
- Termos de Troca
- ULC Industrial
- FEER (Conta Corrente)
- Carry-Stripped
- Modelo Jera

### Importante

A série histórica do stack legado é **heurística** e mantém a mesma lógica visual do material original, calibrada em **Q1/2026**. Ela é útil para:

- mostrar dispersão entre famílias de modelos;
- preservar comparabilidade com o painel anterior;
- apoiar a conversa sobre “linguagens de valuation”.

Ela **não** substitui o benchmark REER como âncora institucional.

## 3) Híbridos experimentais

Foram incluídos dois overlays combinados, em resposta direta ao briefing:

### Híbrido A — REER × dólar global

justo = justo_REER × (DXY / 100) ^ beta_dxy

Parâmetros-padrão no app:

- broad dollar / proxy DXY atual: **117,906**
- beta_dxy = **0,45**
- justo REER puro = **R$ 4,77**
- justo REER + dólar global = **R$ 5,14**

### Híbrido B — REER × dólar global × produtividade

justo = justo_REER × (DXY / 100) ^ beta_dxy × exp(beta_prod × gap_prod)

Onde:

- `gap_prod` = diferencial acumulado de produtividade EUA vs Brasil
- `beta_prod` = sensibilidade da camada de produtividade

### Governança metodológica

Esses híbridos aparecem como **overlays experimentais**, não como benchmark oficial. O motivo é simples: a camada de produtividade é anual e lenta; logo, faz mais sentido como teste de sensibilidade para horizonte longo do que como target tático.

## Cenários 2026–2036

Endpoints mantidos na peça:

- benigno: **R$ 5,40**
- base: **R$ 6,30**
- fiscal: **R$ 9,00**
- super-dólar: **R$ 10,30**

## Fontes

- Spot BRL/USD mensal e anual: **FRED / Board of Governors**
- PTAX: **Banco Central do Brasil**
- REER amplo do Brasil: **BIS via FRED**
- Broad dollar / proxy de DXY: **FRED**
- Focus, Selic, RPM: **Banco Central do Brasil**
- IPCA: **IBGE**
