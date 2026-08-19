import os
from datetime import datetime, timedelta
import csv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
import pandas as pd
import uvicorn

app = FastAPI()

DATA_FILE = "call_logs.csv"

# Создаем файл с русскими заголовками, если его еще нет
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Имя устройства",
            "Номер телефона",
            "Тип звонка",
            "Номер контакта",
            "Дата и время",
            "Длительность (сек)",
        ])

@app.post("/log")
async def receive_log(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = []

    items = body if isinstance(body, list) else [body]
    
    device_name = request.headers.get("Device-Name", "Неизвестно")
    phone_number = request.headers.get("Device-Number", "Неизвестно")

    rows_to_write = []
    time_threshold = datetime.now() - timedelta(hours=48)

    for item in items:
        contact_number = item.get("NUMBER", "Неизвестно")
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

        # Если звонок пропущенный или отклоненный, принудительно ставим длительность 0 секунд
        if call_type in ["Пропущенный", "Отклоненный"]:
            duration = 0

        raw_date = item.get("DATE", 0)
        try:
            timestamp_ms = int(raw_date)
            # Переводим в дату и добавляем 5 часов для местного времени (Ташкент UTC+5)
            call_dt = datetime.fromtimestamp(timestamp_ms / 1000.0) + timedelta(hours=5)
            
            # Отсекаем звонки старше 48 часов
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

    # --- 1. Первый лист: Звонки ---
    def format_duration(sec):
        try:
            sec = int(sec)
            m = sec // 60
            s = sec % 60
            return f"{m} мин {s} сек"
        except:
            return "0 мин 0 сек"

    df_sheet1 = df.copy()
    df_sheet1["Длительность"] = df_sheet1["Длительность (сек)"].apply(format_duration)
    df_sheet1 = df_sheet1.drop(columns=["Длительность (сек)"])

    # --- 2. Второй лист: Сводка по сотрудникам ---
    summary_data = []
    grouped = df.groupby(["Имя устройства", "Номер телефона"])

    for (dev_name, dev_phone), group in grouped:
        total_calls = len(group)
        incoming = len(group[group["Тип звонка"] == "Входящий"])
        outgoing = len(group[group["Тип звонка"] == "Исходящий"])
        missed = len(group[group["Тип звонка"].isin(["Пропущенный", "Отклоненный"])])
        
        total_sec = group["Длительность (сек)"].sum()
        hours = total_sec // 3600
        minutes = (total_sec % 3600) // 60
        seconds = total_sec % 60
        total_time_str = f"{hours} ч {minutes} мин {seconds} сек"

        summary_data.append({
            "Имя устройства": dev_name,
            "Номер телефона": dev_phone,
            "Всего звонков": total_calls,
            "Входящие": incoming,
            "Исходящие": outgoing,
            "Пропущенные": missed,
            "Общее время": total_time_str
        })

    df_sheet2 = pd.DataFrame(summary_data)

    # --- 3. Сохранение файла Excel с двумя вкладками ---
    output_filename = "Call_Report.xlsx"
    with pd.ExcelWriter(output_filename, engine="openpyxl") as writer:
        df_sheet1.to_excel(writer, sheet_name="Журнал звонков", index=False)
        df_sheet2.to_excel(writer, sheet_name="Сводка по сотрудникам", index=False)

    return FileResponse(
        output_filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="Call_Report.xlsx",
    )

@app.get("/", response_class=HTMLResponse)
async def read_root():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Файл index.html не найден на сервере</h1>"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
