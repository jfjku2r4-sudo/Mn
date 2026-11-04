# Video Downloader AI — Streamlit free deployment

Arabic Streamlit app by محمد عبد الله / Mohamed Abdallah.

## Deploy
Upload `app.py`, `requirements.txt`, and `packages.txt` to GitHub, then deploy `app.py` from Streamlit Community Cloud.

## YouTube 403 best-effort support
The first time a YouTube URL is analyzed, the app attempts to:
1. Install Deno using Deno's official installer in the app user's home directory.
2. Clone the `bgutil-ytdlp-pot-provider` 2.0.2 repository.
3. Install its Deno script dependencies.
4. Use the installed `bgutil-ytdlp-pot-provider` yt-dlp plugin to request fresh PO Tokens for YouTube's `mweb` client.

The first YouTube analysis may take several minutes. Other supported sites do not run this setup.

## Important limitations
- PO Tokens can help with YouTube's token-related 403 responses, but they do not guarantee access.
- The provider project explicitly notes that PO Tokens do not bypass IP-based login restrictions. Streamlit Community Cloud uses shared cloud infrastructure; if YouTube blocks or challenges that egress IP, the free Streamlit deployment may continue to receive 403.
- This app does not bypass DRM, private-video restrictions, or login requirements.
- Download only content you own or are authorized to download.
- Large files may exceed Streamlit Cloud's resource limits.

## حل خطأ "Sign in to confirm you're not a bot"
سببه حظر YouTube لعناوين IP الخاصة بالاستضافة السحابية، وموفّر PO Token لا يحلّه. الحل:
1. افتح نافذة تصفح خاص، سجّل الدخول إلى YouTube بحساب **ثانوي**.
2. في نفس النافذة افتح `https://www.youtube.com/robots.txt`.
3. صدّر الكوكيز بإضافة مثل "Get cookies.txt LOCALLY" بصيغة Netscape، ثم أغلق النافذة.
4. إمّا ارفع الملف من قسم 🍪 داخل التطبيق، أو (للمالك) ضعه في Streamlit → Settings → Secrets:
```
YOUTUBE_COOKIES = """
# Netscape HTTP Cookie File
...محتوى الملف...
"""
```
الكوكيز تنتهي صلاحيتها؛ جدّدها عند عودة الخطأ. لا ترفع الملف إلى GitHub أبدًا.
