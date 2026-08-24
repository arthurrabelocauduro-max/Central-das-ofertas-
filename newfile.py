import hashlib
import json
import os
import time
from pathlib import Path

import requests


# ============================================================
# CONFIGURAÇÃO
# ============================================================

ID_DO_APLICATIVO = os.getenv("SHOPEE_APP_ID")
SECRETO = os.getenv("SHOPEE_SECRET")

URL = "https://open-api.affiliate.shopee.com.br/graphql"

# Tempo entre as execuções
INTERVALO_MINUTOS = 5

# Quantos produtos NOVOS queremos encontrar por rodada
QUANTIDADE_BUSCA = 10

# Quantidade de produtos por página da API
PRODUTOS_POR_PAGINA = 10

# Segurança para não ficar buscando páginas infinitamente
MAX_PAGINAS = 10

ARQUIVO_HISTÓRICO = Path("ofertas_enviadas.json")
ARQUIVO_OFERTAS = Path("ofertas_para_postar.txt")


# ============================================================
# VERIFICAR CONFIGURAÇÃO
# ============================================================

if not ID_DO_APLICATIVO:
    raise RuntimeError("A secret SHOPEE_APP_ID não foi encontrada.")

if not SECRETO:
    raise RuntimeError("A secret SHOPEE_SECRET não foi encontrada.")


# ============================================================
# HISTÓRICO
# ============================================================

def carregar_histórico():
    if not ARQUIVO_HISTÓRICO.exists():
        return set()

    try:
        dados = json.loads(
            ARQUIVO_HISTÓRICO.read_text(
                encoding="utf-8"
            )
        )

        return set(dados)

    except Exception:
        return set()


def salvar_histórico(histórico):
    ARQUIVO_HISTÓRICO.write_text(
        json.dumps(
            sorted(list(histórico)),
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


# ============================================================
# BUSCAR PRODUTOS NA SHOPEE
# ============================================================

def buscar_ofertas():
    todos_os_produtos = []

    for pagina in range(1, MAX_PAGINAS + 1):

        consulta = f"""
        {{
          productOfferV2(
            page: {pagina},
            limit: {PRODUTOS_POR_PAGINA}
          ) {{
            nodes {{
              itemId
              productName
              priceMin
              priceMax
              sales
              offerLink
              productLink
              imageUrl
              commissionRate
              shopName
            }}

            pageInfo {{
              page
              limit
              hasNextPage
            }}
          }}
        }}
        """

        carga_util = json.dumps(
            {
                "query": consulta
            },
            ensure_ascii=False,
            separators=(",", ":")
        )

        timestamp = str(int(time.time()))

        assinatura_texto = (
            f"{ID_DO_APLICATIVO}"
            f"{timestamp}"
            f"{carga_util}"
            f"{SECRETO}"
        )

        assinatura = hashlib.sha256(
            assinatura_texto.encode("utf-8")
        ).hexdigest()

        cabecalhos = {
            "Authorization": (
                f"SHA256 Credential={ID_DO_APLICATIVO},"
                f"Timestamp={timestamp},"
                f"Signature={assinatura}"
            ),
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        resposta = requests.post(
            URL,
            data=carga_util,
            headers=cabecalhos,
            timeout=30
        )

        resposta.raise_for_status()

        dados = resposta.json()

        if "errors" in dados:
            print("\n❌ ERRO DA SHOPEE:")
            print(json.dumps(
                dados["errors"],
                ensure_ascii=False,
                indent=2
            ))
            break

        resultado = (
            dados
            .get("data", {})
            .get("productOfferV2", {})
        )

        produtos = resultado.get("nodes", [])
        page_info = resultado.get("pageInfo", {})

        if not produtos:
            break

        todos_os_produtos.extend(produtos)

        print(
            f"📄 Página {pagina}: "
            f"{len(produtos)} produtos encontrados."
        )

        # Se não existe próxima página, acabou.
        if not page_info.get("hasNextPage", False):
            break

    return todos_os_produtos


# ============================================================
# ID ÚNICO DO PRODUTO
# ============================================================

def id_produto(produto):

    item_id = str(
        produto.get("itemId", "")
    )

    link = str(
        produto.get("offerLink")
        or produto.get("productLink")
        or ""
    )

    # O ID da Shopee é a melhor identificação.
    # Se não existir, usamos nome + link.
    identificação = item_id or (
        str(produto.get("productName", "")) + link
    )

    return hashlib.sha256(
        identificação.encode("utf-8")
    ).hexdigest()


# ============================================================
# FORMATAR PREÇO
# ============================================================

def formatar_preço(preço):

    if preço is None or preço == "":
        return "Consultar"

    try:
        valor = float(preço)

        return (
            f"R$ {valor:,.2f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )

    except Exception:
        return str(preço)


# ============================================================
# CRIAR MENSAGEM
# ============================================================

def criar_mensagem(produto):

    nome = produto.get(
        "productName",
        "Produto"
    )

    preço = formatar_preço(
        produto.get("priceMin")
    )

    vendas = produto.get(
        "sales",
        0
    )

    link = (
        produto.get("offerLink")
        or produto.get("productLink")
        or ""
    )

    foto = produto.get(
        "imageUrl",
        ""
    )

    if vendas:
        vendas_txt = f"🔥 {vendas} vendas"
    else:
        vendas_txt = "🔥 Oferta disponível"

    mensagem = f"""
🛍️ OFERTA DA SHOPEE!

📦 {nome}

💰 Por apenas: {preço}

{vendas_txt}

👉 COMPRE AQUI:
{link}
""".strip()

    # Se existir imagem, adiciona também a imagem
    # em formato Markdown.
    if foto:
        mensagem += f"""

🖼️ IMAGEM:
![{nome}]({foto})
"""

    return mensagem.strip()


# ============================================================
# PROCESSAR OFERTAS
# ============================================================

def processar_ofertas():

    print("=" * 50)
    print("🔎 PROCURANDO NOVAS OFERTAS...")
    print("=" * 50)

    histórico = carregar_histórico()

    try:
        produtos = buscar_ofertas()

    except Exception as erro:

        print("\n❌ ERRO AO BUSCAR OFERTAS:")
        print(erro)

        return

    if not produtos:

        print("\n⚠️ Nenhum produto encontrado.")
        return

    print(
        f"\n📦 {len(produtos)} produtos recebidos da Shopee."
    )

    novas_ofertas = []
    ids_da_rodada = set()

    # ========================================================
    # NÃO ORDENAR.
    #
    # Os produtos são usados na ordem em que a API devolveu.
    # Não escolhemos somente os mais vendidos.
    # ========================================================

    for produto in produtos:

        if len(novas_ofertas) >= QUANTIDADE_BUSCA:
            break

        produto_id = id_produto(produto)

        # Evita repetir dentro da mesma rodada.
        if produto_id in ids_da_rodada:
            continue

        # Evita repetir produtos já enviados anteriormente.
        if produto_id in histórico:
            continue

        mensagem = criar_mensagem(produto)

        novas_ofertas.append(mensagem)
        ids_da_rodada.add(produto_id)
        histórico.add(produto_id)

    # ========================================================
    # NENHUMA OFERTA NOVA
    # ========================================================

    if not novas_ofertas:

        print("\nℹ️ Nenhuma oferta nova encontrada.")
        return

    # ========================================================
    # SALVAR OFERTAS
    # ========================================================

    with ARQUIVO_OFERTAS.open(
        "a",
        encoding="utf-8"
    ) as arquivo:

        for mensagem in novas_ofertas:

            arquivo.write("\n")
            arquivo.write("=" * 60)
            arquivo.write("\n")
            arquivo.write(mensagem)
            arquivo.write("\n")

    # ========================================================
    # SALVAR HISTÓRICO
    # ========================================================

    salvar_histórico(histórico)

    # ========================================================
    # MOSTRAR NO TERMINAL
    # ========================================================

    print(
        f"\n🆕 {len(novas_ofertas)} "
        "NOVA(S) OFERTA(S) ENCONTRADA(S)!"
    )

    for número, mensagem in enumerate(
        novas_ofertas,
        start=1
    ):

        print(
            f"\n========== OFERTA {número} ==========\n"
        )

        print(mensagem)

    print(
        "\n📁 Ofertas salvas em:"
    )

    print(ARQUIVO_OFERTAS)


# ============================================================
# INICIAR SISTEMA
# ============================================================

def iniciar():

    print("\n")
    print("🛍️ CENTRAL DAS OFERTAS INICIADA!")
    print("🔎 Buscando produtos...")
    print(
        f"📦 Meta: até {QUANTIDADE_BUSCA} "
        "produtos novos por rodada."
    )

    processar_ofertas()

    print("\n✅ Rodada concluída!")


# ============================================================
# EXECUTAR
# ============================================================

if __name__ == "__main__":
    iniciar()
