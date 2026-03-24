from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
import httpx
import re
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
# yt-dlp Handler (YouTube, Instagram, etc.) - Smart Extraction V3
# ==========================================
async def handle_with_ytdlp(url: str, download_type: str, quality: str, platform: str = "general"):
    
    # === التعديل هنا: صيغة آمنة 100% مستحيل تضرب خطأ ===
    if download_type == "audio":
        safe_format = "bestaudio/best/worst"
    else:
        safe_format = "best[ext=mp4]/best/worst"

    ydl_opts = {
        "format": safe_format,
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
    if os.path.exists("cookies.txt"):
        ydl_opts["cookiefile"] = "cookies.txt"
    # ==========================================

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

            direct_url = None
            formats = info.get("formats", [])

            # --- بداية نظام الاستخراج الذكي ---
            if formats:
                if download_type == "audio":
                    # تصفية لجلب صيغ الصوت فقط
                    audio_formats = [f for f in formats if f.get("acodec") != "none" and f.get("vcodec") == "none" and f.get("url")]
                    if not audio_formats:
                        audio_formats = [f for f in formats if f.get("acodec") != "none" and f.get("url")]
                    
                    if audio_formats:
                        audio_formats.sort(key=lambda x: x.get("abr") or 0)
                        direct_url = audio_formats[-1]["url"]

                else: # Video
                    # تصفية لجلب الصيغ المدمجة (صوت وصورة) اللي بتشتغل برابط مباشر
                    combined_formats = [f for f in formats if f.get("vcodec") != "none" and f.get("acodec") != "none" and f.get("url")]
                    
                    if combined_formats:
                        combined_formats.sort(key=lambda x: x.get("height") or 0)
                        
                        if quality == "high":
                            mp4_combined = [f for f in combined_formats if f.get("ext") == "mp4"]
                            direct_url = mp4_combined[-1]["url"] if mp4_combined else combined_formats[-1]["url"]
                        elif quality == "medium":
                            med_formats = [f for f in combined_formats if (f.get("height") or 0) <= 480]
                            direct_url = med_formats[-1]["url"] if med_formats else combined_formats[-1]["url"]
                        else: # Low
                            low_formats = [f for f in combined_formats if (f.get("height") or 0) <= 360]
                            direct_url = low_formats[-1]["url"] if low_formats else combined_formats[0]["url"]
                    else:
                        # حالة نادرة: لو مفيش أي صيغة مدمجة، هات أي فيديو شغال
                        video_formats = [f for f in formats if f.get("vcodec") != "none" and f.get("url")]
                        if video_formats:
                            video_formats.sort(key=lambda x: x.get("height") or 0)
                            direct_url = video_formats[-1]["url"]
            # --- نهاية الاستخراج الذكي ---

            # خط الدفاع الأخير: لو كل الفلاتر فشلت، هات الرابط الأساسي اللي yt-dlp جهزه
            if not direct_url:
                direct_url = info.get("url")

            if direct_url:
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
                return {"success": False, "error": "مفيش رابط مباشر متاح للتحميل للفيديو دا."}

    except yt_dlp.utils.DownloadError as e:
        err_str = str(e).lower()
        
        # تصحيح التقاط الأخطاء
        if "requested format is not available" in err_str:
            return {"success": False, "error": "مفيش جودة مناسبة متاحة للتحميل المباشر للفيديو دا."}
        elif "sign in" in err_str or "age" in err_str:
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
