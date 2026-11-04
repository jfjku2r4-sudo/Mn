import os
import re
import glob
import tempfile
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

url = st.text_input("🔗 ضع رابط الفيديو هنا", placeholder="https://...")
analyze = st.button("🔍 تحليل الرابط", type="primary", use_container_width=True)

if analyze:
    if not valid_url(url):
        st.error("أدخل رابطًا صحيحًا يبدأ بـ http:// أو https://")
    else:
        with st.spinner("جارٍ تحليل الرابط واستخراج المعلومات..."):
            try:
                opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True}
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url.strip(), download=False)
                st.session_state["video_info"] = info
                st.session_state["video_url"] = url.strip()
                st.session_state.pop("downloaded_file", None)
            except Exception as e:
                st.error("تعذر تحليل الرابط. قد يكون الموقع غير مدعوم أو يتطلب تسجيل الدخول أو أن الرابط غير متاح.")
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
    for f in formats:
        if f.get("vcodec") not in (None, "none"):
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
        st.caption("سيتم استخراج الصوت وتحويله إلى MP3 باستخدام FFmpeg.")

    if st.button("🚀 ابدأ التحميل", type="primary", use_container_width=True,
                 disabled=(mode == "فيديو" and not selected_format)):
        progress = st.progress(0)
        status = st.empty()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                output_template = os.path.join(temp_dir, "%(title).100B.%(ext)s")
                def hook(data):
                    if data.get("status") == "downloading":
                        total = data.get("total_bytes") or data.get("total_bytes_estimate")
                        done = data.get("downloaded_bytes", 0)
                        if total:
                            progress.progress(min(int(done * 100 / total), 99))
                        status.write("جارٍ تنزيل الملف...")
                    elif data.get("status") == "finished":
                        progress.progress(100)
                        status.write("اكتمل التنزيل، جارٍ تجهيز الملف...")

                ydl_opts = {
                    "outtmpl": output_template,
                    "quiet": True,
                    "no_warnings": True,
                    "noplaylist": True,
                    "progress_hooks": [hook],
                    "restrictfilenames": True,
                }
                if mode == "صوت MP3":
                    ydl_opts["format"] = "bestaudio/best"
                    ydl_opts["postprocessors"] = [{
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }]
                else:
                    ydl_opts["format"] = f"{selected_format}+bestaudio/best"
                    ydl_opts["merge_output_format"] = "mp4"

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([st.session_state["video_url"]])

                candidates = [p for p in Path(temp_dir).glob("*") if p.is_file() and p.stat().st_size > 0]
                if not candidates:
                    raise RuntimeError("لم يتم إنشاء ملف قابل للتنزيل.")
                # Prefer final MP4/MP3 rather than intermediate fragments.
                candidates.sort(key=lambda p: (p.suffix.lower() in (".mp4", ".mp3", ".mkv", ".webm"), p.stat().st_size), reverse=True)
                result = candidates[0]
                mime = "audio/mpeg" if result.suffix.lower() == ".mp3" else "video/mp4"
                st.session_state["downloaded_file"] = {
                    "bytes": result.read_bytes(),
                    "name": clean_filename(title) + result.suffix,
                    "mime": mime,
                    "size": result.stat().st_size,
                }
                progress.progress(100)
                status.success("تم تجهيز الملف بنجاح.")
        except Exception as e:
            st.error("فشل التحميل. تحقق من دعم الموقع للصيغة المطلوبة ومن تثبيت FFmpeg.")
            with st.expander("تفاصيل تقنية"):
                st.code(str(e)[:1800])

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
