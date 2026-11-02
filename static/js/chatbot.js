(function () {
  var root = document.getElementById("chat");
  if (!root) return;
  var log = document.getElementById("chatLog"), form = document.getElementById("chatForm"), input = document.getElementById("chatInput");
  var sendBtn = document.getElementById("sendBtn"), clearBtn = document.getElementById("clearChat"), langSel = document.getElementById("langSelect");
  var quick = document.getElementById("quickReplies"), mic = document.getElementById("micBtn"), sub = document.getElementById("chatSub"), disc = document.getElementById("chatDisclaimer");
  var loggedIn = root.dataset.loggedIn === "true", csrf = root.dataset.csrf, emg = root.dataset.emg, amb = root.dataset.amb;

  var UI = {
    en: { welcome: "Hello! I'm your health information assistant. I can explain common health questions and suggest which type of doctor to see. I can't diagnose or prescribe. How can I help?",
      placeholder: "Type your health question…", send: "Send", clear: "🗑 Clear", sub: "General health information only - no diagnosis or prescriptions.",
      disc: "⚠️ In an emergency call " + emg + " / " + amb + ". This assistant cannot diagnose or prescribe.", confirm: "Clear the whole conversation?",
      err: "Sorry, I couldn't reach the server. Please check your connection and try again.", book: "📅 Book ", speak: "Speak your question", listening: "Listening…",
      quick: ["I have a fever", "I have a headache", "Cough and cold tips", "Which doctor for knee pain?", "Which doctor for skin rash?", "How to sleep better?", "Tips for stress"] },
    hi: { welcome: "नमस्ते! मैं आपका स्वास्थ्य जानकारी सहायक हूँ। मैं सामान्य स्वास्थ्य प्रश्न समझा सकता हूँ और बता सकता हूँ कि किस डॉक्टर को दिखाएँ। मैं बीमारी की पहचान या दवा नहीं बता सकता। मैं कैसे मदद करूँ?",
      placeholder: "अपना स्वास्थ्य सवाल लिखें…", send: "भेजें", clear: "🗑 साफ़ करें", sub: "केवल सामान्य स्वास्थ्य जानकारी - निदान या दवा नहीं।",
      disc: "⚠️ आपातकाल में " + emg + " / " + amb + " पर कॉल करें। यह सहायक निदान या दवा नहीं बता सकता।", confirm: "पूरी बातचीत साफ़ करें?",
      err: "क्षमा करें, सर्वर से संपर्क नहीं हो सका। कृपया इंटरनेट जाँचकर फिर कोशिश करें।", book: "📅 बुक करें: ", speak: "बोलकर पूछें", listening: "सुन रहा हूँ…",
      quick: ["मुझे बुखार है", "मुझे सिरदर्द है", "खांसी-सर्दी के उपाय", "घुटने के दर्द में कौन सा डॉक्टर?", "त्वचा पर दाने - कौन सा डॉक्टर?", "बेहतर नींद कैसे लें?", "तनाव कम करने के उपाय"] },
    mr: { welcome: "नमस्कार! मी तुमचा आरोग्य माहिती सहाय्यक आहे. मी सामान्य आरोग्य प्रश्न समजावू शकतो आणि कोणत्या डॉक्टरांना दाखवावे ते सांगू शकतो. मी निदान किंवा औषध सांगू शकत नाही. मी कशी मदत करू?",
      placeholder: "तुमचा आरोग्य प्रश्न लिहा…", send: "पाठवा", clear: "🗑 पुसून टाका", sub: "फक्त सामान्य आरोग्य माहिती - निदान किंवा औषध नाही.",
      disc: "⚠️ आणीबाणीत " + emg + " / " + amb + " वर कॉल करा. हा सहाय्यक निदान किंवा औषध सांगू शकत नाही.", confirm: "संपूर्ण संभाषण पुसायचे?",
      err: "क्षमस्व, सर्व्हरशी संपर्क होऊ शकला नाही. कृपया इंटरनेट तपासून पुन्हा प्रयत्न करा.", book: "📅 बुक करा: ", speak: "बोलून विचारा", listening: "ऐकत आहे…",
      quick: ["मला ताप आहे", "मला डोकेदुखी आहे", "खोकला-सर्दीवर उपाय", "गुडघेदुखीसाठी कोणते डॉक्टर?", "त्वचेवर पुरळ - कोणते डॉक्टर?", "चांगली झोप कशी घ्यावी?", "ताण कमी करण्याचे उपाय"] }
  };
  var VOICE = { en: "en-IN", hi: "hi-IN", mr: "mr-IN" };
  var lang = "en";
  try { lang = localStorage.getItem("chatLang") || "en"; } catch (e) {}
  if (!UI[lang]) lang = "en";
  langSel.value = lang;
  var guestKey = "chatGuestHistory";

  function guestLoad() { try { return JSON.parse(sessionStorage.getItem(guestKey) || "[]"); } catch (e) { return []; } }
  function guestSave(h) { try { sessionStorage.setItem(guestKey, JSON.stringify(h.slice(-40))); } catch (e) {} }
  var history = loggedIn ? [] : guestLoad();

  function bubble(role, text, extra) {
    var d = document.createElement("div");
    d.className = "msg " + role + (extra && extra.emergency ? " emergency" : "");
    d.textContent = text;
    if (extra && extra.emergency) {
      var a = document.createElement("div"); a.className = "actions";
      [emg, amb].forEach(function (n) { var l = document.createElement("a"); l.className = "btn btn-danger btn-sm"; l.href = "tel:" + n; l.textContent = "📞 " + n; a.appendChild(l); });
      var h = document.createElement("a"); h.className = "btn btn-outline btn-sm"; h.href = "/hospital"; h.textContent = "🏥"; a.appendChild(h); d.appendChild(a);
    }
    if (extra && extra.specialists && extra.specialists.length) {
      var box = document.createElement("div"); box.className = "actions";
      extra.specialists.forEach(function (s) { var l = document.createElement("a"); l.className = "btn btn-primary btn-sm"; l.href = s.url; l.textContent = UI[lang].book + s.name; box.appendChild(l); });
      d.appendChild(box);
    }
    log.appendChild(d); log.scrollTop = log.scrollHeight; return d;
  }
  function typing() {
    var d = document.createElement("div"); d.className = "msg bot"; d.setAttribute("aria-label", "Assistant is typing");
    d.innerHTML = '<span class="typing"><span></span><span></span><span></span></span>'; log.appendChild(d); log.scrollTop = log.scrollHeight; return d;
  }
  function applyLang() {
    var u = UI[lang]; input.placeholder = u.placeholder; sendBtn.textContent = u.send; clearBtn.textContent = u.clear; sub.textContent = u.sub; disc.textContent = u.disc;
    mic.setAttribute("aria-label", u.speak); document.documentElement.lang = lang;
    quick.innerHTML = "";
    u.quick.forEach(function (q) { var b = document.createElement("button"); b.type = "button"; b.textContent = q; b.addEventListener("click", function () { send(q); }); quick.appendChild(b); });
  }
  function welcome() { bubble("bot", UI[lang].welcome); }
  function render() {
    log.innerHTML = ""; welcome(); history.forEach(function (m) { bubble(m.role === "bot" ? "bot" : "user", m.content); });
  }

  function send(text) {
    text = (text || "").trim(); if (!text) return;
    bubble("user", text); input.value = ""; sendBtn.disabled = true; input.disabled = true;
    var t = typing();
    fetch(root.dataset.api, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify({ message: text, lang: lang, history: loggedIn ? [] : history.slice(-8) }) })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        t.remove();
        if (!res.d.success) { bubble("bot", res.d.message || UI[lang].err); return; }
        bubble("bot", res.d.reply, { emergency: res.d.emergency, specialists: res.d.specialists });
        if (!loggedIn) { history.push({ role: "user", content: text }, { role: "bot", content: res.d.reply }); guestSave(history); }
      })
      .catch(function () { t.remove(); bubble("bot", UI[lang].err); })
      .then(function () { sendBtn.disabled = false; input.disabled = false; input.focus(); });
  }

  form.addEventListener("submit", function (e) { e.preventDefault(); send(input.value); });
  langSel.addEventListener("change", function () { lang = langSel.value; try { localStorage.setItem("chatLang", lang); } catch (e) {} applyLang(); render(); });
  clearBtn.addEventListener("click", function () {
    if (!window.confirm(UI[lang].confirm)) return;
    if (loggedIn) fetch("/api/chat/history", { method: "DELETE", headers: { "X-CSRF-Token": csrf } }).catch(function () {});
    history = []; guestSave([]); render();
  });

  // Voice input (Web Speech API; works in Chrome/Edge/Safari, hidden elsewhere)
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SR) {
    mic.hidden = false; var rec = null, on = false;
    mic.addEventListener("click", function () {
      if (on && rec) { rec.stop(); return; }
      rec = new SR(); rec.lang = VOICE[lang]; rec.interimResults = false; rec.maxAlternatives = 1;
      rec.onstart = function () { on = true; mic.classList.add("listening"); input.placeholder = UI[lang].listening; };
      rec.onend = function () { on = false; mic.classList.remove("listening"); input.placeholder = UI[lang].placeholder; };
      rec.onerror = function () { on = false; mic.classList.remove("listening"); };
      rec.onresult = function (ev) { input.value = ev.results[0][0].transcript; input.focus(); };
      try { rec.start(); } catch (e) {}
    });
  }

  applyLang();
  if (loggedIn) {
    fetch(root.dataset.history).then(function (r) { return r.json(); }).then(function (d) { history = (d.messages || []); render(); }).catch(render);
  } else render();
})();
