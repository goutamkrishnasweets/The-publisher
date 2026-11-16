"""
Publishing_Modules / buffer_publisher.py
================================================================================
Buffer API v1 Publishing Client — TikTok, Pinterest & X (Twitter) Channels.

Automatically discovers your connected Buffer channels and dispatches approved
video reels to TikTok, Pinterest, and X (Twitter) using Buffer's REST API.

Configuration (via .env or GitHub Secrets):
  BUFFER_ACCESS_TOKEN = "<your_personal_access_token>"
  (Generate from: https://publish.buffer.com/settings/api?tab=personal-access)

Optional per-channel overrides (auto-discovered from Buffer API if not set):
  BUFFER_TIKTOK_PROFILE_ID  = "..."  # Buffer profile ID for your TikTok channel
  BUFFER_PINTEREST_PROFILE_ID = "..." # Buffer profile ID for your Pinterest channel
  BUFFER_X_PROFILE_ID        = "..."  # Buffer profile ID for your X/Twitter channel

Platform Caption Limits enforced:
  X / Twitter : 280 chars max
  TikTok      : 2200 chars max (uses video upload URL, not direct file)
  Pinterest   : 500 chars max pin description; 100 chars max title

Usage in Phase 4 (via media_publisher_main.py):
  from Publishing_Modules.buffer_publisher import publish_to_buffer, is_buffer_configured
"""

import os
import sys
import json
import time
import logging
import urllib.request
import urllib.parse
from typing import Dict, Any, Optional, List

logger = logging.getLogger("buffer_publisher")
logger.setLevel(logging.INFO)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_REPO_ROOT, ".env"), override=False)
    load_dotenv(os.path.join(_REPO_ROOT, "Credentials", ".env"), override=False)
except ImportError:
    pass

# ── Buffer API Base ────────────────────────────────────────────────────────────
_BUFFER_API_BASE = "https://api.bufferapp.com/1"

# X/Twitter hard character ceiling (enforced by platform)
_X_CAPTION_LIMIT = 280

def _normalize_service_name(svc: str) -> str:
    """Normalizes Buffer service identifiers (e.g. 'twitter' -> 'x')."""
    s = str(svc or "").lower().strip()
    if s in ("twitter", "x"):
        return "x"
    return s


# Cache discovered profiles for the process lifetime to avoid repeated API calls
_profile_cache: Optional[List[Dict[str, Any]]] = None


# ── Token Resolution ───────────────────────────────────────────────────────────

def _get_buffer_token(user_id: Optional[str] = None) -> Optional[str]:
    """
    Resolves Buffer Personal Access Token.
    Non-admin users get their own token from telegram_users.json if set.
    Admin falls back to BUFFER_ACCESS_TOKEN env var.
    """
    if user_id:
        try:
            from Telegram_Storage_Modules.telegram_user_manager import get_user_field, _is_admin_user
            tok = get_user_field(str(user_id), "buffer_access_token")
            if tok and str(tok).strip():
                return str(tok).strip()
            # Non-admin users do NOT inherit admin token
            if not _is_admin_user(str(user_id)):
                return None
        except Exception:
            pass
    return os.getenv("BUFFER_ACCESS_TOKEN", "").strip() or None


def is_buffer_configured(user_id: Optional[str] = None) -> bool:
    """Returns True if a Buffer access token is available for this user/admin."""
    return bool(_get_buffer_token(user_id))


# ── Channel Discovery ──────────────────────────────────────────────────────────

def get_buffer_profiles(token: str, force_refresh: bool = False) -> List[Dict[str, Any]]:
    """
    Fetches all connected Buffer profiles using GET /1/profiles.json.
    Results are cached for the process lifetime to avoid redundant calls.
    """
    global _profile_cache
    if _profile_cache is not None and not force_refresh:
        return _profile_cache

    url = f"{_BUFFER_API_BASE}/profiles.json?access_token={urllib.parse.quote(token)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GeminiEditor-BufferPublisher/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            profiles = json.loads(resp.read().decode("utf-8"))

        if isinstance(profiles, list):
            logger.info(
                "🔍 [Buffer] Discovered %d connected channel(s): %s",
                len(profiles),
                [f"{_normalize_service_name(p.get('service'))}:{p.get('id', '')[:8]}" for p in profiles]
            )
            _profile_cache = profiles
            return profiles

        logger.warning("⚠️ [Buffer] Unexpected profiles response type: %s", type(profiles))
        return []
    except Exception as e:
        logger.error("❌ [Buffer] Profile discovery error: %s", e)
        return []


def _resolve_profile_ids(
    token: str,
    tiktok_pid: Optional[str] = None,
    pinterest_pid: Optional[str] = None,
    x_pid: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, List[str]]:
    """
    Returns resolved profile IDs for ALL Buffer-connected channels dynamically.
    Maps service names (e.g. 'twitter' -> 'x', 'tiktok' -> 'tiktok', 'pinterest' -> 'pinterest', 'linkedin' -> 'linkedin').
    Explicit overrides from env/args take precedence; falls back to auto-discovery.
    """
    resolved: Dict[str, List[str]] = {}

    profiles = get_buffer_profiles(token)
    for p in profiles:
        svc = _normalize_service_name(p.get("service", ""))
        pid = p.get("id")
        if svc and pid:
            resolved.setdefault(svc, []).append(pid)

    # Use explicit overrides if present
    env_tiktok = tiktok_pid or os.getenv("BUFFER_TIKTOK_PROFILE_ID", "").strip()
    env_pinterest = pinterest_pid or os.getenv("BUFFER_PINTEREST_PROFILE_ID", "").strip()
    env_x = x_pid or os.getenv("BUFFER_X_PROFILE_ID", "").strip()
    env_linkedin = os.getenv("BUFFER_LINKEDIN_PROFILE_ID", "").strip()

    if env_tiktok:
        resolved["tiktok"] = [env_tiktok]
    if env_pinterest:
        resolved["pinterest"] = [env_pinterest]
    if env_x:
        resolved["x"] = [env_x]
    if env_linkedin:
        resolved["linkedin"] = [env_linkedin]

    return resolved


# ── Caption Formatters ─────────────────────────────────────────────────────────

def _format_x_caption(title: str, caption: str, tags: str, affiliate_link: Optional[str]) -> str:
    """
    Builds an X (Twitter) post text that fits inside 280 characters.
    Priority: punchy hook from title → primary hashtags → affiliate link.
    """
    # Extract up to 2 hashtags
    all_tags = [t for t in (tags or "").split() if t.startswith("#")]
    top_tags = " ".join(all_tags[:2])

    # Base: short title + top tags
    base = f"{title} {top_tags}".strip()

    # Append affiliate link if space allows (URLs count as ~23 chars in Twitter)
    link_part = f"\n{affiliate_link}" if affiliate_link else ""

    text = f"{base}{link_part}"
    if len(text) <= _X_CAPTION_LIMIT:
        return text

    # Trim title to fit
    budget = _X_CAPTION_LIMIT - len(top_tags) - len(link_part) - 2  # 2 = spaces
    trimmed_title = title[:max(budget, 20)].rstrip()
    if len(trimmed_title) < len(title):
        trimmed_title = trimmed_title[:trimmed_title.rfind(" ")] + "…" if " " in trimmed_title else trimmed_title + "…"
    return f"{trimmed_title} {top_tags}{link_part}".strip()[:_X_CAPTION_LIMIT]


def _format_pinterest_caption(title: str, caption: str, tags: str) -> Dict[str, str]:
    """Returns pin title (≤100 chars) and pin description (≤500 chars)."""
    pin_title = title[:100].strip()
    pin_desc = caption[:500].strip() if caption else f"{title}\n\n{tags}"[:500]
    return {"title": pin_title, "description": pin_desc}


def _format_tiktok_caption(title: str, caption: str, tags: str, affiliate_link: Optional[str]) -> str:
    """Builds TikTok caption ≤2200 chars with energy hook + hashtags + affiliate link."""
    base = caption.strip() if caption.strip() else f"🔥 {title}"
    if tags:
        all_tags = [t for t in tags.split() if t.startswith("#")]
        tag_str = " ".join(all_tags[:20])  # TikTok: 20 hashtags is a practical limit
        if tag_str not in base:
            base = f"{base}\n\n{tag_str}"
    if affiliate_link and affiliate_link not in base:
        base = f"{base}\n🛒 {affiliate_link}"
    return base[:2200]


def _format_linkedin_caption(title: str, caption: str, tags: str, affiliate_link: Optional[str]) -> str:
    """Builds LinkedIn post (≤3000 chars) with headline hook + formatted body + tags + link."""
    base = caption.strip() if caption.strip() else title.strip()
    if title and title not in base:
        base = f"💡 {title}\n\n{base}"
    if tags:
        all_tags = [t for t in tags.split() if t.startswith("#")]
        tag_str = " ".join(all_tags[:5])
        if tag_str not in base:
            base = f"{base}\n\n{tag_str}"
    if affiliate_link and affiliate_link not in base:
        base = f"{base}\n\n🔗 Resource: {affiliate_link}"
    return base[:3000]


def _format_generic_caption(title: str, caption: str, tags: str, affiliate_link: Optional[str], max_len: int = 2200) -> str:
    """General caption formatter for any connected channel (≤max_len chars)."""
    base = caption.strip() if caption.strip() else title.strip()
    if title and title not in base:
        base = f"{title}\n\n{base}"
    if tags and tags not in base:
        base = f"{base}\n\n{tags}"
    if affiliate_link and affiliate_link not in base:
        base = f"{base}\n\n🔗 {affiliate_link}"
    return base[:max_len]


# ── Buffer API Dispatcher ──────────────────────────────────────────────────────

def _post_to_buffer(
    token: str,
    profile_ids: List[str],
    text: str,
    media: Optional[Dict[str, str]] = None,
    link: Optional[str] = None,
    now: bool = True,
) -> Dict[str, Any]:
    """
    Posts to Buffer via POST /1/updates/create.json.
    Args:
        token       : Buffer Personal Access Token.
        profile_ids : List of Buffer profile IDs to broadcast to.
        text        : Caption / post text.
        media       : Optional dict with 'link' (video URL) for video posts.
        link        : Optional URL to attach as a web link (Pinterest pin dest URL).
        now         : If True, publishes immediately (not queued in Buffer calendar).
    Returns:
        dict with 'status', 'updates', 'raw_response'.
    """
    if not profile_ids:
        return {"status": "skipped", "reason": "No matching Buffer profile IDs found for this channel."}

    params: Dict[str, Any] = {
        "access_token": token,
        "text": text,
        "now": "true" if now else "false",
    }
    for i, pid in enumerate(profile_ids):
        params[f"profile_ids[{i}]"] = pid

    if media:
        for k, v in media.items():
            params[f"media[{k}]"] = v

    if link:
        params["media[link]"] = link

    endpoint = f"{_BUFFER_API_BASE}/updates/create.json"
    encoded_data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=encoded_data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "GeminiEditor-BufferPublisher/1.0",
        },
        method="POST",
    )

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                status_code = resp.getcode()
                raw = resp.read().decode("utf-8")
                data = json.loads(raw)

            if status_code in (200, 201, 202) and data.get("success"):
                updates = data.get("updates", [])
                update_id = updates[0].get("id", "") if updates else ""
                logger.info("✅ [Buffer] Post accepted (attempt %d). Update ID: %s", attempt, update_id)
                return {"status": "success", "update_id": update_id, "updates": updates, "raw_response": data}

            logger.warning(
                "⚠️ [Buffer] Unexpected HTTP %d response (attempt %d): %s",
                status_code, attempt, raw[:200],
            )
            return {"status": "failed", "error": raw[:300], "status_code": status_code}

        except urllib.error.HTTPError as http_err:
            err_body = http_err.read().decode("utf-8", errors="ignore") if http_err.fp else ""
            logger.error(
                "❌ [Buffer] HTTP %d error (attempt %d): %s",
                http_err.code, attempt, err_body[:300],
            )
            if http_err.code in (401, 403):
                return {
                    "status": "failed",
                    "error": "Buffer auth failed — check BUFFER_ACCESS_TOKEN.",
                    "status_code": http_err.code,
                }
            if attempt < max_retries:
                time.sleep(2.0 * attempt)
        except Exception as e:
            logger.error("❌ [Buffer] Dispatch error (attempt %d): %s", attempt, e)
            if attempt < max_retries:
                time.sleep(2.0 * attempt)

    return {"status": "failed", "error": f"Failed to post to Buffer after {max_retries} attempts."}


# ── Public URL Resolution via Telegram Vault ──────────────────────────────────

_PUBLIC_URL_CACHE: Dict[str, str] = {}


def _upload_fallback_tmpfiles(local_path: str) -> Optional[str]:
    """Fallback public uploader if file exceeds Telegram Bot API 20MB download limit."""
    try:
        import mimetypes
        import uuid

        boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
        filename = os.path.basename(local_path)
        mime = mimetypes.guess_type(local_path)[0] or "video/mp4"

        with open(local_path, "rb") as f:
            file_bytes = f.read()

        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

        req = urllib.request.Request(
            "https://tmpfiles.org/api/v1/upload",
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "BufferPublisher/1.0"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            if res.get("status") == "success" and res.get("data", {}).get("url"):
                raw_url = res["data"]["url"]
                dl_url = raw_url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
                logger.info("🌐 [Buffer] Resolved public fallback URL via tmpfiles: %s", dl_url)
                return dl_url
    except Exception as e:
        logger.debug(f"[Buffer] Fallback upload notice: {e}")
    return None


def resolve_public_media_url(local_path_or_url: str, user_id: Optional[str] = None) -> Optional[str]:
    """
    Ensures media is accessible via a public HTTP(S) URL for Buffer / social networks.
    If already a URL, returns as-is.
    If a local file, obtains its Telegram Bot API direct download link:
      https://api.telegram.org/file/bot{TOKEN}/{file_path}
    Falls back to direct temporary hosting if file exceeds 20MB.
    Caches resolved URLs to eliminate redundant uploads.
    """
    if not local_path_or_url:
        return None

    if str(local_path_or_url).startswith(("http://", "https://")):
        return str(local_path_or_url)

    if local_path_or_url in _PUBLIC_URL_CACHE:
        return _PUBLIC_URL_CACHE[local_path_or_url]

    if not os.path.isfile(local_path_or_url):
        logger.warning(f"⚠️ [Buffer] File does not exist locally: {local_path_or_url}")
        return None

    file_size_mb = os.path.getsize(local_path_or_url) / (1024 * 1024)

    # Telegram Bot API getFile has a hard 20MB file download limit
    if file_size_mb > 20.0:
        logger.info(f"📦 [Buffer] File is {file_size_mb:.1f}MB (>20MB Telegram limit). Using direct public uploader...")
        fallback_url = _upload_fallback_tmpfiles(local_path_or_url)
        if fallback_url:
            _PUBLIC_URL_CACHE[local_path_or_url] = fallback_url
            return fallback_url

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    storage_chat_id = os.getenv("TELEGRAM_STORAGE_GROUP_ID", "").strip()

    if user_id:
        try:
            from Telegram_Storage_Modules.telegram_user_manager import get_user_storage_group_id
            u_storage = get_user_storage_group_id(user_id)
            if u_storage:
                storage_chat_id = str(u_storage).strip()
        except Exception:
            pass

    clean_token = bot_token[3:] if bot_token.startswith("bot") else bot_token

    if not clean_token or not storage_chat_id:
        logger.warning("⚠️ [Buffer] TELEGRAM_BOT_TOKEN or TELEGRAM_STORAGE_GROUP_ID missing. Cannot resolve public URL via Telegram.")
        return _upload_fallback_tmpfiles(local_path_or_url)

    try:
        # Step 1: Check if file was already uploaded in active session
        file_id = None
        try:
            from Telegram_Storage_Modules.telegram_session_manager import session_manager
            c_name = os.path.basename(local_path_or_url).replace("_master.mp4", "").replace(".mp4", "")
            for s in session_manager.sessions.values():
                if s.get("processed_file_id") and (s.get("clip_id") == c_name or s.get("video_path") == local_path_or_url):
                    file_id = s.get("processed_file_id")
                    logger.info("⚡ [Buffer] Reusing cached Telegram vault file_id: %s", file_id[:20] + "...")
                    break
        except Exception:
            file_id = None

        # Upload to Telegram Storage Group if not already recorded
        if not file_id:
            from Telegram_Storage_Modules.telegram_http import send_document, extract_file_id

            doc_res = send_document(
                local_path=local_path_or_url,
                chat_id=storage_chat_id,
                caption="📦 Media for Buffer Dispatch"
            )
            if doc_res and isinstance(doc_res, dict):
                file_id = extract_file_id(doc_res)
                if not file_id:
                    res_obj = doc_res.get("result", {})
                    file_id = extract_file_id(res_obj)

        if not file_id:
            logger.warning("⚠️ [Buffer] Failed to upload media to Telegram for public URL resolution. Trying fallback...")
            return _upload_fallback_tmpfiles(local_path_or_url)

        # Step 2: Get direct file_path from Telegram Bot API
        get_file_url = f"https://api.telegram.org/bot{clean_token}/getFile?file_id={file_id}"
        req = urllib.request.Request(get_file_url, headers={"User-Agent": "BufferPublisher/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if data.get("ok") and data.get("result", {}).get("file_path"):
            remote_file_path = data["result"]["file_path"]
            public_url = f"https://api.telegram.org/file/bot{clean_token}/{remote_file_path}"
            logger.info("🌐 [Buffer] Resolved public media URL: %s", public_url[:40] + "...")
            _PUBLIC_URL_CACHE[local_path_or_url] = public_url
            return public_url
        else:
            logger.warning("⚠️ [Buffer] Telegram getFile did not return a file_path. Trying fallback...")
            fallback_url = _upload_fallback_tmpfiles(local_path_or_url)
            if fallback_url:
                _PUBLIC_URL_CACHE[local_path_or_url] = fallback_url
            return fallback_url
    except Exception as e:
        logger.warning(f"⚠️ [Buffer] Public URL resolution error: {e}. Trying fallback...")
        fallback_url = _upload_fallback_tmpfiles(local_path_or_url)
        if fallback_url:
            _PUBLIC_URL_CACHE[local_path_or_url] = fallback_url
        return fallback_url


def _resolve_media_url(video_path: str, user_id: Optional[str] = None) -> Optional[str]:
    """Alias for resolve_public_media_url."""
    return resolve_public_media_url(video_path, user_id=user_id)


# ── Main Publish Entry Point ───────────────────────────────────────────────────

def publish_to_buffer(
    video_path: str,
    title: str = "",
    description: str = "",
    tags: str = "",
    seo_data: Optional[Dict[str, Any]] = None,
    affiliate_link: Optional[str] = None,
    user_id: Optional[str] = None,
    channels: Optional[List[str]] = None,
    now: bool = True,
) -> Dict[str, Any]:
    """
    Publishes an approved reel to Buffer-connected channels: TikTok, Pinterest, X (Twitter).

    Args:
        video_path     : Local path to the master reel video file.
        title          : Human-approved video title (required).
        description    : Full caption / description text.
        tags           : Space-separated hashtag string (e.g. "#fashion #viral").
        seo_data       : Optional SEO dict from generate_platform_seo() — extracts
                         platform-specific captions and hashtags if present.
        affiliate_link : Primary affiliate/product link (optional).
        user_id        : Telegram user ID for per-user credential resolution.
        channels       : Explicit list of channels to target e.g. ['tiktok', 'x'].
                         Defaults to all three: ['tiktok', 'pinterest', 'x'].
        now            : If True, posts immediately. If False, adds to Buffer queue.

    Returns:
        dict: {
            "status": "success" | "partial" | "failed" | "skipped",
            "published_to": ["tiktok", ...],
            "failed_on": [...],
            "results": {
                "tiktok":    {"status": "success", "update_id": ...},
                "pinterest": {"status": "skipped", ...},
                "x":         {"status": "success", "update_id": ...},
            }
        }
    """
    token = _get_buffer_token(user_id)
    if not token:
        logger.info("ℹ️ [Buffer] BUFFER_ACCESS_TOKEN not configured. Skipping Buffer broadcast.")
        return {"status": "skipped", "reason": "BUFFER_ACCESS_TOKEN not set. Set via /setbuffer <token>."}

    target_channels = set(channels or ["tiktok", "pinterest", "x"])
    logger.info(
        "🚀 [Buffer] Starting broadcast to: %s (user=%s)",
        ", ".join(sorted(target_channels)), user_id or "admin"
    )

    # ── 1. Resolve public video URL ───────────────────────────────────────────
    video_url = _resolve_media_url(video_path, user_id=user_id)
    if not video_url:
        logger.error("❌ [Buffer] Could not resolve a public video URL for: %s", video_path)
        return {"status": "failed", "error": "Failed to resolve a public video URL for Buffer."}

    # ── 2. Extract platform-specific SEO content ──────────────────────────────
    platforms_seo = (seo_data or {}).get("platforms", {})
    aff_links = list((seo_data or {}).get("_affiliate_links", []) or [])
    if affiliate_link and affiliate_link not in aff_links:
        aff_links.insert(0, affiliate_link)
    primary_aff = aff_links[0] if aff_links else None

    # ── 3. Discover Buffer profile IDs ────────────────────────────────────────
    profile_ids = _resolve_profile_ids(token)
    logger.info(
        "📋 [Buffer] Discovered active services: %s",
        ", ".join(profile_ids.keys()) if profile_ids else "None"
    )

    if channels:
        target_channels = [_normalize_service_name(c) for c in channels]
    else:
        # Default to whatever services are actually connected in Buffer
        target_channels = list(profile_ids.keys()) if profile_ids else ["tiktok", "pinterest", "x"]

    logger.info(
        "🚀 [Buffer] Starting broadcast to: %s (user=%s)",
        ", ".join(sorted(target_channels)), user_id or "admin"
    )

    results: Dict[str, Dict[str, Any]] = {}
    published_to: List[str] = []
    failed_on: List[str] = []

    for ch in target_channels:
        pids = profile_ids.get(ch, [])
        if not pids:
            logger.warning("⚠️ [Buffer] No profile found for channel '%s' in Buffer account.", ch)
            results[ch] = {"status": "skipped", "reason": f"No profile found for '{ch}' in Buffer account."}
            continue

        ch_seo = platforms_seo.get(ch, {})
        ch_title = (ch_seo.get("title") or title).strip()
        ch_caption = (ch_seo.get("description") or ch_seo.get("caption") or description or f"{title}\n\n{tags}").strip()
        ch_tags = " ".join(ch_seo.get("hashtags", [])) if ch_seo.get("hashtags") else tags

        if ch == "tiktok":
            caption_tt = _format_tiktok_caption(title, ch_caption, ch_tags, primary_aff)
            media_tt = {"link": video_url, "picture": video_url, "title": title[:100]}
            logger.info("📱 [Buffer → TikTok] Posting: '%s'...", caption_tt[:60])
            tt_res = _post_to_buffer(token=token, profile_ids=pids, text=caption_tt, media=media_tt, now=now)
            results["tiktok"] = tt_res
            (published_to if tt_res.get("status") == "success" else failed_on).append("tiktok")

        elif ch == "pinterest":
            pin_texts = _format_pinterest_caption(ch_title or title, ch_caption, ch_tags)
            media_pin = {
                "link": video_url,
                "picture": video_url,
                "title": pin_texts["title"],
                "description": pin_texts["description"],
            }
            pin_dest_link = primary_aff or video_url
            logger.info("📌 [Buffer → Pinterest] Posting pin: '%s'...", pin_texts["title"])
            pin_res = _post_to_buffer(
                token=token, profile_ids=pids, text=pin_texts["description"],
                media=media_pin, link=pin_dest_link, now=now
            )
            results["pinterest"] = pin_res
            (published_to if pin_res.get("status") == "success" else failed_on).append("pinterest")

        elif ch in ("x", "twitter"):
            caption_x = _format_x_caption(ch_title or title, ch_caption, ch_tags, primary_aff)
            media_x = {"link": video_url, "picture": video_url}
            logger.info("🐦 [Buffer → X] Posting: '%s'...", caption_x[:60])
            x_res = _post_to_buffer(token=token, profile_ids=pids, text=caption_x, media=media_x, now=now)
            results["x"] = x_res
            (published_to if x_res.get("status") == "success" else failed_on).append("x")

        elif ch == "linkedin":
            caption_li = _format_linkedin_caption(ch_title or title, ch_caption, ch_tags, primary_aff)
            media_li = {"link": video_url, "picture": video_url, "title": title[:100]}
            logger.info("💼 [Buffer → LinkedIn] Posting: '%s'...", caption_li[:60])
            li_res = _post_to_buffer(token=token, profile_ids=pids, text=caption_li, media=media_li, now=now)
            results["linkedin"] = li_res
            (published_to if li_res.get("status") == "success" else failed_on).append("linkedin")

        else:
            caption_gen = _format_generic_caption(ch_title or title, ch_caption, ch_tags, primary_aff)
            media_gen = {"link": video_url, "picture": video_url, "title": title[:100]}
            logger.info("📡 [Buffer → %s] Posting...", ch)
            gen_res = _post_to_buffer(token=token, profile_ids=pids, text=caption_gen, media=media_gen, now=now)
            results[ch] = gen_res
            (published_to if gen_res.get("status") == "success" else failed_on).append(ch)

    # ── 7. Build Final Summary ─────────────────────────────────────────────────
    if published_to and not failed_on:
        overall = "success"
    elif published_to and failed_on:
        overall = "partial"
    elif not published_to and not failed_on:
        overall = "skipped"  # all channels were missing
    else:
        overall = "failed"

    logger.info(
        "🎯 [Buffer] Broadcast complete — Status: %s | Published: %s | Failed: %s",
        overall.upper(), published_to or "none", failed_on or "none"
    )

    return {
        "status": overall,
        "published_to": published_to,
        "failed_on": failed_on,
        "results": results,
        "video_url": video_url,
    }


# ── Credential Helpers for /setbuffer Telegram command ────────────────────────

def set_user_buffer_token(user_id_str: str, token: str) -> bool:
    """
    Saves a user's Buffer Personal Access Token to telegram_users.json and GitHub Secrets.
    Called by the /setbuffer <token> Telegram command handler in main.py.
    """
    try:
        from Telegram_Storage_Modules.telegram_user_manager import (
            load_all_users, save_all_users, _is_admin_user, _persist_env_var_to_disk,
            sync_user_secret_to_github,
        )
        clean_tok = token.strip()
        if not clean_tok:
            return False

        users = load_all_users()
        uid = str(user_id_str).strip()
        users.setdefault(uid, {})["buffer_access_token"] = clean_tok
        save_all_users(users)

        if _is_admin_user(uid):
            os.environ["BUFFER_ACCESS_TOKEN"] = clean_tok
            _persist_env_var_to_disk("BUFFER_ACCESS_TOKEN", clean_tok)

        sync_user_secret_to_github(uid, "BUFFER_ACCESS_TOKEN", clean_tok)

        # Invalidate profile cache so next run re-discovers channels with new token
        global _profile_cache
        _profile_cache = None

        logger.info("🔑 [Buffer] Access Token saved for User ID %s", uid)
        return True
    except Exception as e:
        logger.error("❌ [Buffer] Failed to save token for User %s: %s", user_id_str, e)
        return False


def get_user_buffer_token(user_id_str: Optional[str] = None) -> Optional[str]:
    """
    Returns the Buffer Access Token for a user (or admin fallback).
    Thin wrapper for external callers.
    """
    return _get_buffer_token(user_id_str)


def get_user_connected_platforms(user_id: Optional[str] = None) -> List[str]:
    """
    Resolves the active social platforms for this user:
    1. Custom channels explicitly saved via /setchannels
    2. Dynamically discovered channels from user's Buffer account if token is set
    3. Plus native channels (telegram if group configured, youtube, instagram)
    4. Fallback default: ['youtube', 'instagram', 'tiktok', 'x', 'pinterest']
    """
    platforms: List[str] = []
    uid_str = str(user_id).strip() if user_id else ""

    # 1. Custom user override
    if uid_str:
        try:
            from Telegram_Storage_Modules.telegram_user_manager import get_user_active_channels
            custom = get_user_active_channels(uid_str)
            if custom:
                return custom
        except Exception:
            pass

    # 2. Discover from Buffer
    token = _get_buffer_token(user_id)
    if token:
        try:
            profiles = get_buffer_profiles(token)
            for p in profiles:
                svc = _normalize_service_name(p.get("service", ""))
                if svc and svc not in platforms:
                    platforms.append(svc)
        except Exception as e:
            logger.debug("Buffer channel discovery notice: %s", e)

    # 3. Check native channels
    if uid_str:
        try:
            from Telegram_Storage_Modules.telegram_user_manager import load_all_users
            u_rec = load_all_users().get(uid_str, {})
            if (u_rec.get("telegram_storage_group_id") or u_rec.get("telegram_public_group_id")) and "telegram" not in platforms:
                platforms.append("telegram")
            if u_rec.get("youtube_token_json") and "youtube" not in platforms:
                platforms.append("youtube")
            if u_rec.get("ig_business_token") and "instagram" not in platforms:
                platforms.append("instagram")
        except Exception:
            pass

    if not platforms:
        platforms = ["youtube", "instagram", "tiktok", "x", "pinterest"]

    return platforms


# ── Drop-In PublishQueue Compatibility Class ──────────────────────────────────

class PublishQueue:
    """Drop-in adapter for legacy callers. All broadcasting is orchestrated by Phase 4."""

    @classmethod
    def add(
        cls,
        video_path: str,
        channel_title: str = "",
        channel_folder: str = "General",
        caption: str = "",
        tags: str = "",
        seo_data: Optional[Dict[str, Any]] = None,
        post_type: str = "reel",
        **kwargs: Any
    ) -> bool:
        logger.info("ℹ️ [PublishQueue] Registered reel '%s' for Phase 4 orchestration", os.path.basename(video_path))
        return True

    @classmethod
    def status(cls) -> Dict[str, Any]:
        return {
            "queue_type": "Buffer / Direct Phase 4 Publisher",
            "configured": is_buffer_configured(),
        }


__all__ = [
    "publish_to_buffer",
    "is_buffer_configured",
    "get_buffer_profiles",
    "set_user_buffer_token",
    "get_user_buffer_token",
    "get_user_connected_platforms",
    "resolve_public_media_url",
    "PublishQueue",
]

