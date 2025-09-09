export async function verificaServereUpdate(params) {
  const serverListResp = await fetch('/config_servere');
  const SERVER_LIST = await serverListResp.json();

  const btnVerificaUpdate = document.getElementById('btn_verifica_update');
  const btnTest = document.getElementById('btn_test');
  const btnUpdate = document.getElementById('btn_update');
  const status = document.getElementById('status');
  const btnExportPdf = document.getElementById('btn_export_pdf');
  const tbodyTest = document.getElementById(params.testTbodyId);
  const tbodyProd = document.getElementById(params.prodTbodyId);

  if (!btnVerificaUpdate || !btnTest || !btnUpdate || !status || !btnExportPdf || !tbodyTest || !tbodyProd) {
    console.error("Unul sau mai multe elemente HTML lipsesc în verificaServereUpdate:", {
      btnVerificaUpdate: !!btnVerificaUpdate,
      btnTest: !!btnTest,
      btnUpdate: !!btnUpdate,
      status: !!status,
      btnExportPdf: !!btnExportPdf,
      tbodyTest: !!tbodyTest,
      tbodyProd: !!tbodyProd
    });
    return;
  }

  btnVerificaUpdate.disabled = true;
  status.innerText = '🔄 Verific serverele...';

  try {
    const resp = await fetch('/verifica_servere');
    if (!resp.ok) {
      throw new Error(`Eroare la fetch /verifica_servere: ${resp.status} - ${resp.statusText}`);
    }
    const serverStatuses = await resp.json();

    let allServersOk = true;

    // separă rândurile după tip server
    tbodyTest.innerHTML = '';
    tbodyProd.innerHTML = '';

    serverStatuses.forEach(status => {
      const [ipPort, statusText] = status.split(' → ');
      const [ip, port] = ipPort.split(':');
      const serverConfig = SERVER_LIST.find(s => s.ip === ip && s.port.toString() === port);
      const tip = serverConfig?.tip || 'unknown';

      const pingOk = statusText.includes('✔️') ? '✔️' : '❌';
      const appPoolOk = statusText.includes('Application Pool: ✔️') ? '✔️' : '❌';
      const sqlOk = statusText.includes('SQL Server: ✔️') ? '✔️' : '❌';

      if (pingOk !== '✔️' || appPoolOk !== '✔️' || sqlOk !== '✔️') {
        allServersOk = false;
      }

      const row = `<tr>
        <td>${ip}:${port}</td>
        <td class="${pingOk === '✔️' ? 'status-ok' : 'status-error'}">${pingOk}</td>
        <td class="${appPoolOk === '✔️' ? 'status-ok' : 'status-error'}">${appPoolOk}</td>
        <td class="${sqlOk === '✔️' ? 'status-ok' : 'status-error'}">${sqlOk}</td>
      </tr>`;

      if (tip === 'deploy-test') {
        tbodyTest.innerHTML += row;
      } else {
        tbodyProd.innerHTML += row;
      }
    });

    btnExportPdf.style.display = 'inline-block';
    status.innerText = '✔️ Verificare completă';

    if (allServersOk) {
      btnTest.disabled = false;
    } else {
      btnTest.disabled = true;
      btnUpdate.disabled = true;
    }
  } catch (error) {
    console.error("Eroare în verificaServereUpdate:", error);
    status.innerText = `❌ Eroare: ${error.message}`;
  } finally {
    btnVerificaUpdate.disabled = false;
  }
}

window.verificaServereUpdate = verificaServereUpdate;