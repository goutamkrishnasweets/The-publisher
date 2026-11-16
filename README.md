# 🚀 The Publisher — Zero-Env Localhost AI Video Studio

A self-hosted, privacy-first multi-platform video publishing engine. Run it on your local PC, Mac, or home server.

---

### 🌟 Core Philosophy: Zero Mandatory `.env`

You **do not need to create or configure a `.env` file**. Everything is controlled dynamically:

1. **First Boot:** On first run, the bot asks for your Telegram Bot Token in the console once and saves it to `data/bot_config.json`.
2. **Virtual `.ENV` per Identity (`data/telegram_users.json`):**
   * Acts as a per-user replication of environment variables.
   * Every setting, API key, and channel token is bound strictly to your Telegram `chat_id`.
   * Completely controllable via chat commands (`/setstorage`, `/setbuffer`, `/setgemini`, `/setbranding`, etc.).
3. **Master Vault Index (`data/telegram_vault_index.json`):**
   * Mirrors the Telegram Vault architecture from Gemini Editor.
   * Keeps track of every clip's Telegram `file_id`, shortcode, and CDN download URL.
4. **Multimodal Intelligence Pool (`data/pool_metadata.json`):**
   * Stores video and audio hook analysis, pacing scores, and SEO evidence.

---

### 🚀 Quick Start (Under 2 Minutes)

#### 1. Install Dependencies
```bash
cd E:\The_publisher
pip install -r requirements.txt
```

#### 2. Start the Bot
```bash
python main.py
```
*(If it's your first time, paste your bot token from `@BotFather` when prompted).*

---

### 💬 Setup Everything from Telegram Chat

Once your bot is running, configure your accounts directly in chat:

* **Storage Vault (Private Group):**
  * Add the bot as Admin to your private media storage group and run `/setstorage` inside it.
* **Buffer (TikTok, Pinterest, X / Twitter):**
  * `/setbuffer <TOKEN>` (from `https://publish.buffer.com/settings/api?tab=personal-access`).
* **Google Gemini AI:**
  * `/setgemini <KEY>` (free from Google AI Studio).
* **Brand Watermark:**
  * `/setbranding <YOUR_BRAND_TEXT>`.
* **View Your Virtual `.ENV`:**
  * `/myconfig` — check all configured tokens and settings in 1 glance.

---

### 📱 Daily Usage
1. Open your Telegram bot.
2. Send or forward any video.
3. Bot automatically:
   * Uploads it to your private Storage Vault.
   * Audits the video with Gemini Multimodal AI.
   * Applies structured SEO, viral hashtags, and affiliate disclosure policies.
   * Logs everything into `telegram_vault_index.json` and `pool_metadata.json`.
4. Tap **[🚀 Post Immediately]** to broadcast to **TikTok, Pinterest, X, Instagram, and YouTube** in seconds!
