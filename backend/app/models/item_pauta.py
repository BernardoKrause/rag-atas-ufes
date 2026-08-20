from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class ItemPauta(Base):
    __tablename__ = "itens_pauta"
    __table_args__ = (
        UniqueConstraint(
            "documento_id", "secao", "numero_item", "ocorrencia_indice", "fragmento_indice",
            name="uq_itens_pauta_documento_secao_numero_ocorrencia_fragmento",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    documento_id: Mapped[int] = mapped_column(ForeignKey("documentos.id_documento"), nullable=False)
    # deterministico: f"{documento_id}_{secao_slug}_{numero_item}" (+ "_D{n}" se
    # ocorrencia_indice > 0, + "_F{n}" se dividido por overflow) — chave de
    # correlacao logica entre Postgres/Qdrant/Neo4j nas Partes 4/5, resolvida
    # em gerar_item_id_canonico()
    item_id_canonico: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    secao: Mapped[str] = mapped_column(String(30), nullable=False)
    numero_item: Mapped[str] = mapped_column(String(20), nullable=False)
    # conta ocorrencias do mesmo (secao, numero_item) dentro do documento: 0
    # pra primeira, incrementando pra cada repeticao subsequente — cobre tanto
    # numeracao genuinamente duplicada na fonte quanto falso positivo de
    # deteccao (numero citado dentro do corpo de outro item). Nao resolve a
    # causa raiz de conteudo — so evita que a colisao quebre a constraint
    # unica; os casos ficam sinalizados pra revisao manual (achado (c))
    ocorrencia_indice: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fragmento_indice: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    # nullable: nulo pros itens de documentos ainda nao reprocessados com
    # Documento.paginas_offsets preenchido
    pagina_inicio: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pagina_fim: Mapped[int | None] = mapped_column(Integer, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
