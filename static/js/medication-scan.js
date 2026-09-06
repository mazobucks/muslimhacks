const statusElement = document.getElementById("scan-status");
const detailsElement = document.getElementById("medication-details");
let lastScannedValue = "";
let scanner;
let scannedMedicationId = null;

const logMedicationButton = document.getElementById("log-medication-button");
const logMedicationStatus = document.getElementById("log-medication-status");

function medicationIdFromQr(value) {
  const text = value.trim();
  if (/^\d+$/.test(text)) return text;

  try {
    const url = new URL(text);
    const id = url.searchParams.get("medication_id") || url.pathname.match(/medications\/(\d+)/)?.[1];
    return id && /^\d+$/.test(id) ? id : null;
  } catch (_) {
    return null;
  }
}

async function showMedication(value) {
  const medicationId = medicationIdFromQr(value);
  console.log(value);
  if (!medicationId) {
    statusElement.textContent = "This QR code is not a medication code.";
    detailsElement.hidden = true;
    return;
  }

  statusElement.textContent = "Checking medication...";
  const response = await fetch(`/api/medications/${medicationId}`);
  const medication = await response.json();
  if (!response.ok) {
    statusElement.textContent = medication.error || "Medication not found.";
    detailsElement.hidden = true;
    return;
  }

  document.getElementById("medication-name").textContent = medication.name;
  document.getElementById("medication-id").textContent = medication.id;
  document.getElementById("medication-dosage").textContent = medication.dosage;
  document.getElementById("medication-time").textContent = medication.schedule_time;
  scannedMedicationId = medication.id;
  logMedicationButton.disabled = !medication.can_take;
  logMedicationButton.textContent = medication.status === "done" ? "Medication logged" : "Log medication";
  logMedicationStatus.textContent = medication.status === "now"
    ? "This medication can be logged now."
    : medication.status === "done"
      ? "This medication has already been logged today."
      : medication.status === "upcoming"
        ? "This medication is not ready to be logged yet."
        : medication.status === "missed"
          ? "The one-hour medication window has ended."
          : "This medication has no scheduled time.";
  detailsElement.hidden = false;
  statusElement.textContent = "Medication found.";
}

async function logMedication() {
  if (!scannedMedicationId || logMedicationButton.disabled) return;
  logMedicationButton.disabled = true;
  logMedicationStatus.textContent = "Logging medication...";
  const response = await fetch(`/api/medications/${scannedMedicationId}/done`, { method: "POST" });
  const result = await response.json();
  if (!response.ok) {
    logMedicationButton.disabled = false;
    logMedicationStatus.textContent = result.error || "Medication could not be logged.";
    return;
  }
  logMedicationButton.textContent = "Medication logged";
  logMedicationStatus.textContent = "Medication logged successfully.";
}

function onScanSuccess(decodedText) {
  if (decodedText === lastScannedValue) return;
  lastScannedValue = decodedText;
  showMedication(decodedText).catch(() => {
    statusElement.textContent = "Could not check this medication.";
  });
}

function startScanner() {
  if (typeof Html5Qrcode === "undefined") {
    statusElement.textContent = "The QR scanner could not load. Check your internet connection.";
    return;
  }
  scanner = new Html5Qrcode("qr-reader");
  scanner.start(
    { facingMode: "environment" },
    { fps: 10, qrbox: { width: 250, height: 250 } },
    onScanSuccess,
    () => {}
  ).catch(() => {
    statusElement.textContent = "Camera access is unavailable. Allow camera access and reload this page.";
  });
}

window.addEventListener("load", startScanner);
logMedicationButton.addEventListener("click", () => {
  logMedication().catch(() => {
    logMedicationButton.disabled = false;
    logMedicationStatus.textContent = "Medication could not be logged.";
  });
});