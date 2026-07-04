# CGU Servidores Federais

**Status:** ⏳ Pendente  
**Fase:** 3 — Motor Forense  
**Tabela destino:** `servidores_federais`  
**Portal:** [Portal da Transparência — CGU](https://portaldatransparencia.gov.br/download-de-dados/servidores)  
**Formato:** CSV mensal

## O que extrai

Servidores públicos federais com remuneração e vínculos empregatícios

## Dependências

Nenhuma

## Agentes (a implementar)

- **Agent A** — Coletor: Fonte → Bronze
- **Agent B** — Normalizador: Bronze → Prata
- **Agent C** — Loader: Prata → PostgreSQL
