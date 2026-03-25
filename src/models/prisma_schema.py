from pydantic import BaseModel, Field
from typing import Optional, List
from decimal import Decimal
from datetime import date

class VerbaIndenizatoria(BaseModel):
    # Campos da lista principal
    id_alba: str = Field(..., description="ID ALBA: 99439")
    processo: str = Field(..., description="N° PROCESSO")
    numero_nf: str = Field(..., description="N° NF")
    competencia: str = Field(..., description="MM/YYYY")
    deputado: str = Field(..., description="Nome Deputado")
    categoria_html: str = Field(..., description="Categoria na lista")
    valor_html: Decimal = Field(..., description="Valor da lista")
    
    # Campos da página detalhes
    categoria_detalhe: Optional[str] = Field(default=None)
    numero_recibo: Optional[str] = Field(default=None)
    cpf_cnpj: Optional[str] = Field(default=None)
    fornecedor: Optional[str] = Field(default=None)
    valor_pdf: Optional[Decimal] = Field(default=None)
    glosa: Optional[Decimal] = Field(default=Decimal('0'))
    link_pdf: Optional[str] = Field(default=None)
    
    # Análise LLM (Agent 3 & 4)
    risco_nivel: Optional[str] = Field(default="BAIXO", description="Baixo/Médio/Alto")
    comentario_aguia: Optional[str] = Field(default="", description="Análise detalhada")
    
    # Metadados
    data_captura: date = Field(default_factory=date.today)
    fonte_pdf: Optional[str] = Field(default=None, description="Dados extraídos do PDF")
