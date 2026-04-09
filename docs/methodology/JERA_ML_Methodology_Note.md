# JERA ML — nota metodológica

## O que era o Modelo Jera
Nos artefatos anteriores, o “Modelo Jera” aparecia como um modelo multivariado com DXY, carry real, CDS, commodities e volatilidade global, e era descrito como o menor RMSE do stack legado. O problema é que o método exato de estimação, a janela de amostra, a governança dos dados e o backtest não estavam documentados nos arquivos entregues.

## O que virou o Jera ML
O novo Jera ML substitui o *slot* do antigo Jera na leitura principal, mas não substitui o REER como benchmark estrutural. Ele é um meta-modelo regularizado, calibrado em frequência mensal, para combinar o benchmark REER com a informação do stack legado em um regime recente.

### Método
- classe do modelo: regressão ridge regularizada
- frequência: mensal
- amostra usada para treinamento final: Jan/2010–Dez/2023
- janela de validação: Jan/2021–Dez/2023
- holdout congelado: Jan/2024–Mar/2026
- penalização escolhida: alpha = 150

### Features finais
1. REER fair
2. Consenso legado ponderado
3. Carry fair
4. Dispersão cross-model
5. Range cross-model
6. Gap consenso vs REER

## Resultado do holdout congelado
- Jera ML: RMSE 0.2976 | MAE 0.2306 | R² 0.192
- Consenso legado: RMSE 0.6357
- Jera legado: RMSE 0.7661
- REER fair: RMSE 0.7857

## Leitura atual
No último ponto da amostra, o Jera ML gera fair value de **R$ 5.54**, contra spot de **R$ 5.30**. Isso equivale a um gap de **+4.6%** do fair sobre o spot.

## Recomendação de arquitetura
- **REER em bandas**: benchmark estrutural oficial
- **Jera ML**: modelo tático default e modelo a ser mostrado na capa
- **Jera legado**: referência histórica dentro do stack comparativo

Essa arquitetura é melhor do que uma substituição total. O REER continua sendo a linguagem institucional mais defensável para horizonte estrutural; o Jera ML melhora o comportamento do slot tático sem perder transparência.
