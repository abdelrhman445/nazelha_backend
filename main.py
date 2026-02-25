from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
import httpx
import os

app = FastAPI(title="Video Downloader API")

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
    return {"message": "الباك إند شغال تمام على Vercel!"}

@app.post("/api/download")
async def get_download_link(request: VideoRequest):
    url_lower = request.url.lower()
    
    # 1. إعداد ملف الكوكيز في المجلد المؤقت (حل مشكلة Read-only)
    cookie_path = "/tmp/cookies.txt"
    youtube_cookies = os.getenv("YOUTUBE_COOKIES")
    
    if youtube_cookies:
        try:
            with open(cookie_path, "w") as f:
                f.write(youtube_cookies)
        except Exception as e:
            print(f"Error writing cookies: {e}")

    # ==========================================
    # 2. تيك توك (TikWM API)
    # ==========================================
    if "tiktok.com" in url_lower or "douyin.com" in url_lower:
        try:
            async with httpx.AsyncClient() as client:
                api_url = f"https://www.tikwm.com/api/?url={request.url}"
                response = await client.get(api_url, timeout=15.0)
                data = response.json()
                if data.get("code") == 0:
                    vid_data = data.get("data", {})
                    final_url = vid_data.get("music") if request.download_type == "audio" else vid_data.get("play")
                    if final_url:
                        return {
                            "success": True, 
                            "download_url": final_url,
                            "title": vid_data.get("title", "TikTok Video"),
                            "thumbnail": vid_data.get("cover", "")
                        }
                return {"success": False, "error": "مقدرناش نجيب فيديو تيك توك."}
        except:
            return {"success": False, "error": "مشكلة في الاتصال بسيرفر تيك توك."}

    # ==========================================
    # 3. يوتيوب (yt-dlp مع الكوكيز من /tmp)
    # ==========================================
    else:
        format_string = 'best'
        if request.download_type == "audio":
            format_string = 'bestaudio/best'
        else:
            if request.quality == "high": format_string = 'best[ext=mp4]/best'
            elif request.quality == "medium": format_string = 'best[height<=480][ext=mp4]/best'
            else: format_string = 'best[height<=360][ext=mp4]/worst'

        ydl_opts = {
            'format': format_string, 
            'quiet': True,         
            'noplaylist': True,
            'nocheckcertificate': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'referer': 'https://www.google.com/',
        }

        # نستخدم ملف الكوكيز فقط إذا كان موجوداً
        if os.path.exists(cookie_path):
            ydl_opts['cookiefile'] = cookie_path

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(request.url, download=False)
                if not info:
                    return {"success": False, "error": "فشل استخراج البيانات."}

                direct_url = info.get('url')
                if not direct_url and 'formats' in info:
                    valid_formats = [f for f in info['formats'] if f.get('url') and f.get('url').startswith('http')]
                    if valid_formats: direct_url = valid_formats[-1]['url']

                if direct_url:
                    return {
                        "success": True, 
                        "download_url": direct_url,
                        "title": info.get('title', 'Video'),
                        "thumbnail": info.get('thumbnail', '')
                    }
                return {"success": False, "error": "مقدرناش نوصل لرابط مباشر."}
        except Exception as e:
            return {"success": False, "error": "حدث خطأ أثناء المعالجة.", "details": str(e)}
