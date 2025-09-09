# Application Update

## Overview
RSR Update is a **web-based tool** for managing and deploying update packages across multiple servers.  
It automates the update process by validating packages, testing them on a deploy server, and then releasing updates to production servers.  
The system reduces human error, ensures consistency across environments, and includes a rollback mechanism for safety.

---

## Features
- 📦 **Package validation** – checks update packages stored in the `actualizari` folder.  
- 🧪 **Test deployment** – deploy updates first on a dedicated test server.  
- 🚀 **Controlled production deployment** – production deployment is enabled only after successful test deployment.  
- 🔍 **Server monitoring** – verify if servers are active and agents are listening on their configured ports.  
- ↩️ **Rollback** – automatically roll back all servers to the previous version if an update fails on any server.  
- ⚙️ **Agent setup scripts** – `.bat` scripts create and configure agents on servers for communication and deployment.  

---

## How It Works
1. Upload update packages into the `actualizari` folder.  
2. Validate packages through the web interface.  
3. Run **deploy on test server**.  
4. If successful, unlock and run **deploy on production servers**.  
5. Monitor server status (Ping, Application Pool, SQL Server).  
6. If any issue occurs, execute **Rollback** to revert all servers to the last working version.  

---

## Project Structure
- **agent_app/** – agent component installed on servers  
  - `agent.py` – core agent logic  
  - `agent.ini` – agent configuration  
  - `requirements.txt` – Python dependencies  
  - `.bat` scripts – install/start the agent  
  - `build/`, `dist/` – generated executables  

- **update_app/** – main web application (Flask/FastAPI)  
  - `app.py` – web server entry point  
  - `config/` – JSON configuration files for applications, folders, and servers  
  - `templates/` – HTML frontend (index page)  
  - `static/` – frontend static files (JS, CSS)  
  - `requirements.txt` – Python dependencies  
  - `logs/` – application logs  

---

## Getting Started

### Prerequisites
- [Python 3.10+](https://www.python.org/downloads/)  
- Windows environment (for `.bat` agent scripts)  

### Setup
```bash
# Clone the repository
git clone https://github.com/ioanapetrea12/update-app.git
cd update_app

# Install dependencies for the update app
cd update_app
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Run the update application
python app.py
