import sys
import uvicorn
from config import settings

def main():
    print("=" * 60)
    print("📜 Tarinamoottori – Tekoälypohjainen roolipelisimulaattori")
    print(f"Käynnistetään Web-palvelin osoitteessa: http://{settings.HOST}:{settings.PORT}")
    print("=" * 60)
    
    uvicorn.run(
        "web.api:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
        log_level="info",
    )

if __name__ == "__main__":
    main()
