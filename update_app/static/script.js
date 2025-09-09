import { currentMode, setCurrentMode, startPoolingStatusUpdate } from './pooling.js';
import { verificaServereUpdate } from './verificaServere.js';
import { exportToPDF, debugZipuri, rollback } from './utils.js';
import { repornesteCountdownVerificare } from './utils.js';

repornesteCountdownVerificare(verificaServereUpdate);


let date_pachete = {};
let validGlob = false;
let aplicatiiCuProbleme = new Set();
let SERVER_LIST = [];

async function incarca() {
  console.log("Încărcare inițială...");
  const tabel = document.getElementById('tabel');
  const versiune = document.getElementById('versiune');
  const btnVerificaUpdate = document.getElementById('btn_verifica_update');
  const btnTest = document.getElementById('btn_test');
  const btnUpdate = document.getElementById('btn_update');
  if (!tabel || !versiune || !btnVerificaUpdate || !btnTest || !btnUpdate) {
    console.error("Unul sau mai multe elemente HTML lipsesc.");
    document.body.innerHTML = `<div style="color: red;">Eroare: Elemente HTML lipsă. Verifică structura paginii.</div>`;
    return;
  }

  try {
    const resp = await fetch('/pachete');
    if (!resp.ok) {
      console.error("Eroare la fetch /pachete:", resp.status, resp.statusText);
      tabel.innerHTML = `<tr><td colspan="5">Eroare: ${resp.status} - ${resp.statusText}</td></tr>`;
      return;
    }
    const json = await resp.json();
    console.log("Răspuns JSON de la /pachete:", json);
    date_pachete = json.pachete || {};
    validGlob = json.valid || false;
    aplicatiiCuProbleme.clear();

    let html = '';
    let mesaj = '';
    let existaPachet = false;

    if (Object.keys(date_pachete).length === 0) {
      html = `<tr><td colspan="5">Niciun aplicație configurată.</td></tr>`;
      mesaj = '❌ Niciun aplicație configurată.';
    } else {
      for (const app in date_pachete) {
        const row = date_pachete[app];
        const areFisiere = row.scriptsql || row.surse || row.rdl;
        if (areFisiere) existaPachet = true;

        const problemeVersiuni = json.probleme_versiuni[app];
        let disabled = '';
        if (problemeVersiuni) {
          aplicatiiCuProbleme.add(app);
          disabled = 'disabled';
        }

        html += `<tr>
          <td>${app}</td>
          <td><input type='checkbox' name='${app}' ${!areFisiere || disabled ? 'disabled' : ''}></td>
          <td>${row.scriptsql ? row.scriptsql : '❌'}</td>
          <td>${row.surse ? row.surse : '❌'}</td>
          <td>${row.rdl ? row.rdl : '❌'}</td>
        </tr>`;
      }

      const probleme = Object.entries(json.probleme_versiuni).map(
        ([app, vers]) => `❌ ${app} are versiuni multiple: v${vers.join(" și v")}`
      );

      if (!validGlob) {
        mesaj = probleme.length ? probleme.join(" | ") : '❌ Probleme cu versiunile.';
        btnTest.disabled = true;
        btnUpdate.disabled = true;
      } else if (existaPachet) {
        mesaj = '✔️ Pachete valide detectate.';
      } else {
        mesaj = '❌ Niciun pachet disponibil.';
        btnVerificaUpdate.disabled = true;
      }
    }

    tabel.innerHTML = html;
    versiune.innerText = mesaj;

    await loadServerList();
    const tbodyTest = document.getElementById('server-tbody-deploy-test');
    const tbodyProd = document.getElementById('server-tbody-producție');

    tbodyTest.innerHTML = '';
    tbodyProd.innerHTML = '';

    if (SERVER_LIST && SERVER_LIST.length > 0) {
      SERVER_LIST.forEach(server => {
        const row = `<tr>
          <td>${server.ip}:${server.port}</td>
          <td>-</td>
          <td>-</td>
          <td>-</td>
        </tr>`;
        if (server.tip === "deploy-test") {
          tbodyTest.innerHTML += row;
        } else if (server.tip === "deploy") {
          tbodyProd.innerHTML += row;
        }
      });
    }

    if (tbodyTest.innerHTML.trim() === '') {
      tbodyTest.innerHTML = `<tr><td colspan="4">Niciun server de test configurat.</td></tr>`;
    }
    if (tbodyProd.innerHTML.trim() === '') {
      tbodyProd.innerHTML = `<tr><td colspan="4">Niciun server de producție configurat.</td></tr>`;
    }

    btnVerificaUpdate.disabled = false;
    btnTest.disabled = true;
    btnUpdate.disabled = true;
  } catch (error) {
    console.error("Eroare în funcția incarca():", error);
    tabel.innerHTML = `<tr><td colspan="5">Eroare la încărcarea datelor: ${error.message}</td></tr>`;
  }
}

async function loadServerList() {
  console.log("Încărcare listă servere...");
  try {
    const resp = await fetch('/config_servere');
    const servereJson = await resp.json();
    SERVER_LIST = servereJson;

    console.log("Lista servere încărcată:", SERVER_LIST);

    // Aflăm IP-ul local
    const ipResp = await fetch('/ip_local');
    const ipData = await ipResp.json();
    const ipLocal = ipData.ip;

    const serverCurent = SERVER_LIST.find(s => s.ip === ipLocal);
    if (serverCurent) {
      const infoEl = document.getElementById("tip_server_info");
      if (infoEl) {
        if (serverCurent.tip === "deploy-test") {
          infoEl.innerHTML = "Acesta este un server de tip <u>DEPLOY-TEST</u>.";
        } else if (serverCurent.tip === "deploy") {
          infoEl.innerHTML = "Acesta este un server de tip <u>DEPLOY</u>.";
        } else {
          infoEl.innerHTML = "Tip server necunoscut.";
        }
      }
    }

    const btnRollback = document.getElementById("btn_rollback");
    if (serverCurent && btnRollback) {
      if (serverCurent.tip === "deploy") {
        btnRollback.disabled = false;
      } else {
        btnRollback.disabled = true;
      }
    } else {
      console.warn("Serverul curent nu a fost găsit în lista de servere. Rollback dezactivat.");
      if (btnRollback) btnRollback.disabled = true;
    }
  } catch (error) {
    console.error("Eroare la încărcarea listei de servere sau determinarea IP-ului:", error);
    SERVER_LIST = [];
  }
}

async function trimiteActiune(tip) {
  const btnTest = document.getElementById('btn_test');
  const btnUpdate = document.getElementById('btn_update');
  const status = document.getElementById('status');
  const debugOutput = document.getElementById('debug_output');
  const btnRollback = document.getElementById('btn_rollback');

  if (!btnTest || !btnUpdate || !status || !debugOutput) {
    console.error("Unul sau mai multe elemente HTML lipsesc în trimiteActiune:", {
      btnTest: !!btnTest,
      btnUpdate: !!btnUpdate,
      status: !!status,
      debugOutput: !!debugOutput
    });
    return;
  }

  if (tip === 'rollback') {
    const app = btnRollback?.dataset.aplicatie;
    const timestamp = btnRollback?.dataset.timestamp;

    if (!app || !timestamp) {
      alert("Rollback indisponibil – lipsesc datele salvate pentru aplicație și versiune.");
      return;
    }

    const rollbackProgressContainer = document.getElementById("rollback-progress-container");
    const rollbackProgressBar = document.getElementById("rollback-progress-bar");
    rollbackProgressContainer.style.display = "block";
    rollbackProgressBar.style.width = "10%";

    status.innerText = `Trimit comanda rollback pentru ${app} la ${timestamp}`;

    try {
      const formData = new FormData();
      formData.append("aplicatie", app);
      formData.append("backup_timestamp", timestamp);

      if (btnRollback) btnRollback.disabled = true;

      const response = await fetch('/rollback', {
        method: 'POST',
        body: formData
      });

      document.getElementById('progress-bar').style.width = '60%';

      const rezultat = await response.json();
      rollbackProgressBar.style.width = "80%";
      let out = rezultat.detalii.map(d => {
        if (d.includes("❌")) {
          return `<span class="status-error">${d}</span>`;
        }
        return d;
      }).join('\n  - ');

      debugOutput.innerHTML = `<strong>Rezultat rollback:</strong><br>${out}`;

    } catch (error) {
      console.error("Eroare rollback:", error);
      debugOutput.innerHTML = `<span class="status-error">Eroare rollback: ${error.message}</span>`;
    } finally {
      rollbackProgressBar.style.width = "100%";
      setTimeout(() => {
        rollbackProgressContainer.style.display = "none";
        rollbackProgressBar.style.width = "0%";
      }, 3000);
      if (btnRollback) btnRollback.disabled = false;
    }

    return; 
  }

  if (tip === 'debug_zipuri') {
    await debugZipuri();
    return;
  }

  const selectate = [];
  document.querySelectorAll("#update-section input[type='checkbox']").forEach(cb => {
    if (cb.checked) selectate.push(cb.name);
  });
  if (selectate.length === 0) {
    alert("Selectează cel puțin o aplicație pentru actualizare.");
    return;
  }
  status.innerText = `Trimit comanda ${tip} către: ` + selectate.join(', ');

  if (tip === 'test') {
    btnTest.disabled = true;
  } else if (tip === 'update') {
    btnUpdate.disabled = true;
  }

  //currentMode = tip;
  setCurrentMode(tip);
 
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 150000); // 15 secunde timeout

  try {
    const resp = await fetch('/start_update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ aplicatii: selectate, test: tip === 'test' }),
      signal: controller.signal
    });

    clearTimeout(timeoutId);

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

    // if (!rezultat.toate_ok && tip === 'update') {
    //   debugOutput.innerHTML += '\n\n<span class="status-error">Actualizarea a eșuat pe cel puțin un server!</span>';
    //   if (tip === 'test') {
    //     btnTest.disabled = false;
    //   }
    // } else {
    //   if (tip === 'test') {
    //     btnUpdate.disabled = false;
    //   }
    // }
    if (tip === 'test') {
      if (!rezultat.toate_ok) {
        btnTest.disabled = false;
      } else {
        btnUpdate.disabled = false;
      }
    } else if (tip === 'update') {
      if (!rezultat.toate_ok) {
        debugOutput.innerHTML += '\n\n<span class="status-error">Actualizarea a eșuat pe cel puțin un server!</span>';

        //Activăm butonul de rollback
        const btnRollback = document.getElementById('btn_rollback');
        if (btnRollback) btnRollback.disabled = false;
    }
  }
  } catch (error) {
    clearTimeout(timeoutId);
    console.error(`Eroare în trimiteActiune(${tip}):`, error);
    status.innerText = `❌ Eroare: ${error.message}`;
    debugOutput.innerHTML = `<span class="status-error">Eroare la trimiterea comenzii: ${error.message}</span>`;
    if (tip === 'test') {
      btnTest.disabled = false;
    }
  }

  startPoolingStatusUpdate();
}

const script = document.createElement('script');
script.src = 'https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js';
script.onload = () => window.jsPDF = window.jspdf.jsPDF;
document.head.appendChild(script);

window.onload = async () => {
  try {
    await incarca();
  } catch (error) {
    console.error("Eroare la încărcarea inițială:", error);
  }
};

export { trimiteActiune };