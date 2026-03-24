from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
import httpx
import re
import os  # تمت إضافة هذه المكتبة للتحقق من وجود ملف الكوكيز

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
        "version": "2.0",
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
    
    # Basic URL validation
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="الرابط مش صحيح، لازم يبدأ بـ http:// أو https://")

    url_lower = url.lower()

    # ==========================================
    # 1. TikTok - tikwm API (بدون علامة مائية)
    # ==========================================
    if "tiktok.com" in url_lower or "douyin.com" in url_lower or "vm.tiktok.com" in url_lower:
        return await handle_tiktok(url, request.download_type)

    # ==========================================
    # 2. Instagram
    # ==========================================
    elif "instagram.com" in url_lower or "instagr.am" in url_lower:
        return await handle_with_ytdlp(url, request.download_type, request.quality, platform="instagram")

    # ==========================================
    # 3. YouTube وكل المواقع التانية
    # ==========================================
    else:
        return await handle_with_ytdlp(url, request.download_type, request.quality, platform="general")


# ==========================================
# TikTok Handler
# ==========================================
async def handle_tiktok(url: str, download_type: str):
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            # tikwm is the most reliable no-watermark API
            api_url = f"https://www.tikwm.com/api/?url={url}&hd=1"
            response = await client.get(api_url)
            response.raise_for_status()
            data = response.json()

            if data.get("code") == 0:
                vid_data = data.get("data", {})

                if download_type == "audio":
                    final_url = vid_data.get("music") or vid_data.get("music_info", {}).get("play")
                else:
                    # Prefer HD version
                    final_url = (
                        vid_data.get("hdplay")
                        or vid_data.get("play")
                        or vid_data.get("wmplay")
                    )

                if final_url:
                    return {
                        "success": True,
                        "download_url": final_url,
                        "title": vid_data.get("title", "TikTok Video"),
                        "thumbnail": vid_data.get("cover", ""),
                        "duration": vid_data.get("duration", 0),
                        "platform": "tiktok"
                    }

        return {"success": False, "error": "مقدرناش نجيب الفيديو من تيك توك، جرب تاني بعد شوية."}

    except httpx.TimeoutException:
        return {"success": False, "error": "انتهى الوقت، سيرفر تيك توك بطيء. جرب تاني."}
    except Exception as e:
        return {"success": False, "error": "مشكلة في الاتصال بسيرفر تيك توك.", "details": str(e)}


# ==========================================
# yt-dlp Handler (YouTube, Instagram, etc.)
# ==========================================
async def handle_with_ytdlp(url: str, download_type: str, quality: str, platform: str = "general"):
    
    # Build format string
    if download_type == "audio":
        if quality == "high":
            format_string = "bestaudio[ext=m4a]/bestaudio/best"
        elif quality == "medium":
            format_string = "bestaudio[abr<=128]/bestaudio/best"
        else:
            format_string = "worstaudio/worst"
    else:
        if quality == "high":
            format_string = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        elif quality == "medium":
            format_string = "bestvideo[height<=480][ext=mp4]+bestaudio/best[height<=480][ext=mp4]/best[height<=480]/best"
        else:
            format_string = "bestvideo[height<=360][ext=mp4]+bestaudio/best[height<=360][ext=mp4]/best[height<=360]/worst"

    # yt-dlp options with anti-bot measures
    ydl_opts = {
        "format": format_string,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "extract_flat": False,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
    }

    # ==========================================
    # === التعديل الجديد: التحقق من وجود الكوكيز ===
    if os.path.exists("cookies.txt"):
        ydl_opts["cookiefile"] = "cookies.txt"
    # ==========================================

    # Extra options for YouTube to bypass bot detection
    if "youtube.com" in url.lower() or "youtu.be" in url.lower():
        ydl_opts.update({
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "web"],
                    "player_skip": ["webpage"],
                }
            },
        })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                return {"success": False, "error": "مقدرناش نجيب معلومات عن الفيديو دا."}

            # Extract the direct URL
            direct_url = info.get("url")
            
            # If no direct URL, get from formats
            if not direct_url and "formats" in info:
                formats = [f for f in info["formats"] if f.get("url")]
                if formats:
                    # Prefer mp4 for video
                    if download_type != "audio":
                        mp4_formats = [f for f in formats if f.get("ext") == "mp4"]
                        direct_url = mp4_formats[-1]["url"] if mp4_formats else formats[-1]["url"]
                    else:
                        direct_url = formats[-1]["url"]

            if direct_url:
                # Clean up YouTube signed URLs (they expire, but still work fine)
                return {
                    "success": True,
                    "download_url": direct_url,
                    "title": info.get("title", "Video"),
                    "thumbnail": info.get("thumbnail", ""),
                    "duration": info.get("duration", 0),
                    "uploader": info.get("uploader", ""),
                    "platform": platform
                }
            else:
                return {"success": False, "error": "مقدرناش نستخرج رابط التحميل المباشر من الفيديو دا."}

    except yt_dlp.utils.DownloadError as e:
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

    except Exception as e:
        return {"success": False, "error": "خطأ غير متوقع حصل.", "details": str(e)}
