# REER database — o que melhora nos modelos do BRL/USD

Base usada: `REER_database_ver11Mar2026.xls` (séries do Brasil).

## 1) O que os testes mostram

- **REER 120 e REER 51 contam praticamente a mesma história de valuation**: correlação pós-1993 = **0.985**.
- O **último REER broad (120 parceiros)** do Brasil na planilha está em **76.07**, perto do **30.2º percentil** da história 1993–2026.
- O **último REER narrow (51 parceiros)** está em **73.81**, perto do **25.1º percentil** da história 1979–2026.
- Interpretação: o real está **fraco**, mas **não em extremo comparável a 2002**.

## 2) O que melhora de fato

### A. Usar REER como âncora estrutural principal
Half-life estimada da reversão do REER:
- REER 120: **43.0 meses**
- REER 51: **42.8 meses**

Isso reforça que REER é melhor para **horizonte de 2–5 anos** do que para call tática de 1–3 meses.

### B. Tornar o modelo não linear
Half-life por regime (REER 120):
- Cauda fraca: **11.4 meses**
- Cauda forte: **25.5 meses**
- Miolo: **68.9 meses**

A reversão é mais rápida nas caudas. Isso favorece **bandas/thresholds** em vez de uma única linha de fair value.

### C. Separar valuation de inflação relativa
O spread **log(REER) – log(NEER)** funciona como um estado lento de inflação relativa / competitividade de preços. Em amostra, ele ajuda a explicar parte do retorno futuro do REER, mas no teste recursivo ele é menos estável que o z-score puro do REER em horizontes curtos.

### D. Usar o spread entre broad e narrow como filtro de regime longo
O spread **REER120 – REER51** quase não ajuda em 12m, mas melhora os testes de **60 meses**. Isso sugere que o diferencial entre basket amplo e basket mais estreito carrega informação sobre **regime global** e composição dos parceiros.

## 3) Backtest resumido

Veja o arquivo CSV anexo para todos os números. Destaques:
- **REER120 z-score** bate a hipótese de “sem mudança” em todos os horizontes testados.
- O ganho fora da amostra foi de aproximadamente:
  - **12m:** 16%
  - **24m:** 26%
  - **36m:** 32%
  - **60m:** 32%
- Em **60m**, a especificação **REER120 + wedge de inflação + basket spread** sobe para cerca de **37%** de ganho fora da amostra contra “sem mudança”.

## 4) Recomendações práticas para o modelo institucional

### Stack recomendado
1. **Modelo núcleo (institucional):**
   - REER 120 em bandas históricas
   - percentil, z-score e faixa 10/25/50/75/90

2. **Filtro de regime de longo prazo:**
   - REER 51
   - spread REER120 – REER51

3. **Decomposição estrutural:**
   - NEER
   - REER − NEER (wedge de inflação relativa)

4. **Camada externa a adicionar depois:**
   - DXY
   - termos de troca / commodities
   - CDS / fiscal
   - produtividade relativa (via painel anual)

## 5) O que eu implementaria no app

- Gráfico principal: **REER 120 com bandas**
- Overlay opcional: **REER 51**
- Painel de decomposição:
  - valuation (REER)
  - nominal effective (NEER)
  - inflação relativa (REER−NEER)
- Laboratório:
  - slider de percentil do REER
  - toggle broad vs narrow
  - toggle regime global (via spread 120–51)
- Modelo de cenário 10 anos:
  - base estrutural = banda REER
  - overlay cíclico = DXY + commodities + CDS
  - overlay secular = produtividade

## 6) Conclusão

Sim. **Esses dados melhoram bastante os modelos**, mas principalmente por três caminhos:
- melhor âncora estrutural,
- melhor modelagem de bandas/extremos,
- melhor separação entre câmbio nominal e inflação relativa.

O que **não** melhora muito é adicionar mais linhas muito parecidas entre si. REER 120 e REER 51 são úteis juntos como **núcleo + filtro de regime**, não como dois “fair values” independentes.
