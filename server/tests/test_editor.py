# -*- coding: utf-8 -*-
"""Testes do editor de video (funcoes puras — nao precisam de ffmpeg)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import editor  # noqa: E402
import server  # noqa: E402


# === parse_tempo ===

@pytest.mark.parametrize("txt,esperado", [
    ("45", 45.0),
    ("45.5", 45.5),
    ("1:23", 83.0),
    ("01:02:03", 3723.0),
    ("0:30", 30.0),
])
def test_parse_tempo(txt, esperado):
    assert editor.parse_tempo(txt) == esperado


@pytest.mark.parametrize("txt", ["", "a:b", "1:2:3:4", "1::2"])
def test_parse_tempo_invalido(txt):
    with pytest.raises(editor.EdicaoErro):
        editor.parse_tempo(txt)


# === validar_spec ===

def test_spec_valido_completo():
    spec = {
        "cortes": [["0:30", "1:20"], ["2:00", "2:10"]],
        "velocidade": 2, "formato": "vertical", "texto": "Oi",
        "texto_pos": "topo", "fade": True, "mudo": True, "comprimir_mb": 16,
    }
    assert editor.validar_spec(spec) == []


@pytest.mark.parametrize("spec,trecho_erro", [
    ({"cortes": [["1:20", "0:30"]]}, "fim antes do inicio"),
    ({"cortes": "0:30-1:20"}, "lista"),
    ({"velocidade": 99}, "velocidade"),
    ({"formato": "circular"}, "formato"),
    ({"texto_pos": "lateral"}, "texto_pos"),
    ({"volume": -1}, "volume"),
    ({"comprimir_mb": 0}, "comprimir_mb"),
])
def test_spec_invalido(spec, trecho_erro):
    erros = editor.validar_spec(spec)
    assert erros and any(trecho_erro in e for e in erros)


# === spec_tem_edicao ===

@pytest.mark.parametrize("spec,esperado", [
    (None, False),
    ({}, False),
    ({"velocidade": 1.0, "volume": 1.0}, False),
    ({"cortes": [["0", "10"]]}, True),
    ({"formato": "vertical"}, True),
    ({"mudo": True}, True),
    ({"comprimir_mb": 16}, True),
])
def test_spec_tem_edicao(spec, esperado):
    assert editor.spec_tem_edicao(spec) is esperado


# === montar_filtros ===

def test_filtros_vertical_e_texto():
    fv, fa, dur = editor.montar_filtros(
        {"formato": "vertical", "texto": "Oi"}, duracao=60, tem_audio=True
    )
    cadeia = ",".join(fv)
    assert "1080:1920" in cadeia
    assert "drawtext" in cadeia
    assert fa == []  # audio preservado, sem filtro
    assert dur == 60


def test_filtros_velocidade_ajusta_duracao_e_audio():
    fv, fa, dur = editor.montar_filtros(
        {"velocidade": 4}, duracao=60, tem_audio=True
    )
    assert dur == 15
    assert any("setpts" in f for f in fv)
    # 4x = atempo=2.0 encadeado duas vezes
    assert fa is not None and fa[0].count("atempo") == 2


def test_filtros_mudo_descarta_audio():
    _, fa, _ = editor.montar_filtros({"mudo": True}, duracao=10, tem_audio=True)
    assert fa is None


def test_filtros_sem_audio_na_origem():
    _, fa, _ = editor.montar_filtros({"fade": True}, duracao=10, tem_audio=False)
    assert fa is None


def test_drawtext_escapa_caracteres():
    fv, _, _ = editor.montar_filtros(
        {"texto": "a:b'c"}, duracao=10, tem_audio=False
    )
    cadeia = ",".join(fv)
    assert "a\\:b" in cadeia and "'c" not in cadeia.split("text='", 1)[1].split(":")[0]


# === rota /mobile-download com edicao ===

@pytest.fixture
def client():
    server.app.config["TESTING"] = True
    with server.app.test_client() as c:
        yield c


def test_mobile_download_edicao_invalida(client):
    r = client.post("/mobile-download", json={
        "url": "https://example.com/v",
        "mode": "video",
        "edit": {"cortes": [["1:20", "0:30"]]},
    })
    data = r.get_json()
    assert data["ok"] is False
    assert "edicao invalida" in data["error"]


def test_health_anuncia_edicao(client):
    data = client.get("/health").get_json()
    assert "edicao" in data.get("features", [])
