from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
import httpx
import os

app = FastAPI(title="Nazelha API")

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
    return {"message": "الباك إند شغال تمام على Vercel يا ريس!"}

@app.post("/api/download")
async def get_download_link(request: VideoRequest):
    url_lower = request.url.lower()
    
    # 1. حل مشكلة الـ Read-only في Vercel عن طريق استخدام مجلد /tmp
    cookie_path = "/tmp/cookies.txt"
    youtube_cookies = os.getenv("YOUTUBE_COOKIES")
    if youtube_cookies:
        try:
            with open(cookie_path, "w") as f:
                f.write(youtube_cookies)
        except: pass

    # ==========================================
    # 2. تيك توك (شغال بالـ API الخارجي)
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
                    return {
                        "success": True, 
                        "download_url": final_url,
                        "title": vid_data.get("title", "TikTok Video"),
                        "thumbnail": vid_data.get("cover", "")
                    }
                return {"success": False, "error": "تيك توك رافض الطلب حالياً."}
        except:
            return {"success": False, "error": "مشكلة في الاتصال بتيك توك."}

    # ==========================================
    # 3. يوتيوب (تعديل الجودة ليتناسب مع غياب ffmpeg في Vercel)
    # ==========================================
    else:
        # السر هنا: بنطلب 'best' مباشرة عشان يوتيوب يدينا ملف مدمج جاهز
        # لأن Vercel مفيهاش ffmpeg يدمج الصوت والصورة لو طلبناهم منفصلين
        if request.download_type == "audio":
            format_string = 'bestaudio/best'
        else:
            # بنحاول نجيب أفضل ملف mp4 مدمج (صوت وصورة مع بعض)
            format_string = 'best[ext=mp4]/best'

        ydl_opts = {
            'format': format_string, 
            'quiet': True,         
            'noplaylist': True,
            'nocheckcertificate': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        }

        # نستخدم ملف الكوكيز من المجلد المسموح به /tmp
        if os.path.exists(cookie_path):
            ydl_opts['cookiefile'] = cookie_path

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(request.url, download=False)
                if not info:
                    return {"success": False, "error": "مقدرناش نسحب البيانات من يوتيوب."}

                # البحث عن الرابط المباشر
                direct_url = info.get('url')
                if not direct_url and 'formats' in info:
                    # نفلتر الروابط اللي فيها بروتوكول http وشغالة
                    valid_formats = [f for f in info['formats'] if f.get('url')]
                    if valid_formats:
                        direct_url = valid_formats[-1]['url']

                if direct_url:
                    return {
                        "success": True, 
                        "download_url": direct_url,
                        "title": info.get('title', 'Video'),
                        "thumbnail": info.get('thumbnail', '')
                    }
                return {"success": False, "error": "يوتيوب مش راضي يدينا رابط مباشر للفيديو ده."}
        except Exception as e:
            return {"success": False, "error": "حصلت مشكلة في المعالجة.", "details": str(e)}
