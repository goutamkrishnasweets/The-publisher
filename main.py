"""
The Publisher — Standalone Localhost AI Video & Post Publisher
================================================================================
A self-hosted, privacy-first multi-platform publishing bot powered by Telegram:
  • ZERO MANDATORY .ENV: All settings, API keys, and channel connections are
    controllable via chat commands.
  • Per-Identity Virtual .ENV: data/telegram_users.json acts as the virtual .env
    isolated strictly by each user's chat_id.
  • Master Vault Index: data/telegram_vault_index.json indexes permanent Telegram
    file_id references in your private storage group.
  • Multimodal Intelligence Pool: data/pool_metadata.json stores video/audio audits,
    pacing scores, and evidence.
  • Multi-Platform 1-Click Publishing:
      1. Buffer (TikTok, Pinterest, X / Twitter)
      2. YouTube Shorts (Direct Google Data API)
      3. Meta (Instagram Reels & Facebook Pages)
      4. Telegram Channel / Group

Usage:
  1. pip install -r requirements.txt
  2. python main.py
"""

import os
import sys
import json
import time
import logging
import asyncio
from typing import Dict, Any, Optional, Tuple

from dotenv import load_dotenv

# Ensure local directories are in python path
_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

load_dotenv(os.path.join(_REPO_ROOT, ".env"), override=False)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("the_publisher")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

DATA_DIR = os.path.join(_REPO_ROOT, "data")
DOWNLOAD_DIR = os.path.join(_REPO_ROOT, "downloads")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

VAULT_INDEX_PATH = os.path.join(DATA_DIR, "master_vault_index.json")
VAULT_INDEX_ALIAS_PATH = os.path.join(DATA_DIR, "telegram_vault_index.json")
POOL_METADATA_PATH = os.path.join(DATA_DIR, "pool_metadata.json")
BOT_CONFIG_PATH = os.path.join(DATA_DIR, "bot_config.json")


# ── Bot Token & Storage Group Resolver (Zero-Mandatory .ENV with Native GUI) ────

def normalize_telegram_group_id(chat_id: str) -> str:
    """Preserves Telegram chat/group IDs accurately without corrupting basic group IDs."""
    s = str(chat_id).strip()
    if not s:
        return ""
    if s.startswith("-"):
        return s
    if s.startswith("100"):
        return f"-{s}"
    return f"-{s}"


def prompt_setup_gui(default_token: str = "", default_storage_id: str = "") -> Tuple[Optional[str], Optional[str]]:
    """Displays a graphical UI dialog to configure Bot API Token and Storage Vault Group ID."""
    try:
        import tkinter as tk
        from tkinter import messagebox

        config_result = {"token": None, "storage_group_id": None}

        root = tk.Tk()
        root.title("🚀 The Publisher — Setup Bot & Storage Vault")
        root.geometry("540x440")
        root.resizable(False, False)

        # Center on screen
        root.update_idletasks()
        w = 540
        h = 440
        x = (root.winfo_screenwidth() // 2) - (w // 2)
        y = (root.winfo_screenheight() // 2) - (h // 2)
        root.geometry(f"{w}x{h}+{x}+{y}")

        # Bring to front
        root.lift()
        root.attributes("-topmost", True)
        root.after_idle(root.attributes, "-topmost", False)

        tk.Label(
            root,
            text="🚀 The Publisher — Initial Setup",
            font=("Segoe UI", 13, "bold"),
        ).pack(pady=(16, 2))

        tk.Label(
            root,
            text="Configure your Telegram Bot and Storage Vault below.\nSaved locally to data/bot_config.json — zero .env required!",
            font=("Segoe UI", 9),
            fg="#555555",
            justify="center",
        ).pack(pady=(0, 10))

        form_frame = tk.Frame(root)
        form_frame.pack(fill="x", padx=30)

        # 1. Bot Token
        tk.Label(
            form_frame,
            text="1. Telegram Bot Token (from @BotFather):",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(4, 2))

        token_var = tk.StringVar(value=default_token)
        token_entry = tk.Entry(form_frame, textvariable=token_var, width=50, font=("Segoe UI", 10))
        token_entry.pack(fill="x", pady=(0, 10))

        # 2. Storage Vault Group ID
        tk.Label(
            form_frame,
            text="2. Storage Vault Group ID (e.g. -100xxxxxxxxxx):",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(4, 2))

        storage_var = tk.StringVar(value=default_storage_id)
        storage_entry = tk.Entry(form_frame, textvariable=storage_var, width=50, font=("Segoe UI", 10))
        storage_entry.pack(fill="x", pady=(0, 8))

        # 3. Prominent Admin Requirement Banner
        notice_frame = tk.Frame(root, bg="#fff8e1", bd=1, relief="solid", padx=12, pady=8)
        notice_frame.pack(fill="x", padx=30, pady=(4, 12))

        notice_text = (
            "⚠️ CRITICAL SETUP INSTRUCTIONS:\n"
            "• Create a private Telegram Group for your cloud vault.\n"
            "• Add this bot as a member to that group.\n"
            "• PROMOTE THE BOT TO ADMINISTRATOR with permissions to post\n"
            "  and pin messages (required for zero-disk vault indexing)!"
        )
        tk.Label(
            notice_frame,
            text=notice_text,
            font=("Segoe UI", 8, "bold"),
            bg="#fff8e1",
            fg="#b78103",
            justify="left",
            anchor="w",
        ).pack(fill="x")

        def on_save(event=None):
            tok = token_var.get().strip()
            if not tok or ":" not in tok:
                messagebox.showwarning(
                    "Invalid Bot Token",
                    "A valid Telegram Bot Token usually looks like:\n123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ\n\nPlease check your input.",
                    parent=root,
                )
                return

            raw_gid = storage_var.get().strip()
            clean_gid = normalize_telegram_group_id(raw_gid) if raw_gid else ""

            if not clean_gid:
                confirm = messagebox.askyesno(
                    "No Storage Group ID",
                    "You did not provide a Storage Vault Group ID.\n\n"
                    "Without it, Cloud Vault backup will be disabled until you run /setstorage in the bot chat.\n\n"
                    "Do you want to continue without a storage group?",
                    parent=root,
                )
                if not confirm:
                    return

            config_result["token"] = tok
            config_result["storage_group_id"] = clean_gid
            root.destroy()

        def on_cancel():
            root.destroy()

        token_entry.bind("<Return>", on_save)
        storage_entry.bind("<Return>", on_save)

        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=4)

        save_btn = tk.Button(
            btn_frame,
            text="  Save & Connect  ",
            command=on_save,
            font=("Segoe UI", 10, "bold"),
            bg="#0088cc",
            fg="white",
            relief="flat",
            padx=14,
            pady=5,
            cursor="hand2",
        )
        save_btn.pack(side="left", padx=8)

        cancel_btn = tk.Button(
            btn_frame,
            text="  Cancel  ",
            command=on_cancel,
            font=("Segoe UI", 9),
            relief="groove",
            padx=10,
            pady=5,
            cursor="hand2",
        )
        cancel_btn.pack(side="left", padx=8)

        if not default_token:
            token_entry.focus_set()
        else:
            storage_entry.focus_set()

        root.mainloop()
        return config_result["token"], config_result["storage_group_id"]
    except Exception as e:
        logger.debug("Tkinter GUI not available: %s", e)
        return None, None


def resolve_bot_token() -> str:
    """
    Resolves the Telegram Bot Token and Storage Group ID:
      1. Checks TELEGRAM_BOT_TOKEN and TELEGRAM_STORAGE_GROUP_ID environment variables.
      2. Checks data/bot_config.json on disk.
      3. Launches graphical UI popup dialog if either is missing.
      4. Falls back to console input if GUI is closed or headless.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    storage_gid = os.getenv("TELEGRAM_STORAGE_GROUP_ID", "").strip()

    if os.path.exists(BOT_CONFIG_PATH):
        try:
            with open(BOT_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                if not token:
                    tok = cfg.get("bot_token", "").strip()
                    if tok and ":" in tok:
                        token = tok
                        os.environ["TELEGRAM_BOT_TOKEN"] = token
                if not storage_gid:
                    gid = cfg.get("storage_group_id", "").strip()
                    if gid:
                        storage_gid = normalize_telegram_group_id(gid)
                        os.environ["TELEGRAM_STORAGE_GROUP_ID"] = storage_gid
                if cfg.get("telegram_api_id"):
                    os.environ["TELEGRAM_API_ID"] = str(cfg["telegram_api_id"]).strip()
                if cfg.get("telegram_api_hash"):
                    os.environ["TELEGRAM_API_HASH"] = str(cfg["telegram_api_hash"]).strip()
        except Exception:
            pass

    # If both token and storage group id are already resolved, return token immediately
    if token and token != "your_bot_token_from_botfather" and storage_gid:
        return token

    # 1. Try modern Graphical UI Dialog Popup
    gui_token, gui_gid = prompt_setup_gui(default_token=token, default_storage_id=storage_gid)
    if gui_token:
        token = gui_token
        if gui_gid:
            storage_gid = gui_gid
        try:
            cfg_to_save = {"bot_token": token, "storage_group_id": storage_gid}
            with open(BOT_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg_to_save, f, indent=2)
            os.environ["TELEGRAM_BOT_TOKEN"] = token
            if storage_gid:
                os.environ["TELEGRAM_STORAGE_GROUP_ID"] = storage_gid
            print(f"✅ Credentials saved to {BOT_CONFIG_PATH}!")
            return token
        except Exception as e:
            logger.warning("Could not persist credentials: %s", e)
            return token

    # If GUI was closed without input but token already exists, continue with token
    if token and token != "your_bot_token_from_botfather":
        return token

    # 2. Console fallback if GUI closed or cancelled
    print("\n" + "=" * 65)
    print("🔑 SETUP: Initial Telegram Configuration")
    print("=" * 65)
    print("Get a free bot token by messaging @BotFather on Telegram.")
    try:
        user_input = input("\n👉 Paste your Telegram Bot Token: ").strip()
        print("\n⚠️ NOTE: Create a private Telegram Group, add this bot, and PROMOTE IT TO ADMIN!")
        user_gid = input("👉 Paste your Storage Vault Group ID (or press Enter to skip): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(1)

    if not user_input:
        print("❌ Error: A valid bot token is required to start.")
        sys.exit(1)

    token = user_input
    storage_gid = normalize_telegram_group_id(user_gid) if user_gid else ""

    try:
        cfg_to_save = {"bot_token": token, "storage_group_id": storage_gid}
        with open(BOT_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg_to_save, f, indent=2)
        os.environ["TELEGRAM_BOT_TOKEN"] = token
        if storage_gid:
            os.environ["TELEGRAM_STORAGE_GROUP_ID"] = storage_gid
        print(f"✅ Credentials saved to {BOT_CONFIG_PATH}! (.env is completely optional)")
    except Exception as e:
        logger.warning("Could not persist credentials: %s", e)

    return token


# Safe Telegram Bot API imports with auto-install if missing
try:
    from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
    from telegram.ext import (
        ApplicationBuilder,
        CommandHandler,
        MessageHandler,
        CallbackQueryHandler,
        ContextTypes,
        filters,
    )
except ImportError:
    import subprocess
    print("📦 Installing required package 'python-telegram-bot'...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "python-telegram-bot>=21.0"])
        from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
        from telegram.ext import (
            ApplicationBuilder,
            CommandHandler,
            MessageHandler,
            CallbackQueryHandler,
            ContextTypes,
            filters,
        )
    except Exception as _pip_err:
        print(f"❌ Failed to install python-telegram-bot: {_pip_err}")
        print("Please run: pip install python-telegram-bot")
        sys.exit(1)


# Import publishing and storage engines
from Publishing_Modules.media_publisher_main import run_phase4_publishing_async
from Publishing_Modules.buffer_publisher import (
    publish_to_buffer,
    set_user_buffer_token,
    get_buffer_profiles,
    get_user_connected_platforms,
    _get_buffer_token,
    resolve_public_media_url,
)
from Telegram_Storage_Modules.telegram_user_manager import (
    load_all_users,
    save_all_users,
    format_user_credentials_summary,
    set_user_gemini_key,
    get_user_gemini_key,
    set_user_public_group_id,
    set_user_storage_group_id,
    get_user_storage_group_id,
    set_user_branding,
    set_user_instagram_token,
    get_user_instagram_token,
    set_user_instagram_id,
    get_user_instagram_id,
    set_user_facebook_token,
    get_user_facebook_token,
    set_user_facebook_id,
    get_user_facebook_id,
    set_user_meta_app,
    get_user_meta_app_id,
    get_user_meta_app_secret,
    set_user_youtube_client_secret,
    get_user_youtube_client_secret,
    set_user_youtube_token,
    get_user_youtube_token_json,
    _is_admin_user,
    is_vault_enabled,
    set_user_vault_mode,
    get_user_seo_blueprint,
    set_user_seo_blueprint,
    get_user_active_channels,
    set_user_active_channels,
)
from Publishing_Modules.meta_uploader import (
    build_meta_oauth_url,
    exchange_meta_oauth_code,
    save_and_sync_meta_credentials,
)
from Telegram_Storage_Modules.telegram_session_manager import session_manager
from Telegram_Storage_Modules.telegram_http import send_document, extract_file_id, download_telegram_document
from Core_Modules.proxy_encoder import encode_for_gemini, _safe_remove
from Gemini_Modules.platform_seo_generator import (
    generate_platform_seo,
    strip_system_and_tracking_tokens,
    clean_entity_name,
)


# ── Vault & Pool Metadata Helpers ─────────────────────────────────────────────

def record_media_to_pool_metadata(
    clip_id: str,
    file_id: str,
    title: str = "",
    seo_data: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None
):
    """
    Stores the media file_id, title, and SEO intelligence into pool_metadata.json.
    Syncs pool_metadata.json to Telegram Storage Group, updates pool_metadata_file_id in master_vault_index.json,
    and re-pins master_vault_index.json in the Telegram group.
    """
    try:
        from Telegram_Storage_Modules.telegram_vault_indexer import TelegramVaultIndexer
        indexer = TelegramVaultIndexer()
        indexer.record_media_file_id(
            clip_id=clip_id,
            file_id=file_id,
            title=title,
            seo_data=seo_data,
            user_id=user_id,
        )
    except Exception as e:
        logger.warning("Record media to pool metadata notice: %s", e)


# ── Visual AI Analysis & SEO Blueprint Helpers ────────────────────────────────

def _extract_keyframes_for_gemini(media_path: str, is_photo: bool = False, max_frames: int = 6) -> list:
    """Extracts lightweight in-memory PIL images spread across the media duration."""
    frames = []
    if is_photo:
        try:
            from PIL import Image
            img = Image.open(media_path).copy()
            frames.append(img)
        except Exception as e:
            logger.debug("Photo load notice: %s", e)
        return frames

    try:
        from PIL import Image
        import subprocess
        tmp_dir = os.path.dirname(media_path)
        base = os.path.splitext(os.path.basename(media_path))[0]
        out_pattern = os.path.join(tmp_dir, f"_kf_{base}_%02d.jpg")
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", media_path,
            "-vf", "fps=1/5,scale=480:-2",
            "-vframes", str(max_frames),
            out_pattern
        ]
        subprocess.run(cmd, timeout=20)
        for i in range(1, max_frames + 1):
            kf_file = os.path.join(tmp_dir, f"_kf_{base}_{i:02d}.jpg")
            if os.path.exists(kf_file):
                try:
                    img = Image.open(kf_file).copy()
                    frames.append(img)
                except Exception:
                    pass
                finally:
                    _safe_remove(kf_file)
    except Exception as e:
        logger.debug("Keyframe extraction notice: %s", e)
    return frames


def analyze_media_for_seo(media_path: str, is_photo: bool = False, user_id: Optional[str] = None) -> str:
    """
    Extracts authentic visual and narrative intelligence with Gemini AI.
    For videos, passes the FULL COMPRESSED VIDEO to Gemini's native File API so Gemini
    analyzes the entire timeline from 0:00 to the end (actions, scene changes, speech, hooks).
    """
    if not media_path or not os.path.exists(media_path):
        return ""

    if is_photo:
        frames = _extract_keyframes_for_gemini(media_path, is_photo=True, max_frames=1)
        if not frames:
            return ""
        try:
            from Gemini_Modules.gemini_router_module.gemini_governor import gemini_router
            if gemini_router:
                prompt = (
                    "You are an expert social media strategist. Inspect this photo and describe: "
                    "1. The primary hero subject, product, or person. "
                    "2. The setting, visual aesthetic, and mood. "
                    "3. The primary visual hook. "
                    "Return a concise 2-sentence summary describing the visual reality."
                )
                raw = gemini_router.generate(task_type="vision", prompt=frames + [prompt], module_name="gemini_media_seo")
                if raw:
                    return raw.strip()
        except Exception as e:
            logger.debug("Photo visual analysis notice: %s", e)
        return ""

    # ── FULL VIDEO ANALYSIS (100% TIMELINE & AUDIO) ──────────────────────────
    proxy_path = None
    try:
        # 1. Compress with proxy_encoder to 480p 1fps 16kHz audio (shrinks 100MB video to ~1.5MB!)
        try:
            proxy_res = encode_for_gemini(media_path, output_dir=DOWNLOAD_DIR, fps=1.0, short_edge=480)
            proxy_path = proxy_res.get("gemini_ready_path")
        except Exception as _p_err:
            logger.warning("Proxy compression notice: %s. Using source directly.", _p_err)
            proxy_path = media_path

        target_video = proxy_path if (proxy_path and os.path.exists(proxy_path)) else media_path

        # 2. Try Gemini Native File API for 100% Full Video Understanding
        api_key = get_user_gemini_key(user_id) if user_id else (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))

        if api_key:
            try:
                from google import genai
                client = genai.Client(api_key=api_key.strip())
                logger.info("📤 Uploading full video proxy to Gemini File API (%s)...", os.path.basename(target_video))
                uploaded_file = client.files.upload(file=target_video)

                # Wait for processing (typically 1-3 seconds for 1-2MB proxy video)
                poll = 0
                while getattr(uploaded_file, "state", None) and uploaded_file.state.name == "PROCESSING" and poll < 25:
                    time.sleep(1.5)
                    uploaded_file = client.files.get(name=uploaded_file.name)
                    poll += 1

                video_prompt = (
                    "You are an expert viral content auditor, video strategist, and social media copywriter. "
                    "Analyze this FULL video from 0:00 to the very end. Provide: "
                    "1. Scene-by-Scene Narrative: Describe what happens from beginning, middle, to ending. "
                    "2. The 3-second opening Hook: Visual and auditory attention-grabber. "
                    "3. Spoken Dialogue & Audio Reality: Words spoken, sound effects, or background speech. "
                    "4. Hero Subject & Key Entities: People, products, outfit, environment, and vibe. "
                    "5. Climax & Call-to-Action (CTA): What happens at the end and the viewer takeaway. "
                    "Return a clear, detailed, comprehensive breakdown of the entire video."
                )

                logger.info("🧠 Gemini analyzing full video timeline and audio...")
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[uploaded_file, video_prompt]
                )

                # Clean up remote Gemini file
                try:
                    client.files.delete(name=uploaded_file.name)
                except Exception:
                    pass

                if response and response.text:
                    full_intel = response.text.strip()
                    logger.info("✅ Full video Gemini intelligence captured (%d chars)", len(full_intel))
                    return full_intel
            except Exception as _g_err:
                logger.warning("Gemini File API full video upload notice: %s. Falling back to multi-frame timeline.", _g_err)

        # 3. Fallback: Multi-Frame Keyframe Analysis across the FULL VIDEO timeline
        frames = _extract_keyframes_for_gemini(target_video, is_photo=False, max_frames=6)
        if frames:
            from Gemini_Modules.gemini_router_module.gemini_governor import gemini_router
            if gemini_router:
                prompt = (
                    "You are an expert viral content auditor. Inspect these sequential frames sampled from throughout the ENTIRE video. "
                    "Describe: "
                    "1. The hero subject, products, or actions shown. "
                    "2. The visual hook and how the scene progresses over time. "
                    "3. The setting, aesthetic, and mood. "
                    "Return a detailed summary of the full video content."
                )
                raw = gemini_router.generate(task_type="vision", prompt=frames + [prompt], module_name="gemini_media_seo")
                if raw:
                    return raw.strip()

    finally:
        if proxy_path and proxy_path != media_path and os.path.exists(proxy_path):
            _safe_remove(proxy_path)

    return ""


def extract_blueprint_from_sample(sample_text: str) -> Dict[str, Any]:
    """Analyzes a viral post sample and extracts its structural SEO blueprint."""
    blueprint = {
        "hook_style": "Attention grabbing opening",
        "body_structure": "Value points & benefits",
        "cta": "Follow & Save for later",
        "hashtag_count": 6,
        "format_template": "{hook}\n\n{body}\n\n{cta}\n\n{hashtags}"
    }
    try:
        from Gemini_Modules.gemini_router_module.gemini_governor import gemini_router
        if gemini_router:
            prompt = (
                "Analyze this social media post caption and extract its structural layout into a JSON blueprint.\n\n"
                f"POST CONTENT:\n\"\"\"{sample_text}\"\"\"\n\n"
                "Return ONLY a JSON dictionary with keys:\n"
                "{\n"
                '  "hook_style": "<how the first 1-2 lines grab attention>",\n'
                '  "body_structure": "<how value/points are formatted>",\n'
                '  "cta": "<call to action format>",\n'
                '  "emoji_style": "<minimal | moderate | high>",\n'
                '  "hashtag_count": <int count of tags>,\n'
                '  "sample_keywords": ["keyword1", "keyword2"]\n'
                "}"
            )
            raw = gemini_router.generate(task_type="seo_generation", prompt=prompt, module_name="blueprint_extractor")
            if raw:
                cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
                parsed = json.loads(cleaned)
                if isinstance(parsed, dict):
                    blueprint.update(parsed)
    except Exception as e:
        logger.warning("Blueprint extraction notice: %s", e)

    return blueprint


# ── Review Keyboards ──────────────────────────────────────────────────────────

def build_review_keyboard(session_id: str, vault_on: bool = True) -> InlineKeyboardMarkup:
    vault_label = "📦 Vault: ON ✅" if vault_on else "⚡ Fast: ON 🚀"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🚀 Post Immediately", callback_data=f"pub_now_{session_id}"),
            InlineKeyboardButton("✏️ Set Title", callback_data=f"pub_title_{session_id}"),
        ],
        [
            InlineKeyboardButton(vault_label, callback_data=f"toggle_v_{session_id}"),
            InlineKeyboardButton("🗑️ Discard", callback_data=f"pub_discard_{session_id}")
        ]
    ])


# ── Command Handlers (Controllable via Chat) ──────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👋 **Welcome to The Publisher — Localhost AI Video Studio!**\n\n"
        "Send or forward me any raw video reel, short, or photo.\n\n"
        "⚙️ **Your Identity & Virtual .ENV:**\n"
        "All credentials and settings are saved on this machine in `data/telegram_users.json` "
        "bound directly to your Telegram Chat ID.\n\n"
        "📋 **Setup Commands (All In-Chat):**\n"
        "• `/vault` — Toggle Telegram Storage Vault vs Direct Fast API Mode\n"
        "• `/setpattern <example_post>` — Train AI to use your custom SEO caption pattern\n"
        "• `/resetpattern` — Reset SEO pattern back to default\n"
        "• `/setstorage <GROUP_ID>` — Connect your private Telegram Storage Vault\n"
        "• `/setbuffer <TOKEN>` — Connect TikTok, Pinterest & X (Twitter) via Buffer\n"
        "• `/setgemini <KEY>` — Connect your free Google Gemini API key\n"
        "• `/setbranding <TEXT>` — Set custom brand watermark text\n"
        "• `/myconfig` — View your configured virtual .env checklist"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_myconfig(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_chat.id)
    summary = format_user_credentials_summary(uid)
    await update.message.reply_text(summary, parse_mode="Markdown")


async def cmd_setstorage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sets user's private Telegram Storage Vault group ID in telegram_users.json and bot_config.json."""
    gid = " ".join(context.args).strip() if context.args else ""
    user = update.effective_user
    uid = str(user.id) if user else str(update.effective_chat.id)

    # If sent from inside a group or channel, auto-detect the group ID directly!
    if not gid and update.effective_chat.type in ("group", "supergroup", "channel"):
        gid = str(update.effective_chat.id)

    if not gid:
        await update.message.reply_text(
            "📦 **Storage Vault Setup**\n\n"
            "Create a private Telegram Group (e.g. *'My Media Vault'*), add this bot as Admin, and:\n"
            "1. Either run `/setstorage` directly inside that group\n"
            "2. Or send: `/setstorage -100xxxxxxxxxx` here"
        )
        return

    ok = set_user_storage_group_id(uid, gid)
    try:
        cfg = {}
        if os.path.exists(BOT_CONFIG_PATH):
            with open(BOT_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        cfg["storage_group_id"] = gid
        with open(BOT_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

    if ok:
        await update.message.reply_text(
            f"✅ **Telegram Storage Vault Linked!**\n\n"
            f"📦 **Storage Group ID:** `{gid}`\n"
            f"All incoming media will now be backed up to your vault and assigned CDN streaming URLs."
        )
    else:
        await update.message.reply_text("❌ Failed to save storage group ID.")


async def cmd_setgemini(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = " ".join(context.args).strip() if context.args else ""
    uid = str(update.effective_chat.id)
    if not key:
        await update.message.reply_text("Usage: `/setgemini YOUR_GEMINI_API_KEY`\nGet a free key from Google AI Studio.")
        return
    ok = set_user_gemini_key(uid, key)
    if ok:
        await update.message.reply_text("✅ **Google Gemini API Key Saved in Your Profile!**")
    else:
        await update.message.reply_text("❌ Failed to save key.")


async def cmd_setmtproto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sets user's Telegram MTProto API_ID and API_HASH for downloading videos >20MB up to 2GB."""
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "⚡ **Telegram MTProto Setup (Bypass 20MB Limit up to 2GB)**\n\n"
            "To download and analyze full raw videos over 20MB:\n"
            "1. Visit: https://my.telegram.org in your web browser\n"
            "2. Log in with your **personal phone number** (enter the code sent to your Telegram app)\n"
            "3. Click **API development tools**\n"
            "4. Fill in: App title: `ThePublisher`, Short name: `publisher`, Platform: `Other`\n"
            "5. Copy your **api_id** and **api_hash** and send here:\n"
            "`/setmtproto <api_id> <api_hash>`\n\n"
            "*Example:* `/setmtproto 29384751 a1b2c3d4e5f6g7h8i9j0`",
            parse_mode="Markdown"
        )
        return

    api_id_str = args[0].strip()
    api_hash_str = args[1].strip()

    if not api_id_str.isdigit():
        await update.message.reply_text("❌ `api_id` must be numeric (e.g. `29384751`).")
        return

    os.environ["TELEGRAM_API_ID"] = api_id_str
    os.environ["TELEGRAM_API_HASH"] = api_hash_str

    try:
        cfg = {}
        if os.path.exists(BOT_CONFIG_PATH):
            with open(BOT_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        cfg["telegram_api_id"] = api_id_str
        cfg["telegram_api_hash"] = api_hash_str
        with open(BOT_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

    user = update.effective_user
    uid = str(user.id) if user else str(update.effective_chat.id)
    try:
        users = load_all_users()
        u_rec = users.setdefault(uid, {})
        u_rec["telegram_api_id"] = api_id_str
        u_rec["telegram_api_hash"] = api_hash_str
        save_all_users(users, sync_to_vault=False)
    except Exception:
        pass

    await update.message.reply_text(
        f"✅ **MTProto 2GB Engine Activated!**\n\n"
        f"• **API ID:** `{api_id_str}`\n"
        f"• **API Hash:** `{api_hash_str[:6]}...`\n\n"
        f"The bot can now download and analyze full raw videos up to **2 GB**!",
        parse_mode="Markdown"
    )


async def cmd_setbuffer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tok = " ".join(context.args).strip() if context.args else ""
    uid = str(update.effective_chat.id)
    if not tok:
        await update.message.reply_text(
            "🔑 **Buffer Multi-Channel Setup**\n\n"
            "Publish approved reels to **TikTok, Pinterest & X (Twitter)**:\n"
            "1. Get token: `https://publish.buffer.com/settings/api?tab=personal-access`\n"
            "2. Send: `/setbuffer <YOUR_ACCESS_TOKEN>`"
        )
        return
    ok = set_user_buffer_token(uid, tok)
    if ok:
        profiles = get_buffer_profiles(tok, force_refresh=True) or []
        channels = [f"{p.get('service', 'channel').capitalize()} (@{p.get('service_username', p.get('id', '')[:8])})" for p in profiles]
        chan_text = "\n".join([f"  • {c}" for c in channels]) if channels else "  (No channels detected yet in Buffer)"
        await update.message.reply_text(
            f"✅ **Buffer Token Saved Locally in Your Profile!**\n\nConnected channels:\n{chan_text}\n\n"
            "Approved videos will now auto-publish to your Buffer channels!"
        )
    else:
        await update.message.reply_text("❌ Invalid token.")


# ── YouTube Shorts Setup Commands ─────────────────────────────────────────────

async def cmd_setytclient(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sets Google OAuth client_secret JSON for YouTube Data API."""
    uid = str(update.effective_chat.id)
    raw_text = " ".join(context.args).strip() if context.args else ""
    if not raw_text:
        await update.message.reply_text(
            "🔴 **YouTube Shorts Client Setup**\n\n"
            "**Option A (Easiest):** Drag & drop your `client_secret.json` file directly into this chat!\n\n"
            "**Option B (Paste JSON):**\n"
            "`/setytclient <paste contents of client_secret.json>`\n\n"
            "**Option C (Client ID & Secret):**\n"
            "`/setytclient <client_id> <client_secret>`\n\n"
            "Need credentials? Create an OAuth 2.0 Client ID (Desktop App) in Google Cloud Console:\n"
            "👉 `https://console.cloud.google.com/apis/credentials`"
        )
        return

    # Check if raw_text is two arguments (client_id client_secret)
    parts = raw_text.split()
    if len(parts) == 2 and not raw_text.startswith("{"):
        client_dict = {
            "installed": {
                "client_id": parts[0].strip(),
                "client_secret": parts[1].strip(),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
        raw_text = json.dumps(client_dict)

    ok = set_user_youtube_client_secret(uid, raw_text)
    if ok:
        await update.message.reply_text(
            "✅ **YouTube Client Secret Saved!**\n\n"
            "Next Step: Generate your channel authorization link by sending:\n"
            "👉 `/connectyt` (or `/ytlogin`)"
        )
    else:
        await update.message.reply_text("❌ Failed to save YouTube client secret. Please verify JSON format.")


async def cmd_connectyt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generates the Google OAuth authorization URL for YouTube Shorts."""
    import urllib.parse
    uid = str(update.effective_chat.id)
    secret_str = get_user_youtube_client_secret(uid) or os.getenv("CLIENT_SECRET_FILE", "")

    client_id = None
    if secret_str:
        if os.path.isfile(secret_str):
            try:
                with open(secret_str, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    client_id = data.get("installed", {}).get("client_id") or data.get("web", {}).get("client_id")
            except Exception:
                pass
        else:
            try:
                data = json.loads(secret_str)
                client_id = data.get("installed", {}).get("client_id") or data.get("web", {}).get("client_id")
            except Exception:
                pass

    if not client_id:
        await update.message.reply_text(
            "⚠️ **YouTube Client Secret Not Configured**\n\n"
            "Please configure your client credentials first:\n"
            "👉 Drop your `client_secret.json` into this chat, or run `/setytclient`"
        )
        return

    scopes = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.force-ssl"
    redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={urllib.parse.quote(client_id)}&"
        f"redirect_uri={urllib.parse.quote(redirect_uri)}&"
        f"response_type=code&"
        f"scope={urllib.parse.quote(scopes)}&"
        f"access_type=offline&"
        f"prompt=consent"
    )

    await update.message.reply_text(
        f"🔴 **YouTube Channel Authorization**\n\n"
        f"1. 👉 [Click Here to Authorize YouTube]({auth_url})\n\n"
        f"2. Sign in with your YouTube account and tap **Allow**.\n"
        f"3. Copy the authorization code shown on your screen.\n"
        f"4. Send it back here:\n"
        f"`/ytcode <YOUR_CODE>`",
        parse_mode="Markdown"
    )


async def cmd_ytcode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exchanges Google authorization code for YouTube access & refresh token."""
    import urllib.request
    import urllib.parse
    uid = str(update.effective_chat.id)
    code = " ".join(context.args).strip() if context.args else ""
    if not code:
        await update.message.reply_text("Usage: `/ytcode YOUR_AUTHORIZATION_CODE`")
        return

    status_msg = await update.message.reply_text("🔄 **Exchanging code with Google API...**")
    secret_str = get_user_youtube_client_secret(uid) or os.getenv("CLIENT_SECRET_FILE", "")

    client_id = None
    client_secret = None
    if secret_str:
        if os.path.isfile(secret_str):
            try:
                with open(secret_str, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    info = data.get("installed") or data.get("web") or {}
                    client_id, client_secret = info.get("client_id"), info.get("client_secret")
            except Exception:
                pass
        else:
            try:
                data = json.loads(secret_str)
                info = data.get("installed") or data.get("web") or {}
                client_id, client_secret = info.get("client_id"), info.get("client_secret")
            except Exception:
                pass

    if not client_id or not client_secret:
        await status_msg.edit_text("❌ Could not read client_id/client_secret. Please run `/setytclient` first.")
        return

    try:
        token_url = "https://oauth2.googleapis.com/token"
        params = urllib.parse.urlencode({
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
            "grant_type": "authorization_code",
        }).encode("utf-8")

        req = urllib.request.Request(token_url, data=params, headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            token_data = json.loads(resp.read().decode("utf-8"))

        token_data["client_id"] = client_id
        token_data["client_secret"] = client_secret
        token_json_str = json.dumps(token_data)

        ok = set_user_youtube_token(uid, token_json_str)
        if ok:
            await status_msg.edit_text(
                "🎉 **YouTube Shorts Connected Successfully!**\n\n"
                "Your channel is now authorized. Approved videos will be published to YouTube Shorts.\n"
                "Check `/myconfig` to view configuration.",
                parse_mode="Markdown"
            )
        else:
            await status_msg.edit_text("❌ Failed to save YouTube token.")
    except Exception as e:
        logger.error("YouTube code exchange error: %s", e)
        await status_msg.edit_text(f"❌ YouTube authorization error: {e}")


async def cmd_setyttoken(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Saves raw YouTube token.json directly."""
    uid = str(update.effective_chat.id)
    raw_text = " ".join(context.args).strip() if context.args else ""
    if not raw_text:
        await update.message.reply_text("Usage: `/setyttoken <paste token.json content>`\nOr upload your `token.json` file directly.")
        return
    ok = set_user_youtube_token(uid, raw_text)
    if ok:
        await update.message.reply_text("✅ **YouTube Token Saved Successfully!** Channel is active.")
    else:
        await update.message.reply_text("❌ Failed to save YouTube token.")


# ── Meta (Instagram & Facebook) Setup Commands ─────────────────────────────────

async def cmd_connectmeta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """1-Click Meta (Instagram & Facebook) OAuth Setup."""
    uid = str(update.effective_chat.id)
    args = context.args or []

    app_id = None
    app_secret = None
    if len(args) >= 2:
        app_id = args[0].strip()
        app_secret = args[1].strip()
        set_user_meta_app(uid, app_id, app_secret)
    else:
        app_id = get_user_meta_app_id(uid) or os.getenv("META_APP_ID")
        app_secret = get_user_meta_app_secret(uid) or os.getenv("META_APP_SECRET")

    if not app_id or not app_secret:
        await update.message.reply_text(
            "📸 **Meta (Instagram & Facebook) Setup**\n\n"
            "**Option A (1-Click OAuth Connect):**\n"
            "Send your Meta App ID and Secret:\n"
            "`/setmeta <APP_ID> <APP_SECRET>` (or `/connectmeta <APP_ID> <APP_SECRET>`)\n\n"
            "**Option B (Direct Access Token):**\n"
            "If you already have a Page or Instagram access token:\n"
            "• `/instagramtoken <YOUR_TOKEN>`\n"
            "• `/instagramid <YOUR_IG_BUSINESS_ID>`\n"
            "• `/facebooktoken <YOUR_PAGE_TOKEN>`\n"
            "• `/facebookid <YOUR_PAGE_ID>`\n\n"
            "Need a Meta App? Create one at `https://developers.facebook.com/apps`"
        )
        return

    redirect_uri = "https://localhost/"
    auth_url = build_meta_oauth_url(app_id, redirect_uri)
    await update.message.reply_text(
        f"📸 **Meta 1-Click Authorization**\n\n"
        f"1. 👉 [Click Here to Authorize Instagram & Facebook]({auth_url})\n\n"
        f"2. Log in and select your Facebook Page and Instagram Business account.\n"
        f"3. Grant all publishing permissions and tap **Done**.\n"
        f"4. You will be redirected to a page that starts with `https://localhost/?code=...`\n"
        f"5. Copy the entire redirected URL (or just the `code=...` part) and send:\n"
        f"`/metacode <PASTE_REDIRECTED_URL>`",
        parse_mode="Markdown"
    )


async def cmd_metacode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exchanges Meta authorization code and automatically saves Page & Instagram tokens."""
    uid = str(update.effective_chat.id)
    code = " ".join(context.args).strip() if context.args else ""
    if not code:
        await update.message.reply_text("Usage: `/metacode <PASTE_REDIRECTED_URL_OR_CODE>`")
        return

    app_id = get_user_meta_app_id(uid) or os.getenv("META_APP_ID")
    app_secret = get_user_meta_app_secret(uid) or os.getenv("META_APP_SECRET")
    if not app_id or not app_secret:
        await update.message.reply_text("⚠️ Meta App ID or Secret missing. Please run `/setmeta <APP_ID> <APP_SECRET>` first.")
        return

    status_msg = await update.message.reply_text("🔄 **Exchanging code with Meta Graph API & discovering accounts...**")
    auth_res = exchange_meta_oauth_code(code, app_id, app_secret, redirect_uri="https://localhost/")
    if not auth_res.get("success"):
        err = auth_res.get("error", "Unknown error")
        await status_msg.edit_text(f"❌ Meta authorization failed: {err}")
        return

    ok, msg = save_and_sync_meta_credentials(auth_res, uid)
    if ok:
        ig_set = bool(auth_res.get("ig_business_id"))
        fb_set = bool(auth_res.get("meta_page_id"))
        await status_msg.edit_text(
            f"🎉 **Meta Connected Successfully!**\n\n"
            f"📘 Facebook Page: `{'✅ Connected' if fb_set else '❌ Not Found'}`\n"
            f"📸 Instagram Business: `{'✅ Connected' if ig_set else '❌ Not Found'}`\n\n"
            f"Approved reels will now automatically syndicate to your Meta channels!\n"
            f"Check `/myconfig` to view status.",
            parse_mode="Markdown"
        )
    else:
        await status_msg.edit_text(f"❌ Failed to save Meta credentials: {msg}")


async def cmd_instagramtoken(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sets Instagram Business Access Token directly."""
    uid = str(update.effective_chat.id)
    tok = " ".join(context.args).strip() if context.args else ""
    if not tok:
        await update.message.reply_text("Usage: `/instagramtoken <YOUR_ACCESS_TOKEN>`\nAlso remember to set `/instagramid <YOUR_IG_BUSINESS_ID>`.")
        return
    ok = set_user_instagram_token(uid, tok)
    if ok:
        await update.message.reply_text("✅ **Instagram Access Token Saved!**\nNext: Set your business ID via `/instagramid <ID>`")
    else:
        await update.message.reply_text("❌ Failed to save Instagram token.")


async def cmd_instagramid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sets Instagram Business Account ID directly."""
    uid = str(update.effective_chat.id)
    ig_id = " ".join(context.args).strip() if context.args else ""
    if not ig_id:
        await update.message.reply_text("Usage: `/instagramid <YOUR_IG_BUSINESS_ID>`")
        return
    ok = set_user_instagram_id(uid, ig_id)
    if ok:
        await update.message.reply_text("✅ **Instagram Business Account ID Saved!** Check `/myconfig`.")
    else:
        await update.message.reply_text("❌ Failed to save Instagram ID.")


async def cmd_facebooktoken(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sets Facebook Page Access Token directly."""
    uid = str(update.effective_chat.id)
    tok = " ".join(context.args).strip() if context.args else ""
    if not tok:
        await update.message.reply_text("Usage: `/facebooktoken <YOUR_PAGE_TOKEN>`\nAlso remember to set `/facebookid <YOUR_PAGE_ID>`.")
        return
    ok = set_user_facebook_token(uid, tok)
    if ok:
        await update.message.reply_text("✅ **Facebook Page Token Saved!**\nNext: Set your page ID via `/facebookid <ID>`")
    else:
        await update.message.reply_text("❌ Failed to save Facebook Page token.")


async def cmd_facebookid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sets Facebook Page ID directly."""
    uid = str(update.effective_chat.id)
    page_id = " ".join(context.args).strip() if context.args else ""
    if not page_id:
        await update.message.reply_text("Usage: `/facebookid <YOUR_PAGE_ID>`")
        return
    ok = set_user_facebook_id(uid, page_id)
    if ok:
        await update.message.reply_text("✅ **Facebook Page ID Saved!** Check `/myconfig`.")
    else:
        await update.message.reply_text("❌ Failed to save Facebook Page ID.")


async def cmd_setbranding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    brand = " ".join(context.args).strip() if context.args else ""
    uid = str(update.effective_chat.id)
    if not brand:
        await update.message.reply_text("Usage: `/setbranding Your Brand Name`")
        return
    ok = set_user_branding(uid, brand)
    if ok:
        await update.message.reply_text(f"✅ **Brand Watermark set to:** `{brand}`")
    else:
        await update.message.reply_text("❌ Failed to save brand watermark.")


async def cmd_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    guide_text = (
        "📚 **The Publisher Setup Guide**\n\n"
        "• 🌐 **Publishing Channels:**\n"
        "   `/channels` — View active channels & detected accounts\n"
        "   `/setchannels <platforms>` — Choose target platforms (e.g. `tiktok, x, pinterest, linkedin`)\n"
        "   `/syncchannels` — Auto-sync all channels from your Buffer account\n"
        "   `/resetchannels` — Reset to default auto-detection\n\n"
        "• 🔄 **Buffer Integration:**\n"
        "   Generate token at `https://publish.buffer.com/settings/api?tab=personal-access`\n"
        "   Send: `/setbuffer <TOKEN>`\n\n"
        "• 🎨 **SEO Pattern Designer:**\n"
        "   Send `/setpattern <paste post>` to train Gemini on your custom viral caption style.\n\n"
        "• 📦 **Cloud Backup Storage:**\n"
        "   Add bot as Admin to your private group and send `/setstorage` inside it.\n"
        "   Send `/vault` to toggle backup mode on or off.\n\n"
        "• 🤖 **Gemini Multimodal AI:**\n"
        "   Get free API key at `https://aistudio.google.com/app/apikey`\n"
        "   Send: `/setgemini <KEY>`\n\n"
        "• ⚡ **MTProto 2GB High-Speed Engine:**\n"
        "   Send: `/setmtproto <api_id> <api_hash>`\n\n"
        "• 🔴 **YouTube Shorts Setup:**\n"
        "   1. Drop `client_secret.json` into chat (or run `/setytclient`)\n"
        "   2. Send `/connectyt` to get your Google authorization link\n"
        "   3. Send `/ytcode <CODE>` (or paste `/setyttoken <JSON>`)\n\n"
        "• 📸 **Meta (Instagram & Facebook Setup):**\n"
        "   • 1-Click OAuth: `/setmeta <APP_ID> <APP_SECRET>` then `/connectmeta`\n"
        "   • Instagram Direct: `/instagramtoken <TOKEN>` & `/instagramid <ID>`\n"
        "   • Facebook Direct: `/facebooktoken <TOKEN>` & `/facebookid <PAGE_ID>`"
    )
    await update.message.reply_text(guide_text)


async def cmd_vault(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Interactive UI to toggle between Cloud Backup mode vs Fast mode."""
    uid = str(update.effective_chat.id)
    vault_on = is_vault_enabled(uid)

    status_text = (
        "📦 **Cloud Backup: ACTIVE ✅**\nMedia is securely archived in the cloud."
        if vault_on
        else "⚡ **Fast Mode: ACTIVE 🚀**\nMedia is dispatched directly to social channels."
    )
    btn_text = "⚡ Switch to Fast Mode" if vault_on else "📦 Switch to Cloud Backup"
    kbd = InlineKeyboardMarkup([[InlineKeyboardButton(btn_text, callback_data=f"toggle_vault_{uid}")]])

    msg = (
        "⚙️ **Cloud Backup Settings**\n\n"
        f"{status_text}\n\n"
        "• **Backup Mode (ON):** Media files are preserved in your private storage.\n"
        "• **Fast Mode (OFF):** Uploads directly to social platforms."
    )
    await update.message.reply_text(msg, reply_markup=kbd, parse_mode="Markdown")


async def cmd_setpattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Analyzes a user-provided viral post and sets it as the active SEO Blueprint pattern."""
    uid = str(update.effective_chat.id)
    text = " ".join(context.args).strip() if context.args else ""
    if not text:
        bp = get_user_seo_blueprint(uid)
        curr = f"```json\n{json.dumps(bp, indent=2)}\n```" if bp else "*(No custom pattern active — using standard Gemini SEO)*"
        await update.message.reply_text(
            "🎨 **SEO Blueprint Pattern Designer**\n\n"
            "Paste any viral competitor caption or ideal post format, and Gemini will analyze its structure and use it for all your future videos!\n\n"
            f"**Your Current Pattern:**\n{curr}\n\n"
            "**Usage:** `/setpattern <paste example post caption>`\n"
            "**Reset:** `/resetpattern` to restore default."
        )
        return

    status = await update.message.reply_text("🧠 **Analyzing post structure with Gemini AI...**")
    blueprint = extract_blueprint_from_sample(text)
    set_user_seo_blueprint(uid, blueprint)
    await status.edit_text(
        f"✅ **SEO Blueprint Pattern Saved & Active!**\n\n"
        f"**Extracted Structure:**\n"
        f"• Hook Style: `{blueprint.get('hook_style', 'Attention Grabbing')}`\n"
        f"• Structure: `{blueprint.get('body_structure', 'Optimized Value')}`\n"
        f"• CTA: `{blueprint.get('cta', 'Included')}`\n"
        f"• Hashtags: `{blueprint.get('hashtag_count', 6)} tags`\n\n"
        f"All future videos sent from this chat will now follow this exact format!\n"
        f"Send `/resetpattern` anytime to reset.",
        parse_mode="Markdown"
    )


async def cmd_resetpattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resets user SEO blueprint back to default."""
    uid = str(update.effective_chat.id)
    set_user_seo_blueprint(uid, None)
    await update.message.reply_text("🔄 **SEO Blueprint reset to default Gemini AI generator.**")


async def cmd_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays active publishing channels and detected Buffer profiles."""
    uid = str(update.effective_chat.id)
    custom = get_user_active_channels(uid)
    active = get_user_connected_platforms(uid)

    ch_list = ", ".join(c.upper() if len(c) <= 2 else c.capitalize() for c in active)
    custom_desc = "Custom selection active" if custom else "Auto-detected from accounts"

    await update.message.reply_text(
        f"🌐 **Publishing Channels**\n\n"
        f"**Active Target Channels:** `{ch_list}`\n"
        f"**Mode:** `{custom_desc}`\n\n"
        f"**Commands:**\n"
        f"• `/setchannels <platforms>` — Choose specific channels (e.g. `/setchannels tiktok, x, pinterest, linkedin`)\n"
        f"• `/syncchannels` — Auto-sync all channels from your Buffer account\n"
        f"• `/resetchannels` — Reset to default auto-detection\n\n"
        f"Supported: `tiktok`, `pinterest`, `x`, `linkedin`, `instagram`, `youtube`, `facebook`, `telegram`",
        parse_mode="Markdown"
    )


async def cmd_setchannels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sets custom publishing channels for the user."""
    uid = str(update.effective_chat.id)
    raw_args = " ".join(context.args).strip() if context.args else ""
    if not raw_args:
        curr = get_user_active_channels(uid)
        curr_str = ", ".join(c.upper() if len(c) <= 2 else c.capitalize() for c in curr) if curr else "None (Auto-detecting)"
        await update.message.reply_text(
            f"🌐 **Set Publishing Channels**\n\n"
            f"**Current Channels:** `{curr_str}`\n\n"
            f"**Usage:** `/setchannels <platform1, platform2, ...>`\n"
            f"**Example:** `/setchannels tiktok, x, pinterest, linkedin`\n\n"
            f"Supported platforms: `tiktok`, `pinterest`, `x`, `linkedin`, `instagram`, `youtube`, `facebook`, `telegram`"
        )
        return

    parts = re.split(r"[,;\s]+", raw_args)
    clean_parts = [p.strip().lower() for p in parts if p.strip()]
    if not clean_parts:
        await update.message.reply_text("⚠️ No valid channels provided.")
        return

    set_user_active_channels(uid, clean_parts)
    saved = get_user_active_channels(uid) or clean_parts
    ch_display = ", ".join(c.upper() if len(c) <= 2 else c.capitalize() for c in saved)
    await update.message.reply_text(
        f"✅ **Active Publishing Channels Saved!**\n\n"
        f"Target Channels: `{ch_display}`\n\n"
        f"Gemini will now generate platform-tailored SEO tactics and syndicate content strictly to these channels.\n"
        f"Use `/resetchannels` anytime to return to auto-detection.",
        parse_mode="Markdown"
    )


async def cmd_syncchannels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Queries Buffer API and automatically activates all profiles connected to the user's account."""
    uid = str(update.effective_chat.id)
    token = _get_buffer_token(uid)
    if not token:
        await update.message.reply_text(
            "⚠️ **Buffer Access Token Not Configured**\n\n"
            "Please configure your Buffer token first:\n"
            "`/setbuffer <your_access_token>`",
            parse_mode="Markdown"
        )
        return

    status = await update.message.reply_text("🔄 **Querying Buffer API for connected channels...**")
    profiles = get_buffer_profiles(token, force_refresh=True)
    if not profiles:
        await status.edit_text(
            "⚠️ **No channels found in your Buffer account.**\n\n"
            "Please ensure you have linked social channels (TikTok, Pinterest, X, LinkedIn, etc.) in your Buffer dashboard."
        )
        return

    discovered: List[str] = []
    for p in profiles:
        svc = str(p.get("service") or "").lower().strip()
        svc_norm = "x" if svc in ("twitter", "x") else svc
        if svc_norm and svc_norm not in discovered:
            discovered.append(svc_norm)

    set_user_active_channels(uid, discovered)
    ch_display = ", ".join(c.upper() if len(c) <= 2 else c.capitalize() for c in discovered)
    await status.edit_text(
        f"✅ **Buffer Channels Synced & Activated!**\n\n"
        f"Found {len(discovered)} channel(s): `{ch_display}`\n\n"
        f"Gemini will now generate tailored SEO and publish to these channels.",
        parse_mode="Markdown"
    )


async def cmd_resetchannels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resets user active channels back to auto-discovery mode."""
    uid = str(update.effective_chat.id)
    set_user_active_channels(uid, None)
    active = get_user_connected_platforms(uid)
    ch_display = ", ".join(c.upper() if len(c) <= 2 else c.capitalize() for c in active)
    await update.message.reply_text(
        f"🔄 **Channels Reset to Auto-Discovery Mode.**\n\n"
        f"Active Channels: `{ch_display}`",
        parse_mode="Markdown"
    )


# ── Media Handler (Incoming Raw Videos / Photos) ───────────────────────────────

async def handle_incoming_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    chat_id = msg.chat.id
    user_id = str(chat_id)

    # Auto-detect dropped JSON credential files (client_secret.json or token.json)
    if msg.document and msg.document.file_name and msg.document.file_name.lower().endswith(".json"):
        try:
            doc_file = await msg.document.get_file()
            f_bytes = await doc_file.download_as_bytearray()
            f_text = f_bytes.decode("utf-8")
            data = json.loads(f_text)

            # Detect Google client_secret.json
            if "installed" in data or "web" in data:
                set_user_youtube_client_secret(user_id, f_text)
                await msg.reply_text(
                    "✅ **`client_secret.json` Detected & Saved!**\n\n"
                    "Next step: Authorize your YouTube channel by sending:\n"
                    "👉 `/connectyt` (or `/ytlogin`)",
                    parse_mode="Markdown"
                )
                return

            # Detect Google token.json
            if "refresh_token" in data or ("access_token" in data and ("client_id" in data or "token_uri" in data)):
                set_user_youtube_token(user_id, f_text)
                await msg.reply_text(
                    "🎉 **`token.json` Detected & Saved!**\n\n"
                    "YouTube Shorts is now authorized and active for auto-publishing!",
                    parse_mode="Markdown"
                )
                return
        except Exception as _doc_err:
            logger.debug("Document JSON auto-detect notice: %s", _doc_err)

    # 1. Detect media type (Video or Photo)
    is_photo = bool(msg.photo or (msg.document and msg.document.mime_type and msg.document.mime_type.startswith("image/")))
    photo_obj = msg.photo[-1] if msg.photo else (msg.document if is_photo else None)
    video_obj = msg.video or (msg.document if (msg.document and msg.document.mime_type and msg.document.mime_type.startswith("video/")) else None)
    media_obj = photo_obj if is_photo else video_obj
    if not media_obj:
        return

    caption_text = (msg.caption or "").strip()
    vault_on = is_vault_enabled(user_id)
    storage_chat_id = get_user_storage_group_id(user_id) or os.getenv("TELEGRAM_STORAGE_GROUP_ID", "").strip()

    status_prefix = "📦 [Vault Mode]" if vault_on else "⚡ [Direct Fast Mode]"
    status_msg = await msg.reply_text(f"⏳ **Received {'photo' if is_photo else 'video'}!** Analyzing with Gemini AI... ({status_prefix})")

    # 2. Server-side Cloud Relay if Vault is enabled (Zero local storage on phone!)
    vault_file_id = media_obj.file_id
    vault_notice = ""
    if vault_on and storage_chat_id:
        target_ids = []
        try:
            target_ids.append(int(storage_chat_id))
        except Exception:
            target_ids.append(storage_chat_id)
        s_gid = str(storage_chat_id).strip()
        if s_gid.startswith("-100"):
            try:
                target_ids.append(int(f"-{s_gid[4:]}"))
            except Exception:
                pass
        elif s_gid.startswith("-"):
            try:
                target_ids.append(int(f"-100{s_gid[1:]}"))
            except Exception:
                pass

        relay_ok = False
        for candidate_id in target_ids:
            try:
                copied = await context.bot.copy_message(
                    chat_id=candidate_id,
                    from_chat_id=msg.chat.id,
                    message_id=msg.message_id
                )
                logger.info("📦 [CLOUD RELAY] Media copied to vault group %s", candidate_id)
                relay_ok = True
                break
            except Exception as _c_err:
                logger.debug("Cloud relay attempt for %s failed: %s", candidate_id, _c_err)

        if not relay_ok:
            logger.warning("Could not copy media to storage group (%s). Ensure bot is in group as Admin.", storage_chat_id)
            vault_notice = (
                f"\n\n⚠️ *Vault Notice:* Could not copy to storage group `{storage_chat_id}` (Chat not found).\n"
                f"Please ensure the bot is added to your Storage Group as Admin, or run `/setstorage` directly inside that group."
            )

    # 3. Download media for Gemini Full Video Analysis
    ext = ".jpg" if is_photo else ".mp4"
    sess_id = f"sess_{int(time.time())}_{abs(hash(media_obj.file_id)) % 10000}"
    local_path = os.path.join(DOWNLOAD_DIR, f"{sess_id}{ext}")
    used_thumb_fallback = False

    try:
        if is_photo:
            tg_file = await media_obj.get_file()
            await tg_file.download_to_drive(custom_path=local_path)
        else:
            # Full Video Download: Handles files up to 2GB via MTProto engine!
            await download_telegram_document(
                media_obj=media_obj,
                message_obj=msg,
                destination_path=local_path,
                status_msg=status_msg
            )
    except Exception as e:
        logger.warning("Notice downloading full media (%s). Attempting cloud thumbnail fallback...", e)
        thumb_obj = getattr(media_obj, "thumbnail", None)
        if thumb_obj:
            try:
                thumb_file = await context.bot.get_file(thumb_obj.file_id)
                thumb_path = os.path.join(DOWNLOAD_DIR, f"{sess_id}_thumb.jpg")
                await thumb_file.download_to_drive(custom_path=thumb_path)
                local_path = thumb_path
                is_photo = True  # Analyze high-res thumbnail preview
                used_thumb_fallback = True
                logger.info("✅ Resumed successfully via cloud preview thumbnail.")
            except Exception as _th_err:
                logger.error("Thumbnail fallback also failed: %s", _th_err)
                await status_msg.edit_text(f"❌ Failed to download media: {e}")
                return
        else:
            await status_msg.edit_text(f"❌ Failed to download media: {e}")
            return

    # 4. Multimodal Full Video Understanding with Gemini
    visual_intel_summary = analyze_media_for_seo(local_path, is_photo=is_photo, user_id=user_id)

    # 5. Create Session
    session_manager.create_session(
        session_id=sess_id,
        video_path=local_path,
        clip_id=sess_id,
        raw_file_id=media_obj.file_id,
        processed_file_id=vault_file_id,
        requestor_chat_id=chat_id,
        user_id=user_id,
    )

    # 6. Inject Video Visual Intelligence + Custom SEO Blueprint into Platform SEO Generator
    user_blueprint = get_user_seo_blueprint(user_id)
    target_platforms = get_user_connected_platforms(user_id)
    seo_context_parts = []
    if visual_intel_summary:
        seo_context_parts.append(f"Visual Reality of Video: {visual_intel_summary}")
    if caption_text:
        seo_context_parts.append(f"User Hint: {caption_text}")
    if user_blueprint:
        seo_context_parts.append(
            f"MANDATORY STRUCTURAL BLUEPRINT PATTERN: "
            f"Hook Style: {user_blueprint.get('hook_style')}; "
            f"Body Structure: {user_blueprint.get('body_structure')}; "
            f"CTA: {user_blueprint.get('cta')}; "
            f"Hashtags: exactly {user_blueprint.get('hashtag_count', 6)} relevant tags; "
            f"Template: {user_blueprint.get('format_template')}"
        )

    rich_video_context = " | ".join(seo_context_parts) if seo_context_parts else f"Media: {sess_id}"

    seo_res = {}
    try:
        seo_res = generate_platform_seo(
            video_context=rich_video_context,
            user_hint=caption_text,
            platforms=target_platforms,
            affiliate_link=None,
        ) or {}
    except Exception as _seo_err:
        logger.warning("SEO generation notice: %s", _seo_err)

    main_subject = seo_res.get("main_subject") or caption_text or ("Viral Photo" if is_photo else "Viral Reel")
    platforms_dict = seo_res.get("platforms", {})
    first_title = None
    for p_name in target_platforms:
        if platforms_dict.get(p_name, {}).get("title"):
            first_title = platforms_dict[p_name]["title"]
            break
    yt_title = first_title or platforms_dict.get("youtube", {}).get("title") or f"{main_subject} 🌟"
    approved_title = strip_system_and_tracking_tokens(yt_title)

    session_manager.set_seo_result(sess_id, seo_res)
    session_manager.set_approved_title(sess_id, approved_title)

    # 7. Store media file_id & SEO metadata into pool_metadata.json and sync to Telegram Vault
    record_media_to_pool_metadata(
        clip_id=sess_id,
        file_id=vault_file_id,
        title=approved_title,
        seo_data=seo_res,
        user_id=user_id,
    )

    # 8. Deliver Review Card to Chat with Live Vault Toggle
    kbd = build_review_keyboard(sess_id, vault_on=vault_on)
    ch_display = ", ".join(c.upper() if len(c) <= 2 else c.capitalize() for c in target_platforms)
    review_card = (
        f"🎉 **AI Multimodal Full Video Analysis Complete!**\n\n"
        f"📝 **Suggested Title & Hook:**\n`{approved_title}`\n\n"
        f"🌐 **Target Channels:** `{ch_display}`\n"
        f"🎨 **SEO Pattern:** `{'Custom Blueprint' if user_blueprint else 'Default'}`\n"
        f"📦 **Cloud Backup:** `{'Enabled ✅' if vault_on else 'Disabled ⚡'}`\n"
        f"🆔 **Session:** `{sess_id}`\n\n"
        f"Tap **🚀 Post Immediately** to syndicate across your connected channels, or tap **📦 Vault / ⚡ Fast** to toggle mode."
    )
    if vault_notice:
        review_card += vault_notice
    if used_thumb_fallback:
        review_card += (
            "\n\n💡 *Note:* Video is >20MB. Analyzed using cloud preview thumbnail.\n"
            "To unlock downloading full raw videos >20MB up to 2GB, link your Telegram API credentials:\n"
            "`/setmtproto <api_id> <api_hash>`"
        )
    await status_msg.delete()
    await msg.reply_text(review_card, reply_markup=kbd, parse_mode="Markdown")


# ── Text & Directives Handler ──────────────────────────────────────────────────

async def handle_incoming_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return

    chat_id = msg.chat.id
    user_id = str(chat_id)
    text_in = msg.text.strip()

    pending_sess = session_manager.get_pending_title_session(chat_id)
    if pending_sess:
        sess_id = pending_sess["session_id"]
        v_path = pending_sess.get("video_path")

        session_manager.set_approved_title(sess_id, text_in)
        status_msg = await msg.reply_text(f"🚀 Title set to: **{text_in}**\nBroadcasting across connected channels...")

        try:
            res = await run_phase4_publishing_async(
                video_path=v_path,
                title=text_in,
                user_id=user_id,
                seo_data=pending_sess.get("seo_result"),
            )
            success_count = res.get("published_count", 0)
            await status_msg.edit_text(
                f"🎉 **Publishing Complete!** (Published to {success_count} platforms)\n\n"
                f"Check your social channels or `/myconfig` to view configuration."
            )
        except Exception as e:
            logger.error("Publishing error: %s", e)
            await status_msg.edit_text(f"⚠️ Publishing encountered an error: {e}")
        finally:
            if v_path and os.path.exists(v_path):
                _safe_remove(v_path)
        return


# ── Callback Query Handler (Inline Buttons) ────────────────────────────────────

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    chat_id = query.message.chat_id
    user_id = str(chat_id)

    if data.startswith("pub_now_"):
        sess_id = data.replace("pub_now_", "")
        sess = session_manager.get_session(sess_id)
        if not sess:
            await query.edit_message_text("⚠️ Session expired or not found.")
            return

        v_path = sess.get("video_path")
        title = sess.get("approved_title") or sess.get("suggested_title") or "Viral Reel"

        await query.edit_message_text(f"🚀 **Publishing live:** '{title}'\nBroadcasting across all configured channels...")

        try:
            res = await run_phase4_publishing_async(
                video_path=v_path,
                title=title,
                user_id=user_id,
                seo_data=sess.get("seo_result"),
            )
            success_count = res.get("published_count", 0)
            await query.edit_message_text(
                f"🎉 **Broadcast Complete!**\n"
                f"Successfully dispatched to {success_count} platform(s)."
            )
        except Exception as e:
            logger.error("Broadcast error: %s", e)
            await query.edit_message_text(f"⚠️ Broadcast error: {e}")
        finally:
            if v_path and os.path.exists(v_path):
                _safe_remove(v_path)

    elif data.startswith("pub_title_"):
        sess_id = data.replace("pub_title_", "")
        session_manager.set_awaiting_title(sess_id)
        await query.edit_message_text(
            "✏️ **Please type and send your desired title or caption in chat.**\n\n"
            "You can also include directives like `/trail_reels`, `/collab @user`, or an affiliate URL!"
        )

    elif data.startswith("pub_discard_"):
        sess_id = data.replace("pub_discard_", "")
        sess = session_manager.get_session(sess_id)
        if sess:
            v_path = sess.get("video_path")
            if v_path and os.path.exists(v_path):
                _safe_remove(v_path)
        session_manager.set_rejected(sess_id)
        await query.edit_message_text("🗑️ **Post discarded and local storage purged.**")

    elif data.startswith("toggle_v_"):
        sess_id = data.replace("toggle_v_", "")
        curr_vault = is_vault_enabled(user_id)
        new_vault = not curr_vault
        set_user_vault_mode(user_id, new_vault)
        new_kbd = build_review_keyboard(sess_id, vault_on=new_vault)
        try:
            await query.edit_message_reply_markup(reply_markup=new_kbd)
        except Exception:
            pass

    elif data.startswith("toggle_vault_"):
        curr_vault = is_vault_enabled(user_id)
        new_vault = not curr_vault
        set_user_vault_mode(user_id, new_vault)
        gid = get_user_storage_group_id(user_id)
        status_text = (
            "📦 **Cloud Backup: ACTIVE ✅**\nMedia is securely archived in the cloud."
            if new_vault
            else "⚡ **Fast Mode: ACTIVE 🚀**\nMedia is dispatched directly to social channels."
        )
        btn_text = "⚡ Switch to Fast Mode" if new_vault else "📦 Switch to Cloud Backup"
        kbd = InlineKeyboardMarkup([[InlineKeyboardButton(btn_text, callback_data=f"toggle_vault_{user_id}")]])
        msg_text = (
            "⚙️ **Cloud Backup Settings**\n\n"
            f"{status_text}\n\n"
            "• **Backup Mode (ON):** Media files are preserved in your private storage.\n"
            "• **Fast Mode (OFF):** Uploads directly to social platforms."
        )
        try:
            await query.edit_message_text(msg_text, reply_markup=kbd, parse_mode="Markdown")
        except Exception:
            pass


# ── Main Entry Point ───────────────────────────────────────────────────────────

def main():
    token = resolve_bot_token()

    # Hydrate users and ensure vault index and pool metadata exist on local disk
    try:
        load_all_users()
        from Telegram_Storage_Modules.telegram_vault_indexer import TelegramVaultIndexer
        indexer = TelegramVaultIndexer()
        # Ensure pool_metadata.json physically exists on disk
        if not os.path.exists(POOL_METADATA_PATH):
            with open(POOL_METADATA_PATH, "w", encoding="utf-8") as _pf:
                json.dump({}, _pf, indent=2)
        indexer.hydrate_all_vault_jsons_on_startup()
    except Exception as _h_err:
        logger.debug("Startup vault hydration notice: %s", _h_err)

    app = ApplicationBuilder().token(token).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("myconfig", cmd_myconfig))
    app.add_handler(CommandHandler("vault", cmd_vault))
    app.add_handler(CommandHandler("channels", cmd_channels))
    app.add_handler(CommandHandler("setchannels", cmd_setchannels))
    app.add_handler(CommandHandler("syncchannels", cmd_syncchannels))
    app.add_handler(CommandHandler("resetchannels", cmd_resetchannels))
    app.add_handler(CommandHandler("setpattern", cmd_setpattern))
    app.add_handler(CommandHandler("resetpattern", cmd_resetpattern))
    app.add_handler(CommandHandler("setstorage", cmd_setstorage))
    app.add_handler(CommandHandler("setgroup", cmd_setstorage))
    app.add_handler(CommandHandler("setgemini", cmd_setgemini))
    app.add_handler(CommandHandler("setmtproto", cmd_setmtproto))
    app.add_handler(CommandHandler("setbuffer", cmd_setbuffer))
    app.add_handler(CommandHandler("buffertoken", cmd_setbuffer))
    app.add_handler(CommandHandler("setbranding", cmd_setbranding))
    app.add_handler(CommandHandler("guide", cmd_guide))

    # YouTube Shorts Setup
    app.add_handler(CommandHandler("setytclient", cmd_setytclient))
    app.add_handler(CommandHandler("ytclient", cmd_setytclient))
    app.add_handler(CommandHandler("connectyt", cmd_connectyt))
    app.add_handler(CommandHandler("ytlogin", cmd_connectyt))
    app.add_handler(CommandHandler("ytcode", cmd_ytcode))
    app.add_handler(CommandHandler("setyttoken", cmd_setyttoken))
    app.add_handler(CommandHandler("yttoken", cmd_setyttoken))

    # Meta (Instagram & Facebook) Setup
    app.add_handler(CommandHandler("connectmeta", cmd_connectmeta))
    app.add_handler(CommandHandler("setmeta", cmd_connectmeta))
    app.add_handler(CommandHandler("metacode", cmd_metacode))
    app.add_handler(CommandHandler("instagramtoken", cmd_instagramtoken))
    app.add_handler(CommandHandler("setigtoken", cmd_instagramtoken))
    app.add_handler(CommandHandler("instagramid", cmd_instagramid))
    app.add_handler(CommandHandler("setigid", cmd_instagramid))
    app.add_handler(CommandHandler("facebooktoken", cmd_facebooktoken))
    app.add_handler(CommandHandler("setfbtoken", cmd_facebooktoken))
    app.add_handler(CommandHandler("facebookid", cmd_facebookid))
    app.add_handler(CommandHandler("setfbid", cmd_facebookid))

    # Media and Messages (Supports Videos, Photos, and Documents)
    app.add_handler(MessageHandler(filters.VIDEO | filters.PHOTO | filters.Document.ALL, handle_incoming_media))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_incoming_text))
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    print("\n" + "=" * 65)
    print("🚀 THE PUBLISHER — Zero-Env Autonomous Localhost Bot")
    print("=" * 65)
    print(f"📁 Local Root:      {_REPO_ROOT}")
    print(f"🔒 Virtual .ENV:    {os.path.join(DATA_DIR, 'telegram_users.json')}")
    print(f"📦 Master Vault:    {VAULT_INDEX_PATH}")
    print(f"📊 Pool Metadata:   {POOL_METADATA_PATH}")
    print("🤖 Bot Service:     ONLINE (Send any video directly to your bot)")
    print("=" * 65 + "\n")

    import signal
    def _sudden_shutdown(signum=None, frame=None):
        print("\n🛑 [SHUTDOWN] Sudden shutdown triggered via Ctrl+C. Exiting immediately.\n")
        os._exit(0)

    try:
        signal.signal(signal.SIGINT, _sudden_shutdown)
    except Exception:
        pass

    try:
        app.run_polling(drop_pending_updates=True)
    except (KeyboardInterrupt, SystemExit):
        _sudden_shutdown()


if __name__ == "__main__":
    main()
