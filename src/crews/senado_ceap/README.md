# Senado CEAP

**Status:** ⏳ Pendente  
**Fase:** 1 — Dinheiro Direto  
**Tabela destino:** `senado_verbas_ceap`  
**Portal:** [Senado Federal — Dados Abertos](https://www12.senado.leg.br/transparencia/dados-abertos-transparencia/dados-abertos-ceaps)  
**Formato:** CSV anual

## O que extrai

Cota para Exercício da Atividade Parlamentar dos senadores

## Dependências

`politicos`, `fornecedores_rf`

## Agentes (a implementar)

- **Agent A** — Coletor: Fonte → Bronze
- **Agent B** — Normalizador: Bronze → Prata
- **Agent C** — Loader: Prata → PostgreSQL
