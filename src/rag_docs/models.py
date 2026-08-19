"""Schemas Pydantic expostos pela API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Resposta do healthcheck. `ok` exige banco e pgvector respondendo."""

    status: Literal["ok", "degradado"]
    versao: str = Field(description="Versao da aplicacao")
    banco: Literal["ok", "erro"]
    pgvector: str | None = Field(default=None, description="Versao da extensao pgvector")
    langfuse: Literal["configurado", "desativado"]
    detalhe: str | None = Field(default=None, description="Causa do estado degradado")
