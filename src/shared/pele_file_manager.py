#!/usr/bin/env python3
"""
📁 PELE FILE MANAGER v1.0 — GERENCIAMENTO ENTERPRISE DE ARQUIVOS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESPONSABILIDADE:
  Evitar arquivos lixo gerados múltiplas vezes.
  Controlar versões Bronze/Prata/Ouro por ANO + TIPO.
  Manifesto persistido em data/saida/pele/.manifest.json

FUNCIONALIDADES:
  - skip_se_existir()    → compara hash SHA-256 antes de reprocessar
  - registrar()          → grava metadados no manifesto após cada fase
  - limpar_orfaos()      → remove arquivos sem entrada no manifesto
  - relatorio_saude()    → imprime estado de todos os anos/tipos
  - purgar_ano()         → apaga todos os arquivos de um ano (rollback)
  - exportar_catalogo()  → gera catalogo.json com todo o inventário

USO NOS AGENTES:
    from src.shared.pele_file_manager import PeleFileManager
    fm = PeleFileManager()
    if fm.skip_se_existir("B", "estadual", "2024"):
        print("Prata 2024 estadual já existe e não mudou. Pulando.")
        sys.exit(0)
    # ... processa ...
    fm.registrar("B", "estadual", "2024", path_saida, n_records)
"""

import json
import hashlib
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, List

VERSAO = "pele_fm_v1.0"

# ── Caminhos canônicos ────────────────────────────────────────────────────────
# Pode ser instanciado de qualquer lugar; calcula BASE_DIR a partir deste arquivo
_THIS = Path(__file__).resolve()                          # src/shared/pele_file_manager.py
_SRC  = _THIS.parent.parent                               # src/
_ROOT = _SRC.parent                                        # raiz do projeto

DATA_DIR = _ROOT / "data" / "saida" / "pele"

FASES_PATH = {
    "A1": DATA_DIR / "bronze",
    "A2": DATA_DIR / "bronze",
    "B":  DATA_DIR / "prata",
    "C":  DATA_DIR / "ouro",
    "D":  None,   # banco — sem arquivo local
}

FASES_NOME_ARQUIVO = {
    "A1": "pele_estadual_{ano}_bronze.json",
    "A2": "pele_federal_{ano}_bronze.json",
    "B":  "pele_{tipo}_{ano}_prata.json",
    "C":  "pele_{tipo}_{ano}_ouro.json",
}

MANIFESTO_PATH = DATA_DIR / ".manifest.json"


# ── Helpers ──────────────────────────────────────────────────────────────────
def _sha256(path: Path) -> str:
    """Hash SHA-256 do conteúdo do arquivo."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cor(txt, c): return f"\033[{c}m{txt}\033[0m"
def _ok(t):   print(_cor(f"📁 FM ✅ {t}", "92"))
def _info(t): print(_cor(f"📁 FM 🔹 {t}", "96"))
def _warn(t): print(_cor(f"📁 FM ⚠️  {t}", "93"))
def _erro(t): print(_cor(f"📁 FM ❌ {t}", "91"))


# ── Classe Principal ──────────────────────────────────────────────────────────
class PeleFileManager:
    """
    Gerenciador enterprise de arquivos da pipeline Pelé.
    Mantém manifesto persistido e evita reprocessamento desnecessário.
    """

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = Path(data_dir) if data_dir else DATA_DIR
        self.manifesto_path = self.data_dir / ".manifest.json"
        self._manifesto: Dict = self._carregar_manifesto()

    # ── Manifesto ─────────────────────────────────────────────────────────────
    def _carregar_manifesto(self) -> Dict:
        if self.manifesto_path.exists():
            try:
                with open(self.manifesto_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                _warn("Manifesto corrompido — reiniciando manifesto limpo.")
        return {"versao": VERSAO, "criado_em": _agora(), "entradas": {}}

    def _salvar_manifesto(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with open(self.manifesto_path, "w", encoding="utf-8") as f:
            json.dump(self._manifesto, f, ensure_ascii=False, indent=2)

    def _chave(self, fase: str, tipo: str, ano: str) -> str:
        """Chave única do manifesto: fase|tipo|ano"""
        # Normaliza fase A1/A2 para 'bronze_estadual'/'bronze_federal'
        tipo_norm = tipo
        if fase == "A1": tipo_norm = "estadual"
        if fase == "A2": tipo_norm = "federal"
        return f"{fase}|{tipo_norm}|{ano}"

    # ── Path do arquivo de saída ──────────────────────────────────────────────
    def path_saida(self, fase: str, tipo: str, ano: str) -> Optional[Path]:
        """Retorna Path canônico do arquivo de saída para fase/tipo/ano."""
        template = FASES_NOME_ARQUIVO.get(fase)
        if not template:
            return None
        pasta = FASES_PATH.get(fase)
        if not pasta:
            return None
        nome = template.format(tipo=tipo, ano=ano)
        return pasta / nome

    # ── Skip inteligente (por hash) ───────────────────────────────────────────
    def skip_se_existir(
        self,
        fase: str,
        tipo: str,
        ano: str,
        hash_input: Optional[str] = None,
    ) -> bool:
        """
        Retorna True se o arquivo de saída já existe E não houve mudança.
        Compara:
          1. Existência do arquivo
          2. Hash SHA-256 do arquivo de saída (integridade)
          3. hash_input (hash do CSV de entrada) se fornecido — detecta CSV novo
        """
        p = self.path_saida(fase, tipo, ano)
        if p is None or not p.exists():
            return False

        chave = self._chave(fase, tipo, ano)
        entrada = self._manifesto["entradas"].get(chave, {})

        # Hash do arquivo de saída atual
        hash_atual = _sha256(p)

        # Se não há entrada no manifesto, registra e continua (não pula)
        if not entrada:
            _warn(f"Arquivo existe mas não está no manifesto: {p.name}. Reprocessando.")
            return False

        # Verifica integridade do arquivo de saída
        if entrada.get("hash_saida") and entrada["hash_saida"] != hash_atual:
            _warn(f"Hash divergente em {p.name}. Arquivo pode ter sido editado. Reprocessando.")
            return False

        # Verifica se o CSV de entrada mudou
        if hash_input and entrada.get("hash_input") and entrada["hash_input"] != hash_input:
            _info(f"CSV de entrada mudou para {fase}|{tipo}|{ano}. Reprocessando.")
            return False

        n = entrada.get("n_records", "?")
        _info(f"Skip ✓  {fase}|{tipo}|{ano} → {p.name} ({n} records, hash OK)")
        return True

    # ── Registro após processamento ───────────────────────────────────────────
    def registrar(
        self,
        fase: str,
        tipo: str,
        ano: str,
        path_saida: Path,
        n_records: int,
        hash_input: Optional[str] = None,
        extra: Optional[Dict] = None,
    ):
        """
        Registra um arquivo processado no manifesto.
        Chame SEMPRE após salvar o arquivo de saída.
        """
        chave = self._chave(fase, tipo, ano)
        entrada = {
            "fase":         fase,
            "tipo":         tipo,
            "ano":          str(ano),
            "arquivo":      path_saida.name,
            "path_relativo": str(path_saida.relative_to(self.data_dir.parent.parent.parent)
                                  if path_saida.is_absolute() else path_saida),
            "n_records":    n_records,
            "hash_saida":   _sha256(path_saida) if path_saida.exists() else None,
            "hash_input":   hash_input,
            "registrado_em": _agora(),
            **(extra or {}),
        }
        self._manifesto["entradas"][chave] = entrada
        self._manifesto["atualizado_em"] = _agora()
        self._salvar_manifesto()
        _ok(f"Registrado: {fase}|{tipo}|{ano} → {path_saida.name} ({n_records} records)")

    # ── Limpeza de órfãos ─────────────────────────────────────────────────────
    def limpar_orfaos(self, dry_run: bool = True) -> List[Path]:
        """
        Remove arquivos Bronze/Prata/Ouro que não estão no manifesto.
        dry_run=True apenas lista sem deletar.
        """
        arquivos_validos = set()
        for entrada in self._manifesto["entradas"].values():
            arquivos_validos.add(entrada["arquivo"])

        orfaos = []
        for pasta_nome in ["bronze", "prata", "ouro"]:
            pasta = self.data_dir / pasta_nome
            if not pasta.exists():
                continue
            for f in pasta.iterdir():
                if f.name.startswith("."):
                    continue
                if f.name not in arquivos_validos:
                    orfaos.append(f)

        if not orfaos:
            _ok("Nenhum arquivo órfão encontrado. Pipeline limpo!")
            return []

        _warn(f"{len(orfaos)} arquivo(s) órfão(s) encontrado(s):")
        for f in orfaos:
            print(f"   📄 {f.relative_to(self.data_dir)}")
            if not dry_run:
                f.unlink()
                print(f"      → DELETADO")

        if dry_run:
            _warn("dry_run=True: nenhum arquivo deletado. Use dry_run=False para limpar.")
        else:
            _ok(f"{len(orfaos)} arquivo(s) órfão(s) removido(s).")

        return orfaos

    # ── Purgar um ano inteiro ─────────────────────────────────────────────────
    def purgar_ano(self, ano: str, tipo: str = "ambos", dry_run: bool = True) -> int:
        """
        Remove todos os arquivos de um ano específico do manifesto e disco.
        Útil para rollback: re-rodar do zero para um ano sem lixo.
        """
        chaves_remover = []
        for chave, entrada in self._manifesto["entradas"].items():
            if entrada["ano"] == str(ano):
                if tipo == "ambos" or entrada["tipo"] == tipo:
                    chaves_remover.append((chave, entrada))

        if not chaves_remover:
            _info(f"Nenhuma entrada no manifesto para ano={ano} tipo={tipo}.")
            return 0

        _warn(f"Purgando {len(chaves_remover)} entrada(s) para ano={ano} tipo={tipo}:")
        removidos = 0
        for chave, entrada in chaves_remover:
            for pasta in ["bronze", "prata", "ouro"]:
                p = self.data_dir / pasta / entrada["arquivo"]
                if p.exists():
                    print(f"   🗑️  {p.name}")
                    if not dry_run:
                        p.unlink()
                        removidos += 1
            if not dry_run:
                del self._manifesto["entradas"][chave]

        if not dry_run:
            self._salvar_manifesto()
            _ok(f"{removidos} arquivo(s) purgado(s) para ano={ano}.")
        else:
            _warn("dry_run=True: nada deletado.")

        return len(chaves_remover)

    # ── Relatório de Saúde ────────────────────────────────────────────────────
    def relatorio_saude(self):
        """
        Imprime tabela com estado de todos os anos/tipos no manifesto.
        Verifica integridade dos arquivos em disco (hash).
        """
        entradas = self._manifesto.get("entradas", {})
        if not entradas:
            _warn("Manifesto vazio. Nenhum arquivo registrado ainda.")
            return

        C_HEADER = "\033[1m\033[97m"
        C_OK     = "\033[92m"
        C_ERR    = "\033[91m"
        C_WARN   = "\033[93m"
        C_END    = "\033[0m"
        C_CYAN   = "\033[96m"

        width = 90
        print(f"\n{C_HEADER}{'─'*width}{C_END}")
        print(f"{C_HEADER}  📁 SAÚDE DO PIPELINE PELÉ — {len(entradas)} arquivo(s) registrado(s){C_END}")
        print(f"{C_HEADER}{'─'*width}{C_END}")
        fmt = f"  {{:<6}}{{:<12}}{{:<8}}{{:<8}}{{:<12}}{{:<20}}  {{}}"
        print(f"{C_HEADER}{fmt.format('FASE','ANO','TIPO','RECDS','STATUS','ARQUIVO','REGISTRADO')}{C_END}")
        print(f"{C_HEADER}{'─'*width}{C_END}")

        anos = sorted(set(e["ano"] for e in entradas.values()), reverse=True)
        for ano in anos:
            for chave, e in sorted(entradas.items()):
                if e["ano"] != ano:
                    continue
                p_nome = e["arquivo"]
                fase   = e["fase"]
                tipo   = e["tipo"]
                n      = e.get("n_records", "?")
                reg_em = e.get("registrado_em", "")[:16].replace("T", " ")

                # Verifica integridade
                found_path = None
                for pasta in ["bronze", "prata", "ouro"]:
                    p = self.data_dir / pasta / p_nome
                    if p.exists():
                        found_path = p
                        break

                if not found_path:
                    status = f"{C_ERR}AUSENTE ❌{C_END}"
                elif e.get("hash_saida") and _sha256(found_path) != e["hash_saida"]:
                    status = f"{C_WARN}HASH ≠ ⚠️{C_END}"
                else:
                    status = f"{C_OK}OK ✅{C_END}"

                print(fmt.format(fase, ano, tipo[:6], str(n), "", p_nome[:18], reg_em))
                print(f"  {' '*46}{status}")

        print(f"{C_HEADER}{'─'*width}{C_END}\n")

    # ── Exportar Catálogo ─────────────────────────────────────────────────────
    def exportar_catalogo(self, destino: Optional[Path] = None) -> Path:
        """
        Exporta catálogo completo em JSON para auditoria externa.
        Inclui hash, records, timestamps e status de integridade.
        """
        catalogo = {
            "gerado_em":     _agora(),
            "versao_fm":     VERSAO,
            "total_arquivos": len(self._manifesto["entradas"]),
            "entradas":      self._manifesto["entradas"],
        }
        dest = destino or (self.data_dir / "catalogo_pipeline.json")
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(catalogo, f, ensure_ascii=False, indent=2)
        _ok(f"Catálogo exportado: {dest}")
        return dest

    # ── Hash de pasta de CSVs de entrada ─────────────────────────────────────
    @staticmethod
    def hash_pasta_csv(pasta: Path) -> Optional[str]:
        """
        Gera hash SHA-256 combinado de todos os CSVs de uma pasta.
        Permite detectar se novos CSVs foram adicionados/modificados.
        """
        pasta = Path(pasta)
        if not pasta.exists():
            return None
        csvs = sorted(pasta.glob("*.csv")) + sorted(pasta.glob("*.CSV"))
        if not csvs:
            return None
        combined = hashlib.sha256()
        for csv in csvs:
            combined.update(csv.name.encode())
            combined.update(_sha256(csv).encode())
        return combined.hexdigest()


# ── CLI standalone ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Pelé File Manager — CLI")
    ap.add_argument("cmd", choices=["saude", "orfaos", "purgar", "catalogo"],
                    help="saude: relatório | orfaos: lista órfãos | purgar: remove ano | catalogo: exporta JSON")
    ap.add_argument("--ano",  type=str, default=None)
    ap.add_argument("--tipo", type=str, default="ambos")
    ap.add_argument("--exec", action="store_true", help="Executa de verdade (sem dry-run)")
    args = ap.parse_args()

    fm = PeleFileManager()

    if args.cmd == "saude":
        fm.relatorio_saude()
    elif args.cmd == "orfaos":
        fm.limpar_orfaos(dry_run=not args.exec)
    elif args.cmd == "purgar":
        if not args.ano:
            print("❌ --ano obrigatório para purgar")
        else:
            fm.purgar_ano(args.ano, args.tipo, dry_run=not args.exec)
    elif args.cmd == "catalogo":
        fm.exportar_catalogo()
