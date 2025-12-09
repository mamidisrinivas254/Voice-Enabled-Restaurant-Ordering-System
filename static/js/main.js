
let MENU_LANG = "en"; 

function setMenuLanguage(lang) {
  MENU_LANG = lang;
  loadMenu();

  
  document.getElementById("btnMenuEn").classList.toggle("active", lang === "en");
  document.getElementById("btnMenuTe").classList.toggle("active", lang === "te");
}

// Global helper: Fetch JSON with session

async function jsonFetch(url, options = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    ...options,
  });

   // Validate JSON

  const type = res.headers.get("content-type") || "";
  if (!type.includes("application/json")) {
    const txt = await res.text();
    throw new Error("Expected JSON, server returned: " + txt.slice(0, 120));
  }

  return res.json();
}

// Login Handler

async function loginUser() {
  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value.trim();

  if (!username || !password) {
    alert("Enter both username and password");
    return;
  }

  const res = await fetch("/login", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username, password }),
  });

  const data = await res.json();
  console.log("Login:", data);

  if (data.status === "ok") {
    window.location.href = "/dashboard";
  } else {
    alert("Invalid username or password");
  }
}

window.addEventListener("DOMContentLoaded", () => {
  loadMe();
  loadMenu();
});

// User Info Loader for Dashboard Top Bar

async function loadMe() {
  const who = document.getElementById("who");
  const role = document.getElementById("role");

  if (!who || !role) return;

  try {
    const me = await jsonFetch("/api/me");

    if (!me.logged_in) {
      window.location.href = "/";
      return;
    }

    who.textContent = me.username;
    role.textContent = me.role;

    
    const adminParts = document.querySelectorAll(".admin-only");
    const userParts = document.querySelectorAll(".user-only");

   if (me.role === "admin") {
  document.querySelectorAll(".admin-only").forEach(el => el.style.display = "block");
  document.querySelectorAll(".user-only").forEach(el => el.style.display = "none");
} else {
  document.querySelectorAll(".admin-only").forEach(el => el.style.display = "none");
  document.querySelectorAll(".user-only").forEach(el => el.style.display = "block");
}

  } catch (err) {
    console.error("loadMe error:", err);
  }
}

function setEnglishMenu() {
  MENU_LANG = "en";
  loadMenu();
}

function setTeluguMenu() {
  MENU_LANG = "te";
  loadMenu();
}

async function loadMenu() {
  const tbody = document.getElementById("menuBody");
  const select = document.getElementById("itemSelect");

  tbody.innerHTML = "";
  select.innerHTML = "";

  try {
    const data = await jsonFetch("/api/menu");
    console.log("Menu:", data);

    data.forEach((item) => {
      const displayName =
        MENU_LANG === "te"
          ? (item.name_te || item.name_en)
          : item.name_en;

      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${item.id}</td>
        <td>${displayName}</td>
        <td>₹${Number(item.price).toFixed(2)}</td>
        <td>${item.availability === "yes" ? "✅" : "❌"}</td>
      `;
      tbody.appendChild(tr);

      if (item.availability === "yes") {
        const opt = document.createElement("option");
        opt.value = item.id;
        opt.textContent = `${displayName} (₹${Number(item.price).toFixed(2)})`;
        select.appendChild(opt);
      }
    });

  } catch (err) {
    console.error("Menu Load Error:", err);
    tbody.innerHTML = `<tr><td colspan="4">Error loading menu</td></tr>`;
  }
}


async function placeOrder() {
  const sel = document.getElementById("itemSelect");
  const qty = document.getElementById("qty").value;
  const msg = document.getElementById("orderMsg");

  if (!sel.value) {
    msg.textContent = "Pick an item first!";
    msg.style.color = "red";
    return;
  }

  try {
    const data = await jsonFetch("/api/order", {
      method: "POST",
      body: JSON.stringify({ item_id: sel.value, quantity: qty }),
    });

    if (data.status !== "ok") {
      msg.textContent = data.msg || "Order failed";
      msg.style.color = "red";
      return;
    }

    msg.textContent = `Order placed! Total: ₹${data.total}`;
    msg.style.color = "limegreen";
    showReceipt(data.receipt);

  } catch (err) {
    console.error(err);
  }
}


function showReceipt(r) {
  const card = document.getElementById("receiptCard");
  const box = document.getElementById("receiptBox");
  
  const lines = [
    `Order ID : ${r.order_id}`,
    `Customer : ${r.customer}`,
    `Item     : ${r.item}`,
    `Quantity : ${r.quantity}`,
    `Price    : ₹${r.unit_price}`,
    `Total    : ₹${r.total_price}`,
    `Time     : ${r.timestamp}`,
  ];

  box.textContent = lines.join("\n");
  card.style.display = "block";
}

function printReceipt() {
  const w = window.open("", "_blank");
  w.document.write(`<pre>${document.getElementById("receiptBox").textContent}</pre>`);
  w.print();
}


async function speakText(text) {
  const voiceText = document.getElementById("voiceText");
  

  const lang = /[\u0C00-\u0C7F]/.test(text) ? "te" : "en";

  if (voiceText) voiceText.textContent = text;  

  try {
    const data = await jsonFetch("/speak", {
      method: "POST",
      body: JSON.stringify({ text, lang }),
    });
    new Audio(data.file).play();
  } catch (err) {
    console.error("Speech error:", err);
  }
}


let recognition;

function setupRecognizer(lang) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return null;
  const rec = new SR();
  rec.lang = lang;
  return rec;
}



function voiceOrder(lang) {
  const voiceText = document.getElementById("voiceText");

  if (!recognition) recognition = setupRecognizer(lang);
  if (!recognition) {
    alert("Speech not supported");
    return;
  }

  recognition.lang = lang;
  recognition.start();

  recognition.onresult = async (e) => {
    const transcript = e.results[0][0].transcript;
    voiceText.textContent = transcript;

    const data = await jsonFetch("/api/order_voice", {
      method: "POST",
      body: JSON.stringify({
        transcript,
        lang: lang.startsWith("te") ? "te" : "en",
      }),
    });

    if (data.status === "ok") {
      showReceipt(data.receipt);
      if (data.tts) await speakText(data.tts);
    } else {
      voiceText.textContent = "Voice order failed: " + data.msg;
    }
  };

  recognition.onerror = (e) =>
    (voiceText.textContent = "Speech error: " + e.error);
}
async function speakEnglish() {
  await speakText(
    "Welcome to the Voice Enabled Restaurant Ordering System. Please login with your username and password."
  );
}

async function speakTelugu() {
  await speakText(
    "వోయిస్ ఎనేబుల్ రెస్టారెంట్ ఆర్డరింగ్ సిస్టమ్ కి స్వాగతం. దయచేసి మీ యూజర్ నేమ్ మరియు పాస్‌వర్డ్ తో లాగిన్ అవ్వండి.",
    "te"
  );
}
