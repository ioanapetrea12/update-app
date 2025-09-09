from flask import Flask, request, jsonify
from waitress import serve
import configparser
import os
import logging
import subprocess
import zipfile
import shutil
import datetime
import sys
import socket
import json

# ThreadPoolExecutor și locking pentru status update
from concurrent.futures import ThreadPoolExecutor
import threading

executor = ThreadPoolExecutor(max_workers=3)
last_update_status = {}
last_update_lock = threading.Lock()

# Inițializare Flask
app = Flask(__name__)

# Citire configurații din agent.ini
config = configparser.ConfigParser()
#config.read("agent.ini", encoding="utf-8")
# if getattr(sys, 'frozen', False):
#     ini_path = os.path.join(os.path.dirname(sys.executable), "agent.ini")

# if os.path.exists(ini_path):
#     print(f"Fișierul INI a fost găsit la: {ini_path}")
#     config.read(ini_path, encoding="utf-8")
# else:
#     print(f"Fișierul INI nu a fost găsit la: {ini_path}")

# config.read(ini_path, encoding="utf-8")


if getattr(sys, 'frozen', False):
    base_path = os.path.dirname(sys.executable)
else:
    base_path = os.path.abspath(os.path.dirname(__file__))

ini_path = os.path.join(base_path, "agent.ini")

print(f"Caut ini_path în: {ini_path}")
if os.path.exists(ini_path):
    print("Fișierul .ini a fost găsit.")
    config.read(ini_path, encoding="utf-8-sig")
else:
    print("Fișierul .ini NU a fost găsit.")


UPLOAD_FOLDER = config.get("agent", "upload_folder", fallback="C:/RSR/Primite")
IIS_ROOT = config.get("agent", "iis_root", fallback="C:/Simec/AplicatiiPort80/AERO")
BACKUP_FOLDER = config.get("agent", "backup_folder", fallback="C:/RSR/Backup")
PORT = config.getint("agent", "port", fallback=5000)
LOG_FILE = config.get("agent", "log_file", fallback=os.path.join(UPLOAD_FOLDER, "agent_update.log"))
APPLICATION_POOL = config.get("agent", "application_pool", fallback="SimecAero")
SQL_SERVER = config.get("agent", "sql_server", fallback="localhost")
SQL_USER = config.get("agent", "sql_user", fallback="sa")
SQL_PASS = config.get("agent", "sql_pass", fallback="password")
SQL_DBNAME = config.get("agent", "sql_dbName", fallback="dbname")

# Asigurare existență foldere
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
os.makedirs(BACKUP_FOLDER, exist_ok=True)
os.makedirs(IIS_ROOT, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

@app.route("/verifica", methods=["GET"])
def verifica():
    # Inițializăm rezultatele
    ping = False
    app_pool = False
    sql = False

    # Verificare ping (cererea HTTP a ajuns, deci serverul este accesibil)
    try:
        logger.info("Verificare accesibilitate prin cerere HTTP")
        sys.stdout.flush()
        ping = True  # Dacă cererea ajunge aici, serverul este accesibil
    except Exception as e:
        logger.error(f"Eroare la verificarea ping: {e}")
        sys.stdout.flush()
        ping = False

    # Verificare Application Pool
    try:
        logger.info(f"Verificare starea Application Pool: {APPLICATION_POOL}")
        sys.stdout.flush()
        app_pool_cmd = ['powershell', '-Command', f'(Get-WebAppPoolState -Name "{APPLICATION_POOL}").Value']
        app_pool_result = subprocess.run(app_pool_cmd, capture_output=True, text=True, timeout=5)
        app_pool = app_pool_result.stdout.strip().lower() == "started"
        logger.info(f"Stare Application Pool: {app_pool}")
        sys.stdout.flush()
    except Exception as e:
        logger.error(f"Eroare la verificarea Application Pool: {e}")
        sys.stdout.flush()
        app_pool = False

    # Verificare SQL Server
    try:
        logger.info(f"Verificare SQL Server pe {SQL_SERVER}")
        sys.stdout.flush()
        sql_cmd = ['sqlcmd', '-S', SQL_SERVER, '-U', SQL_USER, '-P', SQL_PASS, '-Q', 'SELECT 1']
        sql_result = subprocess.run(sql_cmd, capture_output=True, text=True, timeout=10)  # Timeout crescut
        sql = sql_result.returncode == 0
        logger.info(f"Rezultat SQL Server: {sql}")
        sys.stdout.flush()
    except Exception as e:
        logger.error(f"Eroare la verificarea SQL Server: {e}")
        sys.stdout.flush()
        sql = False

    # Returnăm rezultatele
    return jsonify({"ping": ping, "appPool": app_pool, "sql": sql})

@app.route("/update", methods=["POST"])
def update():
    logger.info("Primire update de la: %s", request.remote_addr)
    sys.stdout.flush()

    num_files = int(request.form.get("num_files", 0))
    if num_files == 0:
            logger.error("Nu s-a specificat numărul de fișiere sau nu s-au trimis fișiere.")
            sys.stdout.flush()
            return jsonify({"status": "error", "message": "No files specified"}), 400

    files_to_process = []
    for i in range(num_files):
        file_key = f"file_{i}"
        if file_key not in request.files:
            logger.error(f"Fișierul {file_key} lipsește din request.")
            sys.stdout.flush()
            return jsonify({"status": "error", "message": f"Missing file {file_key}"}), 400

        f = request.files[file_key]
        tip = request.form.get(f"{file_key}_tip")
        aplicatie = request.form.get(f"{file_key}_aplicatie")
        versiune = request.form.get(f"{file_key}_versiune")
        data = request.form.get(f"{file_key}_data")

        if not all([tip, aplicatie, versiune, data]):
            missing = [param for param, value in [("tip", tip), ("aplicatie", aplicatie), ("versiune", versiune), ("data", data)] if not value]
            logger.error(f"Parametri lipsă pentru {file_key}: {missing}")
            sys.stdout.flush()
            return jsonify({"status": "error", "message": f"Missing parameters for {file_key}: {missing}"}), 400

        filepath = os.path.join(UPLOAD_FOLDER, f.filename)
        try:
            f.save(filepath)
            logger.info("Fișier salvat imediat: %s", filepath)
            sys.stdout.flush()
        except Exception as e:
            logger.exception("Eroare la salvarea imediată a fișierului: %s", f.filename)
            sys.stdout.flush()
            return jsonify({"status": "error", "message": f"Eroare la salvarea fișierului {f.filename}: {e}"}), 500

        files_to_process.append({
            "filepath": filepath,
            "filename": f.filename,
            "tip": tip,
            "aplicatie": aplicatie,
            "versiune": versiune,
            "data": data
        })

    app_pool = APPLICATION_POOL if APPLICATION_POOL else f"{files_to_process[0]['aplicatie']}AppPool"

    # Stocăm inițial statusul ca pending
    with last_update_lock:
        last_update_status["status"] = "pending"
        last_update_status["detalii"] = []
        last_update_status["start_time"] = datetime.datetime.now().isoformat()
        # Setează un identificator unic pentru update
        last_update_status["id"] = f"{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{request.remote_addr}"

    executor.submit(handle_update_async, files_to_process, app_pool)

    return jsonify({
        "status": "started",
        "message": "Procesare pornită în fundal",
        "status_url": "/status"
    }), 202
def handle_update_async(files_to_process, app_pool):
    # Inițializare status update la începutul procesului
    with last_update_lock:
        last_update_status["id"] = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        last_update_status["status"] = "in_progress"
        last_update_status["message"] = "Proces de update pornit"
        last_update_status["detalii"] = []
        last_update_status["start_time"] = datetime.datetime.now().isoformat()
    detalii = []
    try:
        result = subprocess.run(
            ['powershell', '-Command', f'(Get-WebAppPoolState -Name "{app_pool}").Value'],
            capture_output=True, text=True, check=True
        )
        pool_state = result.stdout.strip()
        logger.info(f"Stare Application Pool {app_pool}: {pool_state}")
        sys.stdout.flush()

        if pool_state.lower() != "stopped":
            subprocess.run(['powershell', '-Command', f'Stop-WebAppPool -Name "{app_pool}"'], check=True)
            logger.info(f"Application Pool {app_pool} oprit cu succes")
            sys.stdout.flush()
            detalii.append(f"Application Pool {app_pool} oprit")
            with last_update_lock:
                last_update_status["detalii"].append(f"Application Pool {app_pool} oprit")
        else:
            logger.info(f"Application Pool {app_pool} este deja oprit")
            sys.stdout.flush()
            detalii.append(f"Application Pool {app_pool} este deja oprit")
            with last_update_lock:
                last_update_status["detalii"].append(f"Application Pool {app_pool} este deja oprit")
    except subprocess.CalledProcessError as e:
        if hasattr(e, "stderr") and e.stderr and "already stopped" in e.stderr.lower():
            logger.info(f"Application Pool {app_pool} este deja oprit (ignorăm eroarea)")
            sys.stdout.flush()
            detalii.append(f"Application Pool {app_pool} este deja oprit")
            with last_update_lock:
                last_update_status["detalii"].append(f"Application Pool {app_pool} este deja oprit")
        else:
            logger.error(f"Eroare la oprirea Application Pool {app_pool}: {e}")
            sys.stdout.flush()
            with last_update_lock:
                last_update_status["status"] = "error"
                last_update_status["message"] = f"Eroare la oprirea Application Pool: {e}"
                last_update_status["detalii"] = detalii
                last_update_status["end_time"] = datetime.datetime.now().isoformat()
            return

    for file_info in files_to_process:
        logger.info(f"--- Procesăm fișier: {file_info}")
        filepath = file_info["filepath"]
        tip = file_info["tip"]
        aplicatie = file_info["aplicatie"]
        versiune = file_info["versiune"]
        data = file_info["data"]
        filename = file_info["filename"]
        extract_path = os.path.join(UPLOAD_FOLDER, f"{aplicatie}_{tip}_{data}_v{versiune}")

        # 1. Creează folderul de extracție
        # Șterge folderul anterior dacă există, ca să nu rămână fișiere vechi
        if os.path.exists(extract_path):
            shutil.rmtree(extract_path)

        os.makedirs(extract_path, exist_ok=True)
        try:
            logger.info("Fișier salvat: %s", filepath)
            sys.stdout.flush()
            detalii.append(f"Fișier salvat: {filename}")
            with last_update_lock:
                last_update_status["detalii"].append(f"Fișier salvat: {filename}")
        except Exception as e:
            logger.exception("Eroare la salvarea fișierului: %s", filename)
            sys.stdout.flush()
            detalii.append(f"❌ {filename} eșuat: Eroare la salvare: {str(e)}")
            with last_update_lock:
                last_update_status["detalii"].append(f"❌ {filename} eșuat: Eroare la salvare: {str(e)}")
            continue

        # 2. Dezarhivează fișierul ZIP
        try:
            with zipfile.ZipFile(filepath, 'r') as zip_ref:
                logger.info(f"[{tip.upper()}] Dezarhivare fișier ZIP: {filename}")
                zip_ref.extractall(extract_path)
            logger.info(f"Fișier extras în {extract_path}")
            sys.stdout.flush()
            detalii.append(f"Fișier extras în {extract_path}")
            with last_update_lock:
                last_update_status["detalii"].append(f"Fișier extras în {extract_path}")
        except zipfile.BadZipFile as e:
            logger.error(f"Fișierul zip {filename} este corupt: {e}")
            sys.stdout.flush()
            detalii.append(f"❌ {filename} eșuat: Fișierul zip este corupt: {e}")
            with last_update_lock:
                last_update_status["detalii"].append(f"❌ {filename} eșuat: Fișierul zip este corupt: {e}")
            continue


        if tip == "surse":
            # 2. Backup IIS folder
            backup_iis_path = os.path.join(BACKUP_FOLDER, "IIS")
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_version_path = os.path.join(backup_iis_path, timestamp)
            os.makedirs(backup_version_path, exist_ok=True)
            try:
                if os.path.exists(IIS_ROOT) and os.listdir(IIS_ROOT):
                    shutil.copytree(IIS_ROOT, os.path.join(backup_version_path, os.path.basename(IIS_ROOT)), dirs_exist_ok=True)
                    logger.info(f"Backup IIS creat în {backup_version_path}")
                    sys.stdout.flush()
                    detalii.append(f"Backup IIS creat în {backup_version_path}")
                    with last_update_lock:
                        last_update_status["detalii"].append(f"Backup IIS creat în {backup_version_path}")
                else:
                    logger.warning(f"Nu există fișiere în {IIS_ROOT} pentru backup")
                    sys.stdout.flush()
                    detalii.append(f"Nu există fișiere în {IIS_ROOT} pentru backup")
                    with last_update_lock:
                        last_update_status["detalii"].append(f"Nu există fișiere în {IIS_ROOT} pentru backup")
            except Exception as e:
                logger.error(f"Eroare la backup IIS: {e}")
                sys.stdout.flush()
                detalii.append(f"❌ {filename} eșuat: Eroare la backup IIS: {e}")
                with last_update_lock:
                    last_update_status["detalii"].append(f"❌ {filename} eșuat: Eroare la backup IIS: {e}")
                continue
            # 3. Copiere fișiere direct din folderul dezarhivat în IIS_ROOT
            try:
                if not os.path.exists(extract_path):
                    logger.error(f"Folderul de surse nu există: {extract_path}")
                    sys.stdout.flush()
                    detalii.append(f"❌ {filename} eșuat: Folderul de surse nu există: {extract_path}")
                    with last_update_lock:
                        last_update_status["detalii"].append(f"❌ {filename} eșuat: Folderul de surse nu există: {extract_path}")
                    continue

                for item in os.listdir(extract_path):
                    src = os.path.join(extract_path, item)
                    dst = os.path.join(IIS_ROOT, item)
                    if os.path.isdir(src):
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                    else:
                        shutil.copy2(src, dst)
                logger.info(f"Surse copiate din {extract_path} în {IIS_ROOT}")
                sys.stdout.flush()
                detalii.append(f"Surse copiate din {extract_path} în {IIS_ROOT}")
                with last_update_lock:
                    last_update_status["detalii"].append(f"Surse copiate din {extract_path} în {IIS_ROOT}")
            except Exception as e:
                logger.error(f"Eroare la copierea fișierelor în {IIS_ROOT}: {e}")
                sys.stdout.flush()
                detalii.append(f"❌ {filename} eșuat: Eroare la copierea fișierelor în {IIS_ROOT}: {e}")
                with last_update_lock:
                    last_update_status["detalii"].append(f"❌ {filename} eșuat: Eroare la copierea fișierelor în {IIS_ROOT}: {e}")
                continue
        elif tip == "scriptsql":
             # 1. Creează backup cu timestamp
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_timestamp = timestamp 
            backup_db_path = os.path.join(BACKUP_FOLDER, "BackupDB")
            os.makedirs(backup_db_path, exist_ok=True)
            backup_file = os.path.join(backup_db_path, f"ErpSimecRS_{timestamp}.bak")
            backup_cmd = (
                f'sqlcmd -S {SQL_SERVER} -U {SQL_USER} -P {SQL_PASS} '
                f'-Q "BACKUP DATABASE [{SQL_DBNAME}] TO DISK = N\'{backup_file}\' '
                f'WITH NOFORMAT, INIT, NAME = N\'{SQL_DBNAME} Full Backup\', SKIP, NOREWIND, NOUNLOAD, STATS = 10;"'
            )

            try:
                result = subprocess.run(backup_cmd, shell=True, check=True, capture_output=True, text=True)
                logger.info(f"✅ Backup DB creat: {backup_file}")
                sys.stdout.flush()
                detalii.append(f"Backup DB creat: {backup_file}")
                with last_update_lock:
                    last_update_status["detalii"].append(f"Backup DB creat: {backup_file}")
            except subprocess.CalledProcessError as e:
                error_message = f"Eroare la backup DB: {e.stderr or e.stdout}"
                logger.error(error_message)
                sys.stdout.flush()
                detalii.append(f"❌ {filename} eșuat: {error_message}")
                with last_update_lock:
                    last_update_status["detalii"].append(f"❌ {filename} eșuat: {error_message}")
                continue

            # 2. Verifică backup-ul cu RESTORE VERIFYONLY
            verify_cmd = (
                f'sqlcmd -S {SQL_SERVER} -U {SQL_USER} -P {SQL_PASS} '
                f'-Q "DECLARE @pos INT; '
                f'SELECT @pos = position FROM msdb..backupset WHERE database_name = N\'{SQL_DBNAME}\' '
                f'AND backup_set_id = (SELECT MAX(backup_set_id) FROM msdb..backupset WHERE database_name = N\'{SQL_DBNAME}\'); '
                f'IF @pos IS NULL RAISERROR(\'Backup inexistent\', 16, 1); '
                f'RESTORE VERIFYONLY FROM DISK = N\'{backup_file}\' WITH FILE = @pos;"'
            )
            try:
                subprocess.run(verify_cmd, shell=True, check=True, capture_output=True, text=True)
                logger.info("✅ Backup verificat cu succes")
                sys.stdout.flush()
                detalii.append("Backup verificat cu succes")
                with last_update_lock:
                    last_update_status["detalii"].append("Backup verificat cu succes")
            except subprocess.CalledProcessError as e:
                error_message = f"Eroare la verificarea backup-ului: {e.stderr or e.stdout}"
                logger.error(error_message)
                sys.stdout.flush()
                detalii.append(f"❌ {filename} eșuat: {error_message}")
                with last_update_lock:
                    last_update_status["detalii"].append(f"❌ {filename} eșuat: {error_message}")
                continue

            # 3. Rulează scriptul SQL
            sql_script = os.path.join(extract_path, f"update_Produse.sql")
            log_file = os.path.join(extract_path, 'sql_script.log')
            if not os.path.exists(sql_script):
                logger.error(f"Fișierul SQL nu există: {sql_script}")
                detalii.append(f"Fișierul SQL lipsește: {sql_script}")
                raise FileNotFoundError(f"Fișierul SQL nu a fost găsit: {sql_script}")
            sql_cmd = (
                f'sqlcmd -S {SQL_SERVER} -U {SQL_USER} -P {SQL_PASS} '
                f'-d {SQL_DBNAME} -i "{sql_script}" -o "{log_file}"'
            )

            try:
                subprocess.run(sql_cmd, shell=True, check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as e:
                error_message = f"Eroare la rularea scriptului SQL: {e.stderr or e.stdout}"
                logger.error(error_message)
                sys.stdout.flush()
                detalii.append(f"❌ {filename} eșuat: {error_message}")
                with last_update_lock:
                    last_update_status["detalii"].append(f"❌ {filename} eșuat: {error_message}")
                continue

            # 4. Verificare erori în fișierul de log
            with open(log_file, 'r', encoding='utf-8') as lf:
                log_content = lf.read()
                if 'error' in log_content.lower():
                    logger.error(f"Eroare în scriptul SQL: {log_content}")
                    sys.stdout.flush()
                    detalii.append(f"❌ {filename} eșuat: Eroare în scriptul SQL: {log_content}")
                    with last_update_lock:
                        last_update_status["detalii"].append(f"❌ {filename} eșuat: Eroare în scriptul SQL: {log_content}")
                    continue

            logger.info("✅ Script SQL rulat cu succes")
            sys.stdout.flush()
            detalii.append("Script SQL rulat cu succes")
            with last_update_lock:
                last_update_status["detalii"].append("Script SQL rulat cu succes")
        elif tip == "rdl":
            try:
                extract_path = os.path.join(UPLOAD_FOLDER, f"{aplicatie}_rdl_{data}_v{versiune}")
                os.makedirs(extract_path, exist_ok=True)

                # Dezarhivare zip
                with zipfile.ZipFile(filepath, 'r') as zip_ref:
                    zip_ref.extractall(extract_path)

                logger.info(f"Arhiva RDL a fost dezarhivată în: {extract_path}")
                detalii.append(f"Arhiva RDL a fost dezarhivată în: {extract_path}")
                with last_update_lock:
                    last_update_status["detalii"].append(f"Arhiva RDL a fost dezarhivată în: {extract_path}")

                # Copiere .rdl în reports/planificare
                rdl_dest_path = os.path.join(UPLOAD_FOLDER, "reports", "planificare")
                os.makedirs(rdl_dest_path, exist_ok=True)

                rdl_files_copied = 0
                for root, _, files in os.walk(extract_path):
                    for file in files:
                        if file.lower().endswith(".rdl"):
                            shutil.copy(os.path.join(root, file), rdl_dest_path)
                            rdl_files_copied += 1

                if rdl_files_copied == 0:
                    msg = "⚠️ Nu a fost găsit niciun fișier .rdl în arhivă."
                    logger.warning(msg)
                    detalii.append(msg)
                    with last_update_lock:
                        last_update_status["detalii"].append(msg)
                else:
                    msg = f"{rdl_files_copied} fișiere .rdl copiate în: {rdl_dest_path}"
                    logger.info(msg)
                    detalii.append(msg)
                    with last_update_lock:
                        last_update_status["detalii"].append(msg)

                # Rulează DeployReports.bat
                deploy_script_path = os.path.join("C:/RSR/Agent/reports", "DeployReports.bat")
                if not os.path.isfile(deploy_script_path):
                    msg = f"❌ Nu a fost găsit DeployReports.bat la: {deploy_script_path}"
                    logger.error(msg)
                    detalii.append(msg)
                    with last_update_lock:
                        last_update_status["detalii"].append(msg)
                else:
                    try:
                        result = subprocess.run(
                            f'"{deploy_script_path}"',
                            shell=True,
                            capture_output=True,
                            text=True,
                            timeout=300  # <--- timeout 
                        )
                        if result.returncode == 0:
                            msg = "DeployReports.bat a fost rulat cu succes."
                            logger.info(msg)
                            detalii.append(msg)
                            with last_update_lock:
                                last_update_status["detalii"].append(msg)
                        else:
                            msg = f"❌ Eroare la rularea DeployReports.bat:\n{result.stderr}"
                            logger.error(msg)
                            detalii.append(msg)
                            with last_update_lock:
                                last_update_status["detalii"].append(msg)
                    except subprocess.TimeoutExpired:
                        msg = "❌ DeployReports.bat a depășit timpul maxim permis (timeout)."
                        logger.error(msg)
                        detalii.append(msg)
                        with last_update_lock:
                            last_update_status["detalii"].append(msg)

            except Exception as e:
                error_message = f"❌ Eroare la procesarea RDL: {str(e)}"
                logger.error(error_message)
                sys.stdout.flush()
                detalii.append(error_message)
                last_update_status["status"] = "ERROR"
                with last_update_lock:
                    last_update_status["detalii"].append(error_message)
                continue

        try:
            shutil.rmtree(extract_path)
            logger.info(f"Folderul temporar {extract_path} a fost șters")
            sys.stdout.flush()
            detalii.append(f"Folderul temporar {extract_path} a fost șters")
            with last_update_lock:
                last_update_status["detalii"].append(f"Folderul temporar {extract_path} a fost șters")
        except Exception as e:
            logger.warning(f"Eroare la ștergerea folderului temporar {extract_path}: {e}")
            sys.stdout.flush()
            detalii.append(f"Avertisment: Eroare la ștergerea folderului temporar {extract_path}: {e}")
            with last_update_lock:
                last_update_status["detalii"].append(f"Avertisment: Eroare la ștergerea folderului temporar {extract_path}: {e}")
        # Verificare dacă există erori pentru a nu continua cu repornirea Application Pool
        if any("❌" in d for d in detalii):
            logger.warning("Au apărut erori în update.")
            sys.stdout.flush()

            try:
                with open("config_servere.json", encoding="utf-8") as f:
                    servere_config = json.load(f)
                hostname = socket.gethostname()
                ip_local = socket.gethostbyname(hostname)
                server_gasit = next((s for s in servere_config if s["ip"] == ip_local), None)
            except Exception as e:
                logger.error(f"Eroare la determinarea tipului de server: {e}")
                server_gasit = None

            if not server_gasit or server_gasit.get("tip") != "deploy":
                logger.info("Rollback disponibil doar pe servere de tip 'deploy'.")
                detalii.append("Rollback disponibil doar pe servere de tip 'deploy'.")
                break

            # Verificăm dacă e vorba de SQL sau Surse
            rollback_needed = any(
                file_info["tip"] in ["scriptsql", "surse"] for file_info in files_to_process
            )
            if rollback_needed:
                aplicatie = files_to_process[0]["aplicatie"]
                with last_update_lock:
                    last_update_status["status"] = "rollback_ready"
                    last_update_status["message"] = "Actualizare eșuată – Rollback disponibil"
                    last_update_status["rollback_ready"] = True
                    last_update_status["backup_timestamp"] = backup_timestamp
                    last_update_status["aplicatie"] = aplicatie
                    last_update_status["detalii"].append("❌ Update eșuat. Poți face rollback.")
                    last_update_status["end_time"] = datetime.datetime.now().isoformat()
                detalii.append("❌ Update eșuat. Poți face rollback.")
            else:
                logger.info("Eroare detectată, dar rollback-ul nu este necesar pentru tipul curent.")
            break
    # Repornirea Application Pool și actualizare status
    try:
        subprocess.run(['powershell', '-Command', f'Start-WebAppPool -Name "{app_pool}"'], check=True)
        logger.info(f"Application Pool {app_pool} repornit cu succes")
        sys.stdout.flush()
        detalii.append(f"Application Pool {app_pool} repornit")
        with last_update_lock:
            last_update_status["detalii"].append(f"Application Pool {app_pool} repornit")
    except subprocess.CalledProcessError as e:
        logger.error(f"Eroare la repornirea Application Pool {app_pool}: {e}")
        sys.stdout.flush()
        detalii.append(f"❌ Eroare la repornirea Application Pool {app_pool}: {e}")
        with last_update_lock:
            last_update_status["detalii"].append(f"❌ Eroare la repornirea Application Pool {app_pool}: {e}")
            last_update_status["status"] = "error"
            last_update_status["message"] = f"Eroare la repornirea Application Pool: {e}"
            last_update_status["detalii"] = detalii
            last_update_status["end_time"] = datetime.datetime.now().isoformat()
        return
    # Status final
    with last_update_lock:
        if any("❌" in d for d in detalii):
            last_update_status["status"] = "error"
            last_update_status["message"] = "Unele actualizări au eșuat"
        else:
            last_update_status["status"] = "success"
            last_update_status["message"] = "Actualizare finalizată"
        last_update_status["detalii"] = detalii
        last_update_status["end_time"] = datetime.datetime.now().isoformat()
    # Logare explicită a detaliilor
    logger.info("Rezumat actualizare:")
    for linie in detalii:
        logger.info(f"> {linie}")
    sys.stdout.flush()


@app.route("/ping")
def ping():
    return "pong", 200

@app.route("/status", methods=["GET"])
def status():
    with last_update_lock:
        return jsonify({
            "id": last_update_status.get("id", ""),
            "status": last_update_status.get("status", ""),
            "message": last_update_status.get("message", ""),
            "detalii": last_update_status.get("detalii", []),
            "start_time": last_update_status.get("start_time", ""),
            "end_time": last_update_status.get("end_time", ""),
            "rollback_ready": last_update_status.get("rollback_ready", False),
            "backup_timestamp": last_update_status.get("backup_timestamp", ""),
            "aplicatie": last_update_status.get("aplicatie", "")
        }), 200

@app.route("/rollback", methods=["POST"])
def rollback():
    if config.get("agent", "tip", fallback="deploy") == "deploy-test":
        return jsonify({
            "status": "error",
            "message": "Rollback-ul nu este permis pe servere de test."
        }), 403

    logger.info("Primire cerere rollback de la: %s", request.remote_addr)
    sys.stdout.flush()
    detalii = []

    aplicatie = request.form.get("aplicatie")
    backup_timestamp = request.form.get("backup_timestamp")

    if not all([aplicatie, backup_timestamp]):
        missing = [param for param, value in [("aplicatie", aplicatie), ("backup_timestamp", backup_timestamp)] if not value]
        logger.error(f"Parametri lipsă în request: {missing}")
        sys.stdout.flush()
        return jsonify({"status": "error", "message": f"Missing parameters: {missing}", "detalii": detalii}), 400

    try:
        datetime.datetime.strptime(backup_timestamp, "%Y%m%d_%H%M%S")
    except ValueError:
        logger.error(f"Format invalid pentru backup_timestamp: {backup_timestamp}. Așteptat: YYYYMMDD_HHMMSS")
        sys.stdout.flush()
        detalii.append(f"❌ Rollback eșuat: Format invalid pentru backup_timestamp: {backup_timestamp}. Așteptat: YYYYMMDD_HHMMSS")
        return jsonify({"status": "error", "message": "Invalid backup_timestamp format", "detalii": detalii}), 400

    app_pool = APPLICATION_POOL if APPLICATION_POOL else f"{aplicatie}AppPool"

    try:
        result = subprocess.run(
            ['powershell', '-Command', f'(Get-WebAppPoolState -Name "{app_pool}").Value'],
            capture_output=True, text=True, check=True
        )
        pool_state = result.stdout.strip()
        logger.info(f"Stare Application Pool {app_pool}: {pool_state}")
        sys.stdout.flush()

        if pool_state.lower() != "stopped":
            subprocess.run(['powershell', '-Command', f'Stop-WebAppPool -Name "{app_pool}"'], check=True)
            logger.info(f"Application Pool {app_pool} oprit cu succes")
            sys.stdout.flush()
            detalii.append(f"Application Pool {app_pool} oprit")
        else:
            logger.info(f"Application Pool {app_pool} este deja oprit")
            sys.stdout.flush()
            detalii.append(f"Application Pool {app_pool} este deja oprit")
    except subprocess.CalledProcessError as e:
        if "already stopped" in e.stderr.lower():
            logger.info(f"Application Pool {app_pool} este deja oprit (ignorăm eroarea)")
            sys.stdout.flush()
            detalii.append(f"Application Pool {app_pool} este deja oprit")
        else:
            logger.error(f"Eroare la oprirea Application Pool {app_pool}: {e}")
            sys.stdout.flush()
            return jsonify({"status": "error", "message": f"Eroare la oprirea Application Pool: {e}", "detalii": detalii}), 500

    backup_app_path = os.path.join(BACKUP_FOLDER, aplicatie)
    backup_path = os.path.join(backup_app_path, backup_timestamp)
    #current_sources_path = os.path.join(APP_STRUCTURE_ROOT, aplicatie, "SurseCurent")
    iis_app_path = os.path.join(IIS_ROOT, aplicatie)

    backup_iis_path = os.path.join(BACKUP_FOLDER, "IIS", backup_timestamp)
    if not os.path.exists(backup_iis_path):
        msg = f"❌ Folderul cu surse IIS nu a fost găsit: {backup_iis_path}"
        logger.error(msg)
        sys.stdout.flush()
        detalii.append(msg)
        return jsonify({"status": "error", "message": msg, "detalii": detalii}), 400


    #backup_file_path = os.path.join(backup_path, backup_file)

    try:
        if os.path.exists(iis_app_path):
            shutil.rmtree(iis_app_path)
        os.makedirs(iis_app_path, exist_ok=True)

        for item in os.listdir(backup_iis_path):
            src = os.path.join(backup_iis_path, item)
            dst = os.path.join(iis_app_path, item)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)

        logger.info(f"Surse restaurate din backup în {iis_app_path}: {backup_iis_path}")
        sys.stdout.flush()
        detalii.append(f"Surse restaurate în {iis_app_path} din {backup_iis_path}")
    except Exception as e:
        logger.error(f"Eroare la restaurarea backup-ului: {e}")
        sys.stdout.flush()
        detalii.append(f"❌ Rollback eșuat: Eroare la restaurarea backup-ului: {e}")
        return jsonify({"status": "error", "message": f"Eroare la restaurarea backup-ului: {e}", "detalii": detalii}), 500
    
    try:
        backup_db_folder = os.path.join(BACKUP_FOLDER, "BackupDB")
        backup_sql_file = f"{SQL_DBNAME}_{backup_timestamp}.bak"
        backup_sql_path = os.path.join(backup_db_folder, backup_sql_file)

        if not os.path.exists(backup_sql_path):
            msg = f"❌ Fișierul .bak nu a fost găsit: {backup_sql_path}"
            logger.error(msg)
            sys.stdout.flush()
            detalii.append(msg)
            return jsonify({
                "status": "error",
                "message": msg,
                "detalii": detalii
            }), 400

        restore_cmd = (
            f'sqlcmd -S {SQL_SERVER} -U {SQL_USER} -P {SQL_PASS} '
            f'-Q "RESTORE DATABASE [{SQL_DBNAME}] FROM DISK = N\'{backup_sql_path}\' WITH REPLACE;"'
        )
        subprocess.run(restore_cmd, shell=True, check=True, capture_output=True, text=True)

        logger.info(f"Baza de date {SQL_DBNAME} a fost restaurată din {backup_sql_path}")
        sys.stdout.flush()
        detalii.append(f"Baza de date {SQL_DBNAME} a fost restaurată din {backup_sql_path}")

    except subprocess.CalledProcessError as e:
        msg = f"❌ Eroare la restaurarea bazei de date: {e.stderr}"
        logger.error(msg)
        sys.stdout.flush()
        detalii.append(msg)
        return jsonify({
            "status": "error",
            "message": "Eroare la restaurarea bazei de date",
            "detalii": detalii
        }), 500

    try:
        subprocess.run(['powershell', '-Command', f'Start-WebAppPool -Name "{app_pool}"'], check=True)
        logger.info(f"Application Pool {app_pool} repornit cu succes")
        sys.stdout.flush()
        detalii.append(f"Application Pool {app_pool} repornit")
    except subprocess.CalledProcessError as e:
        logger.error(f"Eroare la repornirea Application Pool {app_pool}: {e}")
        sys.stdout.flush()
        detalii.append(f"❌ Eroare la repornirea Application Pool {app_pool}: {e}")
        return jsonify({"status": "error", "message": f"Eroare la repornirea Application Pool: {e}", "detalii": detalii}), 500

    return jsonify({"status": "success", "message": "Rollback finalizat", "detalii": detalii}), 200

def perform_rollback(backup_timestamp, aplicatie):
    with app.test_request_context(method='POST', data={
        'backup_timestamp': backup_timestamp,
        'aplicatie': aplicatie
    }):
        return rollback()


if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=PORT, threads=1)