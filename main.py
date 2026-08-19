import os
from datetime import datetime, timedelta
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
        ])

@app.post("/log")
async def receive_log(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = []

    items = body if isinstance(body, list) else [body]
    
    device_name = request.headers.get("Device-Name", "Unknown")
    phone_number = request.headers.get("Device-Number", "Unknown")

    rows_to_write = []
    time_threshold = datetime.now() - timedelta(hours=48)

    for item in items:
        contact_number = item.get("NUMBER", "Unknown")
        duration = item.get("DURATION", 0)

        raw_type = item.get("TYPE", 0)
        call_type_map = {
            1: "Входящий",
            2: "Исходящий",
            3: "Пропущенный",
            5: "Отклоненный",
            6: "Пропущенный"
        }
        try:
            call_type = call_type_map.get(int(raw_type), f"Другой ({raw_type})")
        except Exception:
            call_type = str(raw_type)

        raw_date = item.get("DATE", 0)
        try:
            timestamp_ms = int(raw_date)
            call_dt = datetime.fromtimestamp(timestamp_ms / 1000.0) + timedelta(hours=5)
            
            if call_dt < time_threshold:
                continue
                
            call_date = call_dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            call_date = str(raw_date)

        rows_to_write.append([
            device_name,
            phone_number,
            call_type,
            contact_number,
            call_date,
            duration,
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
    if df.empty:
        return {"error": "Call log is empty"}

    # --- 1. Обработка первого листа (Sheet1) ---
    # Переводим секунды длительности в формат "минуты:секунды" или читаемые минуты
    def format_duration(sec):
        try:
            sec = int(sec)
            m = sec // 60
            s = sec % 60
            return f"{m} мин {s} сек"
        except:
            return "0 мин 0 сек"

    df_sheet1 = df.copy()
    df_sheet1["Duration"] = df_sheet1["Duration (sec)"].apply(format_duration)
    df_sheet1 = df_sheet1.drop(columns=["Duration (sec)"])
    df_sheet1 = df_sheet1.rename(columns={"Duration": "Duration (Min:Sec)"})

    # --- 2. Создание сводки для второго листа (Sheet2) ---
    summary_data = []
    # Группируем по сотруднику (Имя устройства + номер телефона)
    grouped = df.groupby(["Device Name", "Phone Number"])

    for (dev_name, dev_phone), group in grouped:
        total_calls = len(group)
        
        # Считаем типы звонков
        incoming = len(group[group["Call Type"] == "Входящий"])
        outgoing = len(group[group["Call Type"] == "Исходящий"])
        missed = len(group[group["Call Type"].isin(["Пропущенный", "Отклоненный"])])
        
        # Общее время в секундах -> переводим в часы и минуты
        total_sec = group["Duration (sec)"].sum()
        hours = total_sec // 3600
        minutes = (total_sec % 3600) // 60
        seconds = total_sec % 60
        total_time_str = f"{hours} ч {minutes} мин {seconds} сек"

        summary_data.append({
            "Device Name": dev_name,
            "Phone Number": dev_phone,
            "Total Calls": total_calls,
            "Incoming": incoming,
            "Outgoing": outgoing,
            "Missed": missed,
            "Total Duration": total_time_str
        })

    df_sheet2 = pd.DataFrame(summary_data)

    # --- 3. Сохранение в Excel с двумя вкладками ---
    output_filename = "Call_Report.xlsx"
    with pd.ExcelWriter(output_filename, engine="openpyxl") as writer:
        df_sheet1.to_excel(writer, sheet_name="Звонки", index=False)
        df_sheet2.to_excel(writer, sheet_name="Сводка по сотрудникам", index=False)

    return FileResponse(
        output_filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="Call_Report.xlsx",
    )

@app.get("/")
def read_root():
    return {"message": "Server is running"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
