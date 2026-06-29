(function () {
  'use strict';

  const synth = window.speechSynthesis;

  if (!synth) {
    window.ChatTTS = { speak() {}, setEnabled() {}, setVoice() {}, init() {} };
    return;
  }

  let enabled = false;
  let desiredVoiceName = '';
  let voices = [];
  const queue = [];
  let _speaking = false;
  const MAX_QUEUE = 3;
  const MAX_TEXT  = 200;

  function loadVoices() {
    try {
      const v = synth.getVoices();
      if (v && v.length) voices = Array.from(v);
    } catch (_) {}
  }

  try { synth.addEventListener('voiceschanged', loadVoices); } catch (_) {}
  loadVoices();

  function findRuVoice() {
    if (!voices.length) return null;
    if (desiredVoiceName) {
      const match = voices.find(v => v.name === desiredVoiceName && v.lang.startsWith('ru'));
      if (match) return match;
    }
    return voices.find(v => v.lang.startsWith('ru')) || null;
  }

  function drain() {
    if (_speaking || !queue.length) return;
    const text = queue.shift();
    try {
      const utt = new SpeechSynthesisUtterance(text);
      utt.lang = 'ru-RU';
      const voice = findRuVoice();
      if (voice) utt.voice = voice;
      utt.rate = 1.0;
      utt.onend  = () => { _speaking = false; drain(); };
      utt.onerror = () => { _speaking = false; drain(); };
      _speaking = true;
      synth.speak(utt);
    } catch (_) {
      _speaking = false;
      if (queue.length) setTimeout(drain, 50);
    }
  }

  function speak(rawText) {
    if (!enabled) return;
    try {
      let text = String(rawText == null ? '' : rawText).trim();
      if (!text) return;
      text = text.replace(/https?:\/\/\S+/g, '').trim();
      if (!text) return;
      if (text.length > MAX_TEXT) text = text.slice(0, MAX_TEXT);
      if (queue.length >= MAX_QUEUE) queue.shift();
      queue.push(text);
      drain();
    } catch (_) {}
  }

  function setEnabled(flag) { enabled = !!flag; }
  function setVoice(name)   { desiredVoiceName = String(name || ''); }

  function init() {
    try {
      fetch('/api/settings')
        .then(r => r.ok ? r.json() : {})
        .then(data => {
          if (!data) return;
          enabled = !!data.tts_enabled;
          desiredVoiceName = String(data.tts_voice || '');
          loadVoices();
        })
        .catch(() => {});
    } catch (_) {}
  }

  window.ChatTTS = { speak, setEnabled, setVoice, init };
})();
