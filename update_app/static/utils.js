let countdownInterval = null;

function exportToPDF() {
  const { jsPDF } = window.jspdf;
  const doc = new jsPDF();
  let content = 'Status Servere\n\n';
  const table = document.getElementById('server-table');
  const rows = table.querySelectorAll('tr');
  rows.forEach(row => {
    content += Array.from(row.cells).map(cell => cell.textContent).join(', ') + '\n';
  });
  doc.text(content, 10, 10);
  doc.save('server_status.pdf');
};

async function debugZipuri() {
  const debugOutput = document.getElementById('debug_output');
  if (!debugOutput) {
    console.error("Elementul debug_output lipsește.");
    return;
  }

  try {
    const resp = await fetch('/debug_zipuri');
    const data = await resp.json();
    debugOutput.innerText = data.join('\n');
  } catch (error) {
    console.error("Eroare în debugZipuri:", error);
    debugOutput.innerText = `❌ Eroare: ${error.message}`;
  }
};

async function rollback() {
  const aplicatie = document.getElementById('rollback_app').value;
  const backupTimestamp = document.getElementById('rollback_timestamp').value;
  const status = document.getElementById('status');
  const debugOutput = document.getElementById('debug_output');

  if (!aplicatie || !backupTimestamp) {
    alert("Selectează aplicația și timestamp-ul backup-ului!");
    return;
  }

  if (!status || !debugOutput) {
    console.error("Unul sau mai multe elemente HTML lipsesc în rollback:", {
      status: !!status,
      debugOutput: !!debugOutput
    });
    return;
  }

  status.innerText = `Trimit cerere rollback pentru ${aplicatie} la ${backupTimestamp}...`;

  try {
    const resp = await fetch('/rollback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ aplicatie: aplicatie, backup_timestamp: backupTimestamp })
    });

    const rezultat = await resp.json();
    let out = rezultat.rezultate.map(r => {
      let detaliiFormatate = r.detalii.map(d => {
        if (d.includes("❌")) {
          return `<span class="status-error">${d}</span>`;
        }
        return d;
      });
      return `${r.ip}:${r.port} → ${r.status.toUpperCase()}\n  - ${detaliiFormatate.join('\n  - ')}`;
    }).join('\n\n');

    debugOutput.innerHTML = out;

    if (!rezultat.toate_ok) {
      debugOutput.innerHTML += '\n\n<span class="status-error">Rollback-ul a eșuat pe cel puțin un server!</span>';
    }
  } catch (error) {
    console.error("Eroare în rollback:", error);
    status.innerText = `❌ Eroare: ${error.message}`;
  }
}

function repornesteCountdownVerificare(callback, intervalSecunde = 10) {
  const timer = document.getElementById("countdown_timer");
  if (!timer) return;

  let secunde = intervalSecunde;
  timer.innerText = `Următoarea actualizare în: ${secunde} secunde`;

  if (countdownInterval) clearInterval(countdownInterval);

  countdownInterval = setInterval(() => {
    secunde--;
    if (secunde <= 0) {
      clearInterval(countdownInterval);
     // timer.innerText = "Actualizare în curs...";
      callback(); // ex: verificaServereUpdate()
    } else {
      //timer.innerText = `Următoarea actualizare în: ${secunde} secunde`;
    }
  }, 1000);
}

export { exportToPDF, debugZipuri, rollback, repornesteCountdownVerificare };