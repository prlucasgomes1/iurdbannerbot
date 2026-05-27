"""
Bot Telegram — Edição Automática de Fotos
Igreja Universal Long Branch (@universallongbranch)

Fluxo:
  1. /start         → bot pede o banner do evento
  2. Usuário envia banner (foto)
                    → remove fundo, extrai paleta de cores, salva template
  3. Bot pede as fotos do evento
  4. Usuário envia 1–10 fotos
  5. /pronto        → bot processa e devolve todas as fotos editadas
  6. /reset         → recomeça (novo banner)
"""

import os
import io
import logging
import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Estados da conversa ────────────────────────────────────────────────────────
WAITING_BANNER = 1
WAITING_PHOTOS = 2

# ── Configurações de saída ─────────────────────────────────────────────────────
TARGET_SIZE      = 1080          # px — tamanho final quadrado (Instagram ideal)
GRADIENT_RATIO   = 0.38          # altura do degradê = 38% da imagem
BANNER_WIDTH_PCT = 0.44          # largura do banner = 44% da imagem (50% do tamanho original)
BANNER_MARGIN    = 0.025         # margem inferior do banner
JPEG_QUALITY     = 95

# ── remove.bg API ──────────────────────────────────────────────────────────────
REMOVEBG_API_KEY = os.environ.get("REMOVEBG_API_KEY", "")

def remove_background(image_bytes: bytes) -> bytes:
    """Remove o fundo da imagem usando a API do remove.bg."""
    if not REMOVEBG_API_KEY:
        raise ValueError("REMOVEBG_API_KEY não configurada.")
    response = requests.post(
        "https://api.remove.bg/v1.0/removebg",
        files={"image_file": ("banner.png", image_bytes, "image/png")},
        data={"size": "auto"},
        headers={"X-Api-Key": REMOVEBG_API_KEY},
        timeout=30,
    )
    if response.status_code == 200:
        return response.content
    else:
        raise Exception(f"Erro remove.bg {response.status_code}: {response.text}")

# ── Handlers ───────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Olá! Sou o bot de edição de fotos da Igreja Universal Long Branch.\n\n"
        "📌 *Como funciona:*\n"
        "1️⃣ Envie o *banner do evento* (pode ser PNG ou JPG)\n"
        "2️⃣ Envie as *fotos do evento* (até 10)\n"
        "3️⃣ Digite /pronto e receba as fotos editadas!\n\n"
        "📎 Envie o banner para começar:",
        parse_mode="Markdown",
    )
    return WAITING_BANNER


async def receive_banner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o banner, extrai a cor do fundo, remove o fundo e salva o template."""
    if not update.message.photo and not update.message.document:
        await update.message.reply_text("Por favor, envie uma *imagem* do banner.", parse_mode="Markdown")
        return WAITING_BANNER

    msg = await update.message.reply_text("⏳ Processando o banner... aguarde.")

    try:
        # Download da imagem em alta resolução
        if update.message.photo:
            file_obj = await update.message.photo[-1].get_file()
        else:
            file_obj = await update.message.document.get_file()

        banner_bytes = bytes(await file_obj.download_as_bytearray())

        # ── Extrai a cor do FUNDO antes de removê-lo ──────────────────────────
        # Lê os pixels nas bordas/cantos — quase sempre são fundo puro
        dominant_color = extract_background_color(banner_bytes)

        # ── Remove o fundo via remove.bg ──────────────────────────────────────
        banner_no_bg_bytes = remove_background(banner_bytes)
        banner_rgba = Image.open(io.BytesIO(banner_no_bg_bytes)).convert("RGBA")

        # Armazena no contexto do usuário
        context.user_data["banner"]         = banner_rgba
        context.user_data["dominant_color"] = dominant_color
        context.user_data["photos"]         = []

        r, g, b = dominant_color
        await msg.edit_text(
            f"✅ Banner processado!\n"
            f"🎨 Cor do fundo detectada: RGB({r}, {g}, {b})\n"
            f"_(esta cor será usada no degradê)_\n\n"
            f"📸 Agora envie as *fotos do evento* (1 a 10 fotos).\n"
            f"Quando terminar, envie /pronto",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.exception("Erro ao processar banner")
        await msg.edit_text(f"❌ Erro ao processar o banner: {e}\nTente novamente.")
        return WAITING_BANNER

    return WAITING_PHOTOS


def extract_background_color(banner_bytes: bytes) -> tuple:
    """
    Determina a cor do fundo do banner amostrando pixels nas bordas da imagem.
    Borda superior, inferior, esquerda e direita — onde o fundo quase sempre aparece.
    Retorna a cor mais frequente entre essas amostras como tupla RGB.
    """
    img = Image.open(io.BytesIO(banner_bytes)).convert("RGB")
    w, h = img.size
    pixels = np.array(img)

    # Amostra as 4 bordas com espessura de 5% da dimensão menor
    margin = max(5, int(min(w, h) * 0.05))

    border_pixels = np.concatenate([
        pixels[:margin, :].reshape(-1, 3),          # topo
        pixels[-margin:, :].reshape(-1, 3),         # base
        pixels[:, :margin].reshape(-1, 3),          # esquerda
        pixels[:, -margin:].reshape(-1, 3),         # direita
    ])

    # Quantiza em blocos de 16 para agrupar tons similares e achar o mais frequente
    quantized = (border_pixels // 16).astype(np.int32)
    # Converte para escalar único para contar com np.unique
    keys = quantized[:, 0] * 10000 + quantized[:, 1] * 100 + quantized[:, 2]
    unique, counts = np.unique(keys, return_counts=True)
    dominant_key = unique[np.argmax(counts)]

    # Reconstrói a cor quantizada e multiplica para recuperar escala original
    r_q = (dominant_key // 10000) * 16
    g_q = ((dominant_key % 10000) // 100) * 16
    b_q = (dominant_key % 100) * 16

    # Refina: média real dos pixels próximos a essa cor quantizada
    mask = (
        (np.abs(border_pixels[:, 0].astype(int) - r_q) < 24) &
        (np.abs(border_pixels[:, 1].astype(int) - g_q) < 24) &
        (np.abs(border_pixels[:, 2].astype(int) - b_q) < 24)
    )
    matching = border_pixels[mask]
    if len(matching) > 0:
        r, g, b = matching.mean(axis=0).astype(int).tolist()
    else:
        r, g, b = int(r_q), int(g_q), int(b_q)

    return (r, g, b)


async def receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Acumula as fotos do evento enviadas pelo usuário."""
    if "photos" not in context.user_data:
        await update.message.reply_text(
            "⚠️ Nenhum banner configurado ainda. Envie /start para começar."
        )
        return WAITING_BANNER

    photos_list = context.user_data["photos"]
    if len(photos_list) >= 10:
        await update.message.reply_text(
            "⚠️ Limite de 10 fotos atingido. Envie /pronto para processar."
        )
        return WAITING_PHOTOS

    try:
        file_obj = await update.message.photo[-1].get_file()
        photo_bytes = bytes(await file_obj.download_as_bytearray())
        photos_list.append(photo_bytes)
        count = len(photos_list)
        await update.message.reply_text(
            f"📸 Foto {count}/10 recebida!\n"
            f"{'Envie mais fotos ou ' if count < 10 else ''}"
            f"Digite /pronto para processar."
        )
    except Exception as e:
        logger.exception("Erro ao receber foto")
        await update.message.reply_text(f"❌ Erro ao receber a foto: {e}")

    return WAITING_PHOTOS


async def process_photos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processa todas as fotos acumuladas e envia os resultados."""
    photos_list = context.user_data.get("photos", [])
    if not photos_list:
        await update.message.reply_text("⚠️ Nenhuma foto recebida ainda. Envie as fotos primeiro.")
        return WAITING_PHOTOS

    banner_rgba     = context.user_data.get("banner")
    dominant_color  = context.user_data.get("dominant_color", (20, 10, 5))

    msg = await update.message.reply_text(
        f"⚙️ Processando {len(photos_list)} foto(s)... pode levar alguns segundos."
    )

    processed = 0
    errors = 0
    for i, photo_bytes in enumerate(photos_list, 1):
        try:
            result_img = apply_template(photo_bytes, banner_rgba, dominant_color)
            buf = io.BytesIO()
            result_img.save(buf, format="JPEG", quality=JPEG_QUALITY)
            buf.seek(0)
            await update.message.reply_photo(
                photo=buf,
                caption=f"✅ Foto {i}/{len(photos_list)} — pronta para postar!",
            )
            processed += 1
        except Exception as e:
            logger.exception(f"Erro ao processar foto {i}")
            await update.message.reply_text(f"❌ Erro na foto {i}: {e}")
            errors += 1

    summary = f"🎉 *{processed} foto(s) processada(s) com sucesso!*"
    if errors:
        summary += f"\n⚠️ {errors} erro(s)."
    summary += "\n\nEnvie /start para um novo banner ou continue enviando fotos."
    await msg.edit_text(summary, parse_mode="Markdown")

    # Limpa apenas as fotos (mantém o banner para reutilização)
    context.user_data["photos"] = []
    return WAITING_PHOTOS


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Reinicia completamente — novo banner."""
    context.user_data.clear()
    await update.message.reply_text(
        "🔄 Reiniciado! Envie o novo banner do evento para começar.",
    )
    return WAITING_BANNER


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("❌ Operação cancelada. Envie /start para recomeçar.")
    return ConversationHandler.END


# ── Lógica de edição de imagem ─────────────────────────────────────────────────

def apply_template(
    photo_bytes: bytes,
    banner_rgba: Image.Image,
    dominant_color: tuple,
) -> Image.Image:
    """
    Transforma uma foto do evento:
      1. Recorta para quadrado (1:1), centralizado
      2. Redimensiona para TARGET_SIZE x TARGET_SIZE
      3. Aplica degradê escuro na parte inferior (cor baseada no banner)
      4. Composta o banner (sem fundo) no rodapé
    """

    # ── 1. Abre e recorta para quadrado centralizado ──────────────────────────
    img = Image.open(io.BytesIO(photo_bytes)).convert("RGBA")
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top  = (h - side) // 2
    img  = img.crop((left, top, left + side, top + side))
    img  = img.resize((TARGET_SIZE, TARGET_SIZE), Image.LANCZOS)

    # ── 2. Cria camada de degradê ─────────────────────────────────────────────
    grad_height = int(TARGET_SIZE * GRADIENT_RATIO)
    gradient    = Image.new("RGBA", (TARGET_SIZE, TARGET_SIZE), (0, 0, 0, 0))
    r, g, b     = dominant_color

    # Degradê suave: usa curva quadrática para transição natural
    pixels = np.zeros((TARGET_SIZE, TARGET_SIZE, 4), dtype=np.uint8)
    for y in range(grad_height):
        # Posição relativa dentro da área do degradê (0 = topo, 1 = base)
        t     = y / grad_height
        alpha = int(220 * (t ** 1.6))   # 220 = máx opacidade (não 255 para manter alguma textura)
        row   = TARGET_SIZE - grad_height + y
        pixels[row, :] = [r, g, b, alpha]

    gradient = Image.fromarray(pixels, "RGBA")

    # ── 3. Composta o degradê sobre a foto ────────────────────────────────────
    img = Image.alpha_composite(img, gradient)

    # ── 4. Redimensiona e posiciona o banner ──────────────────────────────────
    banner_w = int(TARGET_SIZE * BANNER_WIDTH_PCT)
    ratio    = banner_w / banner_rgba.width
    banner_h = int(banner_rgba.height * ratio)
    banner   = banner_rgba.resize((banner_w, banner_h), Image.LANCZOS)

    # Posição: centralizado horizontalmente, com margem inferior
    bx = (TARGET_SIZE - banner_w) // 2
    by = TARGET_SIZE - banner_h - int(TARGET_SIZE * BANNER_MARGIN)

    img.paste(banner, (bx, by), banner)  # usa canal alpha do banner como máscara

    return img.convert("RGB")


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError(
            "Token não encontrado. Defina a variável de ambiente TELEGRAM_BOT_TOKEN.\n"
            "Exemplo: export TELEGRAM_BOT_TOKEN='seu_token_aqui'"
        )
    if not REMOVEBG_API_KEY:
        raise ValueError(
            "Chave remove.bg não encontrada. Defina a variável REMOVEBG_API_KEY.\n"
            "Crie sua chave gratuita em: https://www.remove.bg/api"
        )

    app = Application.builder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_BANNER: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_banner),
            ],
            WAITING_PHOTOS: [
                MessageHandler(filters.PHOTO, receive_photo),
                CommandHandler("pronto", process_photos),
                CommandHandler("reset", reset),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
        ],
    )

    app.add_handler(conv_handler)

    logger.info("Bot iniciado. Aguardando mensagens...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
