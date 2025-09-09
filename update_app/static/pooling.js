// pooling.js

export let poolingInterval;
export let currentMode = '';

export function setCurrentMode(mode) {
  currentMode = mode;
}

export function getCurrentMode() {
  return currentMode;
}

export function startPoolingStatusUpdate() {
  if (poolingInterval) {
    clearInterval(poolingInterval);
  }

  const mesajProgres = document.getElementById('mesaj_progres');
  if (mesajProgres) {
    mesajProgres.style.display = 'block';
  }

  const progressContainer = document.getElementById('progress-container');
  const progressBar = document.getElementById('progress-bar');

  if (progressContainer && progressBar) {
    progressContainer.style.display = 'block';
    progressBar.style.width = '0%';
  }

  poolingInterval = setInterval(async () => {
    try {
      let url = '/status_update';
      if (currentMode === 'test') {
        url += '?test=1';
      }

      const resp = await fetch(url);
      if (!resp.ok) return;
      const rezultat = await resp.json();

      if (rezultat.rollback_ready) {
        const btnRollback = document.getElementById("btn_rollback");
        const appSelect = document.getElementById("rollback_app");
        const timestampInput = document.getElementById("rollback_timestamp");

        if (btnRollback) btnRollback.disabled = false;  // activez butonul
        if (appSelect && rezultat.aplicatie) appSelect.value = rezultat.aplicatie;
        if (timestampInput && rezultat.backup_timestamp) timestampInput.value = rezultat.backup_timestamp;

        const rollbackSection = document.getElementById("rollback-section");
        if (rollbackSection) rollbackSection.style.border = "2px solid red";  // vizibil vizual că trebuie rollback
      }

      //progress bar
      let totalSteps = 19; 
      let completedSteps = 0;
      rezultat.rezultate.forEach(r => {
        completedSteps += (r.detalii || []).length;
      });

      let percent = Math.min((completedSteps / (totalSteps * rezultat.rezultate.length)) * 100, 100);
      if (progressBar) {
        progressBar.style.width = percent + '%';
      }

      const debugOutput = document.getElementById('debug_output');
      if (!debugOutput) return;

      let out = rezultat.rezultate.map(r => {
        let detaliiFormatate = (r.detalii || []).map(d => {
          if (d.includes("❌")) {
            return `<span class="status-error">${d}</span>`;
          }
          return d;
        });
        return `${r.ip}:${r.port} → ${r.status.toUpperCase()}\n  - ${detaliiFormatate.join('\n  - ')}`;
      }).join('\n\n');

      debugOutput.innerHTML = `<pre>${out}</pre>`;

      if (rezultat.toate_ok || rezultat.status === "ERROR") {
        clearInterval(poolingInterval);
        
        if (progressBar) {
          progressBar.style.width = '100%';
        }
        if (mesajProgres) {
          mesajProgres.style.display = 'none';
        }
        setTimeout(() => {
          if (progressContainer) {
            progressContainer.style.display = 'none';
          }
        }, 3000);
      }

    } catch (e) {
      console.error('pooling /status_update a eșuat:', e);
    }
  }, 5000);
}
