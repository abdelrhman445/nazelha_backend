from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
import httpx

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
    return {"message": "الباك إند شغال تمام!"}

@app.post("/api/download")
async def get_download_link(request: VideoRequest):
    url_lower = request.url.lower()
    
    # ==========================================
    # 1. التعامل مع تيك توك (بدون علامة مائية وبدون مساحة)
    # ==========================================
    if "tiktok.com" in url_lower or "douyin.com" in url_lower:
        try:
            async with httpx.AsyncClient() as client:
                # استخدام API مخصص لتخطي حماية تيك توك
                api_url = f"https://www.tikwm.com/api/?url={request.url}"
                response = await client.get(api_url, timeout=15.0)
                data = response.json()
                
                if data.get("code") == 0:
                    vid_data = data.get("data", {})
                    
                    # تحديد الرابط بناءً على اختيار المستخدم
                    final_url = vid_data.get("music") if request.download_type == "audio" else vid_data.get("play")
                    
                    if final_url:
                        return {
                            "success": True, 
                            "download_url": final_url,
                            "title": vid_data.get("title", "TikTok Video"),
                            "thumbnail": vid_data.get("cover", "")
                        }
                return {"success": False, "error": "مقدرناش نجيب الفيديو من تيك توك."}
        except Exception as e:
            return {"success": False, "error": "مشكلة في الاتصال بسيرفر تيك توك."}

    # ==========================================
    # 2. التعامل مع يوتيوب وباقي المواقع بـ yt-dlp
    # ==========================================
    else:
        format_string = 'best'
        if request.download_type == "audio":
            if request.quality == "high": format_string = 'bestaudio/best'
            elif request.quality == "medium": format_string = 'bestaudio[abr<=128]/bestaudio/best'
            else: format_string = 'worstaudio/worst'
        else:
            if request.quality == "high": format_string = 'best[ext=mp4]/best'
            elif request.quality == "medium": format_string = 'best[height<=480][ext=mp4]/best'
            else: format_string = 'best[height<=360][ext=mp4]/worst'

        ydl_opts = {
            'format': format_string, 
            'quiet': True,         
            'noplaylist': True,
            'cookiefile': 'cookies.txt',  # السطر ده هو اللي هيحل الأزمة
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'referer': 'https://www.google.com/',
            'http_headers': {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Sec-Fetch-Mode': 'navigate',
            }
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(request.url, download=False)
                
                direct_url = info.get('url')
                if not direct_url and 'formats' in info:
                    formats = [f for f in info['formats'] if f.get('url')]
                    if formats: direct_url = formats[-1]['url']

                if direct_url:
                    return {
                        "success": True, 
                        "download_url": direct_url,
                        "title": info.get('title', 'Video'),
                        "thumbnail": info.get('thumbnail', '')
                    }
                else:
                    return {"success": False, "error": "مقدرناش نستخرج رابط التحميل المباشر."}

        except Exception as e:
            # إرجاع تفاصيل الخطأ عشان الواجهة تعرضه لو حصلت مشكلة
            return {"success": False, "error": "حدث خطأ أثناء المعالجة.", "details": str(e)}
