from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class StatusAprovacao(str, enum.Enum):
    APROVADA = "aprovada"
    PENDENTE_APROVACAO = "pendente_aprovacao"


class TipoEntidade(str, enum.Enum):
    PESSOA = "pessoa"
    PROCESSO = "processo"
    CPF = "cpf"
    RG = "rg"
    EMAIL = "email"
    SIAPE = "siape"
    MATRICULA = "matricula"
    LINK_PESSOAL = "link_pessoal"


class Documento(Base):
    __tablename__ = "documentos"
    __table_args__ = (
        # nome_arquivo sozinho nao e globalmente unico: orgaos diferentes podem
        # nomear atas com o mesmo padrao generico (ex.: "10-2025.pdf"); tipo_orgao
        # + orgao (codigo bruto do inventario) desambiguam a origem
        UniqueConstraint(
            "tipo_orgao", "orgao", "nome_arquivo", name="uq_documentos_tipo_orgao_orgao_nome_arquivo"
        ),
    )

    id_documento: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome_arquivo: Mapped[str] = mapped_column(String(255), nullable=False)
    url_origem: Mapped[str] = mapped_column(String(500), nullable=False)
    data_coleta: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status_aprovacao: Mapped[str] = mapped_column(String(30), default=StatusAprovacao.APROVADA.value)

    centro: Mapped[str] = mapped_column(String(20), nullable=False)
    campus: Mapped[str] = mapped_column(String(30), nullable=False)
    tipo_orgao: Mapped[str] = mapped_column(String(1), nullable=False)
    orgao: Mapped[str] = mapped_column(String(50), nullable=False)
    departamento: Mapped[str | None] = mapped_column(String(50), nullable=True)
    curso: Mapped[str | None] = mapped_column(String(80), nullable=True)
    area_tematica: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # nulo para orgaos que nao numeram suas atas na fonte (ex.: CAR, CEFD)
    numero_reuniao: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # nulo quando o orgao nao declara o carater (ordinaria/extraordinaria) da
    # reuniao na fonte (CAR, CT, CEFD e outros — confirmado no CSV real: 50/288)
    tipo_reuniao: Mapped[str | None] = mapped_column(String(20), nullable=True)
    data_reuniao: Mapped[date] = mapped_column(Date, nullable=False)
    horario_inicio: Mapped[str | None] = mapped_column(String(10), nullable=True)
    modalidade: Mapped[str | None] = mapped_column(String(30), nullable=True)
    local: Mapped[str | None] = mapped_column(String(200), nullable=True)

    quantidade_presentes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quantidade_ausentes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quorum_declarado: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    departamentos_representados: Mapped[str | None] = mapped_column(Text, nullable=True)

    texto_limpo: Mapped[str] = mapped_column(Text, nullable=False)

    # nulo ate o documento ser reprocessado pelo pipeline (Parte 2) depois da
    # Parte 3 — os 357 documentos ja ingeridos precisam de um rerun idempotente
    # pra essa coluna deixar de ser nula
    paginas_offsets: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)


class EntidadeAnonimizada(Base):
    __tablename__ = "entidades_anonimizadas"
    __table_args__ = (
        UniqueConstraint("hash_entidade", name="uq_entidades_anonimizadas_hash_entidade"),
        UniqueConstraint("tipo", "token", name="uq_entidades_anonimizadas_tipo_token"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hash_entidade: Mapped[str] = mapped_column(String(64), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    token: Mapped[str] = mapped_column(String(50), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
