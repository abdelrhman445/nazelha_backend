from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
import httpx
import os

app = FastAPI(title="Nazelha Video Downloader API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class VideoRequest(BaseModel):
    url: str
    download_type: str = "video"
    quality: str = "high"


@app.get("/")
def read_root():
    return {
        "message": "الباك إند شغال تمام!",
        "status": "online",
        "version": "3.0",
        "supported_sites": ["YouTube", "TikTok", "Instagram", "Facebook", "Twitter/X", "و أكثر من 1000 موقع تاني"]
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/api/download")
async def get_download_link(request: VideoRequest):
    url = request.url.strip()

    if not url:
        raise HTTPException(status_code=400, detail="الرابط فاضي!")

    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="الرابط مش صحيح")

    url_lower = url.lower()

    if "tiktok.com" in url_lower or "douyin.com" in url_lower or "vm.tiktok.com" in url_lower:
        return await handle_tiktok(url, request.download_type)
    else:
        return await handle_with_ytdlp(url, request.download_type, request.quality)


# ==========================================
# TikTok Handler
# ==========================================
async def handle_tiktok(url: str, download_type: str):
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            api_url = f"https://www.tikwm.com/api/?url={url}&hd=1"
            response = await client.get(api_url)
            response.raise_for_status()
            data = response.json()

            if data.get("code") == 0:
                vid_data = data.get("data", {})
                if download_type == "audio":
                    final_url = vid_data.get("music") or vid_data.get("music_info", {}).get("play")
                else:
                    final_url = vid_data.get("hdplay") or vid_data.get("play") or vid_data.get("wmplay")

                if final_url:
                    return {
                        "success": True,
                        "download_url": final_url,
                        "title": vid_data.get("title", "TikTok Video"),
                        "thumbnail": vid_data.get("cover", ""),
                        "platform": "tiktok"
                    }

        return {"success": False, "error": "مقدرناش نجيب الفيديو من تيك توك، جرب تاني."}
    except Exception as e:
        return {"success": False, "error": "مشكلة في الاتصال بسيرفر تيك توك.", "details": str(e)}


# ==========================================
# yt-dlp Handler - الاستراتيجية الصح لـ YouTube
# ==========================================
async def handle_with_ytdlp(url: str, download_type: str, quality: str):

    # ============================================================
    # الحل الصح: بنجيب معلومات الفيديو الأول بدون format selection
    # وبعدين نختار بإيدينا
    # ============================================================
    base_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        },
        "socket_timeout": 30,
        "retries": 3,
    }

    # لو في cookies.txt على السيرفر استخدمه
    if os.path.exists("cookies.txt"):
    ydl_opts["cookiefile"] = "cookies.txt"

    # YouTube: استخدم android player عشان يتجاوز الحجب
    is_youtube = "youtube.com" in url.lower() or "youtu.be" in url.lower()
    if is_youtube:
        base_opts["extractor_args"] = {
            "youtube": {
                "player_client": ["android", "ios", "web"],
            }
        }

    try:
        # الخطوة 1: جيب كل الـ formats المتاحة
        info_opts = {**base_opts, "format": "bestaudio/best"}

        with yt_dlp.YoutubeDL(info_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            return {"success": False, "error": "مقدرناش نجيب معلومات عن الفيديو دا."}

        formats = info.get("formats", [])
        title = info.get("title", "Video")
        thumbnail = info.get("thumbnail", "")
        duration = info.get("duration", 0)
        uploader = info.get("uploader", "")

        # الخطوة 2: اختيار أفضل رابط مناسب
        direct_url = pick_best_url(formats, download_type, quality, info)

        if direct_url:
            return {
                "success": True,
                "download_url": direct_url,
                "title": title,
                "thumbnail": thumbnail,
                "duration": duration,
                "uploader": uploader,
            }
        else:
            return {"success": False, "error": "مقدرناش نستخرج رابط تحميل مباشر من الفيديو دا."}

    except yt_dlp.utils.DownloadError as e:
        return handle_ytdlp_error(e)
    except Exception as e:
        return {"success": False, "error": "خطأ غير متوقع.", "details": str(e)}


def pick_best_url(formats, download_type, quality, info):
    """
    اختيار أفضل رابط - بيجرب بالترتيب:
    1. Combined formats (فيديو + صوت في ملف واحد) - الأسهل للتحميل المباشر
    2. Video-only formats (لو مفيش combined)
    3. info.get('url') كـ fallback أخير
    """

    urls_only = [f for f in formats if f.get("url")]

    if download_type == "audio":
        # جيب audio-only formats
        audio_only = [f for f in urls_only if f.get("acodec") != "none" and f.get("vcodec") == "none"]
        if audio_only:
            audio_only.sort(key=lambda x: x.get("abr") or 0)
            return audio_only[-1]["url"]

        # fallback: أي format فيه صوت
        with_audio = [f for f in urls_only if f.get("acodec") != "none"]
        if with_audio:
            with_audio.sort(key=lambda x: x.get("abr") or 0)
            return with_audio[-1]["url"]

    else:
        # فيديو: جيب combined formats أول (فيديو + صوت)
        combined = [
            f for f in urls_only
            if f.get("vcodec") != "none"
            and f.get("acodec") != "none"
            and f.get("vcodec") != "none"
        ]

        if combined:
            combined.sort(key=lambda x: x.get("height") or 0)

            if quality == "high":
                # أعلى جودة mp4 لو متاحة
                mp4 = [f for f in combined if f.get("ext") == "mp4"]
                return (mp4[-1] if mp4 else combined[-1])["url"]

            elif quality == "medium":
                targets = [f for f in combined if (f.get("height") or 9999) <= 480]
                return (targets[-1] if targets else combined[len(combined)//2])["url"]

            else:  # low
                targets = [f for f in combined if (f.get("height") or 9999) <= 360]
                return (targets[-1] if targets else combined[0])["url"]

        # لو مفيش combined (YouTube الجديد بيعمل كده)
        # هنرجع video-only بأعلى جودة - المتصفح هيشغله عادي
        video_only = [f for f in urls_only if f.get("vcodec") != "none"]
        if video_only:
            video_only.sort(key=lambda x: x.get("height") or 0)

            if quality == "high":
                mp4 = [f for f in video_only if f.get("ext") == "mp4"]
                return (mp4[-1] if mp4 else video_only[-1])["url"]
            elif quality == "medium":
                targets = [f for f in video_only if (f.get("height") or 9999) <= 480]
                return (targets[-1] if targets else video_only[len(video_only)//2])["url"]
            else:
                targets = [f for f in video_only if (f.get("height") or 9999) <= 360]
                return (targets[-1] if targets else video_only[0])["url"]

    # آخر حل ممكن
    return info.get("url")


def handle_ytdlp_error(e):
    err_str = str(e).lower()
    if "sign in" in err_str or "age" in err_str:
        return {"success": False, "error": "الفيديو دا محتاج تسجيل دخول أو مقيد بالسن."}
    elif "private" in err_str:
        return {"success": False, "error": "الفيديو دا برايفيت ومش متاح."}
    elif "not available" in err_str or "unavailable" in err_str:
        return {"success": False, "error": "الفيديو دا مش متاح في منطقتك أو اتحذف."}
    elif "copyright" in err_str:
        return {"success": False, "error": "الفيديو دا محجوب بسبب حقوق النشر."}
    elif "rate" in err_str or "429" in err_str:
        return {"success": False, "error": "في ضغط كبير دلوقتي، جرب تاني بعد دقيقة."}
    elif "bot" in err_str or "captcha" in err_str:
        return {"success": False, "error": "يوتيوب شايف إنك بوت دلوقتي، جرب بعد شوية."}
    else:
        return {"success": False, "error": "حدث خطأ أثناء المعالجة.", "details": str(e)}
