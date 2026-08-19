import os
from datetime import datetime
import csv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
import pandas as pd
import uvicorn

app = FastAPI()

DATA_FILE = "call_logs.csv"

# Создаем файл с заголовками, если его еще нет
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Device Name",
            "Phone Number",
            "Call Type",
            "Contact Number",
            "Date & Time",
            "Duration (sec)",
            "Received At",
        ])

@app.post("/log")
async def receive_log(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = []

    # Android шлет массив звонков (JSONArray)
    items = body if isinstance(body, list) else [body]
    
    # Получаем заголовки устройства из запроса
    device_name = request.headers.get("Device-Name", "Unknown")
    phone_number = request.headers.get("Device-Number", "Unknown")

    rows_to_write = []
    received_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for item in items:
        call_id = item.get("ID", "Unknown")
        contact_number = item.get("NUMBER", "Unknown")
        duration = item.get("DURATION", 0)

        # Конвертируем тип звонка из цифры в читаемый текст
        raw_type = item.get("TYPE", 0)
        call_type_map = {
            1: "Входящий",
            2: "Исходящий",
            3: "Пропущенный",
            5: "Отклоненный",
            6: "Заблокированный"
        }
        try:
            call_type = call_type_map.get(int(raw_type), f"Другой ({raw_type})")
        except Exception:
            call_type = str(raw_type)

        # Конвертируем миллисекунды в красивую дату и время
        raw_date = item.get("DATE", 0)
        try:
            timestamp_ms = int(raw_date)
            call_date = datetime.fromtimestamp(timestamp_ms / 1000.0).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            call_date = str(raw_date)

        rows_to_write.append([
            device_name,
            phone_number,
            call_type,
            contact_number,
            call_date,
            duration,
            received_at,
        ])

    with open(DATA_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(rows_to_write)

    return {"status": "success", "saved": len(rows_to_write)}

@app.get("/download-report")
async def download_report():
    if not os.path.exists(DATA_FILE):
        return {"error": "No data found"}

    df = pd.read_csv(DATA_FILE)
    output_filename = "Call_Report.xlsx"
    df.to_excel(output_filename, index=False)

    return FileResponse(
        output_filename,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        filename="Call_Report.xlsx",
    )

@app.get("/")
def read_root():
    return {"message": "Server is running"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
