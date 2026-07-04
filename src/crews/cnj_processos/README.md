# CNJ Processos Judiciais

**Status:** ⏳ Pendente  
**Fase:** 3 — Motor Forense  
**Tabela destino:** `processos_judiciais`  
**Portal:** [CNJ — DataJud](https://www.cnj.jus.br/sistemas/datajud/)  
**Formato:** JSON API REST

## O que extrai

Processos judiciais de interesse forense via DataJud do CNJ

## Dependências

Nenhuma

## Agentes (a implementar)

- **Agent A** — Coletor: Fonte → Bronze
- **Agent B** — Normalizador: Bronze → Prata
- **Agent C** — Loader: Prata → PostgreSQL
