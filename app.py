import os
import re
import glob
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlparse

import streamlit as st
import yt_dlp

st.set_page_config(page_title="Video Downloader AI", page_icon="🎬", layout="centered")

st.markdown("""
<style>
.main {max-width: 900px; margin: auto;}
.hero {padding: 22px; border-radius: 18px; background: linear-gradient(120deg,#172554,#312e81); color:white; text-align:center;}
.hero h1 {color:white; margin-bottom:6px;}
.small-note {font-size: .9rem; opacity:.85;}
</style>
<div class="hero">
<h1>🎬 Video Downloader AI</h1>
<p>حلّل رابط الفيديو واختر الجودة أو استخرج الصوت</p>
<div class="small-note">واجهة عربية • تعمل على الهاتف والكمبيوتر</div>
<p style="margin:12px 0 0; font-size:0.95rem;">تطوير: <strong>محمد عبد الله</strong> · <strong>Mohamed Abdallah</strong></p>
</div>
""", unsafe_allow_html=True)

st.write("")
st.info("استخدم الموقع لتنزيل الفيديوهات التي تملكها أو لديك إذن بتنزيلها. لا يدعم تجاوز DRM أو الفيديوهات الخاصة أو قيود تسجيل الدخول.")


def is_youtube_url(value: str) -> bool:
    host = (urlparse(value.strip()).hostname or "").lower()
    return host == "youtu.be" or host.endswith("youtube.com")


@st.cache_resource(show_spinner=False)
def setup_youtube_po_token_provider():
    """
    Best-effort first-run setup for the bgutil PO Token provider.
    Installs Deno and the provider's script backend in the Streamlit container.
    """
    home = Path.home()
    deno_home = home / ".deno"
    deno_bin = deno_home / "bin"
    deno_path = deno_bin / "deno"
    repo_dir = home / "bgutil-ytdlp-pot-provider"
    env = os.environ.copy()
    env["DENO_INSTALL"] = str(deno_home)
    env["PATH"] = f"{deno_bin}:{env.get('PATH', '')}"

    try:
        if not deno_path.exists():
            subprocess.run(
                ["bash", "-lc", "curl -fsSL https://deno.land/install.sh | sh"],
                check=True, capture_output=True, text=True, timeout=240, env=env
            )
        if not deno_path.exists():
            return {"ok": False, "reason": "Deno was not installed by the official installer."}

        if not repo_dir.exists():
            subprocess.run(
                [
                    "git", "clone", "--depth", "1", "--single-branch",
                    "--branch", "2.0.2",
                    "https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git",
                    str(repo_dir),
                ],
                check=True, capture_output=True, text=True, timeout=180, env=env
            )

        server_dir = repo_dir / "server"
        if not (server_dir / "node_modules").exists():
            subprocess.run(
                [str(deno_path), "install", "--allow-scripts=npm:canvas", "--frozen"],
                cwd=str(server_dir), check=True, capture_output=True,
                text=True, timeout=360, env=env
            )

        # Make Deno visible to yt-dlp and its PO Token provider subprocess.
        os.environ["DENO_INSTALL"] = str(deno_home)
        os.environ["PATH"] = env["PATH"]
        return {"ok": True, "reason": "bgutil PO Token provider is prepared."}
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "انتهت مهلة إعداد Deno أو موفّر PO Token. أعد المحاولة بعد قليل."}
    except Exception as exc:
        detail = getattr(exc, "stderr", None) or str(exc)
        return {"ok": False, "reason": str(detail)[-1800:]}


def normalize_cookies(text: str) -> str:
    """Make sure a Netscape cookies file is valid (tabs between the 7 fields)."""
    lines = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            continue
        if not line.startswith("#") or line.startswith("#HttpOnly_"):
            parts = line.split(None, 6)
            if len(parts) == 7:
                line = "\t".join(parts)
        lines.append(line)
    if not lines or not lines[0].startswith("# Netscape HTTP Cookie File"):
        lines.insert(0, "# Netscape HTTP Cookie File")
    return "\n".join(lines) + "\n"


def get_cookiefile():
    """
    Returns a path to a private temp copy of the cookies file, or None.
    Priority: Streamlit secret YOUTUBE_COOKIES (owner) > file uploaded in this session.
    """
    content = None
    try:
        content = st.secrets.get("YOUTUBE_COOKIES")
    except Exception:
        content = None
    if not content:
        up = st.session_state.get("cookies_upload")
        if up is not None:
            content = up.getvalue().decode("utf-8", errors="ignore")
    if not content or not content.strip():
        return None
    sid = st.session_state.setdefault("cookie_sid", uuid.uuid4().hex)
    path = Path(tempfile.gettempdir()) / f"yt_cookies_{sid}.txt"
    path.write_text(normalize_cookies(content), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass
    return str(path)

def valid_url(value: str) -> bool:
    try:
        parsed = urlparse(value.strip())
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False

def human_size(num):
    if not num:
        return "الحجم غير معروف"
    value = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return "غير معروف"

def clean_filename(name):
    name = re.sub(r'[\\/*?:"<>|]', "_", name or "video")
    return name[:100].strip(" .") or "video"

with st.expander("🍪 YouTube يطلب تأكيد أنك لست روبوتًا؟ (ملف الكوكيز)"):
    st.markdown(
        "إذا ظهر الخطأ *Sign in to confirm you're not a bot* فارفع ملف `cookies.txt` "
        "(صيغة Netscape) من حساب YouTube **ثانوي** وليس حسابك الأساسي. "
        "الملف يُستخدم لهذه الجلسة فقط ولا يُحفظ. "
        "صاحب التطبيق يمكنه بدلًا من ذلك وضعه في Secrets باسم `YOUTUBE_COOKIES`."
    )
    st.file_uploader("ملف cookies.txt", type=["txt"], key="cookies_upload")
    if get_cookiefile():
        st.success("تم تفعيل ملف الكوكيز.")

url = st.text_input("🔗 ضع رابط الفيديو هنا", placeholder="https://...")
analyze = st.button("🔍 تحليل الرابط", type="primary", use_container_width=True)

if analyze:
    if not valid_url(url):
        st.error("أدخل رابطًا صحيحًا يبدأ بـ http:// أو https://")
    else:
        with st.spinner("جارٍ تحليل الرابط واستخراج المعلومات..."):
            try:
                opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True}
                if is_youtube_url(url):
                    with st.spinner("تهيئة دعم YouTube ورمز PO Token لأول استخدام... قد يستغرق ذلك عدة دقائق."):
                        pot_setup = setup_youtube_po_token_provider()
                    st.session_state["youtube_pot_ready"] = bool(pot_setup.get("ok"))
                    if not pot_setup.get("ok"):
                        st.warning("تعذر إعداد موفّر PO Token تلقائيًا. سيحاول الموقع التحليل بالطريقة المعتادة. التفاصيل: " + pot_setup.get("reason", "غير متاحة"))
                    else:
                        st.success("تم تجهيز دعم YouTube ورمز PO Token.")
                    opts["js_runtimes"] = {"deno": {}}
                    opts["extractor_args"] = {"youtube": {"player_client": ["mweb"]}}
                    cookiefile = get_cookiefile()
                    if cookiefile:
                        opts["cookiefile"] = cookiefile
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url.strip(), download=False)
                st.session_state["video_info"] = info
                st.session_state["video_url"] = url.strip()
                st.session_state.pop("downloaded_file", None)
            except Exception as e:
                st.error("تعذر تحليل الرابط. قد يكون الموقع غير مدعوم أو يتطلب تسجيل الدخول أو أن الرابط غير متاح.")
                if "not a bot" in str(e).lower():
                    st.warning("YouTube يحظر عنوان IP الخاص بخادم Streamlit ويطلب التحقق. الحل: ارفع ملف cookies.txt من الإعداد أعلاه (🍪)، أو شغّل التطبيق على جهازك.")
                with st.expander("تفاصيل تقنية"):
                    st.code(str(e)[:1800])

info = st.session_state.get("video_info")
if info:
    title = info.get("title") or "فيديو بدون عنوان"
    st.subheader("📋 معلومات الفيديو")
    col1, col2 = st.columns(2)
    col1.write(f"**العنوان:** {title}")
    col2.write(f"**المدة:** {info.get('duration_string') or 'غير معروفة'}")
    thumb = info.get("thumbnail")
    if thumb:
        st.image(thumb, use_container_width=True)

    formats = info.get("formats") or []
    video_formats = []
    seen = set()
    ffmpeg_available = shutil.which("ffmpeg") is not None
    for f in formats:
        has_video = f.get("vcodec") not in (None, "none")
        has_audio = f.get("acodec") not in (None, "none")
        # Without FFmpeg, separate video/audio streams cannot be merged.
        if has_video and (ffmpeg_available or has_audio):
            height = f.get("height")
            ext = f.get("ext") or "?"
            fid = f.get("format_id")
            if not fid:
                continue
            key = (fid, height, ext)
            if key in seen:
                continue
            seen.add(key)
            label_quality = f"{height}p" if height else (f.get("format_note") or "جودة غير محددة")
            fps = f.get("fps")
            label = f"{label_quality} | {ext} | {fps}fps" if fps else f"{label_quality} | {ext}"
            label += f" | {human_size(f.get('filesize') or f.get('filesize_approx'))}"
            video_formats.append((label, fid, f))

    st.divider()
    st.subheader("⬇️ اختر طريقة التحميل")
    mode = st.radio("نوع الملف", ["فيديو", "صوت MP3"], horizontal=True)

    selected_format = None
    if mode == "فيديو":
        if not video_formats:
            st.warning("لم يعثر الموقع على صيغ فيديو قابلة للاختيار.")
        else:
            # Prefer a high-resolution format, while keeping every discovered option available.
            video_formats.sort(key=lambda item: (item[2].get("height") or 0, item[2].get("fps") or 0), reverse=True)
            labels = [item[0] for item in video_formats]
            selected_label = st.selectbox("جودة الفيديو", labels)
            selected_format = next(item[1] for item in video_formats if item[0] == selected_label)
    else:
        if not ffmpeg_available:
            st.warning("أداة FFmpeg غير متاحة على الخادم؛ لن يمكن تحويل الصوت إلى MP3. ثبّت FFmpeg من packages.txt ثم أعد نشر التطبيق.")
        else:
            st.caption("سيتم استخراج الصوت وتحويله إلى MP3 باستخدام FFmpeg.")

    if st.button("🚀 ابدأ التحميل", type="primary", use_container_width=True,
                 disabled=(mode == "فيديو" and not selected_format)):
        progress = st.progress(0)
        status = st.empty()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                def hook(data):
                    if data.get("status") == "downloading":
                        total = data.get("total_bytes") or data.get("total_bytes_estimate")
                        done = data.get("downloaded_bytes", 0)
                        if total:
                            progress.progress(min(int(done * 100 / total), 99))
                        status.write("جارٍ تنزيل الملف...")
                    elif data.get("status") == "finished":
                        status.write("اكتمل نقل البيانات، جارٍ تجهيز الملف...")

                common_opts = {
                    "quiet": True,
                    "no_warnings": False,
                    "noplaylist": True,
                    "progress_hooks": [hook],
                    "restrictfilenames": True,
                    "overwrites": True,
                    "continuedl": False,
                    "nopart": True,
                    "retries": 10,
                    "fragment_retries": 10,
                    "extractor_retries": 5,
                    "file_access_retries": 5,
                    "concurrent_fragment_downloads": 1,
                    "socket_timeout": 30,
                }

                if is_youtube_url(st.session_state["video_url"]):
                    # bgutil provider plugin (installed from requirements.txt) supplies fresh
                    # video-bound PO Tokens for the mweb client when YouTube requires them.
                    common_opts["js_runtimes"] = {"deno": {}}
                    common_opts["extractor_args"] = {"youtube": {"player_client": ["mweb"]}}
                    cookiefile = get_cookiefile()
                    if cookiefile:
                        common_opts["cookiefile"] = cookiefile

                attempts = []
                if mode == "صوت MP3":
                    if not ffmpeg_available:
                        raise RuntimeError("FFmpeg غير مثبت على الخادم. أضف ffmpeg إلى packages.txt ثم أعد نشر التطبيق.")
                    attempts = [{
                        "format": "bestaudio/best",
                        "postprocessors": [{
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3",
                            "preferredquality": "192",
                        }],
                    }]
                else:
                    chosen = next((item[2] for item in video_formats if item[1] == selected_format), {})
                    selected_height = chosen.get("height")
                    selected_has_audio = chosen.get("acodec") not in (None, "none")

                    # Prefer fresh format selection by height rather than reusing an old
                    # direct format URL/ID captured during analysis (often the source of 403s).
                    if selected_height and ffmpeg_available:
                        attempts.append({
                            "format": f"bestvideo[height<={selected_height}]+bestaudio/best[height<={selected_height}]"
                        })
                    elif selected_has_audio:
                        attempts.append({"format": selected_format})
                    elif ffmpeg_available:
                        attempts.append({"format": f"{selected_format}+bestaudio/{selected_format}"})

                    # Retry with a fresh best-match expression if the selected stream is stale,
                    # unavailable, or returned an empty response.
                    if selected_height and not ffmpeg_available:
                        attempts.append({
                            "format": f"best[height<={selected_height}]"
                        })
                    attempts.extend([
                        {"format": "bestvideo*+bestaudio/best"},
                        {"format": "best"},
                    ])

                result = None
                attempt_errors = []
                for attempt_number, attempt_opts in enumerate(attempts, start=1):
                    attempt_dir = Path(temp_dir) / f"attempt_{attempt_number}"
                    attempt_dir.mkdir(parents=True, exist_ok=True)
                    ydl_opts = {
                        **common_opts,
                        **attempt_opts,
                        "outtmpl": str(attempt_dir / "%(title).100B.%(ext)s"),
                    }
                    if mode == "فيديو" and ffmpeg_available:
                        ydl_opts["merge_output_format"] = "mp4"

                    try:
                        status.write(f"جارٍ تجربة طريقة التحميل {attempt_number} من {len(attempts)}...")
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            ydl.download([st.session_state["video_url"]])

                        # Search recursively and ignore incomplete/temporary files.
                        candidates = [
                            f for f in attempt_dir.rglob("*")
                            if f.is_file()
                            and f.suffix.lower() not in (".part", ".ytdl", ".tmp")
                            and f.stat().st_size > 1024
                        ]
                        if candidates:
                            candidates.sort(
                                key=lambda f: (
                                    f.suffix.lower() in (".mp4", ".mp3", ".mkv", ".webm", ".m4a"),
                                    f.stat().st_size
                                ),
                                reverse=True
                            )
                            result = candidates[0]
                            break
                        attempt_errors.append(f"المحاولة {attempt_number}: لم ينتج ملف صالح.")
                    except Exception as attempt_error:
                        attempt_errors.append(f"المحاولة {attempt_number}: {str(attempt_error)[:700]}")

                if result is None:
                    raise RuntimeError(
                        "فشلت جميع طرق التحميل التلقائية.\\n" + "\\n".join(attempt_errors[-4:])
                    )

                mime = "audio/mpeg" if result.suffix.lower() == ".mp3" else (
                    "audio/mp4" if result.suffix.lower() == ".m4a" else "video/mp4"
                )
                st.session_state["downloaded_file"] = {
                    "bytes": result.read_bytes(),
                    "name": clean_filename(title) + result.suffix,
                    "mime": mime,
                    "size": result.stat().st_size,
                }
                progress.progress(100)
                status.success("تم تجهيز الملف بنجاح.")
        except Exception as e:
            message = str(e)
            st.error("تعذر إكمال التحميل بعد تجربة أكثر من طريقة.")
            if "403" in message or "forbidden" in message.lower():
                st.warning("YouTube رفض طلب ملف الفيديو (HTTP 403). أُضيف دعم Deno وموفّر PO Token تلقائيًا. إذا استمر الرفض رغم ظهور رسالة توليد PO Token في السجل، فقد يكون عنوان IP الخاص بخادم Streamlit محظورًا أو يتطلب YouTube تحققًا/تسجيل دخول؛ لا توجد طريقة مضمونة لإصلاح ذلك من داخل الاستضافة المجانية.")
            elif "requested format is not available" in message.lower():
                st.warning("الصيغة المحددة لم تعد متاحة؛ سيستخدم الإصدار الحالي اختيارًا جديدًا للصيغة حسب الجودة بدل الاعتماد على معرّف قديم.")
            elif "empty" in message.lower():
                st.warning("YouTube أعاد استجابة فارغة. قد يكون هناك تغيير مؤقت في طريقة تقديم الفيديو؛ حدّث yt-dlp وأعد المحاولة لاحقًا أو جرّب جودة أقل.")
            elif "ffmpeg" in message.lower():
                st.warning("تأكد من تثبيت FFmpeg في packages.txt ثم أعد نشر التطبيق.")
            elif "sign in" in message.lower() or "cookies" in message.lower() or "private" in message.lower():
                st.warning("قد يتطلب الفيديو تسجيل الدخول أو يكون خاصًا. لا يتجاوز التطبيق قيود الوصول.")
            with st.expander("تفاصيل تقنية للمساعدة في التشخيص", expanded=True):
                st.code(message[:4000])

downloaded = st.session_state.get("downloaded_file")
if downloaded:
    st.success(f"الملف جاهز — الحجم: {human_size(downloaded['size'])}")
    st.download_button(
        "📥 تنزيل الملف إلى جهازك",
        data=downloaded["bytes"],
        file_name=downloaded["name"],
        mime=downloaded["mime"],
        use_container_width=True,
    )

st.divider()
st.caption("يعتمد الموقع على yt-dlp؛ دعم المواقع والجودات يتغير بمرور الوقت. قد تحتاج بعض المواقع إلى تحديث المكتبة. على الاستضافة السحابية قد توجد حدود لحجم الملفات والوقت.")
