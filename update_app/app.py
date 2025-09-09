from flask import Flask, render_template, jsonify, request
import os
import re
import json
import aiohttp
import asyncio
import logging
import requests
from collections import defaultdict  # Adăugat importul pentru defaultdict

# Configurare logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, template_folder="templates", static_folder="static")

# Încarcă configurările
with open(os.path.join(BASE_DIR, "config", "config_aplicatii.json"), encoding="utf-8") as f:
    CONFIG_APLICATII = json.load(f)
with open(os.path.join(BASE_DIR, "config", "config_folder.json"), encoding="utf-8") as f:
    folder_config = json.load(f)
    FOLDER_UPDATE = folder_config["folder"]
    PORT = folder_config.get("port", 5050)
with open(os.path.join(BASE_DIR, "config", "config_servere.json"), encoding="utf-8") as f:
    SERVER_LIST = json.load(f)

APLICATII = list(CONFIG_APLICATII.keys())
TIPURI = ["surse", "scriptsql", "rdl"]

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/pachete")
def pachete():
    pachete = {app: {"surse": None, "scriptsql": None, "rdl": None} for app in APLICATII}
    versiuni_aplicatii = defaultdict(set)

    logging.info(f"Încerc să citesc directorul FOLDER_UPDATE: {FOLDER_UPDATE}")
    if not os.path.exists(FOLDER_UPDATE):
        logging.error(f"Directorul {FOLDER_UPDATE} nu există.")
        return jsonify({"pachete": pachete, "probleme_versiuni": {}, "valid": False})

    try:
        for fname in os.listdir(FOLDER_UPDATE):
            logging.debug(f"Procesez fișierul: {fname}")
            if not fname.lower().endswith(".zip"):
                continue
            for tip in TIPURI:
                for app in APLICATII:
                    pattern = rf"^{tip}_{app}_(\d{{4}}\.\d{{2}}\.\d{{2}})_v([\d\.]+)\.zip$"
                    match = re.match(pattern, fname, re.IGNORECASE)
                    if match:
                        data, versiune = match.groups()
                        logging.info(f"Găsit pachet valid: {fname} → {tip} pentru {app}, versiune {versiune}")
                        pachete[app][tip] = fname
                        versiuni_aplicatii[app].add(versiune)
                        break
                if match:
                    break
    except PermissionError as e:
        logging.error(f"Eroare de permisiune la citirea {FOLDER_UPDATE}: {e}")
        return jsonify({"pachete": pachete, "probleme_versiuni": {}, "valid": False})
    except Exception as e:
        logging.error(f"Eroare neașteptată la procesarea fișierelor din {FOLDER_UPDATE}: {e}")
        return jsonify({"pachete": pachete, "probleme_versiuni": {}, "valid": False})

    probleme_versiuni = {app: list(v) for app, v in versiuni_aplicatii.items() if len(v) > 1}
    valid = len(probleme_versiuni) == 0
    logging.info(f"Returnez pachete: {pachete}, valid: {valid}, probleme_versiuni: {probleme_versiuni}")

    return jsonify({"pachete": pachete, "probleme_versiuni": probleme_versiuni, "valid": valid})

@app.route("/debug_zipuri")
def debug_zipuri():
    output = []
    if not os.path.exists(FOLDER_UPDATE):
        return jsonify(["❌ Folderul de update nu există."])

    for fname in os.listdir(FOLDER_UPDATE):
        if not fname.lower().endswith(".zip"):
            continue
        matched = False
        for app in APLICATII:
            for tip in TIPURI:
                pattern = rf"^{tip}_{app}_(\d{{4}}\.\d{{2}}\.\d{{2}})_v([\d\.]+)\.zip$"
                if re.match(pattern, fname, re.IGNORECASE):
                    output.append(f"✔️ {fname} → {tip} pentru {app}")
                    matched = True
                    break
            if matched:
                break
        if not matched:
            tip_detectat = next((t for t in TIPURI if fname.lower().startswith(t + "_")), None)
            if tip_detectat:
                output.append(f"❌ {fname} → nerecunoscut după convenție ({tip_detectat}_[Aplicatie]_[yyyy.MM.dd]_vN.N.N.zip)")
            else:
                output.append(f"❌ {fname} → nerecunoscut")

    return jsonify(output)

async def verifica_server(ip, port, tip):
    try:
        logging.info(f"Verific statusul serverului {ip}:{port} prin agent")
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://{ip}:{port}/verifica", timeout=20) as response:
                if response.status == 200:
                    data = await response.json()
                    ping_status = "✔️" if data["ping"] else "❌"
                    app_pool_status = "✔️" if data["appPool"] else "❌"
                    sql_status = "✔️" if data["sql"] else "❌"
                    logging.info(f"Status primit de la agent {ip}:{port}: Ping={ping_status}, AppPool={app_pool_status}, SQL={sql_status}")
                else:
                    logging.warning(f"Agentul de pe {ip}:{port} a returnat status {response.status}")
                    ping_status = "❌"
                    app_pool_status = "❌"
                    sql_status = "❌"
    except Exception as e:
        logging.error(f"Eroare la comunicarea cu agentul de pe {ip}:{port}: {str(e)}")
        ping_status = "❌"
        app_pool_status = "❌"
        sql_status = "❌"

    return f"{ip}:{port} → {tip} (Ping: {ping_status}, Application Pool: {app_pool_status}, SQL Server: {sql_status})"

# Adăugare funcție status_server după verifica_server
async def status_server(ip, port):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://{ip}:{port}/status", timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {f"{ip}:{port}": data}
                else:
                    return {f"{ip}:{port}": {"status": "error", "message": f"Cod HTTP: {resp.status}"}}
    except Exception as e:
        return {f"{ip}:{port}": {"status": "error", "message": str(e)}}


@app.route("/verifica_servere")
async def verifica_servere():
    tasks = []
    for server in SERVER_LIST:
        ip = server["ip"]
        port = server["port"]
        tip = server.get("tip", "unknown")
        tasks.append(verifica_server(ip, port, tip))

    rezultate = await asyncio.gather(*tasks, return_exceptions=True)
    return jsonify([str(r) for r in rezultate])

# Adăugare endpoint /status_update după verifica_servere
@app.route("/status_update")
async def status_update():
    mod_test = request.args.get("test") == "1"

    rezultate = []
    toate_ok = True

    for server in SERVER_LIST:
        # filtrăm în funcție de tip
        if mod_test and server["tip"] != "deploy-test":
            continue
        if not mod_test and server["tip"] == "deploy-test":
            continue

        ip = server["ip"]
        port = server["port"]
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://{ip}:{port}/status", timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        rezultate.append({
                            "ip": ip,
                            "port": port,
                            "status": data.get("status", ""),
                            "message": data.get("message", ""),
                            "detalii": data.get("detalii", []),
                            "start_time": data.get("start_time", ""),
                            "end_time": data.get("end_time", "")
                        })
                        if data.get("status") != "success":
                            toate_ok = False
                    else:
                        rezultate.append({
                            "ip": ip,
                            "port": port,
                            "status": "eroare",
                            "message": f"HTTP {resp.status}",
                            "detalii": [f"❌ Răspuns invalid: HTTP {resp.status}"]
                        })
                        toate_ok = False
        except Exception as e:
            rezultate.append({
                "ip": ip,
                "port": port,
                "status": "eroare",
                "message": str(e),
                "detalii": [f"❌ Eroare la conectare: {str(e)}"]
            })
            toate_ok = False

    return jsonify({
        "status": "verificat",
        "toate_ok": toate_ok,
        "rezultate": rezultate
    })

@app.route("/start_update", methods=["POST"])
def start_update():
    data = request.get_json()
    mod_test = data.get("test", False)
    aplicatii_selectate = data.get("aplicatii", [])
    rezultate = []

    for server in SERVER_LIST:
        if mod_test and server["tip"] != "deploy-test":
            continue
        if not mod_test and server["tip"] == "deploy-test":
            continue

        ip, port, aplicatii = server["ip"], server["port"], server["aplicatii"]
        url = f"http://{ip}:{port}/update"
        rezultat = {"ip": ip, "port": port, "status": "ok", "detalii": []}

        files_to_send = []
        for app in aplicatii:
            if aplicatii_selectate and app not in aplicatii_selectate:
                continue
            for tip in TIPURI:
                pattern = rf"^{tip}_{app}_(\d{{4}}\.\d{{2}}\.\d{{2}})_v([\d\.]+)\.zip$"
                file = next((f for f in os.listdir(FOLDER_UPDATE) if re.match(pattern, f, flags=re.IGNORECASE)), None)
                if not file:
                    continue
                match = re.match(pattern, file, flags=re.IGNORECASE)
                data_val, versiune_val = match.group(1), match.group(2)
                filepath = os.path.join(FOLDER_UPDATE, file)
                files_to_send.append({
                    "file": file,
                    "filepath": filepath,
                    "tip": tip,
                    "aplicatie": app,
                    "versiune": versiune_val,
                    "data": data_val
                })

        if not files_to_send:
            rezultat["detalii"].append("Niciun fișier de actualizare găsit.")
            rezultate.append(rezultat)
            continue

        upload_url = f"http://{ip}:{port}/update"
        try:
            upload_files = [(f"file_{i}", (f["file"], open(f["filepath"], "rb"), "application/zip")) for i, f in enumerate(files_to_send)]
            upload_data = {
                f"file_{i}_tip": f["tip"] for i, f in enumerate(files_to_send)
            }
            upload_data.update({
                f"file_{i}_aplicatie": f["aplicatie"] for i, f in enumerate(files_to_send)
            })
            upload_data.update({
                f"file_{i}_versiune": f["versiune"] for i, f in enumerate(files_to_send)
            })
            upload_data.update({
                f"file_{i}_data": f["data"] for i, f in enumerate(files_to_send)
            })
            upload_data["num_files"] = str(len(files_to_send))

            upload_response = requests.post(upload_url, files=upload_files, data=upload_data, timeout=300)
            if upload_response.status_code in [200, 202]:
                rezultat["detalii"].append("✔️ Upload acceptat de agent")
                rezultat["status"] = "ok"
                try:
                    feedback = upload_response.json()
                    if "id" in feedback:
                        rezultat["detalii"].append(f"🆔 ID update: {feedback['id']}")
                    if "log" in feedback:
                        rezultat["detalii"].append("📝 Log agent: " + feedback["log"][:300] + "...")
                    if "final_status" in feedback:
                        rezultat["detalii"].append("✅ Finalizare agent: " + feedback["final_status"])
                except Exception as e:
                    rezultat["detalii"].append(f"ℹ️ Răspunsul de la agent nu a putut fi interpretat: {str(e)}")
            elif upload_response.status_code == 400:
                rezultat["detalii"].append("⚠️ Upload acceptat de agent (HTTP 400), dar fără feedback JSON. Presupunem lansarea procesului.")
                rezultat["status"] = "ok"
            else:
                rezultat["status"] = "eroare"
                rezultat["detalii"].append(f"❌ Upload eșuat cu status {upload_response.status_code}")
                rezultate.append(rezultat)
                continue
        except Exception as e:
            rezultat["status"] = "eroare"
            rezultat["detalii"].append(f"❌ Eroare la upload: {e}")
            rezultate.append(rezultat)
            continue


        rezultate.append(rezultat)

    toate_ok = all(r["status"] == "ok" for r in rezultate)
    return jsonify({"status": "terminat", "toate_ok": toate_ok, "rezultate": rezultate})

@app.route("/rollback", methods=["POST"])
def rollback():
    data = request.get_json()
    aplicatie = data.get("aplicatie")
    backup_timestamp = data.get("backup_timestamp")
    rezultate = []

    for server in SERVER_LIST:
        ip, port = server["ip"], server["port"]
        url = f"http://{ip}:{port}/rollback"
        rezultat = {"ip": ip, "port": port, "status": "ok", "detalii": []}

        try:
            r = requests.post(url, data={"aplicatie": aplicatie, "backup_timestamp": backup_timestamp}, timeout=30)
            if r.status_code == 200:
                response_data = r.json()
                if response_data["status"] == "success":
                    rezultat["detalii"].extend(response_data["detalii"])
                else:
                    rezultat["status"] = "eroare"
                    if "detalii" in response_data:
                        rezultat["detalii"].extend(response_data["detalii"])
                    rezultat["detalii"].append(f"❌ Rollback eșuat: {response_data.get('message', 'Eroare necunoscută')}")
            else:
                rezultat["status"] = "eroare"
                try:
                    response_data = r.json()
                    if "detalii" in response_data:
                        rezultat["detalii"].extend(response_data["detalii"])
                    rezultat["detalii"].append(f"❌ Rollback eșuat: {response_data.get('message', f'Status {r.status_code}')}")
                except ValueError:
                    rezultat["detalii"].append(f"❌ Rollback eșuat (status {r.status_code})")
        except Exception as e:
            rezultat["status"] = "eroare"
            rezultat["detalii"].append(f"❌ Eroare: {e}")

        rezultate.append(rezultat)

    toate_ok = all(r["status"] == "ok" for r in rezultate)
    return jsonify({"status": "terminat", "toate_ok": toate_ok, "rezultate": rezultate})


# Endpoint pentru returnarea IP-ului local al serverului
@app.route("/ip_local")
def ip_local():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception:
        ip = "127.0.0.1"
    return jsonify({"ip": ip})

# Endpoint pentru expunerea conținutului SERVER_LIST
@app.route("/config_servere")
def config_servere():
    return jsonify(SERVER_LIST)

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    from waitress import serve
    serve(app, host="0.0.0.0", port=PORT, connection_limit=100, cleanup_interval=10, channel_timeout=600)