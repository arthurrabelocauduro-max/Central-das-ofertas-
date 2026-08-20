import hashlib
import json
import time
import requests
from pathlib import Path

# ==================================================
# CONFIGURAÇÃO
# ==================================================

APP_ID = os.getenv("SHOPEE_APP_ID")
SECRET = os.getenv("SHOPEE_SECRET")

URL = "https://open-api.affiliate.shopee.com.br/graphql"

INTERVALO_MINUTOS = 5
QUANTIDADE_BUSCA = 20
MAX_OFERTAS_POR_RODADA = 5

ARQUIVO_HISTORICO = Path("ofertas_enviadas.json")
ARQUIVO_OFERTAS = Path("ofertas_prontas.txt")


# ==================================================
# HISTÓRICO
# ==================================================

def carregar_historico():

    if not ARQUIVO_HISTORICO.exists():
        return set()

    try:
        dados = json.loads(
            ARQUIVO_HISTORICO.read_text(
                encoding="utf-8"
            )
        )

        return set(dados)

    except Exception:
        return set()


def salvar_historico(historico):

    ARQUIVO_HISTORICO.write_text(
        json.dumps(
            list(historico),
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


# ==================================================
# BUSCAR PRODUTOS NA SHOPEE
# ==================================================

def buscar_ofertas():

    timestamp = int(time.time())

    query = f"""
    {{
      productOfferV2(page: 1, limit: {QUANTIDADE_BUSCA}) {{
        nodes {{
          productName
          price
          sales
          offerLink
          imageUrl
        }}
      }}
    }}
    """

    payload = json.dumps({
        "query": query
    })

    sign_str = (
        f"{APP_ID}"
        f"{timestamp}"
        f"{payload}"
        f"{SECRET}"
    )

    signature = hashlib.sha256(
        sign_str.encode("utf-8")
    ).hexdigest()

    headers = {
        "Authorization":
            f"SHA256 Credential={APP_ID}, "
            f"Timestamp={timestamp}, "
            f"Signature={signature}",

        "Content-Type": "application/json"
    }

    response = requests.post(
        URL,
        data=payload,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    dados = response.json()

    if "errors" in dados:

        print("\n❌ ERRO DA SHOPEE:")
        print(
            json.dumps(
                dados["errors"],
                ensure_ascii=False,
                indent=2
            )
        )

        return []

    produtos = (
        dados
        .get("data", {})
        .get("productOfferV2", {})
        .get("nodes", [])
    )

    return produtos


# ==================================================
# ID DO PRODUTO
# ==================================================

def id_produto(produto):

    nome = str(
        produto.get(
            "productName",
            ""
        )
    )

    link = str(
        produto.get(
            "offerLink",
            ""
        )
    )

    identificacao = nome + link

    return hashlib.sha256(
        identificacao.encode("utf-8")
    ).hexdigest()


# ==================================================
# FORMATAR PREÇO
# ==================================================

def formatar_preco(preco):

    if preco is None:
        return "Consulte"

    try:

        valor = float(preco)

        return f"{valor:,.2f}".replace(
            ",",
            "X"
        ).replace(
            ".",
            ","
        ).replace(
            "X",
            "."
        )

    except Exception:

        return str(preco)


# ==================================================
# CRIAR MENSAGEM
# ==================================================

def criar_mensagem(produto):

    nome = produto.get(
        "productName",
        "Produto"
    )

    preco = formatar_preco(
        produto.get("price")
    )

    vendas = produto.get(
        "sales",
        0
    ) or 0

    link = produto.get(
        "offerLink",
        ""
    )

    foto = produto.get(
        "imageUrl",
        ""
    )

    if vendas:

        vendas_txt = (
            f"🛒 +{vendas} vendidos"
        )

    else:

        vendas_txt = (
            "🔥 Oferta em alta!"
        )

    mensagem = f"""
🔥 OLHA ESSA OFERTA DA SHOPEE!

🛍️ {nome}

💰 Por apenas: R$ {preco}

{vendas_txt}

👉 COMPRE AQUI:
{link}

🖼️ FOTO:
{foto}
""".strip()

    return mensagem


# ==================================================
# PROCESSAR OFERTAS
# ==================================================

def processar_ofertas():

    print("\n" + "=" * 50)
    print("🔎 PROCURANDO NOVAS OFERTAS...")
    print("=" * 50)

    historico = carregar_historico()

    try:

        produtos = buscar_ofertas()

    except Exception as erro:

        print("\n❌ ERRO AO BUSCAR OFERTAS:")
        print(erro)

        return

    if not produtos:

        print(
            "\n⚠️ Nenhum produto encontrado."
        )

        return

    # ----------------------------------------------
    # ORDENAR PELO NÚMERO DE VENDAS
    # ----------------------------------------------

    produtos.sort(
        key=lambda produto:
            produto.get("sales", 0) or 0,
        reverse=True
    )

    novas_ofertas = []

    # ----------------------------------------------
    # PEGAR AS MELHORES
    # ----------------------------------------------

    for produto in produtos:

        if len(novas_ofertas) >= MAX_OFERTAS_POR_RODADA:
            break

        produto_id = id_produto(
            produto
        )

        if produto_id in historico:
            continue

        mensagem = criar_mensagem(
            produto
        )

        novas_ofertas.append(
            mensagem
        )

        historico.add(
            produto_id
        )

    # ----------------------------------------------
    # NENHUMA NOVA
    # ----------------------------------------------

    if not novas_ofertas:

        print(
            "\nℹ️ Nenhuma oferta nova encontrada."
        )

        return

    # ----------------------------------------------
    # SALVAR OFERTAS
    # ----------------------------------------------

    with ARQUIVO_OFERTAS.open(
        "a",
        encoding="utf-8"
    ) as arquivo:

        for mensagem in novas_ofertas:

            arquivo.write("\n")
            arquivo.write(
                "=" * 60
            )
            arquivo.write("\n")
            arquivo.write(mensagem)
            arquivo.write("\n")

    # ----------------------------------------------
    # SALVAR HISTÓRICO
    # ----------------------------------------------

    salvar_historico(
        historico
    )

    # ----------------------------------------------
    # MOSTRAR NO TERMINAL
    # ----------------------------------------------

    print(
        f"\n🔥 {len(novas_ofertas)} "
        "NOVA(S) OFERTA(S) ENCONTRADA(S)!"
    )

    for numero, mensagem in enumerate(
        novas_ofertas,
        start=1
    ):

        print(
            f"\n========== OFERTA {numero} ==========\n"
        )

        print(mensagem)

    print(
        "\n💾 Ofertas salvas em:"
    )

    print(
        ARQUIVO_OFERTAS
    )


# ==================================================
# INICIAR SISTEMA
# ==================================================

def iniciar():

    print("\n")
    print(
        "🚀 CENTRAL DAS OFERTAS INICIADA!"
    )

    print(
        f"⏰ Busca automática a cada "
        f"{INTERVALO_MINUTOS} minutos."
    )

    print(
        f"🛍️ Até {MAX_OFERTAS_POR_RODADA} "
        "ofertas novas por rodada."
    )

    print(
        "\nPressione CTRL + C para parar.\n"
    )

    while True:

        processar_ofertas()

        print(
            f"\n😴 Aguardando "
            f"{INTERVALO_MINUTOS} minutos..."
        )

        try:

            time.sleep(
                INTERVALO_MINUTOS * 60
            )

        except KeyboardInterrupt:

            print(
                "\n\n🛑 Sistema encerrado."
            )

            break


# ==================================================
# EXECUTAR
# ==================================================

if __name__ == "__main__":

    iniciar()
