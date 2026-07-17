#!/usr/bin/env python3
"""Agent B — Normalizador TSE Bens Declarados: Bronze → Prata

NÃO resolve politico_id/pessoa_id (fica pro Agent C, set-based via SQL
por sq_candidato+ano — join determinístico, sem fuzzy, sem risco de
colisão de identidade)."""
import json, re, argparse, hashlib
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

try:
    from pydantic import BaseModel, field_validator
    from typing import Optional
except ImportError:
    print("❌ Instale pydantic: pip install pydantic"); raise

BASE_DIR   = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR   = BASE_DIR / "data/tse_bens_declarados"
BRONZE_DIR = DATA_DIR / "bronze"
PRATA_DIR  = DATA_DIR / "prata"
REJEIT_DIR = DATA_DIR / "rejeitados"
for d in (PRATA_DIR, REJEIT_DIR):
    d.mkdir(parents=True, exist_ok=True)


class BemDeclarado(BaseModel):
    prisma_id:    str
    sq_candidato: str
    ano_eleicao:  int
    uf:           str
    nr_ordem:     Optional[int] = None
    tipo_bem_cod: Optional[str] = None
    tipo_bem:     Optional[str] = None
    descricao:    Optional[str] = None
    valor:        Decimal

    @field_validator('valor')
    @classmethod
    def valor_valido(cls, v):
        if v < 0:
            raise ValueError('valor não pode ser negativo')
        if v > Decimal('10000000000'):  # R$ 10 bi — sanidade contra typo de vírgula
            raise ValueError(f'valor absurdo (>10bi): {v}')
        return v

    @field_validator('ano_eleicao')
    @classmethod
    def ano_valido(cls, v):
        if not (2006 <= v <= 2026):
            raise ValueError(f'ano_eleicao inválido: {v}')
        return v


def limpar(v) -> str | None:
    if not v: return None
    s = str(v).strip()
    return None if s in ('#NULO', '#NE', '#NE#', '-1', '-3', '-4', '', '#NULL!') else s


def parse_valor(v) -> Decimal | None:
    v = limpar(v)
    if not v: return None
    try:
        val = Decimal(v.replace('.', '').replace(',', '.'))
        return val if val >= 0 else None
    except InvalidOperation:
        return None


def parse_int(v) -> int | None:
    v = limpar(v)
    if not v: return None
    try:
        return int(v)
    except ValueError:
        return None


def col(row: dict, *nomes) -> str:
    for n in nomes:
        if n in row and str(row[n]).strip():
            return str(row[n]).strip()
    return ''


def processar_bronze(bronze_path: Path) -> None:
    print(f"📂 Bronze: {bronze_path.name}")
    with open(bronze_path, encoding='utf-8') as f:
        bronze = json.load(f)

    meta    = bronze.get('meta', {})
    ano     = int(meta.get('ano_eleicao', 0))
    uf      = meta.get('uf', '')
    records = bronze.get('records', [])
    print(f"📊 Total bruto: {len(records)}")

    validos, rejeitados = [], []
    for r in records:
        sq_cand   = col(r, 'SQ_CANDIDATO')
        ano_el_raw = col(r, 'ANO_ELEICAO')
        ano_el    = int(ano_el_raw) if ano_el_raw.isdigit() else ano
        uf_row    = col(r, 'SG_UF') or uf
        nr_ordem  = parse_int(col(r, 'NR_ORDEM_BEM_CANDIDATO', 'NR_ORDEM_CANDIDATO'))
        valor     = parse_valor(col(r, 'VR_BEM_CANDIDATO'))

        if not sq_cand:
            rejeitados.append({**r, 'motivo_rejeicao': 'sq_candidato vazio'}); continue
        if valor is None:
            rejeitados.append({**r, 'motivo_rejeicao': 'valor inválido/negativo'}); continue

        # prisma_id determinístico — inclui nr_ordem pois é a chave natural do TSE
        # (sq_candidato+ano+nr_ordem já vira UNIQUE na tabela; hash só como id estável)
        prisma_id = hashlib.md5(
            f"{sq_cand}_{ano_el}_{nr_ordem}".encode()
        ).hexdigest()

        norm = {
            'prisma_id':    prisma_id,
            'sq_candidato': sq_cand,
            'ano_eleicao':  ano_el,
            'uf':           uf_row,
            'nr_ordem':     nr_ordem,
            'tipo_bem_cod': limpar(col(r, 'CD_TIPO_BEM_CANDIDATO')),
            'tipo_bem':     limpar(col(r, 'DS_TIPO_BEM_CANDIDATO')),
            'descricao':    limpar(col(r, 'DS_BEM_CANDIDATO')),
            'valor':        str(valor),
        }

        try:
            BemDeclarado(**norm)
            validos.append(norm)
        except Exception as e:
            rejeitados.append({**norm, 'motivo_rejeicao': str(e)})

    stem = bronze_path.stem.replace('_bronze', '')
    prata_path = PRATA_DIR / f"{stem}_prata.json"
    with open(prata_path, 'w', encoding='utf-8') as f:
        json.dump({
            'meta': {
                'data_processamento': datetime.now(timezone.utc).isoformat(),
                'fonte_bronze':       bronze_path.name,
                'ano_eleicao':        ano,
                'uf':                 uf,
                'total_validos':      len(validos),
                'total_rejeitados':   len(rejeitados),
            },
            'records': validos,
        }, f, ensure_ascii=False)

    if rejeitados:
        rj = REJEIT_DIR / f"{stem}_rejeitados.json"
        with open(rj, 'w', encoding='utf-8') as f:
            json.dump(rejeitados, f, ensure_ascii=False)

    print(f"✅ Prata: {len(validos)} válidos → {prata_path.name}")
    print(f"⚠️  Rejeitados: {len(rejeitados)}")


def main():
    parser = argparse.ArgumentParser(description='Agent B — Normalizador TSE Bens Declarados')
    parser.add_argument('--bronze', help='Arquivo bronze específico (opcional)')
    parser.add_argument('--todos',  action='store_true', help='Processar todos os bronzes')
    args = parser.parse_args()

    if args.bronze:
        processar_bronze(Path(args.bronze))
    elif args.todos:
        bronzes = sorted(BRONZE_DIR.glob("*_bronze.json"))
        if not bronzes:
            print("❌ Nenhum Bronze encontrado"); return
        for b in bronzes:
            processar_bronze(b)
            print()
    else:
        bronzes = sorted(BRONZE_DIR.glob("*_bronze.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not bronzes:
            print("❌ Nenhum Bronze encontrado"); return
        processar_bronze(bronzes[0])

    print("\n✅ Agent B concluído.")

if __name__ == '__main__':
    main()
